from collections.abc import Callable
from typing import Any, ClassVar

from async_lru import alru_cache

from sentinel.config import get_config
from sentinel.models import Event, EventHandler
from sentinel.modules.distribution import DistributionLogFetcher
from sentinel.modules.formatting import event_footer
from sentinel.notifications import NotificationPlan

MessageTemplate = Callable[..., str]


class EventMessageEngineBase:
    event_handlers: ClassVar[dict[str, EventHandler]]
    event_messages: ClassVar[dict[str, MessageTemplate]]
    chain: Any
    module_adapter: Any
    _distribution_log_fetcher: DistributionLogFetcher

    def __init__(self, module_adapter: Any) -> None:
        self.cfg = get_config()
        self.reconfigure(module_adapter)

    def reconfigure(self, module_adapter: Any) -> None:
        raise NotImplementedError

    @alru_cache(maxsize=3)
    async def _fetch_distribution_log(self, log_cid: str):
        if not log_cid:
            raise ValueError("log_cid must be provided")
        return await self._distribution_log_fetcher(log_cid)

    async def default(self, event: Event):
        return NotificationPlan(broadcast=f"Event {event.event} emitted with data: \n{event.args}")

    async def get_notification_plan(self, event: Event):
        if event.event not in self.module_adapter.notifiable_events():
            return None
        async with self.chain:
            event_handler = self.event_handlers.get(event.event)
            if event_handler is not None:
                result = await event_handler.handler(self, event)
            else:
                result = await self.default(event)

        if result is None:
            return None

        plan = (
            result if isinstance(result, NotificationPlan) else NotificationPlan(broadcast=result)
        )

        if (
            plan.broadcast
            and plan.broadcast_node_operator_ids is None
            and "nodeOperatorId" in event.args
        ):
            plan.with_broadcast_targets({event.args["nodeOperatorId"]})

        return plan

    def footer(self, event: Event):
        tx_template = self._require_template(self.cfg.etherscan_tx_url_template, "ETHERSCAN_URL")
        tx_link = tx_template.format("0x" + event.tx.hex())
        return event_footer(event.args.get("nodeOperatorId"), tx_link)

    def to_hex(self, value) -> str:
        return self.chain.w3.to_hex(value)

    def validator_link(self, pubkey) -> tuple[str, str]:
        key = self.to_hex(pubkey)
        beacon_template = self._require_template(
            self.cfg.beaconchain_url_template, "BEACONCHAIN_URL"
        )
        return key, beacon_template.format(key)

    @staticmethod
    def _require_template(template: str | None, env_var: str) -> str:
        if template is None:
            raise RuntimeError(f"{env_var} must be configured")
        return template

    def _require_message_template(self, event_name: str) -> MessageTemplate:
        template = self.event_messages.get(event_name)
        if template is None:
            raise RuntimeError(f"Missing message template for event {event_name}")
        return template
