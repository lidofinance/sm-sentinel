import asyncio
import json
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.ext import ApplicationBuilder

from sentinel.alertmanager_auth import AlertmanagerSource
from sentinel.app.application import SentinelApplication
from sentinel.app.bootstrap import (
    _bind_persistence_runtime,
    _persist_initial_checkpoint,
    _resolve_backfill_start_block,
    _run,
    _wait_for_subscription_start,
    create_runtime,
)
from sentinel.app.health import HealthState
from sentinel.app.runtime import BotRuntime
from sentinel.app.storage import RuntimeIdentity, create_persistence
from sentinel.module_types import ModuleType
from sentinel.services.subscription import ModuleRuntimeSupervisor


@pytest.mark.parametrize(
    ("configured_block", "persisted_block", "expected"),
    [
        (None, None, 0),
        (None, 0, 0),
        (None, "0x0", 0),
        (None, 42, 43),
        (100, None, 100),
        (0, 42, 0),
    ],
)
def test_resolve_backfill_start_block(
    configured_block: int | None,
    persisted_block: object | None,
    expected: int,
):
    assert _resolve_backfill_start_block(configured_block, persisted_block) == expected


@pytest.mark.asyncio
async def test_legacy_runtime_identity_is_persisted_before_periodic_update(tmp_path):
    persistence = create_persistence(tmp_path)
    application = (
        ApplicationBuilder()
        .application_class(SentinelApplication)
        .token("123:TEST")
        .persistence(persistence)
        .build()
    )
    identity = RuntimeIdentity(
        chain_id=1,
        module_address="0x1234",
        module_type=ModuleType.COMMUNITY,
    )
    application.bot_data["block"] = 25_600_000

    await _bind_persistence_runtime(application, identity)

    restarted_persistence = create_persistence(tmp_path)
    restarted_bot_data = await restarted_persistence.get_bot_data()
    assert restarted_bot_data["runtime_identity"] == identity.to_dict()
    assert restarted_bot_data["block"] == 25_600_000


@pytest.mark.asyncio
async def test_runtime_identity_mismatch_stops_before_polling_and_cleans_up():
    persisted_identity = RuntimeIdentity(
        chain_id=1,
        module_address="0x1234",
        module_type=ModuleType.COMMUNITY,
    )
    current_identity = RuntimeIdentity(
        chain_id=560_048,
        module_address="0x5678",
        module_type=ModuleType.CURATED,
    )
    updater = SimpleNamespace(start_polling=AsyncMock(), stop=AsyncMock())
    application = SimpleNamespace(
        updater=updater,
        bot_data={"runtime_identity": persisted_identity.to_dict(), "block": 25_600_000},
        persistence=SimpleNamespace(flush=AsyncMock()),
        initialize=AsyncMock(),
        update_persistence=AsyncMock(),
        start=AsyncMock(),
        stop=AsyncMock(),
        shutdown=AsyncMock(),
        add_error_handler=MagicMock(),
    )
    heartbeat_task = asyncio.create_task(asyncio.Event().wait())
    health = HealthState()
    module_supervisor = SimpleNamespace(
        cfg=SimpleNamespace(admin_ids=set(), block_from=None),
        request_shutdown=MagicMock(),
        close=AsyncMock(),
    )
    health_server = SimpleNamespace(stop=MagicMock())
    runtime = cast(
        BotRuntime,
        SimpleNamespace(
            application=application,
            module_supervisor=module_supervisor,
            job_context=MagicMock(),
            config=module_supervisor.cfg,
            module_adapter=MagicMock(),
            health=health,
            heartbeat_task=heartbeat_task,
            chain=SimpleNamespace(close=AsyncMock()),
            health_server=health_server,
            runtime_identity=current_identity,
            database=SimpleNamespace(open=AsyncMock(), close=AsyncMock()),
            alertmanager_server=SimpleNamespace(start=AsyncMock(), stop=AsyncMock()),
        ),
    )

    try:
        with pytest.raises(RuntimeError, match="does not match configured runtime"):
            await _run(runtime)
    finally:
        if not heartbeat_task.done():
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    updater.start_polling.assert_not_awaited()
    updater.stop.assert_not_awaited()
    application.stop.assert_awaited_once()
    application.shutdown.assert_awaited_once()
    module_supervisor.close.assert_awaited_once()
    health_server.stop.assert_called_once()
    assert "does not match configured runtime" in (health.snapshot().fatal_error or "")


