import asyncio
from unittest.mock import AsyncMock

import pytest
from prometheus_client import CollectorRegistry, generate_latest
from telegram.error import Forbidden

from sentinel.alertmanager import AlertStatus, OperatorAlert
from sentinel.metrics.registry import AppMetrics
from sentinel.services.alertmanager import AlertmanagerDeliveryService


ALERT = OperatorAlert(1, 3, "42", "MissedDuties", AlertStatus.FIRING, "Missed duties", "")


async def test_queue_age_survives_restart_and_source_revocation(
    tmp_path, monkeypatch, database_factory, module_adapter_factory, chat_migrations_factory
):
    now = [100.0]
    monkeypatch.setattr("sentinel.metrics.alertmanager.time.time", lambda: now[0])
    path = tmp_path / "sentinel.sqlite3"
    registry = CollectorRegistry()
    metrics = AppMetrics(registry).alertmanager
    database = await database_factory(path)
    try:
        service = AlertmanagerDeliveryService(
            chat_migrations=chat_migrations_factory(database),
            chain_id=1,
            module_adapter=module_adapter_factory(),
            database=database,
            metrics=metrics,
            source_ids=frozenset({"evm", "other"}),
            resolve_chats=lambda _: {100},
            send_message=AsyncMock(),
            clock=lambda: now[0],
        )
        await service.submit("evm", "one", (ALERT,))
        await service.submit("other", "two", (ALERT,))
        await service.refresh_queue_metrics()
        now[0] = 110.0
        # The real metrics HTTP server scrapes from another thread.
        exposition = (await asyncio.to_thread(generate_latest, registry)).decode()
        assert (
            'sentinel_alertmanager_oldest_pending_age_seconds{source_id="evm"} 10.0' in exposition
        )
    finally:
        await database.close()

    registry = CollectorRegistry()
    database = await database_factory(path)
    try:
        service = AlertmanagerDeliveryService(
            chat_migrations=chat_migrations_factory(database),
            chain_id=1,
            module_adapter=module_adapter_factory(),
            database=database,
            metrics=AppMetrics(registry).alertmanager,
            source_ids=frozenset({"evm"}),
            resolve_chats=lambda _: {100},
            send_message=AsyncMock(),
            clock=lambda: now[0],
        )
        await service.refresh_queue_metrics()
        for source in ("evm", "other"):
            assert (
                registry.get_sample_value(
                    "sentinel_alertmanager_pending_deliveries", {"source_id": source}
                )
                == 1
            )
            assert (
                registry.get_sample_value(
                    "sentinel_alertmanager_oldest_pending_age_seconds", {"source_id": source}
                )
                == 10
            )
        assert await service.deliver_one() is True
        await service.refresh_queue_metrics()
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_pending_deliveries", {"source_id": "evm"}
            )
            == 0
        )
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_oldest_pending_age_seconds", {"source_id": "evm"}
            )
            == 0
        )
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_deliveries_total", {"source_id": "evm", "outcome": "sent"}
            )
            == 1
        )
        now[0] = 120.0
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_oldest_pending_age_seconds", {"source_id": "other"}
            )
            == 20
        )
    finally:
        await database.close()


@pytest.mark.parametrize("unsubscribed", [False, True])
async def test_dropped_deliveries_are_counted_and_clear_queue(
    tmp_path, unsubscribed, database_factory, module_adapter_factory, chat_migrations_factory
):
    registry = CollectorRegistry()
    database = await database_factory()
    chats = {100}
    sender = AsyncMock(side_effect=Forbidden("blocked"))
    try:
        service = AlertmanagerDeliveryService(
            chat_migrations=chat_migrations_factory(database),
            chain_id=1,
            module_adapter=module_adapter_factory(),
            database=database,
            metrics=AppMetrics(registry).alertmanager,
            source_ids=frozenset({"evm"}),
            resolve_chats=lambda _: chats,
            send_message=sender,
        )
        await service.submit("evm", "batch", (ALERT,))
        if unsubscribed:
            chats.clear()
        assert await service.deliver_one() is True
        await service.refresh_queue_metrics()
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_deliveries_total",
                {"source_id": "evm", "outcome": "unsubscribed" if unsubscribed else "failed"},
            )
            == 1
        )
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_pending_deliveries", {"source_id": "evm"}
            )
            == 0
        )
        if unsubscribed:
            sender.assert_not_awaited()
    finally:
        await database.close()


@pytest.mark.parametrize("after_delivery", [False, True])
async def test_idle_worker_recovers_metrics_after_transient_read_failure(
    database_factory, module_adapter_factory, chat_migrations_factory, monkeypatch, after_delivery
):
    from sqlalchemy.exc import OperationalError
    from sentinel.app.alertmanager_storage import AlertmanagerOutbox

    database = await database_factory()
    registry = CollectorRegistry()
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        database=database,
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AppMetrics(registry).alertmanager,
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
    )
    if after_delivery:
        await service.submit("evm", "batch", (ALERT,))
        await service.refresh_queue_metrics()
    original = AlertmanagerOutbox.queue_state
    reads = 0

    async def flaky_read(outbox):
        nonlocal reads
        reads += 1
        if reads == 1:
            raise OperationalError("metrics", {}, Exception("transient"))
        rows = await original(outbox)
        return rows

    monkeypatch.setattr(AlertmanagerOutbox, "queue_state", flaky_read)
    monkeypatch.setattr("sentinel.services.alertmanager.METRICS_REFRESH_SECONDS", 0.01)
    if after_delivery:
        assert await service.deliver_one()
        await service.refresh_queue_metrics()
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_pending_deliveries", {"source_id": "evm"}
            )
            == 1
        )
    else:
        await service.refresh_queue_metrics()
    worker = asyncio.create_task(service.run())
    try:
        async with asyncio.timeout(3):
            while (
                registry.get_sample_value(
                    "sentinel_alertmanager_pending_deliveries", {"source_id": "evm"}
                )
                != 0
            ):
                await asyncio.sleep(0.01)
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_pending_deliveries", {"source_id": "evm"}
            )
            == 0
        )
        assert (
            registry.get_sample_value(
                "sentinel_alertmanager_oldest_pending_age_seconds", {"source_id": "evm"}
            )
            == 0
        )
        assert sender.await_count == int(after_delivery)
        assert not worker.done()
        assert reads == 2
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def test_worker_coalesces_queue_metric_refreshes_across_deliveries(
    database_factory, module_adapter_factory, chat_migrations_factory, monkeypatch
):
    from sentinel.app.alertmanager_storage import AlertmanagerOutbox

    database = await database_factory()
    registry = CollectorRegistry()
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        database=database,
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AppMetrics(registry).alertmanager,
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100, 200, 300},
        send_message=sender,
    )
    original = AlertmanagerOutbox.queue_state
    reads = 0

    async def counted_read(outbox):
        nonlocal reads
        reads += 1
        return await original(outbox)

    monkeypatch.setattr(AlertmanagerOutbox, "queue_state", counted_read)
    monkeypatch.setattr("sentinel.services.alertmanager.METRICS_REFRESH_SECONDS", 0.3)
    await service.submit("evm", "batch", (ALERT,))
    assert reads == 0
    worker = asyncio.create_task(service.run())
    try:
        async with asyncio.timeout(3):
            while (
                registry.get_sample_value(
                    "sentinel_alertmanager_pending_deliveries", {"source_id": "evm"}
                )
                != 0
            ):
                await asyncio.sleep(0.01)
        assert sender.await_count == 3
        assert reads == 1
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await database.close()
