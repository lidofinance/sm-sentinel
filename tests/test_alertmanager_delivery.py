import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, Mock

import pytest
from prometheus_client import CollectorRegistry

from sentinel.metrics.alertmanager import AlertmanagerMetrics
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

from sentinel.alertmanager import AlertStatus, OperatorAlert
from sentinel.app.alertmanager_storage import (
    REQUEST_DEDUP_SECONDS,
    AlertmanagerOutbox,
    AlertmanagerOutboxFull,
)
from sentinel.services.alertmanager import (
    AlertmanagerDeliveryService,
    AlertmanagerBatchTooLarge,
    AlertmanagerScopeMismatch,
    AlertmanagerScopeUnavailable,
)


def make_alert(operator_id="42", summary="Missed duties"):
    return OperatorAlert(
        1, 3, operator_id, "MissedAttestations", AlertStatus.FIRING, summary, "30 validators"
    )


@pytest.fixture
async def database(database_factory):
    return await database_factory()


async def pending_count(database):
    async with database.session() as session:
        return await AlertmanagerOutbox(session).pending_count()


async def pending_for_source(database, source):
    async with database.session() as session:
        return await AlertmanagerOutbox(session).pending_for_source(source)


async def test_delivery_goes_only_to_each_operators_subscribers(
    database, module_adapter_factory, chat_migrations_factory
):
    targets = {"42": {100}, "7": {200}}
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda operator_id: targets[operator_id],
        send_message=sender,
    )
    await service.submit("evm", "batch", (make_alert(), make_alert("7", "Other operator")))
    while await service.deliver_one():
        pass

    assert await pending_count(database) == 0
    assert [
        (call.args[0], "Other operator" in call.args[1]) for call in sender.await_args_list
    ] == [
        (100, False),
        (200, True),
    ]


async def test_completed_chats_are_not_repeated_after_restart(
    tmp_path, database_factory, module_adapter_factory, chat_migrations_factory
):
    path = tmp_path / "sentinel.sqlite3"
    database = await database_factory(path)
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100, 200},
        send_message=sender,
    )
    await service.submit("evm", "batch", (make_alert(),))
    await service.deliver_one()
    await database.close()

    database = await database_factory(path)
    try:
        restarted_sender = AsyncMock()
        restarted = AlertmanagerDeliveryService(
            chat_migrations=chat_migrations_factory(database),
            chain_id=1,
            module_adapter=module_adapter_factory(),
            metrics=AlertmanagerMetrics(CollectorRegistry()),
            database=database,
            source_ids=frozenset({"evm", "other"}),
            resolve_chats=lambda _: {100, 200},
            send_message=restarted_sender,
        )
        assert await restarted.submit("evm", "batch", (make_alert(),)) is False
        assert await restarted.deliver_one() is True
        assert await restarted.deliver_one() is False
        restarted_sender.assert_awaited_once()
        assert restarted_sender.await_args.args[0] == 200
    finally:
        await database.close()


@pytest.mark.parametrize(
    "error",
    [
        NetworkError("unavailable"),
        TimedOut(),
        RetryAfter(30),
        Forbidden("blocked"),
        BadRequest("invalid"),
    ],
)
async def test_final_ptb_error_is_not_retried_and_does_not_block_following_messages(
    database, module_adapter_factory, chat_migrations_factory, error, caplog
):
    now = [100.0]
    sender = AsyncMock(side_effect=[error, None, None, None])
    registry = CollectorRegistry()
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(registry),
        database=database,
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100, 200},
        send_message=sender,
        clock=lambda: now[0],
    )
    await service.submit(
        "evm", "batch", (make_alert(summary="First"), make_alert(summary="Second"))
    )
    while await service.deliver_one():
        pass
    assert [call.args[0] for call in sender.await_args_list] == [100, 200, 100, 200]
    for chat in (100, 200):
        messages = [call.args[1] for call in sender.await_args_list if call.args[0] == chat]
        assert ["First" in message for message in messages] == [True, False]
    assert await pending_count(database) == 0
    now[0] += 300
    assert await service.deliver_one() is False
    assert sender.await_count == 4
    assert (
        registry.get_sample_value(
            "sentinel_alertmanager_deliveries_total", {"source_id": "evm", "outcome": "failed"}
        )
        == 1
    )
    assert (
        registry.get_sample_value(
            "sentinel_alertmanager_deliveries_total", {"source_id": "evm", "outcome": "sent"}
        )
        == 3
    )
    assert "Alertmanager notification delivery failed" in caplog.text


