from types import SimpleNamespace
from unittest.mock import AsyncMock

from hexbytes import HexBytes
import pytest

from sentinel.app.health import HealthState
from sentinel.config import Config, clear_config, set_config
from sentinel.module_types import ModuleType
from sentinel.app.storage import BotStorage
from sentinel.models import Block, Event
from sentinel.services.subscription import TelegramSubscription


class _FakeEth:
    def contract(self, **kwargs):
        return SimpleNamespace(**kwargs)


class _FakeW3:
    eth = _FakeEth()


class _FakeEventMessages:
    def __init__(self, w3):
        self.w3 = w3
        self.cfg = None
        self.module_adapter = None

    def reconfigure(self, module_adapter):
        self.module_adapter = module_adapter


def _make_config(csm_version: int) -> Config:
    return Config(
        filestorage_path=".storage",
        token="token",
        web3_socket_provider="wss://example.invalid",
        healthcheck_host="0.0.0.0",
        healthcheck_port=8080,
        module_address="0x0000000000000000000000000000000000000001",
        accounting_address="0x0000000000000000000000000000000000000002",
        parameters_registry_address="0x0000000000000000000000000000000000000003",
        vebo_address="0x0000000000000000000000000000000000000004",
        fee_distributor_address="0x0000000000000000000000000000000000000005",
        exit_penalties_address="0x0000000000000000000000000000000000000006",
        lido_locator_address="0x0000000000000000000000000000000000000007",
        staking_router_address="0x0000000000000000000000000000000000000008",
        staking_module_id=1,
        module_type=ModuleType.COMMUNITY,
        csm_version=csm_version,
        etherscan_url="https://etherscan.io",
        beaconchain_url="https://beaconcha.in",
        module_ui_url="https://csm.lido.fi",
        block_batch_size=10_000,
        process_blocks_requests_per_second=None,
        block_from=None,
        admin_ids=set(),
    )


def _make_event(block: int) -> Event:
    return Event(
        event="TestEvent",
        args={"nodeOperatorId": 1},
        block=block,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )


def _make_initialized_event(block: int = 1) -> Event:
    return Event(
        event="Initialized",
        args={"version": 3},
        block=block,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )


def _make_context(block: int) -> SimpleNamespace:
    bot_storage = BotStorage({"block": block, "user_ids": set(), "no_ids_to_chats": {}})
    return SimpleNamespace(bot_storage=bot_storage, bot=AsyncMock())


def _make_subscription(event_messages_return=None) -> TelegramSubscription:
    sub = TelegramSubscription.__new__(TelegramSubscription)
    sub.event_messages = SimpleNamespace(
        get_notification_plan=AsyncMock(return_value=event_messages_return),
    )
    return sub


@pytest.mark.asyncio
async def test_handle_csm_version_changed_rebinds_runtime_adapter_and_events():
    from sentinel.app.module_adapter import build_module_adapter_from_config
    from sentinel.models import get_contract_abis

    cfg = _make_config(csm_version=2)
    w3 = _FakeW3()
    set_config(cfg)
    try:
        module_adapter = build_module_adapter_from_config(cfg, w3)
        application = SimpleNamespace()
        runtime = SimpleNamespace(config=cfg, module_adapter=module_adapter)
        setattr(application, "_module_runtime", runtime)

        event_messages = _FakeEventMessages(w3)
        subscription = TelegramSubscription(
            w3,
            application,
            event_messages,
            health=HealthState(),
            contract_abis=get_contract_abis(2),
        )

        await subscription.handle_csm_version_changed(3)

        assert runtime.config.csm_version == 3
        assert runtime.module_adapter.csm_version == 3
        assert subscription.cfg.csm_version == 3
        assert event_messages.cfg.csm_version == 3
        assert event_messages.module_adapter is runtime.module_adapter
        assert "Initialized" in runtime.module_adapter.catalog_events()
        assert "ValidatorSlashingReported" in runtime.module_adapter.catalog_events()
        assert "ELRewardsStealingPenaltyReported" not in runtime.module_adapter.catalog_events()
    finally:
        clear_config()


@pytest.mark.asyncio
async def test_initialized_event_prepares_runtime_before_queueing_subscription_event():
    sub = TelegramSubscription.__new__(TelegramSubscription)
    sub.event_messages = SimpleNamespace(get_notification_plan=AsyncMock(return_value=None))
    sub.application = SimpleNamespace(update_queue=SimpleNamespace(put=AsyncMock()))
    sub._ignore_subscription_events_until_block = None

    event = _make_initialized_event()

    await sub.process_event_log_from_subscription(event)

    sub.event_messages.get_notification_plan.assert_awaited_once_with(event)
    sub.application.update_queue.put.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_handle_event_log_advances_persisted_block():
    sub = _make_subscription(event_messages_return=None)
    context = _make_context(block=100)

    await sub.handle_event_log(_make_event(block=200), context)

    assert context.bot_storage.block.value == 200


@pytest.mark.asyncio
async def test_handle_event_log_does_not_regress_persisted_block():
    sub = _make_subscription(event_messages_return=None)
    context = _make_context(block=500)

    await sub.handle_event_log(_make_event(block=300), context)

    assert context.bot_storage.block.value == 500


@pytest.mark.asyncio
async def test_handle_event_log_advances_block_with_notification_plan():
    plan = SimpleNamespace(
        per_node_operator={},
        broadcast=None,
        broadcast_node_operator_ids=None,
    )
    sub = _make_subscription(event_messages_return=plan)
    context = _make_context(block=100)

    await sub.handle_event_log(_make_event(block=200), context)

    assert context.bot_storage.block.value == 200


@pytest.mark.asyncio
async def test_process_new_block_advances_persisted_block():
    sub = TelegramSubscription.__new__(TelegramSubscription)
    sub.application = SimpleNamespace(bot_data={"block": 100})

    await sub.process_new_block(Block(number=200))

    assert BotStorage(sub.application.bot_data).block.value == 200


@pytest.mark.asyncio
async def test_process_new_block_does_not_regress_persisted_block():
    sub = TelegramSubscription.__new__(TelegramSubscription)
    sub.application = SimpleNamespace(bot_data={"block": 500})

    await sub.process_new_block(Block(number=300))

    assert BotStorage(sub.application.bot_data).block.value == 500
