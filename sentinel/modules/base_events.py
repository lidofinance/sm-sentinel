import datetime
import logging
from typing import Any

from eth_utils import humanize_wei

from sentinel.models import Event
from sentinel.modules.distribution import (
    DistributionLogFetcher,
    parse_distribution_log,
    validator_sort_key,
)
from sentinel.modules.event_engine import EventMessageEngineBase
from sentinel.notifications import NotificationPlan

logger = logging.getLogger(__name__)


def _format_date(date: datetime.datetime):
    return date.strftime("%a %d %b %Y, %I:%M%p UTC")


class BaseModule(EventMessageEngineBase):
    module: Any
    accounting: Any
    parametersRegistry: Any
    _distribution_log_fetcher: DistributionLogFetcher

    def reconfigure(self, module_adapter: Any) -> None:
        self.module_adapter = module_adapter
        self.chain = module_adapter.chain
        self.module_address = module_adapter.addresses.module
        self.accounting_address = module_adapter.addresses.accounting
        self.parameters_registry_address = module_adapter.addresses.parameters_registry
        self.module = module_adapter.contracts.module
        self.accounting = module_adapter.contracts.accounting
        self.parametersRegistry = module_adapter.contracts.parameters_registry

    async def deposited_signing_keys_count_changed(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["depositedKeysCount"]) + await self.event_footer(event)

    async def total_signing_keys_count_changed(self, event: Event):
        template = self._require_message_template(event.event)
        node_operator = await self.module.functions.getNodeOperator(
            event.args["nodeOperatorId"]
        ).call(block_identifier=event.block - 1)
        return template(
            event.args["totalKeysCount"], node_operator.totalAddedKeys
        ) + await self.event_footer(event)

    async def vetted_signing_keys_count_decreased(self, event: Event):
        template = self._require_message_template(event.event)
        return template() + await self.event_footer(event)

    async def key_removal_charge_applied(self, event: Event):
        template = self._require_message_template(event.event)
        curve_id = await self.accounting.functions.getBondCurveId(
            event.args["nodeOperatorId"]
        ).call(block_identifier=event.block)
        amount = await self.parametersRegistry.functions.getKeyRemovalCharge(curve_id).call(
            block_identifier=event.block
        )
        return template(humanize_wei(amount)) + await self.event_footer(event)

    async def key_allocated_balance_changed(self, event: Event):
        # TODO: batch multiple key balance updates for the same operator when event grouping is
        # available; doing it here would lose per-key context and notification targeting.
        template = self._require_message_template(event.event)
        return template(
            event.args["keyIndex"],
            humanize_wei(event.args["newTotal"]),
        ) + await self.event_footer(event)

    async def bond_curve_set(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["curveId"]) + await self.event_footer(event)

    async def node_operator_manager_address_change_proposed(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["newProposedAddress"]) + await self.event_footer(event)

    async def node_operator_manager_address_changed(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["newAddress"]) + await self.event_footer(event)

    async def node_operator_reward_address_change_proposed(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["newProposedAddress"]) + await self.event_footer(event)

    async def node_operator_reward_address_changed(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["newAddress"]) + await self.event_footer(event)

    async def custom_rewards_claimer_set(self, event: Event):
        template = self._require_message_template(event.event)
        previous_rewards_claimer = await self.accounting.functions.getCustomRewardsClaimer(
            event.args["nodeOperatorId"]
        ).call(block_identifier=event.block - 1)
        return template(
            event.args["rewardsClaimer"], previous_rewards_claimer
        ) + await self.event_footer(event)

    async def fee_splits_set(self, event: Event):
        template = self._require_message_template(event.event)
        return template(event.args["feeSplits"]) + await self.event_footer(event)

    async def bond_debt_increased(self, event: Event):
        template = self._require_message_template(event.event)
        return template(humanize_wei(event.args["amount"])) + await self.event_footer(event)

    async def bond_debt_covered(self, event: Event):
        template = self._require_message_template(event.event)
        return template(humanize_wei(event.args["amount"])) + await self.event_footer(event)

    async def expired_bond_lock_removed(self, event: Event):
        template = self._require_message_template(event.event)
        return template() + await self.event_footer(event)

    async def general_delayed_penalty_reported(self, event: Event):
        template = self._require_message_template(event.event)
        return template(
            humanize_wei(event.args["amount"]),
            humanize_wei(event.args["additionalFine"]),
            event.args["details"],
        ) + await self.event_footer(event)

    async def general_delayed_penalty_settled(self, event: Event):
        template = self._require_message_template(event.event)
        return template(humanize_wei(event.args["amount"])) + await self.event_footer(event)

    async def general_delayed_penalty_cancelled(self, event: Event):
        template = self._require_message_template(event.event)
        remaining_amount = humanize_wei(
            await self.accounting.functions.getActualLockedBond(event.args["nodeOperatorId"]).call(
                block_identifier=event.block
            )
        )
        return template(remaining_amount) + await self.event_footer(event)

    async def general_delayed_penalty_compensated(self, event: Event):
        template = self._require_message_template(event.event)
        return template(humanize_wei(event.args["amount"])) + await self.event_footer(event)

    async def validator_slashing_reported(self, event: Event):
        template = self._require_message_template(event.event)
        key, key_url = self.validator_link(event.args["pubkey"])
        return template(key, key_url, event.args["keyIndex"]) + await self.event_footer(event)

    async def validator_exit_request(self, event: Event):
        template = self._require_message_template(event.event)
        key, key_url = self.validator_link(event.args["validatorPubkey"])
        request_date = datetime.datetime.fromtimestamp(event.args["timestamp"], datetime.UTC)
        curve_id = await self.accounting.functions.getBondCurveId(
            event.args["nodeOperatorId"]
        ).call(block_identifier=event.block)
        allowed_exit_delay = await self.parametersRegistry.functions.getAllowedExitDelay(
            curve_id
        ).call(block_identifier=event.block)
        exit_until = request_date + datetime.timedelta(seconds=allowed_exit_delay)
        return template(
            key, key_url, _format_date(request_date), _format_date(exit_until)
        ) + await self.event_footer(event)

    async def triggered_exit_fee_recorded(self, event: Event):
        template = self._require_message_template(event.event)
        key, key_url = self.validator_link(event.args["pubkey"])
        return template(
            key,
            key_url,
            humanize_wei(event.args["withdrawalRequestRecordedFee"]),
        ) + await self.event_footer(event)

    async def strikes_penalty_processed(self, event: Event):
        template = self._require_message_template(event.event)
        key, key_url = self.validator_link(event.args["pubkey"])
        return template(
            key, key_url, humanize_wei(event.args["strikesPenalty"])
        ) + await self.event_footer(event)

    async def validator_withdrawn(self, event: Event):
        template = self._require_message_template(event.event)
        key, key_url = self.validator_link(event.args["pubkey"])
        return template(
            key,
            key_url,
            humanize_wei(event.args["exitBalance"]),
            humanize_wei(event.args["slashingPenalty"]),
        ) + await self.event_footer(event)

    async def distribution_log_updated(self, event: Event):
        template = self._require_message_template(event.event)
        base_message = template()
        footer = await self.event_footer(event)
        plan = NotificationPlan(broadcast=f"{base_message}{footer}")

        log_cid = event.args.get("logCid")
        try:
            distribution_log = await self._fetch_distribution_log(log_cid)
        except Exception as exc:
            logger.warning(
                "Failed to enrich DistributionLogUpdated for logCid %s: %s",
                log_cid,
                exc,
            )
            return plan

        summary = parse_distribution_log(distribution_log)

        if summary.all_operator_ids:
            plan.with_broadcast_targets(summary.all_operator_ids)

        for operator_id, flagged in summary.strikes_per_operator.items():
            flagged_sorted = sorted(flagged, key=lambda item: validator_sort_key(item[0]))
            plan.add_node_operator_message(
                operator_id, f"{template(operator_id, flagged_sorted)}{footer}"
            )

        return plan
