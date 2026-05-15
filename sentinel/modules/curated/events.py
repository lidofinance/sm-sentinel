import datetime
from dataclasses import replace
from typing import TYPE_CHECKING

from eth_utils import humanize_wei

from sentinel.models import Event, EventHandler
from sentinel.modules.base_events import BaseModule, _format_date
from sentinel.modules.curated.adapter import CURATED_EVENTS
from sentinel.modules.curated.texts import (
    CURATED_EVENT_DESCRIPTIONS,
    CURATED_EVENT_MESSAGES,
)
from sentinel.modules.distribution import DistributionLogFetcher, default_distribution_log_fetcher
from sentinel.modules.formatting import read_field
from sentinel.modules.registry import RegisterEventHandler
from sentinel.notifications import NotificationPlan

if TYPE_CHECKING:
    from sentinel.modules.curated.adapter import CuratedModuleAdapter

CURATED_EVENTS_TO_FOLLOW: dict[str, EventHandler] = {}


def register_event(event_name: str):
    return RegisterEventHandler(CURATED_EVENTS_TO_FOLLOW, event_name)


def assert_event_mappings() -> None:
    catalog_events = set(CURATED_EVENTS)
    events = set(CURATED_EVENTS_TO_FOLLOW.keys())
    messages = set(CURATED_EVENT_MESSAGES.keys())
    descriptions = set(CURATED_EVENT_DESCRIPTIONS.keys())
    assert catalog_events == events, "Missed events: " + str(
        catalog_events.symmetric_difference(events)
    )
    assert events == messages, "Missed events: " + str(events.symmetric_difference(messages))
    assert events == descriptions, "Missed events: " + str(
        events.symmetric_difference(descriptions)
    )


def _sub_node_operators(group_info):
    return read_field(group_info, "subNodeOperators", 0)


def _sub_node_operator_ids(group_info) -> set[int]:
    return {
        int(read_field(operator, "nodeOperatorId", 0))
        for operator in _sub_node_operators(group_info)
    }


def _sub_node_operator_shares(group_info) -> dict[int, int]:
    return {
        int(read_field(operator, "nodeOperatorId", 0)): int(read_field(operator, "share", 1))
        for operator in _sub_node_operators(group_info)
    }


