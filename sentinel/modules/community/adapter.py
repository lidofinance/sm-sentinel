from dataclasses import dataclass
from typing import ClassVar

from web3 import AsyncWeb3

from sentinel.app.contracts import (
    CONTRACT_ABIS_V2,
    CONTRACT_ABIS_V3,
    CommunityContractAddresses,
    CommunityContractABIs,
)
from sentinel.chain import ConnectOnDemand
from sentinel.models import Event
from sentinel.module_types import ModuleType
from sentinel.modules.base import BaseModuleAdapter, EventSource
from sentinel.modules.community.texts import CommunityTexts


@dataclass(frozen=True, slots=True)
class CommunityModuleContracts:
    module: object
    accounting: object
    parameters_registry: object
    fee_distributor: object
    exit_penalties: object
    lido_locator: object
    staking_router: object
    vebo: object


COMMUNITY_COMMON_EVENTS = frozenset(
    {
        "VettedSigningKeysCountDecreased",
        "DepositedSigningKeysCountChanged",
        "TotalSigningKeysCountChanged",
        "KeyRemovalChargeApplied",
        "BondCurveSet",
        "TargetValidatorsCountChanged",
        "NodeOperatorManagerAddressChangeProposed",
        "NodeOperatorManagerAddressChanged",
        "NodeOperatorRewardAddressChangeProposed",
        "NodeOperatorRewardAddressChanged",
        "ValidatorExitRequest",
        "ValidatorExitDelayProcessed",
        "TriggeredExitFeeRecorded",
        "StrikesPenaltyProcessed",
        "DistributionLogUpdated",
    }
)

COMMUNITY_V2_ONLY_EVENTS = frozenset(
    {
        "ELRewardsStealingPenaltyReported",
        "ELRewardsStealingPenaltySettled",
        "ELRewardsStealingPenaltyCancelled",
        "WithdrawalSubmitted",
    }
)

COMMUNITY_V3_ONLY_EVENTS = frozenset(
    {
        "GeneralDelayedPenaltyReported",
        "GeneralDelayedPenaltySettled",
        "GeneralDelayedPenaltyCancelled",
        "GeneralDelayedPenaltyCompensated",
        "ValidatorSlashingReported",
        "BondDebtIncreased",
        "BondDebtCovered",
        "CustomRewardsClaimerSet",
        "FeeSplitsSet",
        "ExpiredBondLockRemoved",
        "KeyAllocatedBalanceChanged",
        "ValidatorWithdrawn",
        "Initialized",
    }
)

COMMUNITY_CATALOG_EVENTS_BY_VERSION: dict[int, frozenset[str]] = {
    2: COMMUNITY_COMMON_EVENTS | COMMUNITY_V2_ONLY_EVENTS,
    3: COMMUNITY_COMMON_EVENTS | COMMUNITY_V3_ONLY_EVENTS,
}
COMMUNITY_NOTIFIABLE_EVENTS = (
    COMMUNITY_COMMON_EVENTS | COMMUNITY_V2_ONLY_EVENTS | COMMUNITY_V3_ONLY_EVENTS
)


class CommunityModuleAdapter(BaseModuleAdapter):
    module_type: ClassVar[ModuleType] = ModuleType.COMMUNITY
    module_name: ClassVar[str] = "CSM"
    ui_label: ClassVar[str] = "CSM UI"
    texts = CommunityTexts

    def __init__(
        self,
        *,
        addresses: CommunityContractAddresses,
        contracts: CommunityModuleContracts,
        module_ui_url: str | None,
        contract_abis: CommunityContractABIs,
        chain: ConnectOnDemand,
    ) -> None:
        if addresses.module_type != ModuleType.COMMUNITY:
            raise RuntimeError(f"Expected community module, got {addresses.module_type!s}")
        super().__init__(
            addresses=addresses,
            contracts=contracts,
            module_ui_url=module_ui_url,
            contract_abis=contract_abis,
            chain=chain,
        )
        self.csm_version = addresses.csm_version

    @staticmethod
    def contract_abis_for(addresses: CommunityContractAddresses) -> CommunityContractABIs:
        if addresses.csm_version == 3:
            return CONTRACT_ABIS_V3
        return CONTRACT_ABIS_V2

    @staticmethod
    def build_contracts(
        w3: AsyncWeb3,
        addresses: CommunityContractAddresses,
        contract_abis: CommunityContractABIs,
    ) -> CommunityModuleContracts:
        return CommunityModuleContracts(
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
        events = COMMUNITY_CATALOG_EVENTS_BY_VERSION.get(
            self.csm_version,
            COMMUNITY_CATALOG_EVENTS_BY_VERSION[3],
        )
        return set(events)

    def notifiable_events(self) -> set[str]:
        return set(COMMUNITY_NOTIFIABLE_EVENTS)

    async def is_valid_operator_id(self, operator_id: int) -> bool:
        async with self.chain:
            count = await self.contracts.module.functions.getNodeOperatorsCount().call()
        return 0 <= operator_id < count

    def staking_module_id_matches(self, event: Event) -> bool:
        return event.args["stakingModuleId"] == self.addresses.staking_module_id

    def event_sources(self) -> tuple[EventSource, ...]:
        return (
            EventSource("module", self.addresses.module),
            EventSource("accounting", self.addresses.accounting),
            EventSource(
                "vebo",
                self.addresses.vebo,
                frozenset({"ValidatorExitRequest"}),
                self.staking_module_id_matches,
            ),
            EventSource(
                "fee_distributor",
                self.addresses.fee_distributor,
                frozenset({"DistributionLogUpdated"}),
            ),
            EventSource("exit_penalties", self.addresses.exit_penalties),
        )

    def topic_abis(self) -> tuple[list[dict], ...]:
        return (
            CONTRACT_ABIS_V2.module,
            CONTRACT_ABIS_V3.module,
            CONTRACT_ABIS_V2.accounting,
            CONTRACT_ABIS_V3.accounting,
            CONTRACT_ABIS_V2.fee_distributor,
            CONTRACT_ABIS_V3.fee_distributor,
            CONTRACT_ABIS_V2.vebo,
            CONTRACT_ABIS_V3.vebo,
            CONTRACT_ABIS_V2.exit_penalties,
            CONTRACT_ABIS_V3.exit_penalties,
        )

    def build_event_messages(self, w3, csm_version_switcher):
        from sentinel.modules.community.events import CommunityEventMessages

        return CommunityEventMessages(w3, self, csm_version_switcher, chain=self.chain)
