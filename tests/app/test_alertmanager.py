from http import HTTPStatus

import asyncio
import copy
from contextlib import suppress
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
from aiohttp import web
import pytest
from prometheus_client import CollectorRegistry, generate_latest

from sentinel.metrics.alertmanager import AlertmanagerMetrics

from sentinel.app.alertmanager import MAX_WEBHOOK_BYTES, AlertmanagerWebhookServer
from sentinel.alertmanager_auth import AlertmanagerSource
from sentinel.app.storage import BotStorage
from sentinel.app.health import HealthState
from sentinel.services.alertmanager import AlertmanagerDeliveryService

KEY_EVM = "a" * 43
KEY_EVM_NEXT = "c" * 43
KEY_OTHER = "b" * 43


@pytest.fixture
def payload():
    return {
        "version": "4",
        "status": "firing",
        "groupKey": "operators",
        "truncatedAlerts": 0,
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "MissedAttestations",
                    "chain_id": "1",
                    "staking_module_id": "3",
                    "node_operator_id": "42",
                },
                "annotations": {"summary": "First operator", "description": "30 validators"},
                "fingerprint": "abc",
                "startsAt": "2026-10-29T10:00:00Z",
            }
        ],
    }


@pytest.fixture
def webhook_module_id():
    return 3


@pytest.fixture
async def receiver(
    tmp_path, webhook_module_id, database_factory, module_adapter_factory, chat_migrations_factory
):
    storage = BotStorage({})
    for chat_id in (100, 200, 300):
        storage.users.add(chat_id)
    for operator_id, chat_ids in {"42": (100, 300, 999), "7": (200, 300)}.items():
        for chat_id in chat_ids:
            storage.node_operator_chats.subscribe(operator_id, chat_id)
    received = asyncio.Event()

    async def record_delivery(chat_id, message):
        received.set()

    sender = AsyncMock(side_effect=record_delivery)
    now = [0.0]
    registry = CollectorRegistry()
    database = await database_factory()
    metrics = AlertmanagerMetrics(registry)
    module_adapter = module_adapter_factory(webhook_module_id)
    service = AlertmanagerDeliveryService(
        chat_migrations=chat_migrations_factory(database),
        metrics=metrics,
        source_ids=frozenset({"evm", "other"}),
        chain_id=1,
        module_adapter=module_adapter,
        database=database,
        resolve_chats=lambda operator_id: storage.resolve_target_chats({operator_id}),
        send_message=sender,
    )
    server = AlertmanagerWebhookServer(
        metrics=metrics,
        sources=(
            AlertmanagerSource("evm", (KEY_EVM, KEY_EVM_NEXT)),
            AlertmanagerSource("other", (KEY_OTHER,)),
        ),
        service=service,
        host="127.0.0.1",
        port=0,
        clock=lambda: now[0],
    )
    worker = asyncio.create_task(service.run())
    await server.start()

    async def wait_for_messages(count):
        async with asyncio.timeout(2):
            while sender.await_count < count:
                received.clear()
                await received.wait()

    try:
        async with aiohttp.ClientSession(
            base_url=f"http://127.0.0.1:{server.port}",
            headers={"Authorization": f"Bearer {KEY_EVM}"},
        ) as client:
            yield SimpleNamespace(
                module_adapter=module_adapter,
                database=database,
                registry=registry,
                clock=now,
                server=server,
                client=client,
                storage=storage,
                sender=sender,
                wait_for_messages=wait_for_messages,
            )
    finally:
        await server.stop()
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


@pytest.mark.parametrize("webhook_module_id", [None])
async def test_missing_module_id_keeps_listener_running_and_rejects_without_enqueuing(
    receiver, payload, tmp_path
):
    async with receiver.database.session() as session:
        assert (await session.execute(text("SELECT * FROM alertmanager_deliveries"))).all() == []
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    assert (await response.json())["error"] == "Staking module ID is unavailable"
    response = await receiver.client.post(
        "/webhooks/alertmanager", json=payload, headers={"Authorization": "Bearer invalid"}
    )
    assert response.status == HTTPStatus.UNAUTHORIZED
    receiver.sender.assert_not_awaited()
    async with receiver.database.session() as session:
        assert (await session.execute(text("SELECT * FROM alertmanager_deliveries"))).all() == []
    assert (
        receiver.registry.get_sample_value(
            "sentinel_alertmanager_webhooks_total",
            {"source_id": "evm", "status": str(HTTPStatus.SERVICE_UNAVAILABLE)},
        )
        == 1
    )


