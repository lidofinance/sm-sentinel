import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

from hexbytes import HexBytes
import pytest
import web3.exceptions
from web3.types import FilterParams

from sentinel.chain import ConnectOnDemand
from sentinel.config import clear_config


def test_event_readable_string():
    from sentinel.models import Event

    event = Event(
        event="TestEvent",
        args={"a": 1, "b": 2},
        block=100,
        tx=HexBytes("0x" + "00" * 32),
        address="0x0000000000000000000000000000000000000000",
    )
    s = event.readable()
    assert s.startswith("TestEvent(")
    assert "a=1" in s and "b=2" in s


def test_main_subscription_helpers_counts():
    from sentinel.handlers.utils import get_active_subscription_counts, get_subscription_totals
    from sentinel.app.storage import BotStorage

    bot_data = {
        "user_ids": {1},
        "group_ids": {2},
        "channel_ids": {3},
        "no_ids_to_chats": {
            "10": {1, 2},  # one user, one group
            "20": {2, 4},  # one group, one inactive
        },
    }

    storage = BotStorage(bot_data)
    counts = get_active_subscription_counts(storage)
    assert counts["10"]["total"] == 2
    assert counts["10"]["users"] == 1
    assert counts["10"]["groups"] == 1
    assert counts["10"]["channels"] == 0

    assert counts["20"]["total"] == 1
    assert counts["20"]["users"] == 0
    assert counts["20"]["groups"] == 1
    assert counts["20"]["channels"] == 0

    subscribers, node_operators = get_subscription_totals(storage)
    assert subscribers == 2  # chat ids 1 and 2 are active across all NOs
    assert node_operators == 2


def test_main_resolve_target_chats():
    from sentinel.handlers.utils import resolve_target_chats_for_node_operators
    from sentinel.app.storage import BotStorage

    bot_data = {
        "user_ids": {1},
        "group_ids": {2},
        "channel_ids": {3},
        "no_ids_to_chats": {
            "10": {1, 2},
            "20": {2, 4},
        },
    }
    storage = BotStorage(bot_data)
    targets = resolve_target_chats_for_node_operators(storage, {"10", "20"})
    assert targets == {1, 2}


def test_texts_manager_address_change_proposed_messages():
    from web3.constants import ADDRESS_ZERO
    from sentinel.modules.community.texts import node_operator_manager_address_change_proposed

    msg_revoked = node_operator_manager_address_change_proposed(ADDRESS_ZERO)
    assert "revoked" in msg_revoked

    msg_proposed = node_operator_manager_address_change_proposed("0x123")
    assert "New manager address proposed" in msg_proposed


@patch.dict(
    os.environ,
    {
        "ETHERSCAN_URL": "https://etherscan.io",
        "BEACONCHAIN_URL": "https://beaconcha.in",
        "ADMIN_IDS": "1, 2 3,invalid,4",
        "BLOCK_BATCH_SIZE": "12345",
        "PROCESS_BLOCKS_REQUESTS_PER_SECOND": "3.5",
        "BLOCK_FROM": "789",
        "WEB3_SOCKET_PROVIDER": "wss://example.invalid",
        "MODULE_ADDRESS": "0x0000000000000000000000000000000000000001",
    },
    clear=True,
)
def test_config_parsing_and_templates(monkeypatch, stub_discover_contract_addresses):
    from sentinel.config import get_config

    clear_config()
    cfg = get_config()

    assert cfg.admin_ids == {1, 2, 3, 4}
    assert cfg.block_batch_size == 12345
    assert cfg.process_blocks_requests_per_second == 3.5
    assert cfg.block_from == 789
    assert cfg.etherscan_block_url_template == "https://etherscan.io/block/{}"
    assert cfg.etherscan_tx_url_template == "https://etherscan.io/tx/{}"
    assert cfg.beaconchain_url_template == "https://beaconcha.in/validator/{}"
    clear_config()


