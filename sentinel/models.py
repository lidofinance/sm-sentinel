import dataclasses
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from eth_typing import ChecksumAddress
from hexbytes import HexBytes


@dataclasses.dataclass
class Block:
    number: int


@dataclasses.dataclass
class Event:
    event: str
    args: dict
    block: int
    tx: HexBytes
    address: ChecksumAddress

    def readable(self):
        args = ", ".join(f"{key}={value}" for key, value in self.args.items())
        return f"{self.event}({args})"


@dataclasses.dataclass
class EventHandler:
    """Dataclass to represent an event handler."""

    event: str
    handler: "EventHandlerFn"


if TYPE_CHECKING:
    from sentinel.notifications import NotificationPlan

EventHandlerFn = Callable[[Any, Event], Awaitable["NotificationPlan | str | None"]]
