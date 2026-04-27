import asyncio
import pytest
from types import SimpleNamespace

from sentinel.config import clear_config, get_config_async, set_config
from sentinel.texts import (
    bond_debt_covered,
    bond_debt_increased,
    custom_rewards_claimer_set,
    expired_bond_lock_removed,
    fee_splits_set,
    key_allocated_balance_changed,
    target_validators_count_changed,
    validator_slashing_reported,
)
from hexbytes import HexBytes


class _DummyConnectProvider:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class _FakeFetcher:
    def __init__(self, result=None, exc: Exception | None = None):
        self.result = result
        self.exc = exc
        self.calls: list[str] = []

    async def __call__(self, log_cid: str):
        self.calls.append(log_cid)
        if self.exc is not None:
            raise self.exc
        return self.result


def test_event_mappings_are_complete():
    from sentinel.main import _assert_event_mappings

    _assert_event_mappings()


def test_new_v3_message_templates_render_core_fields():
    assert "Bond debt increased" in bond_debt_increased("1 ether")
    assert "Debt increase: `1 ether`" in bond_debt_increased("1 ether")

    assert "Bond debt covered" in bond_debt_covered("2 ether")
    assert "Covered amount: `2 ether`" in bond_debt_covered("2 ether")

    assert "Custom rewards claimer changed" in custom_rewards_claimer_set("0x123")
    assert "Rewards claimer: `0x123`" in custom_rewards_claimer_set("0x123")

    assert "Custom rewards claimer removed" in custom_rewards_claimer_set(
        "0x0000000000000000000000000000000000000000"
    )

    assert "Expired bond lock removed" in expired_bond_lock_removed()
    assert "Key allocated balance changed" in key_allocated_balance_changed(7, "3 ether")
    assert "Key index: `7`" in key_allocated_balance_changed(7, "3 ether")
    assert "New allocated balance: `3 ether`" in key_allocated_balance_changed(7, "3 ether")


def test_validator_slashing_reported_template_renders_pubkey_link():
    message = validator_slashing_reported(
        "0x1234",
        "https://beaconcha.in/validator/0x1234",
        7,
    )

    assert "Validator slashing reported" in message
    assert "[0x1234](https://beaconcha.in/validator/0x1234)" in message
    assert "Key index: `7`" in message


def test_fee_splits_set_template_renders_fee_split_entries():
    set_config(SimpleNamespace(module_ui_url="https://csm.lido.fi"))
    try:
        message = fee_splits_set(
            [
                {"recipient": "0x111", "share": 7000},
                SimpleNamespace(recipient="0x222", share=3000),
            ]
        )
    finally:
        clear_config()

    assert "Fee splits changed" in message
    assert "0x111: 7000" in message
    assert "0x222: 3000" in message
    assert "[CSM UI](https://csm.lido.fi)" in message


def test_limit_set_mode_1():
    result = target_validators_count_changed(0, 0, 1, 10)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to 10\."
        "\n"
        r"10 keys will be requested to exit first\."
    )
    assert result == expected


def test_limit_set_mode_2():
    result = target_validators_count_changed(0, 0, 2, 10)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to 10\."
        "\n"
        r"10 keys will be requested to exit immediately\."
    )
    assert result == expected


def test_limit_set_mode_2_from_1():
    result = target_validators_count_changed(1, 5, 2, 10)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to 10\."
        "\n"
        r"10 keys will be requested to exit immediately\."
    )
    assert result == expected


def test_limit_set_mode_1_from_2():
    result = target_validators_count_changed(2, 5, 1, 10)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to 10\."
        "\n"
        r"10 keys will be requested to exit first\."
    )
    assert result == expected


def test_limit_decreased_mode_1():
    result = target_validators_count_changed(1, 10, 1, 3)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been decreased from 10 to 3\."
        "\n"
        r"7 more key\(s\) will be requested to exit first\."
    )
    assert result == expected


def test_limit_decreased_mode_2():
    result = target_validators_count_changed(2, 10, 2, 3)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been decreased from 10 to 3\."
        "\n"
        r"7 more key\(s\) will be requested to exit immediately\."
    )
    assert result == expected


