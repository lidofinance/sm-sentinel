from collections.abc import Callable
from typing import Any, ClassVar

from async_lru import alru_cache

from sentinel.config import get_config
from sentinel.models import Event, EventHandler, EventNotification
from sentinel.modules.distribution import DistributionLogFetcher
from sentinel.notifications import BroadcastDelivery, NotificationPlan

MessageTemplate = Callable[..., str]


class EventMessageEngineBase:
    event_handlers: ClassVar[dict[str, EventHandler]]
    event_messages: ClassVar[dict[str, MessageTemplate]]
    chain: Any
    module_adapter: Any
    _distribution_log_fetcher: DistributionLogFetcher

    def __init__(self, module_adapter: Any) -> None:
        self.cfg = get_config()
        self._bind_module_adapter(module_adapter)

    def _bind_module_adapter(self, module_adapter: Any) -> None:
        raise NotImplementedError

    @alru_cache(maxsize=3)
    async def _fetch_distribution_log(self, log_cid: str):
        if not log_cid:
            raise ValueError("log_cid must be provided")
        return await self._distribution_log_fetcher(log_cid)

    async def default(self, event: EventNotification):
        return NotificationPlan.broadcast(f"Event {event.event} emitted with data: \n{event.args}")

    async def get_notification_plan(self, event: EventNotification):
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
            result if isinstance(result, NotificationPlan) else NotificationPlan.broadcast(result)
        )

        delivery = plan.delivery
        if isinstance(delivery, BroadcastDelivery):
            if delivery.operator_ids is None and "nodeOperatorId" in event.args:
                return NotificationPlan.broadcast_to_operators(
                    delivery.message,
                    {event.args["nodeOperatorId"]},
                )

        return plan

    async def event_footer(self, event: Event) -> str:
        raise NotImplementedError

    def transaction_link(self, event: Event) -> str:
        return self.cfg.explorers.transaction("0x" + event.tx.hex())

    def block_link(self, block: int) -> str:
        return self.cfg.explorers.block(block)

    def to_hex(self, value) -> str:
        return self.chain.w3.to_hex(value)

    def validator_link(self, pubkey) -> tuple[str, str]:
        key = self.to_hex(pubkey)
        return key, self.cfg.explorers.validator(key)

    def _require_message_template(self, event_name: str) -> MessageTemplate:
        template = self.event_messages.get(event_name)
        if template is None:
            raise RuntimeError(f"Missing message template for event {event_name}")
        return template