async def test_cancellation_during_send_keeps_the_delivery(
    database, module_adapter_factory, chat_migrations_factory
):
    sender = AsyncMock(side_effect=asyncio.CancelledError)
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
    )
    await service.submit("evm", "batch", (make_alert(),))
    with pytest.raises(asyncio.CancelledError):
        await service.deliver_one()
    assert await pending_count(database) == 1


async def test_unsubscribe_is_respected_for_already_queued_deliveries(
    database, module_adapter_factory, chat_migrations_factory
):
    targets = {100}
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: set(targets),
        send_message=sender,
    )
    await service.submit("evm", "batch", (make_alert(),))
    targets.clear()
    await service.deliver_one()
    sender.assert_not_awaited()
    assert await pending_count(database) == 0


async def test_blocked_bot_does_not_retry_forever(
    database, module_adapter_factory, chat_migrations_factory
):
    sender = AsyncMock(side_effect=Forbidden("blocked"))
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
    )
    await service.submit("evm", "batch", (make_alert(),))
    await service.deliver_one()
    assert await pending_count(database) == 0


async def test_dedup_does_not_suppress_future_reminders_forever(
    database, module_adapter_factory, chat_migrations_factory
):
    now = [100.0]
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100},
        send_message=AsyncMock(),
        clock=lambda: now[0],
    )
    assert await service.submit("evm", "batch", (make_alert(),)) is True
    assert await service.submit("evm", "batch", (make_alert(),)) is False
    await service.deliver_one()
    now[0] += REQUEST_DEDUP_SECONDS
    assert await service.submit("evm", "batch", (make_alert(),)) is True


async def test_pending_batches_are_deduplicated_even_after_retry_window(
    database, module_adapter_factory, chat_migrations_factory
):
    now = [100.0]
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100},
        send_message=AsyncMock(),
        clock=lambda: now[0],
    )
    await service.submit("evm", "batch", (make_alert(),))
    now[0] += REQUEST_DEDUP_SECONDS * 10
    assert await service.submit("evm", "batch", (make_alert(),)) is False
    assert await pending_count(database) == 1


@pytest.mark.parametrize("limit", ["MAX_PENDING_DELIVERIES", "MAX_PENDING_PER_SOURCE"])
async def test_batch_exceeding_empty_queue_capacity_is_rejected(
    database, monkeypatch, limit, module_adapter_factory, chat_migrations_factory
):
    monkeypatch.setattr(f"sentinel.app.alertmanager_storage.{limit}", 1)
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100, 200},
        send_message=AsyncMock(),
    )
    with pytest.raises(AlertmanagerBatchTooLarge):
        await service.submit("evm", "batch", (make_alert(),))
    assert await pending_count(database) == 0


@pytest.mark.parametrize("limit", ["MAX_PENDING_DELIVERIES", "MAX_PENDING_PER_SOURCE"])
async def test_full_queue_accepts_whole_batch_after_capacity_is_released(
    database, monkeypatch, limit, module_adapter_factory, chat_migrations_factory
):
    monkeypatch.setattr(f"sentinel.app.alertmanager_storage.{limit}", 2)
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda operator: {100} if operator == "7" else {100, 200},
        send_message=AsyncMock(),
    )
    await service.submit("evm", "first", (make_alert("7"),))
    with pytest.raises(AlertmanagerOutboxFull):
        await service.submit("evm", "second", (make_alert(),))
    assert await pending_count(database) == 1
    assert await service.deliver_one() is True
    assert await service.submit("evm", "second", (make_alert(),)) is True
    assert await pending_count(database) == 2