def test_limit_to_zero_exit_first():
    result = target_validators_count_changed(1, 10, 1, 0)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to zero\."
        "\n"
        r"All keys will be requested to exit first\."
    )
    assert result == expected


def test_limit_to_zero_exit_immediately():
    result = target_validators_count_changed(2, 10, 2, 0)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to zero\."
        "\n"
        r"All keys will be requested to exit immediately\."
    )
    assert result == expected


def test_limit_to_zero_exit_first_no_previous_limit():
    result = target_validators_count_changed(0, 0, 1, 0)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to zero\."
        "\n"
        r"All keys will be requested to exit first\."
    )
    assert result == expected


def test_limit_to_zero_exit_immediately_no_previous_limit():
    result = target_validators_count_changed(0, 0, 2, 0)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to zero\."
        "\n"
        r"All keys will be requested to exit immediately\."
    )
    assert result == expected


def test_limit_unset_mode_zero():
    result = target_validators_count_changed(1, 10, 0, 0)
    expected = (
        "🚨 *Target validators count changed*\n\n"
        r"The limit has been set to zero\. No keys will be requested to exit\."
    )
    assert result == expected


@pytest.fixture(autouse=True)
def _clear_alru_cache():
    """Reset the alru_cache on _fetch_distribution_log between tests.

    async_lru ≥ 2.2 enforces single-loop usage per cache instance. Since
    pytest-asyncio creates a new event loop per test, we must also reset the
    internal loop binding alongside the cached entries.
    """
    from sentinel.events import EventMessages

    def _reset():
        instance_method = EventMessages._fetch_distribution_log
        instance_method.cache_clear()
        # Reach through to the underlying _LRUCacheWrapper and clear the
        # event-loop binding so the next test can attach its own loop.
        inner = instance_method._LRUCacheWrapperInstanceMethod__wrapper
        inner._LRUCacheWrapper__first_loop = None

    _reset()
    yield
    _reset()


@pytest.mark.asyncio
async def test_fetch_distribution_log_success():
    from sentinel.events import EventMessages

    event_messages = EventMessages.__new__(EventMessages)
    fetcher = _FakeFetcher(result={"operators": {"123": {}}})
    event_messages._distribution_log_fetcher = fetcher

    data = await event_messages._fetch_distribution_log("QmCID")

    assert data == {"operators": {"123": {}}}
    assert fetcher.calls == ["QmCID"]


@pytest.mark.asyncio
async def test_fetch_distribution_log_caches():
    from sentinel.events import EventMessages

    event_messages = EventMessages.__new__(EventMessages)
    fetcher = _FakeFetcher(result={"operators": {}})
    event_messages._distribution_log_fetcher = fetcher

    await event_messages._fetch_distribution_log("QmCID")
    await event_messages._fetch_distribution_log("QmCID")

    assert fetcher.calls == ["QmCID"]