class CuratedEventMessages(BaseModule):
    event_handlers = CURATED_EVENTS_TO_FOLLOW
    event_messages = CURATED_EVENT_MESSAGES

    def __init__(
        self,
        module_adapter: "CuratedModuleAdapter",
        distribution_log_fetcher: "DistributionLogFetcher | None" = None,
    ):
        self._distribution_log_fetcher = (
            distribution_log_fetcher or default_distribution_log_fetcher
        )
        super().__init__(module_adapter)

    def reconfigure(self, module_adapter: "CuratedModuleAdapter") -> None:
        super().reconfigure(module_adapter)
        self.meta_registry = module_adapter.contracts.meta_registry

    @register_event("TargetValidatorsCountChanged")
    async def target_validators_count_changed(self, event: Event):
        node_operator = await self.module.functions.getNodeOperator(
            event.args["nodeOperatorId"]
        ).call(block_identifier=event.block - 1)
        template = self._require_message_template(event.event)
        return template(
            node_operator.targetLimitMode,
            node_operator.targetLimit,
            event.args["targetLimitMode"],
            event.args["targetValidatorsCount"],
        ) + self.footer(event)

    @register_event("ValidatorExitDelayProcessed")
    async def validator_exit_delay_processed(self, event: Event):
        template = self._require_message_template(event.event)
        key, key_url = self.validator_link(event.args["pubkey"])
        return template(key, key_url, humanize_wei(event.args["delayFee"])) + self.footer(event)

    @register_event("Initialized")
    async def initialized(self, event: Event):
        if event.address.lower() != self.module_address.lower():
            return None
        template = self._require_message_template(event.event)
        return template() + self.footer(event)

    @register_event("BondDepositedETH")
    async def bond_deposited_eth(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["from"], humanize_wei(event.args["amount"])) + self.footer(event)

    @register_event("BondDepositedStETH")
    async def bond_deposited_steth(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["from"], humanize_wei(event.args["amount"])) + self.footer(event)

    @register_event("BondDepositedWstETH")
    async def bond_deposited_wsteth(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["from"], humanize_wei(event.args["amount"])) + self.footer(event)

    @register_event("BondClaimedUnstETH")
    async def bond_claimed_unsteth(self, event: Event):
        template = self._require_message_template(event.event)
        return template(
            event.args["to"],
            humanize_wei(event.args["amount"]),
            event.args["requestId"],
        ) + self.footer(event)

    @register_event("BondClaimedStETH")
    async def bond_claimed_steth(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["to"], humanize_wei(event.args["amount"])) + self.footer(event)

    @register_event("BondClaimedWstETH")
    async def bond_claimed_wsteth(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["to"], humanize_wei(event.args["amount"])) + self.footer(event)

    @register_event("BondBurned")
    async def bond_burned(self, event: Event):
        template = self._require_message_template(event.event)
        return template(humanize_wei(event.args["burnedAmount"])) + self.footer(event)

    @register_event("BondCharged")
    async def bond_charged(self, event: Event):
        template = self._require_message_template(event.event)
        return template(
            humanize_wei(event.args["amountToCharge"]),
            humanize_wei(event.args["chargedAmount"]),
        ) + self.footer(event)

    @register_event("BondLockChanged")
    async def bond_lock_changed(self, event: Event):
        template = self._require_message_template(event.event)
        until = datetime.datetime.fromtimestamp(event.args["until"], datetime.UTC)
        return template(humanize_wei(event.args["newAmount"]), _format_date(until)) + self.footer(
            event
        )

    @register_event("BondLockRemoved")
    async def bond_lock_removed(self, event: Event):
        template = self._require_message_template(event.event)
        return template() + self.footer(event)

    @register_event("BondLockCompensated")
    async def bond_lock_compensated(self, event: Event):
        template = self._require_message_template(event.event)
        return template(humanize_wei(event.args["amount"])) + self.footer(event)

    @register_event("BondLockPeriodChanged")
    async def bond_lock_period_changed(self, event: Event):
        template = self._require_message_template(event.event)
        return template(str(datetime.timedelta(seconds=event.args["period"]))) + self.footer(event)

    @register_event("NodeOperatorEffectiveWeightChanged")
    async def node_operator_effective_weight_changed(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["oldWeight"], event.args["newWeight"]) + self.footer(event)

    @register_event("OperatorGroupCreated")
    async def operator_group_created(self, event: Event):
        template = self._require_message_template(event.event)
        group_info = event.args["groupInfo"]
        operator_ids = _sub_node_operator_ids(group_info)
        if not operator_ids:
            return None
        message = template(event.args["groupId"], _sub_node_operators(group_info)) + self.footer(
            event
        )
        return NotificationPlan(broadcast=message).with_broadcast_targets(operator_ids)

    @register_event("OperatorGroupUpdated")
    async def operator_group_updated(self, event: Event):
        template = self._require_message_template(event.event)
        group_id = event.args["groupId"]
        previous_group = await self.meta_registry.functions.getOperatorGroup(group_id).call(
            block_identifier=event.block - 1
        )
        previous_shares = _sub_node_operator_shares(previous_group)
        current_shares = _sub_node_operator_shares(event.args["groupInfo"])
        changed_operator_ids = set(previous_shares) ^ set(current_shares)
        changed_operator_ids.update(
            node_operator_id
            for node_operator_id in set(previous_shares) & set(current_shares)
            if previous_shares[node_operator_id] != current_shares[node_operator_id]
        )
        if not changed_operator_ids:
            return None

        plan = NotificationPlan().with_broadcast_targets(changed_operator_ids)
        footer = self.footer(event)
        for node_operator_id in changed_operator_ids:
            if node_operator_id not in previous_shares:
                message = template(
                    group_id,
                    node_operator_id,
                    "added",
                    new_share=current_shares[node_operator_id],
                )
            elif node_operator_id not in current_shares:
                message = template(group_id, node_operator_id, "removed")
            else:
                message = template(
                    group_id,
                    node_operator_id,
                    "changed",
                    previous_shares[node_operator_id],
                    current_shares[node_operator_id],
                )
            plan.add_node_operator_message(node_operator_id, f"{message}{footer}")
        return plan

    @register_event("OperatorGroupCleared")
    async def operator_group_cleared(self, event: Event):
        template = self._require_message_template(event.event)
        previous_group = await self.meta_registry.functions.getOperatorGroup(
            event.args["groupId"]
        ).call(block_identifier=event.block - 1)
        operator_ids = _sub_node_operator_ids(previous_group)
        if not operator_ids:
            return None
        message = template(event.args["groupId"]) + self.footer(event)
        return NotificationPlan(broadcast=message).with_broadcast_targets(operator_ids)

    @register_event("BondCurveWeightSet")
    async def bond_curve_weight_set(self, event: Event):
        template = self._require_message_template(event.event)
        message = template(event.args["curveId"], event.args["weight"])
        operator_ids = await self._node_operator_ids_for_bond_curve(
            event.args["curveId"], event.block
        )
        if not operator_ids:
            return message + self.footer(event)

        plan = NotificationPlan()
        for node_operator_id in operator_ids:
            targeted_event = replace(
                event, args=event.args | {"nodeOperatorId": node_operator_id}
            )
            plan.add_node_operator_message(
                node_operator_id, f"{message}{self.footer(targeted_event)}"
            )
        return plan

    @register_event("OperatorMetadataSet")
    async def operator_metadata_set(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["metadata"]) + self.footer(event)

    async def _node_operator_ids_for_bond_curve(self, curve_id: int, block: int) -> set[int]:
        operators_count = await self.module.functions.getNodeOperatorsCount().call(
            block_identifier=block
        )
        operator_ids: set[int] = set()
        for node_operator_id in range(operators_count):
            operator_curve_id = await self.accounting.functions.getBondCurveId(
                node_operator_id
            ).call(block_identifier=block)
            if int(operator_curve_id) == int(curve_id):
                operator_ids.add(node_operator_id)
        return operator_ids


