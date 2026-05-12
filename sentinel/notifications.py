from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from sentinel.models import Event


@dataclass
class NotificationPlan:
    """Container describing how subscribers should be notified for an event."""

    # Optional general broadcast message
    broadcast: str | None = None
    # If set, restrict broadcast to these node operator IDs (as strings)
    broadcast_node_operator_ids: set[str] | None = None
    # Specific messages for individual node operators (keyed by node operator ID as string)
    per_node_operator: dict[str, str] = field(default_factory=dict)

    def add_node_operator_message(self, node_operator_id: int | str, message: str) -> None:
        """Register a node-operator specific message, storing the ID as a string."""

        self.per_node_operator[str(node_operator_id)] = message

    def with_broadcast_targets(self, node_operator_ids: Iterable[int | str]) -> "NotificationPlan":
        """Limit broadcast delivery to the provided node operator identifiers."""

        self.broadcast_node_operator_ids = {str(no_id) for no_id in node_operator_ids}
        return self


class EventMessageEngine(Protocol):
    async def get_notification_plan(self, event: Event) -> NotificationPlan | None: ...

    def reconfigure(self, module_adapter: Any) -> None: ...