@pytest.mark.asyncio
@patch.dict(
    os.environ,
    {
        "WEB3_SOCKET_PROVIDER": "wss://example.invalid",
        "MODULE_ADDRESS": "0x0000000000000000000000000000000000000001",
        "PROCESS_BLOCKS_REQUESTS_PER_SECOND": "2",
    },
    clear=True,
)
async def test_process_blocks_rate_limit(monkeypatch, stub_discover_contract_addresses):
    from sentinel.app.module_adapter import build_module_adapter_from_config
    from sentinel.app.health import HealthState
    from sentinel.config import get_config_async
    from sentinel.rpc import Subscription

    class DummyEth:
        def contract(self, **kwargs):
            return SimpleNamespace(**kwargs)

    class DummyW3:
        provider = None
        eth = DummyEth()

    clear_config()
    cfg = await get_config_async()
    w3 = DummyW3()
    module_adapter = build_module_adapter_from_config(cfg, w3, ConnectOnDemand(w3))
    subscription = Subscription(
        w3,
        health=HealthState(),
        module_adapter=module_adapter,
    )
    try:
        start = asyncio.get_running_loop().time()
        await subscription._throttle_process_blocks_request()
        await subscription._throttle_process_blocks_request()
        elapsed = asyncio.get_running_loop().time() - start
        assert elapsed >= 0.45
    finally:
        clear_config()


@pytest.mark.asyncio
async def test_get_block_number_uses_persistent_provider():
    from sentinel.rpc import Subscription

    main_w3 = SimpleNamespace(
        provider=SimpleNamespace(
            is_connected=AsyncMock(return_value=True),
            connect=AsyncMock(),
        ),
        eth=SimpleNamespace(get_block_number=AsyncMock(return_value=111)),
    )
    backfill_w3 = SimpleNamespace(
        provider=SimpleNamespace(
            is_connected=AsyncMock(return_value=True),
            connect=AsyncMock(),
        ),
        eth=SimpleNamespace(get_block_number=AsyncMock(return_value=222)),
    )

    subscription = Subscription.__new__(Subscription)
    subscription._w3 = main_w3
    subscription._backfill_w3 = backfill_w3

    latest = await subscription.get_block_number()

    assert latest == 111
    main_w3.eth.get_block_number.assert_awaited_once()
    backfill_w3.eth.get_block_number.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_blocks_from_uses_event_source_filters():
    from sentinel.models import Block, Event
    from sentinel.modules.base import EventSource
    from sentinel.rpc import Subscription

    topic = HexBytes("0x" + "01" * 32)

    class ProbeSubscription(Subscription):
        async def process_event_log(self, event: Event):
            self.events.append(event)

        async def process_new_block(self, block: Block):
            self.blocks.append(block.number)

    subscription = ProbeSubscription.__new__(ProbeSubscription)
    subscription._backfill_w3 = SimpleNamespace(
        provider=SimpleNamespace(
            is_connected=AsyncMock(return_value=True),
            connect=AsyncMock(),
        ),
        eth=SimpleNamespace(),
    )
    subscription.cfg = SimpleNamespace(block_batch_size=1000)
    subscription.event_sources = (
        EventSource(
            "scoped",
            "0x0000000000000000000000000000000000000001",
            frozenset({"ScopedEvent"}),
            lambda event: event.args["keep"],
        ),
    )
    subscription.abi_by_topics = {topic: {"name": "ScopedEvent"}}
    subscription._shutdown_event = asyncio.Event()
    subscription._process_blocks_request_interval = None
    subscription._health = SimpleNamespace(mark_progress=lambda: None)
    subscription.events = []
    subscription.blocks = []
    subscription._get_logs_with_retry = AsyncMock(
        return_value=[{"topics": [topic]}, {"topics": [topic]}]
    )

    decoded_events = [
        Event(
            event="ScopedEvent",
            args={"keep": False},
            block=1,
            tx=HexBytes("0xdeadbeef"),
            address="0x0000000000000000000000000000000000000001",
        ),
        Event(
            event="ScopedEvent",
            args={"keep": True},
            block=1,
            tx=HexBytes("0xdeadbeef"),
            address="0x0000000000000000000000000000000000000001",
        ),
    ]
    subscription._decode_event = lambda w3, event_abi, log: decoded_events.pop(0)

    await subscription.process_blocks_from(1, 2)

    filter_params = subscription._get_logs_with_retry.await_args.kwargs["filter_params"]
    assert filter_params["address"] == "0x0000000000000000000000000000000000000001"
    assert filter_params["topics"] == [topic]
    assert [event.args["keep"] for event in subscription.events] == [True]
    assert subscription.blocks == [2]