register_event("DepositedSigningKeysCountChanged")(
    CuratedEventMessages.deposited_signing_keys_count_changed
)
register_event("TotalSigningKeysCountChanged")(CuratedEventMessages.total_signing_keys_count_changed)
register_event("VettedSigningKeysCountDecreased")(
    CuratedEventMessages.vetted_signing_keys_count_decreased
)
register_event("KeyRemovalChargeApplied")(CuratedEventMessages.key_removal_charge_applied)
register_event("KeyAllocatedBalanceChanged")(CuratedEventMessages.key_allocated_balance_changed)
register_event("BondCurveSet")(CuratedEventMessages.bond_curve_set)
register_event("NodeOperatorManagerAddressChangeProposed")(
    CuratedEventMessages.node_operator_manager_address_change_proposed
)
register_event("NodeOperatorManagerAddressChanged")(
    CuratedEventMessages.node_operator_manager_address_changed
)
register_event("NodeOperatorRewardAddressChangeProposed")(
    CuratedEventMessages.node_operator_reward_address_change_proposed
)
register_event("NodeOperatorRewardAddressChanged")(
    CuratedEventMessages.node_operator_reward_address_changed
)
register_event("CustomRewardsClaimerSet")(CuratedEventMessages.custom_rewards_claimer_set)
register_event("FeeSplitsSet")(CuratedEventMessages.fee_splits_set)
register_event("BondDebtIncreased")(CuratedEventMessages.bond_debt_increased)
register_event("BondDebtCovered")(CuratedEventMessages.bond_debt_covered)
register_event("ExpiredBondLockRemoved")(CuratedEventMessages.expired_bond_lock_removed)
register_event("GeneralDelayedPenaltyReported")(
    CuratedEventMessages.general_delayed_penalty_reported
)
register_event("GeneralDelayedPenaltySettled")(CuratedEventMessages.general_delayed_penalty_settled)
register_event("GeneralDelayedPenaltyCancelled")(
    CuratedEventMessages.general_delayed_penalty_cancelled
)
register_event("GeneralDelayedPenaltyCompensated")(
    CuratedEventMessages.general_delayed_penalty_compensated
)
register_event("ValidatorSlashingReported")(CuratedEventMessages.validator_slashing_reported)
register_event("ValidatorExitRequest")(CuratedEventMessages.validator_exit_request)
register_event("TriggeredExitFeeRecorded")(CuratedEventMessages.triggered_exit_fee_recorded)
register_event("StrikesPenaltyProcessed")(CuratedEventMessages.strikes_penalty_processed)
register_event("ValidatorWithdrawn")(CuratedEventMessages.validator_withdrawn)
register_event("DistributionLogUpdated")(CuratedEventMessages.distribution_log_updated)
