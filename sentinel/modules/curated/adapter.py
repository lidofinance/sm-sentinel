from dataclasses import dataclass
from typing import ClassVar

from web3 import AsyncWeb3

from sentinel.app.contracts import ContractAddresses
from sentinel.chain import ConnectOnDemand
from sentinel.models import CURATED_CONTRACT_ABIS, ContractABIs
from sentinel.module_types import ModuleType
from sentinel.modules.base import BaseModuleAdapter, EventSource
from sentinel.modules.curated.texts import CuratedTexts


@dataclass(frozen=True, slots=True)
class CuratedModuleContracts:
    module: object
    accounting: object
    parameters_registry: object
    fee_distributor: object
    exit_penalties: object
    lido_locator: object
    staking_router: object
    vebo: object


CURATED_EVENTS = frozenset[str]()


class CuratedModuleAdapter(BaseModuleAdapter):
    module_type: ClassVar[ModuleType] = ModuleType.CURATED
    module_name: ClassVar[str] = "Curated Module"
    ui_label: ClassVar[str] = "Curated Module UI"
    texts = CuratedTexts

    def __init__(
        self,
        *,
        addresses: ContractAddresses,
        contracts: CuratedModuleContracts,
        module_ui_url: str | None,
        contract_abis: ContractABIs,
        chain: ConnectOnDemand,
    ) -> None:
        if addresses.module_type != ModuleType.CURATED:
            raise RuntimeError(f"Expected curated module, got {addresses.module_type!s}")
        super().__init__(
            addresses=addresses,
            contracts=contracts,
            module_ui_url=module_ui_url,
            contract_abis=contract_abis,
            chain=chain,
        )

    @staticmethod
    def contract_abis_for(addresses: ContractAddresses) -> ContractABIs:
        _ = addresses
        return CURATED_CONTRACT_ABIS

    @staticmethod
    def build_contracts(
        w3: AsyncWeb3,
        addresses: ContractAddresses,
        contract_abis: ContractABIs,
    ) -> CuratedModuleContracts:
        return CuratedModuleContracts(
            module=w3.eth.contract(
                address=addresses.module,
                abi=contract_abis.module,
                decode_tuples=True,
            ),
            accounting=w3.eth.contract(
                address=addresses.accounting,
                abi=contract_abis.accounting,
                decode_tuples=True,
            ),
            parameters_registry=w3.eth.contract(
                address=addresses.parameters_registry,
                abi=contract_abis.parameters_registry,
                decode_tuples=True,
            ),
            fee_distributor=w3.eth.contract(
                address=addresses.fee_distributor,
                abi=contract_abis.fee_distributor,
            ),
            exit_penalties=w3.eth.contract(
                address=addresses.exit_penalties,
                abi=contract_abis.exit_penalties,
            ),
            lido_locator=w3.eth.contract(
                address=addresses.lido_locator,
                abi=contract_abis.lido_locator,
            ),
            staking_router=w3.eth.contract(
                address=addresses.staking_router,
                abi=contract_abis.staking_router,
            ),
            vebo=w3.eth.contract(
                address=addresses.vebo,
                abi=contract_abis.vebo,
            ),
        )

    def catalog_events(self) -> set[str]:
        return set(CURATED_EVENTS)

    def notifiable_events(self) -> set[str]:
        return set(CURATED_EVENTS)

    def event_sources(self) -> tuple[EventSource, ...]:
        return ()

    def topic_abis(self) -> tuple[list[dict], ...]:
        return (self.contract_abis.module,)

    def build_event_messages(self, w3, csm_version_switcher):
        _ = w3
        _ = csm_version_switcher
        from sentinel.modules.curated.events import CuratedEventMessages

        return CuratedEventMessages(self)