async def test_disabled_receiver_lifecycle_needs_no_listener_or_delivery():
    service = AsyncMock(spec=AlertmanagerDeliveryService)
    health = HealthState()
    health.mark_polling_started()
    health.mark_subscription_active()
    health.mark_startup_complete()
    assert health.snapshot().ready is False
    server = AlertmanagerWebhookServer(
        sources=(),
        metrics=AlertmanagerMetrics(CollectorRegistry()),
        service=service,
        host="127.0.0.1",
        port=0,
    )
    await server.start()
    health.mark_alertmanager_ready()
    try:
        assert server.port == 0
        assert health.snapshot().alertmanager_ready is True
        assert health.snapshot().ready is True
        service.submit.assert_not_awaited()
        service.run.assert_not_awaited()
    finally:
        await server.stop()


async def test_http_batch_delivers_only_each_operators_text_to_its_subscribers(receiver, payload):
    second = copy.deepcopy(payload["alerts"][0])
    second["labels"]["node_operator_id"] = "7"
    second["annotations"]["summary"] = "Second operator"
    payload["alerts"].append(second)
    payload["commonAnnotations"] = {"description": "All operators secret"}

    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(4)

    deliveries = [(call.args[0], call.args[1]) for call in receiver.sender.await_args_list]
    assert {chat_id for chat_id, _ in deliveries} == {100, 200, 300}
    assert len(deliveries) == 4
    assert all("All operators secret" not in text for _, text in deliveries)
    assert all("Second operator" not in text for chat_id, text in deliveries if chat_id == 100)
    assert all("First operator" not in text for chat_id, text in deliveries if chat_id == 200)


async def test_receiver_shutdown_does_not_close_shared_database(receiver):
    await receiver.server.stop()
    async with receiver.database.transaction() as session:
        await session.execute(text("CREATE TABLE another_subsystem (value INTEGER)"))
        await session.execute(text("INSERT INTO another_subsystem VALUES (1)"))
    async with receiver.database.session() as session:
        assert (await session.execute(text("SELECT value FROM another_subsystem"))).one() == (1,)


@pytest.mark.parametrize("authorization", ["", "Bearer wrong-token", "Basic test-webhook-token"])
async def test_unauthorized_requests_never_enter_delivery(receiver, payload, authorization, caplog):
    response = await receiver.client.post(
        "/webhooks/alertmanager", json=payload, headers={"Authorization": authorization}
    )
    assert response.status == HTTPStatus.UNAUTHORIZED
    receiver.sender.assert_not_awaited()
    assert KEY_EVM not in caplog.text


@pytest.mark.parametrize("field, value", [("chain_id", "560048"), ("staking_module_id", "1")])
async def test_scope_mismatch_in_later_alert_rejects_whole_batch(receiver, payload, field, value):
    invalid = copy.deepcopy(payload["alerts"][0])
    invalid["labels"][field] = value
    payload["alerts"].append(invalid)
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert field in (await response.json())["error"]
    receiver.sender.assert_not_awaited()


@pytest.mark.parametrize("field", ["chain_id", "staking_module_id", "node_operator_id"])
async def test_missing_label_does_not_fall_back_to_common_labels(receiver, payload, field):
    labels = payload["alerts"][0]["labels"]
    payload["commonLabels"] = {field: labels.pop(field)}
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.UNPROCESSABLE_ENTITY
    receiver.sender.assert_not_awaited()


@pytest.mark.parametrize("body", ["{broken", "[]", '{"a": NaN}', '{"a": "\\ud800"}'])
async def test_malformed_json_or_envelope_is_rejected(receiver, body):
    response = await receiver.client.post(
        "/webhooks/alertmanager", data=body, headers={"Content-Type": "application/json"}
    )
    assert response.status in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNPROCESSABLE_ENTITY)
    receiver.sender.assert_not_awaited()


