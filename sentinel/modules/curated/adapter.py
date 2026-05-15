from dataclasses import dataclass
from typing import ClassVar

from web3 import AsyncWeb3

from sentinel.app.contracts import (
    CURATED_CONTRACT_ABIS,
    ContractAddresses,
    CuratedContractABIs,
    CuratedContractAddresses,
)
from sentinel.chain import ConnectOnDemand
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
    meta_registry: object
    lido_locator: object
    staking_router: object
    vebo: object


CURATED_EVENTS = frozenset(
    {
        # CuratedModule
        "DepositedSigningKeysCountChanged",
        "TotalSigningKeysCountChanged",
        "VettedSigningKeysCountDecreased",
        "KeyRemovalChargeApplied",
        "KeyAllocatedBalanceChanged",
        "TargetValidatorsCountChanged",
        "NodeOperatorManagerAddressChangeProposed",
        "NodeOperatorManagerAddressChanged",
        "NodeOperatorRewardAddressChangeProposed",
        "NodeOperatorRewardAddressChanged",
        "GeneralDelayedPenaltyReported",
        "GeneralDelayedPenaltySettled",
        "GeneralDelayedPenaltyCancelled",
        "GeneralDelayedPenaltyCompensated",
        "ValidatorSlashingReported",
        "ValidatorWithdrawn",
        "Initialized",
        # CSAccounting
        "BondCurveSet",
        "CustomRewardsClaimerSet",
        "FeeSplitsSet",
        "BondDebtIncreased",
        "BondDebtCovered",
        "ExpiredBondLockRemoved",
        "BondDepositedETH",
        "BondDepositedStETH",
        "BondDepositedWstETH",
        "BondClaimedUnstETH",
        "BondClaimedStETH",
        "BondClaimedWstETH",
        "BondBurned",
        "BondCharged",
        "BondLockChanged",
        "BondLockRemoved",
        "BondLockCompensated",
        "BondLockPeriodChanged",
        # CSExitPenalties
        "ValidatorExitDelayProcessed",
        "TriggeredExitFeeRecorded",
        "StrikesPenaltyProcessed",
        # CSFeeDistributor
        "DistributionLogUpdated",
        # ValidatorsExitBusOracle
        "ValidatorExitRequest",
        # MetaRegistry
        "NodeOperatorEffectiveWeightChanged",
        "OperatorGroupCreated",
        "OperatorGroupUpdated",
        "OperatorGroupCleared",
        "BondCurveWeightSet",
        "OperatorMetadataSet",
    }
)

CURATED_FEE_DISTRIBUTOR_EVENTS = frozenset({"DistributionLogUpdated"})
CURATED_VEBO_EVENTS = frozenset({"ValidatorExitRequest"})


class CuratedModuleAdapter(BaseModuleAdapter):
    module_type: ClassVar[ModuleType] = ModuleType.CURATED
    module_name: ClassVar[str] = "Curated Module"
    ui_label: ClassVar[str] = "Curated Module UI"
    texts = CuratedTexts

    def __init__(
        self,
        *,
        addresses: CuratedContractAddresses,
        contracts: CuratedModuleContracts,
        module_ui_url: str | None,
        contract_abis: CuratedContractABIs,
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
        self.curated_addresses = addresses
        self.curated_contract_abis = contract_abis

    @staticmethod
    def contract_abis_for(addresses: ContractAddresses) -> CuratedContractABIs:
        _ = addresses
        return CURATED_CONTRACT_ABIS

    @staticmethod
    def build_contracts(
        w3: AsyncWeb3,
        addresses: CuratedContractAddresses,
        contract_abis: CuratedContractABIs,
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
            meta_registry=w3.eth.contract(
                address=addresses.meta_registry,
                abi=contract_abis.meta_registry,
                decode_tuples=True,
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

    async def is_valid_operator_id(self, operator_id: int) -> bool:
        async with self.chain:
            count = await self.contracts.module.functions.getNodeOperatorsCount().call()
        return 0 <= operator_id < count

    def staking_module_id_matches(self, event) -> bool:
        return event.args["stakingModuleId"] == self.addresses.staking_module_id

    def event_sources(self) -> tuple[EventSource, ...]:
        return (
            EventSource("module", self.addresses.module),
            EventSource("accounting", self.addresses.accounting),
            EventSource("exit_penalties", self.addresses.exit_penalties),
            EventSource(
                "fee_distributor",
                self.addresses.fee_distributor,
                CURATED_FEE_DISTRIBUTOR_EVENTS,
            ),
            EventSource(
                "vebo",
                self.addresses.vebo,
                CURATED_VEBO_EVENTS,
                self.staking_module_id_matches,
            ),
            EventSource(
                "meta_registry",
                self.curated_addresses.meta_registry,
            ),
        )

    def topic_abis(self) -> tuple[list[dict], ...]:
        return (
            self.contract_abis.module,
            self.contract_abis.accounting,
            self.contract_abis.fee_distributor,
            self.contract_abis.exit_penalties,
            self.contract_abis.vebo,
            self.curated_contract_abis.meta_registry,
        )

    def build_event_messages(self, w3, csm_version_switcher):
        _ = w3
        _ = csm_version_switcher
        from sentinel.modules.curated.events import CuratedEventMessages

        return CuratedEventMessages(self)
