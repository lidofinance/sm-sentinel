from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from eth_typing import ChecksumAddress

from sentinel.app.contracts import ContractABIs, ContractAddresses
from sentinel.chain import ConnectOnDemand
from sentinel.module_types import ModuleType
from sentinel.modules.texts import BotTexts

if TYPE_CHECKING:
    from sentinel.models import Event

EventPredicate = Callable[["Event"], bool]


@dataclass(frozen=True, slots=True)
class EventSource:
    name: str
    address: ChecksumAddress
    event_names: frozenset[str] | None = None
    predicate: EventPredicate | None = None


class ModuleAdapter(Protocol):
    module_type: ModuleType
    addresses: ContractAddresses
    contracts: Any
    contract_abis: ContractABIs
    chain: ConnectOnDemand
    texts: BotTexts
    module_ui_url: str | None
    csm_version: int

    def catalog_events(self) -> set[str]: ...

    def notifiable_events(self) -> set[str]: ...

    def build_event_list_text(self) -> str: ...

    async def is_valid_operator_id(self, operator_id: int) -> bool: ...

    def event_sources(self) -> tuple[EventSource, ...]: ...

    def topic_abis(self) -> tuple[list[dict], ...]: ...

    def build_event_messages(self, w3, csm_version_switcher): ...


class BaseModuleAdapter:
    module_type: ClassVar[ModuleType]
    module_name: ClassVar[str] = "Module"
    ui_label: ClassVar[str] = "Module UI"
    texts: ClassVar[BotTexts]

    def __init__(
        self,
        *,
        addresses: ContractAddresses,
        contracts: Any,
        module_ui_url: str | None,
        contract_abis: ContractABIs,
        chain: ConnectOnDemand,
    ) -> None:
        self.addresses = addresses
        self.contracts = contracts
        self.contract_abis = contract_abis
        self.chain = chain
        self.module_ui_url = module_ui_url
        self.csm_version = addresses.csm_version

    def catalog_events(self) -> set[str]:
        raise NotImplementedError

    def notifiable_events(self) -> set[str]:
        return self.catalog_events()

    def event_sources(self) -> tuple[EventSource, ...]:
        raise NotImplementedError

    def topic_abis(self) -> tuple[list[dict], ...]:
        raise NotImplementedError

    def build_event_list_text(self) -> str:
        return self.texts.build_event_list_text(self.catalog_events(), self.module_ui_url)

    async def is_valid_operator_id(self, operator_id: int) -> bool:
        _ = operator_id
        return False