async def test_text_splitting_counts_towards_batch_capacity(
    database, monkeypatch, module_adapter_factory, chat_migrations_factory
):
    monkeypatch.setattr("sentinel.app.alertmanager_storage.MAX_PENDING_PER_SOURCE", 1)
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100},
        send_message=AsyncMock(),
    )
    with pytest.raises(AlertmanagerBatchTooLarge):
        await service.submit("evm", "long", (make_alert(summary="x" * 4000),))
    assert await pending_count(database) == 0


@pytest.mark.parametrize("elapsed", [0, REQUEST_DEDUP_SECONDS * 2])
async def test_retry_acknowledges_original_batch_when_new_subscribers_exceed_capacity(
    database, monkeypatch, elapsed, module_adapter_factory, chat_migrations_factory
):
    monkeypatch.setattr("sentinel.app.alertmanager_storage.MAX_PENDING_PER_SOURCE", 1)
    chats = {100}
    now = [100.0]
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: chats,
        send_message=AsyncMock(),
        clock=lambda: now[0],
    )
    assert await service.submit("evm", "batch", (make_alert(),)) is True
    chats.add(200)
    now[0] += elapsed
    assert await service.submit("evm", "batch", (make_alert(),)) is False
    assert await pending_count(database) == 1


async def test_identical_payloads_from_different_sources_have_independent_receipts(
    database, module_adapter_factory, chat_migrations_factory
):
    now = [100.0]
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
        clock=lambda: now[0],
    )
    assert await service.submit("evm", "same", (make_alert(),)) is True
    assert await service.submit("other", "same", (make_alert(),)) is True
    assert await service.submit("other", "same", (make_alert(),)) is False
    await service.deliver_one()
    now[0] += REQUEST_DEDUP_SECONDS
    assert await service.submit("evm", "same", (make_alert(),)) is True
    assert await service.submit("other", "same", (make_alert(),)) is False
    assert await pending_count(database) == 2


async def test_revoked_source_is_paused_without_blocking_another_source_in_the_same_chat(
    database, module_adapter_factory, chat_migrations_factory
):
    sender = AsyncMock()
    original = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
    )
    await original.submit("evm", "one", (make_alert(),))
    await original.submit("other", "two", (make_alert(),))
    restarted = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"other"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
    )
    assert await restarted.deliver_one() is True
    assert await restarted.deliver_one() is False
    assert "Source: other" in sender.await_args.args[1]
    assert await pending_for_source(database, "evm") == 1
    assert await pending_for_source(database, "other") == 0
    assert await original.deliver_one() is True
    assert "Source: evm" in sender.await_args.args[1]


async def test_one_sources_queue_quota_does_not_consume_anothers(
    database, monkeypatch, module_adapter_factory, chat_migrations_factory
):
    monkeypatch.setattr("sentinel.app.alertmanager_storage.MAX_PENDING_PER_SOURCE", 1)
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        database=database,
        source_ids=frozenset({"evm", "other"}),
        resolve_chats=lambda _: {100},
        send_message=AsyncMock(),
    )
    await service.submit("evm", "one", (make_alert(),))
    with pytest.raises(AlertmanagerOutboxFull):
        await service.submit("evm", "two", (make_alert(),))
    assert await service.submit("other", "two", (make_alert(),)) is True
    assert await pending_for_source(database, "evm") == 1
    assert await pending_for_source(database, "other") == 1