@pytest.mark.asyncio
async def test_initial_checkpoint_is_available_before_periodic_update(tmp_path):
    persistence = create_persistence(tmp_path)
    application = (
        ApplicationBuilder()
        .application_class(SentinelApplication)
        .token("123:TEST")
        .persistence(persistence)
        .build()
    )
    supervisor = MagicMock(spec=ModuleRuntimeSupervisor)

    async def establish_initial_checkpoint() -> int:
        application.bot_data["block"] = 25_600_000
        return 25_600_000

    supervisor.establish_initial_checkpoint = AsyncMock(side_effect=establish_initial_checkpoint)

    initial_checkpoint = await _persist_initial_checkpoint(application, supervisor)

    restarted_persistence = create_persistence(tmp_path)
    assert initial_checkpoint == 25_600_000
    assert (await restarted_persistence.get_bot_data())["block"] == 25_600_000


@pytest.mark.asyncio
async def test_subscription_start_propagates_early_supervisor_failure():
    never_subscribed = asyncio.Event()
    supervisor = SimpleNamespace(wait_until_subscribed=never_subscribed.wait)

    async def fail_supervisor():
        await asyncio.sleep(0)
        raise RuntimeError("subscription setup failed")

    supervisor_task = asyncio.create_task(fail_supervisor())

    with pytest.raises(RuntimeError, match="subscription setup failed"):
        await _wait_for_subscription_start(supervisor, supervisor_task)


@pytest.mark.parametrize(
    ("token", "module_id"),
    [("a" * 43, 3), (None, 3), (None, None), ("a" * 43, None)],
)
async def test_webhook_is_bound_to_validated_rpc_and_discovered_module(
    monkeypatch, tmp_path, fake_contract_addresses, token, module_id
):
    from sentinel.app import bootstrap
    from sentinel.app.storage import BotStorage

    monkeypatch.setenv("WEB3_SOCKET_PROVIDERS", "wss://example.invalid/ws")
    monkeypatch.setenv("MODULE_ADDRESS", "0x0000000000000000000000000000000000000001")
    monkeypatch.setenv("TOKEN", "123:TEST")
    monkeypatch.setenv("FILESTORAGE_PATH", str(tmp_path))
    monkeypatch.delenv("ALERTMANAGER_WEBHOOK_SOURCES", raising=False)
    if token:
        monkeypatch.setenv("ALERTMANAGER_WEBHOOK_SOURCES", json.dumps({"evm": [token]}))
    monkeypatch.setattr("sentinel.config._CONFIG", None)
    monkeypatch.setattr(bootstrap, "load_environment_files", lambda: None)
    monkeypatch.setattr(bootstrap, "HealthServer", MagicMock())
    monkeypatch.setattr(bootstrap, "DEFAULT_METRICS", MagicMock())
    pool = SimpleNamespace(chain_id=560048)
    monkeypatch.setattr(bootstrap, "RpcEndpointPool", MagicMock(return_value=pool))
    provider = SimpleNamespace(
        validate_endpoint_chain_ids=AsyncMock(),
        disconnect=AsyncMock(),
    )
    monkeypatch.setattr(bootstrap, "FallbackRequestProvider", MagicMock(return_value=provider))
    monkeypatch.setattr(bootstrap, "FallbackAsyncWeb3", MagicMock())
    addresses = replace(fake_contract_addresses(), staking_module_id=module_id)
    monkeypatch.setattr(bootstrap, "discover_contract_addresses", AsyncMock(return_value=addresses))
    adapter_factory = MagicMock()
    monkeypatch.setattr(bootstrap, "build_module_adapter_from_addresses", adapter_factory)
    monkeypatch.setattr(bootstrap, "ModuleRuntimeSupervisor", MagicMock())
    monkeypatch.setattr(bootstrap, "JobContext", MagicMock())
    service_factory = MagicMock()
    monkeypatch.setattr(bootstrap, "AlertmanagerDeliveryService", service_factory)
    server_factory = MagicMock()
    monkeypatch.setattr(bootstrap, "AlertmanagerWebhookServer", server_factory)

    runtime = await create_runtime()
    try:
        provider.validate_endpoint_chain_ids.assert_awaited_once()
        assert adapter_factory.call_args.args[0] is addresses
        server_factory.assert_called_once()
        service_factory.assert_called_once()
        arguments = service_factory.call_args.kwargs
        assert arguments["chain_id"] == 560048
        assert arguments["module_adapter"] is adapter_factory.return_value
        assert arguments["database"] is runtime.database
        assert runtime.database.path == tmp_path / "sentinel.sqlite3"
        expected_sources = () if token is None else (AlertmanagerSource("evm", (token,)),)
        assert arguments["source_ids"] == frozenset(source.source_id for source in expected_sources)
        assert server_factory.call_args.kwargs["sources"] == expected_sources
        assert server_factory.call_args.kwargs["service"] is runtime.alertmanager_service
        assert runtime.alertmanager_service is service_factory.return_value
        assert runtime.alertmanager_server is server_factory.return_value
        storage = BotStorage(runtime.application.bot_data)
        storage.users.add(100)
        storage.node_operator_chats.subscribe("42", 100)
        storage.node_operator_chats.subscribe("7", 200)
        assert arguments["resolve_chats"]("42") == {100}
        assert arguments["resolve_chats"]("7") == set()
    finally:
        runtime.heartbeat_task.cancel()
        await asyncio.gather(runtime.heartbeat_task, return_exceptions=True)


