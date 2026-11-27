import dataclasses
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, Any

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from hexbytes import HexBytes
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_serializer


class EventRecord(BaseModel):
    """Persisted event shape; Web3 runtime events remain ordinary dataclasses."""

    model_config = ConfigDict(strict=True, arbitrary_types_allowed=True, extra="ignore")

    event: str
    args: dict[str, Any]
    block: int = Field(strict=False)
    tx: Annotated[HexBytes, BeforeValidator(HexBytes)]
    address: Annotated[ChecksumAddress, AfterValidator(to_checksum_address)]
    log_index: int = Field(strict=False)
    transaction_index: int = Field(strict=False)

    @field_serializer("tx")
    def serialize_tx(self, value: HexBytes) -> str:
        return value.to_0x_hex()

    def to_event(self) -> "Event":
        return Event(
            event=self.event,
            args=self.args,
            block=self.block,
            tx=self.tx,
            address=self.address,
            log_index=self.log_index,
            transaction_index=self.transaction_index,
        )


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
    log_index: int
    transaction_index: int

    def readable(self):
        args = ", ".join(f"{key}={value}" for key, value in self.args.items())
        return f"{self.event}({args})"

    @property
    def log_identity(self) -> tuple[str, str, int]:
        return (
            self.address.lower(),
            self.tx.to_0x_hex(),
            self.log_index,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "args": dict(self.args),
            "block": int(self.block),
            "tx": self.tx.to_0x_hex(),
            "address": str(self.address),
            "log_index": int(self.log_index),
            "transaction_index": int(self.transaction_index),
        }

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "Event":
        return EventRecord.model_validate(record).to_event()


@dataclasses.dataclass
class EventNotification:
    source_events: tuple[Event, ...]

    def __post_init__(self) -> None:
        if not self.source_events:
            raise ValueError("EventNotification must contain at least one source event")

    @classmethod
    def from_event(cls, event: Event) -> "EventNotification":
        return cls(source_events=(event,))

    @property
    def primary_event(self) -> Event:
        return self.source_events[-1]

    @property
    def event(self) -> str:
        return self.primary_event.event

    @property
    def args(self) -> dict:
        return self.primary_event.args

    @property
    def block(self) -> int:
        return self.primary_event.block

    @property
    def tx(self) -> HexBytes:
        return self.primary_event.tx

    @property
    def address(self) -> ChecksumAddress:
        return self.primary_event.address

    def readable(self):
        args = ", ".join(f"{key}={value}" for key, value in self.args.items())
        return f"{self.event}({args})"


@dataclasses.dataclass
class EventHandler:
    """Dataclass to represent an event handler."""

    event: str
    handler: "EventHandlerFn"
    aggregation_group: "AggregationGroup | None" = None
    digest_name: str | None = None

    def __post_init__(self) -> None:
        if self.aggregation_group is not None and self.digest_name is not None:
            raise ValueError(
                f"Event {self.event!r} cannot use both aggregation and digest buffering"
            )


if TYPE_CHECKING:
    from sentinel.modules.aggregation import AggregationGroup
    from sentinel.notifications import NotificationPlan

EventHandlerFn = Callable[
    [Any, EventNotification],
    Awaitable["NotificationPlan | str | None"],
]