async def test_parallel_retries_commit_one_batch_across_sessions(
    database, database_factory, module_adapter_factory, chat_migrations_factory
):
    another = await database_factory(database.path, database.identity)
    # Separate services/locks: SQLite, not the in-process migration lock, must serialize dedup.
    services = [
        AlertmanagerDeliveryService(
            chat_migrations=chat_migrations_factory(db),
            chain_id=1,
            module_adapter=module_adapter_factory(),
            database=db,
            metrics=AlertmanagerMetrics(CollectorRegistry()),
            source_ids=frozenset({"evm"}),
            resolve_chats=lambda _: {100, 200},
            send_message=AsyncMock(),
        )
        for db in (database, another)
    ]
    results = await asyncio.gather(
        *(services[index % 2].submit("evm", "same", (make_alert(),)) for index in range(8))
    )
    assert results.count(True) == 1
    assert results.count(False) == 7
    assert await pending_count(database) == 2


@pytest.mark.parametrize("limit", ["MAX_PENDING_DELIVERIES", "MAX_PENDING_PER_SOURCE"])
async def test_parallel_batches_cannot_exceed_queue_quota(
    database, database_factory, monkeypatch, limit, module_adapter_factory, chat_migrations_factory
):
    monkeypatch.setattr(f"sentinel.app.alertmanager_storage.{limit}", 1)
    another = await database_factory(database.path, database.identity)
    services = [
        AlertmanagerDeliveryService(
            chat_migrations=chat_migrations_factory(database),
            chain_id=1,
            module_adapter=module_adapter_factory(),
            database=db,
            metrics=AlertmanagerMetrics(CollectorRegistry()),
            source_ids=frozenset({"evm"}),
            resolve_chats=lambda _: {100},
            send_message=AsyncMock(),
        )
        for db in (database, another)
    ]
    results = await asyncio.gather(
        *(
            service.submit("evm", str(index), (make_alert(),))
            for index, service in enumerate(services)
        ),
        return_exceptions=True,
    )
    assert results.count(True) == 1
    assert sum(isinstance(result, AlertmanagerOutboxFull) for result in results) == 1
    assert await pending_count(database) == 1


async def test_waiting_for_sqlite_writer_does_not_block_event_loop(
    database, module_adapter_factory, chat_migrations_factory
):
    import sqlite3
    import time

    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        database=database,
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100},
        send_message=AsyncMock(),
    )
    connection = sqlite3.connect(database.path)
    connection.execute("BEGIN IMMEDIATE")
    task = asyncio.create_task(service.submit("evm", "waiting", (make_alert(),)))
    started = time.monotonic()
    try:
        await asyncio.sleep(0.05)
        assert time.monotonic() - started < 1
        assert not task.done()
    finally:
        connection.rollback()
        connection.close()
        await asyncio.wait_for(task, timeout=2)
    assert await pending_count(database) == 1


async def test_network_send_does_not_hold_database_transaction(
    database, module_adapter_factory, chat_migrations_factory
):
    from sqlalchemy import text

    async def send(_chat, _message):
        async with database.transaction() as session:
            assert await session.scalar(text("SELECT 1")) == 1

    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        database=database,
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100},
        send_message=send,
    )
    await service.submit("evm", "one", (make_alert(),))
    assert await asyncio.wait_for(service.deliver_one(), timeout=2)
    assert await pending_count(database) == 0


@pytest.mark.parametrize("field, value", [("chain_id", 560048), ("staking_module_id", 1)])
@pytest.mark.parametrize("duplicate", [False, True])
async def test_scope_validation_rejects_entire_batch_before_fanout_or_deduplication(
    database, module_adapter_factory, field, value, duplicate, chat_migrations_factory
):
    resolve = Mock(return_value={100})
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        database=database,
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        source_ids=frozenset({"evm"}),
        resolve_chats=resolve,
        send_message=AsyncMock(),
    )
    if duplicate:
        await service.submit("evm", "batch", (make_alert(),))
        resolve.reset_mock()
    with pytest.raises(AlertmanagerScopeMismatch, match=field):
        await service.submit(
            "evm", "batch", (make_alert(), replace(make_alert(), **{field: value}))
        )
    resolve.assert_not_called()
    assert await pending_count(database) == int(duplicate)
    if not duplicate:
        async with database.session() as session:
            assert not await AlertmanagerOutbox(session).has_receipt("evm", "batch", now=0)