@pytest.mark.parametrize(
    "worker_fails, enabled, stop_fails",
    [(True, True, False), (False, True, False), (False, False, False), (False, True, True)],
)
async def test_runtime_supervises_delivery_worker(monkeypatch, worker_fails, enabled, stop_fails):
    from sentinel.app import bootstrap

    started = asyncio.Event()
    health = HealthState()
    health.mark_subscription_active()

    recovered = asyncio.Event()
    recovery = AsyncMock(side_effect=recovered.set)
    worker_started = asyncio.Event()
    worker_stopped = asyncio.Event()

    async def run_worker():
        assert recovered.is_set()
        worker_started.set()
        try:
            await started.wait()
            assert health.snapshot().ready is True
            if worker_fails:
                raise RuntimeError("delivery worker failed")
            await asyncio.Event().wait()
        finally:
            worker_stopped.set()

    async def start_receiver():
        snapshot = health.snapshot()
        assert snapshot.startup_complete is True
        assert snapshot.alertmanager_ready is False
        assert snapshot.ready is False
        started.set()

    async def subscription():
        await started.wait()
        assert health.snapshot().ready is True
        if enabled:
            await worker_started.wait()
        if worker_fails:
            await asyncio.Event().wait()

    service = SimpleNamespace(
        run=AsyncMock(side_effect=run_worker), refresh_queue_metrics=AsyncMock()
    )
    server = SimpleNamespace(
        start=AsyncMock(side_effect=start_receiver),
        stop=AsyncMock(side_effect=RuntimeError("receiver cleanup failed") if stop_fails else None),
    )
    application = SimpleNamespace(
        updater=SimpleNamespace(
            start_polling=AsyncMock(
                side_effect=lambda **_: recovered.is_set() or pytest.fail("polling before recovery")
            ),
            stop=AsyncMock(),
        ),
        bot_data={},
        persistence=SimpleNamespace(flush=AsyncMock()),
        initialize=AsyncMock(),
        update_persistence=AsyncMock(),
        start=AsyncMock(),
        stop=AsyncMock(),
        shutdown=AsyncMock(),
        add_error_handler=MagicMock(),
    )
    supervisor = SimpleNamespace(
        cfg=SimpleNamespace(
            admin_ids=set(), block_from=0, alertmanager_webhook_sources=("evm",) if enabled else ()
        ),
        ensure_state_containers=MagicMock(),
        setup_signal_handlers=MagicMock(),
        establish_initial_checkpoint=AsyncMock(return_value=42),
        subscribe=AsyncMock(side_effect=subscription),
        request_shutdown=MagicMock(),
        close=AsyncMock(),
    )
    heartbeat_task = asyncio.create_task(asyncio.Event().wait())
    runtime = cast(
        BotRuntime,
        SimpleNamespace(
            application=application,
            module_supervisor=supervisor,
            job_context=SimpleNamespace(schedule=AsyncMock()),
            config=supervisor.cfg,
            module_adapter=SimpleNamespace(warm_up=AsyncMock()),
            health=health,
            heartbeat_task=heartbeat_task,
            chain=SimpleNamespace(close=AsyncMock()),
            health_server=SimpleNamespace(stop=MagicMock()),
            runtime_identity=RuntimeIdentity(1, "0x1234", ModuleType.COMMUNITY),
            database=SimpleNamespace(open=AsyncMock(), close=AsyncMock()),
            alertmanager_server=server,
            alertmanager_service=service,
            chat_migrations=SimpleNamespace(recover=recovery),
        ),
    )
    monkeypatch.setattr(bootstrap, "_wait_for_subscription_start", AsyncMock())
    with (
        pytest.raises(RuntimeError, match="delivery worker failed")
        if worker_fails
        else pytest.raises(RuntimeError, match="receiver cleanup failed")
        if stop_fails
        else nullcontext()
    ):
        await _run(runtime)
    recovery.assert_awaited_once()
    assert service.run.await_count == int(enabled)
    assert service.refresh_queue_metrics.await_count == int(enabled)
    assert worker_stopped.is_set() is enabled
    server.start.assert_awaited_once()
    server.stop.assert_awaited_once()
    supervisor.close.assert_awaited_once()
    application.shutdown.assert_awaited_once()
    assert heartbeat_task.cancelled()
    assert health.snapshot().alertmanager_ready is False