@pytest.mark.asyncio
@patch.dict(
    os.environ,
    {
        "WEB3_SOCKET_PROVIDER": "wss://example.invalid",
        "MODULE_ADDRESS": "0x0000000000000000000000000000000000000001",
    },
    clear=True,
)
async def test_get_logs_with_retry_recovers_from_rate_limit(
    monkeypatch,
    stub_discover_contract_addresses,
):
    from sentinel.app.module_adapter import build_module_adapter_from_config
    from sentinel.config import get_config_async
    from sentinel.app.health import HealthState
    from sentinel.rpc import Subscription

    class DummyEth:
        def contract(self, **kwargs):
            return SimpleNamespace(**kwargs)

    class DummyW3:
        provider = None
        eth = DummyEth()

    clear_config()
    cfg = await get_config_async()
    w3 = DummyW3()
    module_adapter = build_module_adapter_from_config(cfg, w3, ConnectOnDemand(w3))

    subscription = Subscription(
        w3,
        health=HealthState(),
        module_adapter=module_adapter,
    )
    rate_limit_error = web3.exceptions.Web3RPCError(
        message="{'code': 429, 'message': 'throughput exceeded'}",
        rpc_response={"error": {"code": 429, "message": "throughput exceeded"}},
    )
    rpc_w3 = SimpleNamespace(
        eth=SimpleNamespace(
            get_logs=AsyncMock(side_effect=[rate_limit_error, []]),
        ),
    )
    monkeypatch.setattr("sentinel.rpc.BACKFILL_GET_LOGS_RETRY_INITIAL_DELAY_SECONDS", 0)
    monkeypatch.setattr("sentinel.rpc.BACKFILL_GET_LOGS_RETRY_MAX_DELAY_SECONDS", 0)

    logs = await subscription._get_logs_with_retry(
        w3=rpc_w3,
        filter_params=FilterParams(fromBlock=1, toBlock=1, address="0x1"),
        contract="0x1",
        batch_start=1,
        batch_end=1,
    )

    assert logs == []
    assert rpc_w3.eth.get_logs.await_count == 2
    assert subscription._shutdown_event.is_set() is False
    clear_config()


@pytest.mark.asyncio
@patch.dict(
    os.environ,
    {
        "WEB3_SOCKET_PROVIDER": "wss://example.invalid",
        "MODULE_ADDRESS": "0x0000000000000000000000000000000000000001",
    },
    clear=True,
)
async def test_get_logs_with_retry_raises_non_retryable_errors(
    monkeypatch,
    stub_discover_contract_addresses,
):
    from sentinel.app.module_adapter import build_module_adapter_from_config
    from sentinel.config import get_config_async
    from sentinel.app.health import HealthState
    from sentinel.rpc import Subscription

    class DummyEth:
        def contract(self, **kwargs):
            return SimpleNamespace(**kwargs)

    class DummyW3:
        provider = None
        eth = DummyEth()

    clear_config()
    cfg = await get_config_async()
    w3 = DummyW3()
    module_adapter = build_module_adapter_from_config(cfg, w3, ConnectOnDemand(w3))

    subscription = Subscription(
        w3,
        health=HealthState(),
        module_adapter=module_adapter,
    )
    fatal_error = web3.exceptions.Web3RPCError(
        message="execution reverted",
        rpc_response={"error": {"code": 3, "message": "execution reverted"}},
    )
    rpc_w3 = SimpleNamespace(
        eth=SimpleNamespace(
            get_logs=AsyncMock(side_effect=fatal_error),
        ),
    )
    monkeypatch.setattr("sentinel.rpc.BACKFILL_GET_LOGS_RETRY_INITIAL_DELAY_SECONDS", 0)
    monkeypatch.setattr("sentinel.rpc.BACKFILL_GET_LOGS_RETRY_MAX_DELAY_SECONDS", 0)

    with pytest.raises(web3.exceptions.Web3RPCError):
        await subscription._get_logs_with_retry(
            w3=rpc_w3,
            filter_params=FilterParams(fromBlock=1, toBlock=1, address="0x1"),
            contract="0x1",
            batch_start=1,
            batch_end=1,
        )

    assert rpc_w3.eth.get_logs.await_count == 1
    clear_config()