@pytest.mark.asyncio
async def test_fetch_distribution_log_handles_error():
    from sentinel.events import EventMessages

    event_messages = EventMessages.__new__(EventMessages)
    event_messages._distribution_log_fetcher = _FakeFetcher(exc=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await event_messages._fetch_distribution_log("QmCID")


@pytest.mark.asyncio
async def test_fetch_distribution_log_requires_cid():
    from sentinel.events import EventMessages

    event_messages = EventMessages.__new__(EventMessages)

    with pytest.raises(ValueError):
        await event_messages._fetch_distribution_log(None)


@pytest.mark.asyncio
async def test_fetch_distribution_log_handles_timeout():
    from sentinel.events import EventMessages

    event_messages = EventMessages.__new__(EventMessages)
    event_messages._distribution_log_fetcher = _FakeFetcher(exc=asyncio.TimeoutError("timeout"))

    with pytest.raises(asyncio.TimeoutError):
        await event_messages._fetch_distribution_log("QmCID")


@pytest.mark.asyncio
async def test_distribution_log_updated_produces_strike_notifications():
    from sentinel.events import EventMessages, NotificationPlan
    from sentinel.models import Event
    import sentinel.texts as texts

    set_config(
        SimpleNamespace(
            etherscan_tx_url_template="https://etherscan.io/tx/{}",
            module_ui_url="https://csm.lido.fi",
        )
    )
    event_messages = EventMessages.__new__(EventMessages)
    event_messages.cfg = await get_config_async()

    payload = [
        {
            "operators": {
                "42": {
                    "validators": {
                        "123": {"strikes": 0},
                        "124": {"strikes": 2},
                    }
                },
                "777": {"validators": {"900": {"strikes": 0}}},
            }
        }
    ]

    fetch_calls: list[str | None] = []

    async def fake_fetch(log_cid):
        fetch_calls.append(log_cid)
        return payload

    event_messages._distribution_log_fetcher = fake_fetch

    event = Event(
        event="DistributionLogUpdated",
        args={"logCid": "cid123"},
        block=123,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    plan = await EventMessages.distribution_log_updated(event_messages, event)

    assert isinstance(plan, NotificationPlan)
    assert plan.broadcast_node_operator_ids == {"42", "777"}

    expected_base = texts.distribution_data_updated()
    expected_foot = event_messages.footer(event)
    assert plan.broadcast == f"{expected_base}{expected_foot}"

    assert "42" in plan.per_node_operator
    operator_message = plan.per_node_operator["42"]
    assert expected_base in operator_message
    assert "⚠️" in operator_message
    assert "Validators with strikes: `1`" in operator_message
    assert operator_message.endswith(expected_foot)

    assert "777" not in plan.per_node_operator
    assert fetch_calls == ["cid123"]


@pytest.mark.asyncio
async def test_distribution_log_updated_handles_empty_payload():
    from sentinel.events import EventMessages, NotificationPlan
    from sentinel.models import Event
    import sentinel.texts as texts

    set_config(
        SimpleNamespace(
            etherscan_tx_url_template="https://etherscan.io/tx/{}",
            module_ui_url="https://csm.lido.fi",
        )
    )
    event_messages = EventMessages.__new__(EventMessages)
    event_messages.cfg = await get_config_async()
    event_messages._distribution_log_fetcher = _FakeFetcher(result={})

    event = Event(
        event="DistributionLogUpdated",
        args={"logCid": "cid123"},
        block=123,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    plan = await EventMessages.distribution_log_updated(event_messages, event)

    assert isinstance(plan, NotificationPlan)
    assert plan.per_node_operator == {}
    assert plan.broadcast_node_operator_ids is None
    expected_base = texts.distribution_data_updated()
    expected_foot = event_messages.footer(event)
    assert plan.broadcast == f"{expected_base}{expected_foot}"


@pytest.mark.asyncio
async def test_get_notification_plan_skips_disallowed_event():
    from sentinel.events import EventMessages
    from sentinel.models import Event

    class DummyAdapter:
        def catalog_events(self):
            return set()

        def notifiable_events(self):
            return set()

        async def event_enricher(self, event, messages):
            return None

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.module_adapter = DummyAdapter()

    event = Event(
        event="DepositedSigningKeysCountChanged",
        args={"nodeOperatorId": 321, "depositedKeysCount": 1},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    plan = await EventMessages.get_notification_plan(event_messages, event)

    assert plan is None


@pytest.mark.asyncio
async def test_get_notification_plan_sets_node_operator_target():
    from sentinel.events import EventMessages, NotificationPlan
    from sentinel.models import Event

    class DummyAdapter:
        def catalog_events(self):
            return {"DepositedSigningKeysCountChanged"}

        def notifiable_events(self):
            return {"DepositedSigningKeysCountChanged"}

        async def event_enricher(self, event, messages):
            return None

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.connectProvider = _DummyConnectProvider()
    event_messages.cfg = SimpleNamespace(etherscan_tx_url_template="https://etherscan.io/tx/{}")
    event_messages.footer = EventMessages.footer.__get__(event_messages)
    event_messages.module_adapter = DummyAdapter()

    event = Event(
        event="DepositedSigningKeysCountChanged",
        args={"nodeOperatorId": 321, "depositedKeysCount": 1},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    plan = await EventMessages.get_notification_plan(event_messages, event)

    assert isinstance(plan, NotificationPlan)
    assert plan.broadcast_node_operator_ids == {"321"}
    assert plan.broadcast is not None


@pytest.mark.asyncio
async def test_get_notification_plan_uses_adapter_override():
    from sentinel.events import EventMessages, NotificationPlan
    from sentinel.models import Event

    class DummyAdapter:
        def catalog_events(self):
            return {"BondCurveSet"}

        def notifiable_events(self):
            return {"BondCurveSet"}

        async def event_enricher(self, event, messages):
            if event.event == "BondCurveSet":
                return "override"
            return None

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.connectProvider = _DummyConnectProvider()
    event_messages.module_adapter = DummyAdapter()

    event = Event(
        event="BondCurveSet",
        args={"curveId": 1},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    plan = await EventMessages.get_notification_plan(event_messages, event)

    assert isinstance(plan, NotificationPlan)
    assert plan.broadcast == "override"


def test_subscription_decodes_v2_and_v3_transition_events():
    from web3 import AsyncWeb3

    from sentinel.app.health import HealthState
    from sentinel.models import get_contract_abis
    from sentinel.rpc import Subscription
    from sentinel.texts import COMMUNITY_CATALOG_EVENTS_BY_VERSION

    class ProbeSubscription(Subscription):
        async def process_event_log(self, event):
            raise AssertionError("not used")

        async def process_new_block(self, block):
            raise AssertionError("not used")

    set_config(
        SimpleNamespace(
            csm_version=2,
            process_blocks_requests_per_second=None,
        )
    )
    try:
        subscription = ProbeSubscription(
            AsyncWeb3(),
            health=HealthState(),
            contract_abis=get_contract_abis(2),
        )
        assert "Initialized" not in COMMUNITY_CATALOG_EVENTS_BY_VERSION[2]
        decoded_event_names = {event_abi["name"] for event_abi in subscription.abi_by_topics.values()}
        assert "Initialized" in decoded_event_names
        assert "ELRewardsStealingPenaltyReported" in decoded_event_names
        assert "ValidatorSlashingReported" in decoded_event_names
    finally:
        clear_config()


def test_topics_to_follow_deduplicates_compatible_v2_v3_topics():
    from sentinel.rpc import topics_to_follow

    v2_event = {
        "type": "event",
        "name": "ValidatorExitDelayProcessed",
        "inputs": [
            {"name": "nodeOperatorId", "type": "uint256", "indexed": True},
            {"name": "pubkey", "type": "bytes", "indexed": False},
            {"name": "delayPenalty", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    }
    v3_event = {
        "type": "event",
        "name": "ValidatorExitDelayProcessed",
        "inputs": [
            {"name": "nodeOperatorId", "type": "uint256", "indexed": True},
            {"name": "pubkey", "type": "bytes", "indexed": False},
            {"name": "delayFee", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    }

    topics = topics_to_follow({"ValidatorExitDelayProcessed"}, [v2_event], [v3_event])

    assert len(topics) == 1
    [event_abi] = topics.values()
    assert event_abi["inputs"][2]["name"] == "delayPenalty"


def test_topics_to_follow_rejects_incompatible_same_topic_abis():
    from sentinel.rpc import topics_to_follow

    indexed_event = {
        "type": "event",
        "name": "SameTopic",
        "inputs": [{"name": "value", "type": "uint256", "indexed": True}],
        "anonymous": False,
    }
    non_indexed_event = {
        "type": "event",
        "name": "SameTopic",
        "inputs": [{"name": "value", "type": "uint256", "indexed": False}],
        "anonymous": False,
    }

    with pytest.raises(RuntimeError, match="incompatible ABI inputs"):
        topics_to_follow({"SameTopic"}, [indexed_event], [non_indexed_event])


@pytest.mark.asyncio
async def test_initialized_control_event_switches_runtime_to_v3():
    from sentinel.events import EventMessages, NotificationPlan
    from sentinel.models import Event

    switched_versions: list[int] = []

    class DummyAdapter:
        csm_version = 2

        def catalog_events(self):
            return set()

        def notifiable_events(self):
            return {"Initialized"}

        async def event_enricher(self, event, messages):
            return None

    async def switch_csm_version(csm_version: int) -> None:
        switched_versions.append(csm_version)

    set_config(SimpleNamespace(module_ui_url="https://csm.lido.fi"))
    try:
        event_messages = EventMessages.__new__(EventMessages)
        event_messages.connectProvider = _DummyConnectProvider()
        event_messages.cfg = SimpleNamespace(etherscan_tx_url_template="https://etherscan.io/tx/{}")
        event_messages.footer = EventMessages.footer.__get__(event_messages)
        event_messages.module_adapter = DummyAdapter()
        event_messages.module_address = "0x0000000000000000000000000000000000000abc"
        event_messages._csm_version_switcher = switch_csm_version

        event = Event(
            event="Initialized",
            args={"version": 3},
            block=1,
            tx=HexBytes("0xdeadbeef"),
            address="0x0000000000000000000000000000000000000abc",
        )

        plan = await EventMessages.get_notification_plan(event_messages, event)

        assert isinstance(plan, NotificationPlan)
        assert "CSM v3 is live" in plan.broadcast
        assert switched_versions == [3]
    finally:
        clear_config()


@pytest.mark.asyncio
async def test_get_notification_plan_allows_v2_historical_event_with_v3_adapter():
    from sentinel.events import EventMessages, NotificationPlan
    from sentinel.models import Event
    from sentinel.texts import COMMUNITY_NOTIFIABLE_EVENTS

    class DummyAdapter:
        csm_version = 3

        def catalog_events(self):
            return {"Initialized"}

        def notifiable_events(self):
            return COMMUNITY_NOTIFIABLE_EVENTS

        async def event_enricher(self, event, messages):
            return None

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.connectProvider = _DummyConnectProvider()
    event_messages.w3 = SimpleNamespace(to_hex=lambda value: "0x" + value.hex())
    event_messages.cfg = SimpleNamespace(
        etherscan_block_url_template="https://etherscan.io/block/{}",
        etherscan_tx_url_template="https://etherscan.io/tx/{}",
    )
    event_messages.footer = EventMessages.footer.__get__(event_messages)
    event_messages.module_adapter = DummyAdapter()

    event = Event(
        event="ELRewardsStealingPenaltyReported",
        args={
            "nodeOperatorId": 321,
            "stolenAmount": 10**18,
            "proposedBlockHash": HexBytes("0x" + "12" * 32),
        },
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    plan = await EventMessages.get_notification_plan(event_messages, event)

    assert isinstance(plan, NotificationPlan)
    assert plan.broadcast_node_operator_ids == {"321"}
    assert "Penalty for stealing EL rewards reported" in plan.broadcast


@pytest.mark.asyncio
async def test_validator_slashing_reported_handler_formats_pubkey_and_footer():
    from sentinel.events import EventMessages
    from sentinel.models import Event

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.w3 = SimpleNamespace(to_hex=lambda value: "0x" + value.hex())
    event_messages.cfg = SimpleNamespace(
        beaconchain_url_template="https://beaconcha.in/validator/{}",
        etherscan_tx_url_template="https://etherscan.io/tx/{}",
    )
    event_messages.footer = EventMessages.footer.__get__(event_messages)

    event = Event(
        event="ValidatorSlashingReported",
        args={"nodeOperatorId": 42, "keyIndex": 7, "pubkey": bytes.fromhex("1234")},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    message = await EventMessages.validator_slashing_reported(event_messages, event)

    assert "Validator slashing reported" in message
    assert "[0x1234](https://beaconcha.in/validator/0x1234)" in message
    assert "Key index: `7`" in message
    assert "nodeOperatorId: 42" in message
    assert "[Transaction](https://etherscan.io/tx/0xdeadbeef)" in message


@pytest.mark.asyncio
async def test_validator_exit_delay_processed_accepts_v3_delay_fee_arg():
    from sentinel.events import EventMessages
    from sentinel.models import Event

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.w3 = SimpleNamespace(to_hex=lambda value: "0x" + value.hex())
    event_messages.cfg = SimpleNamespace(
        beaconchain_url_template="https://beaconcha.in/validator/{}",
        etherscan_tx_url_template="https://etherscan.io/tx/{}",
    )
    event_messages.footer = EventMessages.footer.__get__(event_messages)

    event = Event(
        event="ValidatorExitDelayProcessed",
        args={"nodeOperatorId": 42, "pubkey": bytes.fromhex("1234"), "delayFee": 10**18},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    message = await EventMessages.validator_exit_delay_processed(event_messages, event)

    assert "Validator exit delay processed" in message
    assert "[0x1234](https://beaconcha.in/validator/0x1234)" in message
    assert "Delay penalty: `1 ether`" in message


@pytest.mark.asyncio
async def test_validator_exit_delay_processed_keeps_v2_delay_penalty_arg():
    from sentinel.events import EventMessages
    from sentinel.models import Event

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.w3 = SimpleNamespace(to_hex=lambda value: "0x" + value.hex())
    event_messages.cfg = SimpleNamespace(
        beaconchain_url_template="https://beaconcha.in/validator/{}",
        etherscan_tx_url_template="https://etherscan.io/tx/{}",
    )
    event_messages.footer = EventMessages.footer.__get__(event_messages)

    event = Event(
        event="ValidatorExitDelayProcessed",
        args={"nodeOperatorId": 42, "pubkey": bytes.fromhex("1234"), "delayPenalty": 10**18},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    message = await EventMessages.validator_exit_delay_processed(event_messages, event)

    assert "Validator exit delay processed" in message
    assert "[0x1234](https://beaconcha.in/validator/0x1234)" in message
    assert "Delay penalty: `1 ether`" in message


@pytest.mark.asyncio
async def test_key_allocated_balance_changed_handler_humanizes_balance():
    from sentinel.events import EventMessages
    from sentinel.models import Event

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.cfg = SimpleNamespace(
        etherscan_tx_url_template="https://etherscan.io/tx/{}",
    )
    event_messages.footer = EventMessages.footer.__get__(event_messages)

    event = Event(
        event="KeyAllocatedBalanceChanged",
        args={"nodeOperatorId": 42, "keyIndex": 7, "newTotal": 10**18},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000000",
    )

    message = await EventMessages.key_allocated_balance_changed(event_messages, event)

    assert "Key allocated balance changed" in message
    assert "Key index: `7`" in message
    assert "New allocated balance: `1 ether`" in message
    assert "nodeOperatorId: 42" in message


@pytest.mark.asyncio
async def test_initialized_event_only_emits_for_v3_module():
    from sentinel.events import EventMessages
    from sentinel.models import Event

    class DummyAdapter:
        csm_version = 3

        def catalog_events(self):
            return {"Initialized"}

        def notifiable_events(self):
            return {"Initialized"}

        async def event_enricher(self, event, messages):
            return None

    set_config(SimpleNamespace(module_ui_url="https://csm.lido.fi"))

    event_messages = EventMessages.__new__(EventMessages)
    event_messages.connectProvider = _DummyConnectProvider()
    event_messages.cfg = SimpleNamespace(etherscan_tx_url_template="https://etherscan.io/tx/{}")
    event_messages.footer = EventMessages.footer.__get__(event_messages)
    event_messages.module_adapter = DummyAdapter()
    event_messages.module_address = "0x0000000000000000000000000000000000000abc"

    ignored_v2_event = Event(
        event="Initialized",
        args={"version": 2},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000abc",
    )
    emitted_v3_event = Event(
        event="Initialized",
        args={"version": 3},
        block=1,
        tx=HexBytes("0xdeadbeef"),
        address="0x0000000000000000000000000000000000000abc",
    )

    assert await EventMessages.get_notification_plan(event_messages, ignored_v2_event) is None

    plan = await EventMessages.get_notification_plan(event_messages, emitted_v3_event)

    assert plan is not None
    assert "CSM v3 is live" in plan.broadcast