async def test_persisted_queue_delivers_while_new_webhooks_wait_for_registration(
    database, module_adapter_factory, chat_migrations_factory
):
    async with database.transaction() as session:
        outbox = AlertmanagerOutbox(session)
        await outbox.enqueue_new("evm", "old", [("42", 100, "persisted")], now=0)
    adapter = module_adapter_factory(None)
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        database=database,
        chain_id=1,
        module_adapter=adapter,
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
    )
    with pytest.raises(AlertmanagerScopeUnavailable):
        await service.submit("evm", "new", (make_alert(),))
    assert await pending_count(database) == 1
    assert await service.deliver_one() is True
    sender.assert_awaited_once_with(100, "persisted")
    assert await pending_count(database) == 0
    # Delivery did not require registration; accepting a new webhook still does.
    with pytest.raises(AlertmanagerScopeUnavailable):
        await service.submit("evm", "new", (make_alert(),))
    adapter.contracts.staking_router.functions.getStakingModules().call = AsyncMock(
        return_value=[(3, adapter.addresses.module)]
    )
    await adapter.refresh_staking_module_id()
    assert adapter.staking_module_id == 3
    assert await service.submit("evm", "new", (make_alert(),)) is True


@pytest.mark.parametrize("submit_before_wait", [False, True])
async def test_idle_worker_waits_without_polling_and_wakes_for_new_deliveries(
    database, module_adapter_factory, chat_migrations_factory, monkeypatch, submit_before_wait
):
    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        database=database,
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
    )
    first_empty, next_empty, resume = asyncio.Event(), asyncio.Event(), asyncio.Event()
    deliver_one = service.deliver_one

    async def observe_delivery():
        delivered = await deliver_one()
        if not delivered:
            if first_empty.is_set():
                next_empty.set()
            else:
                first_empty.set()
                if submit_before_wait:
                    # Submit after the empty read but before the worker starts waiting.
                    await resume.wait()
        return delivered

    monkeypatch.setattr(service, "deliver_one", observe_delivery)
    worker = asyncio.create_task(service.run())
    try:
        await asyncio.wait_for(first_empty.wait(), timeout=2)
        if not submit_before_wait:
            # A healthy idle worker must not repeat the old once-per-second DB poll.
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(next_empty.wait(), timeout=1.1)
        await service.submit("evm", "batch", (make_alert(),))
        resume.set()
        await asyncio.wait_for(next_empty.wait(), timeout=2)
        sender.assert_awaited_once()
        assert await pending_count(database) == 0
        assert not worker.done()
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


async def test_worker_survives_errors_and_retries_with_backoff(
    database, module_adapter_factory, chat_migrations_factory, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    sender = AsyncMock()
    service = AlertmanagerDeliveryService(
        database=database,
        chat_migrations=chat_migrations_factory(database),
        chain_id=1,
        module_adapter=module_adapter_factory(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        source_ids=frozenset({"evm"}),
        resolve_chats=lambda _: {100},
        send_message=sender,
    )
    await service.submit("evm", "batch", (make_alert(),))
    deliver_one = service.deliver_one
    failures = [OperationalError("next", {}, Exception("locked")), RuntimeError("bug")]

    async def flaky_delivery():
        if failures:
            raise failures.pop(0)
        return await deliver_one()

    monkeypatch.setattr(service, "deliver_one", flaky_delivery)
    monkeypatch.setattr("sentinel.services.alertmanager.WORKER_RETRY_INITIAL_SECONDS", 0.01)
    worker = asyncio.create_task(service.run())
    try:
        async with asyncio.timeout(3):
            while sender.await_count == 0:
                await asyncio.sleep(0.01)
        assert failures == []
        assert await pending_count(database) == 0
        assert not worker.done()
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