async def test_body_size_limit_is_enforced(receiver):
    response = await receiver.client.post(
        "/webhooks/alertmanager",
        data=b"x" * (MAX_WEBHOOK_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert (
        receiver.registry.get_sample_value(
            "sentinel_alertmanager_webhooks_total",
            {"source_id": "evm", "status": str(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)},
        )
        == 1
    )
    receiver.sender.assert_not_awaited()


async def test_wrong_content_type_is_rejected(receiver):
    response = await receiver.client.post("/webhooks/alertmanager", data="{}")
    assert response.status == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


async def test_webhook_metrics_distinguish_duplicates_and_rejections_without_payload_labels(
    receiver, payload
):
    payload["source_id"] = "untrusted-label"
    for _ in range(2):
        response = await receiver.client.post("/webhooks/alertmanager", json=payload)
        assert response.status == HTTPStatus.ACCEPTED
    response = await receiver.client.post(
        "/webhooks/alertmanager", json=payload, headers={"Authorization": "Bearer invalid-key"}
    )
    assert response.status == HTTPStatus.UNAUTHORIZED
    payload["alerts"][0]["labels"]["chain_id"] = "2"
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.UNPROCESSABLE_ENTITY
    for source_id, status, count in [
        ("evm", HTTPStatus.ACCEPTED, 2),
        ("", HTTPStatus.UNAUTHORIZED, 1),
        ("evm", HTTPStatus.UNPROCESSABLE_ENTITY, 1),
    ]:
        assert (
            receiver.registry.get_sample_value(
                "sentinel_alertmanager_webhooks_total",
                {"source_id": source_id, "status": str(status)},
            )
            == count
        )
    for outcome in ("accepted", "duplicate"):
        assert (
            receiver.registry.get_sample_value(
                "sentinel_alertmanager_batches_total", {"source_id": "evm", "outcome": outcome}
            )
            == 1
        )
    exposition = generate_latest(receiver.registry).decode()
    for private_value in (KEY_EVM, "invalid-key", "untrusted-label", "MissedAttestations"):
        assert private_value not in exposition


async def test_retry_is_deduplicated_but_new_occurrence_with_same_fingerprint_is_delivered(
    receiver, payload
):
    first = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert first.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(2)
    retry = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert retry.status == HTTPStatus.ACCEPTED
    assert (await retry.json())["accepted"] is False
    assert receiver.sender.await_count == 2

    payload["alerts"][0]["startsAt"] = "2026-10-29T11:00:00Z"
    reminder = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert reminder.status == HTTPStatus.ACCEPTED
    assert (await reminder.json())["accepted"] is True
    await receiver.wait_for_messages(4)


async def test_unavailable_persistence_returns_retryable_status(receiver, payload, monkeypatch):
    def fail_enqueue(*args, **kwargs):
        raise OperationalError("insert", {}, Exception("disk unavailable"))

    monkeypatch.setattr(
        "sentinel.app.alertmanager_storage.AlertmanagerOutbox.enqueue_new", fail_enqueue
    )
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    receiver.sender.assert_not_awaited()
    assert (
        receiver.registry.get_sample_value(
            "sentinel_alertmanager_webhooks_total",
            {"source_id": "evm", "status": str(HTTPStatus.SERVICE_UNAVAILABLE)},
        )
        == 1
    )


async def test_full_queue_rejects_whole_request(receiver, payload, monkeypatch):
    monkeypatch.setattr("sentinel.app.alertmanager_storage.MAX_PENDING_DELIVERIES", 2)
    release = asyncio.Event()
    record_delivery = receiver.sender.side_effect

    async def blocked_sender(chat_id, message):
        await release.wait()
        await record_delivery(chat_id, message)

    receiver.sender.side_effect = blocked_sender
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    payload["alerts"][0]["annotations"]["summary"] = "Next notification"
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    release.set()
    await receiver.wait_for_messages(2)
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(4)


async def test_oversized_fan_out_returns_permanent_error_without_partial_delivery(
    receiver, payload
):
    payload["alerts"] = [copy.deepcopy(payload["alerts"][0]) for _ in range(501)]
    for index, alert in enumerate(payload["alerts"]):
        alert["annotations"]["summary"] = f"Validator {index}"
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "fan-out" in (await response.json())["error"]
    receiver.sender.assert_not_awaited()

    payload["alerts"] = payload["alerts"][:1]
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(2)


async def test_retry_after_subscription_growth_still_acknowledges_accepted_batch(
    receiver, payload, monkeypatch
):
    monkeypatch.setattr("sentinel.app.alertmanager_storage.MAX_PENDING_PER_SOURCE", 2)
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(2)
    receiver.storage.node_operator_chats.subscribe("42", 200)
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    assert (await response.json())["accepted"] is False
    assert receiver.sender.await_count == 2


async def test_rotating_keys_share_receipts_but_different_sources_do_not(receiver, payload):
    first = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert first.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(2)
    rotated = await receiver.client.post(
        "/webhooks/alertmanager", json=payload, headers={"Authorization": f"Bearer {KEY_EVM_NEXT}"}
    )
    assert rotated.status == HTTPStatus.ACCEPTED
    assert (await rotated.json())["accepted"] is False
    another = await receiver.client.post(
        "/webhooks/alertmanager", json=payload, headers={"Authorization": f"Bearer {KEY_OTHER}"}
    )
    assert another.status == HTTPStatus.ACCEPTED
    assert (await another.json())["accepted"] is True
    await receiver.wait_for_messages(4)
    assert "Source: evm" in receiver.sender.await_args_list[0].args[1]
    assert "Source: other" in receiver.sender.await_args_list[-1].args[1]


async def test_payload_cannot_override_authenticated_source(receiver, payload, caplog):
    payload["source_id"] = "forged"
    payload["alerts"][0]["labels"]["source_id"] = "forged"
    with caplog.at_level("INFO", logger="sentinel.app.alertmanager"):
        response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(2)
    assert "Source: evm" in receiver.sender.await_args.args[1]
    assert "forged" not in receiver.sender.await_args.args[1]
    assert any(getattr(record, "source_id", None) == "evm" for record in caplog.records)
    assert KEY_EVM not in caplog.text


async def test_request_limit_is_per_source_including_rotating_keys(receiver, payload, monkeypatch):
    monkeypatch.setattr("sentinel.app.alertmanager.MAX_REQUESTS_PER_SOURCE_PER_MINUTE", 1)
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    for key in (KEY_EVM, KEY_EVM_NEXT):
        limited = await receiver.client.post(
            "/webhooks/alertmanager", json=payload, headers={"Authorization": f"Bearer {key}"}
        )
        assert limited.status == HTTPStatus.SERVICE_UNAVAILABLE
    another = await receiver.client.post(
        "/webhooks/alertmanager", json=payload, headers={"Authorization": f"Bearer {KEY_OTHER}"}
    )
    assert another.status == HTTPStatus.ACCEPTED
    receiver.clock[0] += 60
    allowed = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert allowed.status == HTTPStatus.ACCEPTED


async def test_slow_source_does_not_occupy_all_other_sources_connections(
    receiver, payload, monkeypatch
):
    monkeypatch.setattr("sentinel.app.alertmanager.MAX_IN_FLIGHT_PER_SOURCE", 1)
    entered = asyncio.Event()
    release = asyncio.Event()
    original = web.Request.json

    async def slow(request):
        if request.headers.get("Authorization") == f"Bearer {KEY_EVM}":
            entered.set()
            await release.wait()
        return await original(request)

    monkeypatch.setattr(web.Request, "json", slow)
    pending = asyncio.create_task(receiver.client.post("/webhooks/alertmanager", json=payload))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        overloaded = await receiver.client.post("/webhooks/alertmanager", json=payload)
        assert overloaded.status == HTTPStatus.SERVICE_UNAVAILABLE
        another = await receiver.client.post(
            "/webhooks/alertmanager", json=payload, headers={"Authorization": f"Bearer {KEY_OTHER}"}
        )
        assert another.status == HTTPStatus.ACCEPTED
    finally:
        release.set()
        response = await pending
        assert response.status == HTTPStatus.ACCEPTED


async def test_slow_request_body_gets_retryable_response_and_releases_capacity(
    receiver, payload, monkeypatch
):
    monkeypatch.setattr("sentinel.app.alertmanager.REQUEST_BODY_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr("sentinel.app.alertmanager.MAX_IN_FLIGHT_PER_SOURCE", 1)

    async def body():
        yield b"{"
        await asyncio.Event().wait()

    response = await receiver.client.post(
        "/webhooks/alertmanager", data=body(), headers={"Content-Type": "application/json"}
    )
    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    receiver.sender.assert_not_awaited()
    allowed = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert allowed.status == HTTPStatus.ACCEPTED


@pytest.mark.parametrize("webhook_module_id", [None])
async def test_webhook_uses_module_registration_discovered_after_listener_start(receiver, payload):
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE
    adapter = receiver.module_adapter
    adapter.contracts.staking_router.functions.getStakingModules().call = AsyncMock(
        return_value=[(3, adapter.addresses.module)]
    )
    await adapter.refresh_staking_module_id()
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(2)
    assert receiver.sender.await_count == 2


async def test_metrics_database_failure_does_not_reject_committed_webhook(
    receiver, payload, monkeypatch
):
    async def unavailable(_self):
        raise OperationalError("queue metrics", {}, Exception("temporary read failure"))

    monkeypatch.setattr(
        "sentinel.app.alertmanager_storage.AlertmanagerOutbox.queue_state", unavailable
    )
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(2)
    # The worker must continue after its own post-delivery metrics refresh fails, too.
    payload["alerts"][0]["startsAt"] = "2026-10-30T10:00:00Z"
    response = await receiver.client.post("/webhooks/alertmanager", json=payload)
    assert response.status == HTTPStatus.ACCEPTED
    await receiver.wait_for_messages(4)
