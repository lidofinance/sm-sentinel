import dataclasses
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eth_typing import ChecksumAddress
from hexbytes import HexBytes

ABI_DIR = Path("abi")
ABI_V3_DIR = ABI_DIR / "v3"


def _load_abi(name: str, *, version: int | None = None) -> list[dict]:
    base_dir = ABI_V3_DIR if version == 3 else ABI_DIR
    with (base_dir / name).open() as fh:
        return json.load(fh)


MODULE_ABI_V2 = _load_abi("CSModuleV2.json")
MODULE_ABI_V3 = _load_abi("CSModule.json", version=3)
CURATED_MODULE_ABI = _load_abi("CuratedModule.json", version=3)

ACCOUNTING_ABI_V2 = _load_abi("CSAccountingV2.json")
ACCOUNTING_ABI_V3 = _load_abi("CSAccounting.json", version=3)

FEE_DISTRIBUTOR_ABI_V2 = _load_abi("CSFeeDistributorV2.json")
FEE_DISTRIBUTOR_ABI_V3 = _load_abi("CSFeeDistributor.json", version=3)

EXIT_PENALTIES_ABI_V2 = _load_abi("CSExitPenalties.json")
EXIT_PENALTIES_ABI_V3 = _load_abi("CSExitPenalties.json", version=3)

PARAMETERS_REGISTRY_ABI_V2 = _load_abi("CSParametersRegistry.json")
PARAMETERS_REGISTRY_ABI_V3 = _load_abi("CSParametersRegistry.json", version=3)

VEBO_ABI = _load_abi("VEBO.json")

LIDO_LOCATOR_ABI_V2 = _load_abi("LidoLocator.json")
LIDO_LOCATOR_ABI_V3 = _load_abi("LidoLocator.json", version=3)

STAKING_ROUTER_ABI_V2 = _load_abi("StakingRouter.json")
STAKING_ROUTER_ABI_V3 = _load_abi("StakingRouter.json", version=3)


@dataclasses.dataclass(frozen=True, slots=True)
class ContractABIs:
    module: list[dict]
    accounting: list[dict]
    parameters_registry: list[dict]
    fee_distributor: list[dict]
    exit_penalties: list[dict]
    lido_locator: list[dict]
    staking_router: list[dict]
    vebo: list[dict]


CONTRACT_ABIS_V2 = ContractABIs(
    module=MODULE_ABI_V2,
    accounting=ACCOUNTING_ABI_V2,
    parameters_registry=PARAMETERS_REGISTRY_ABI_V2,
    fee_distributor=FEE_DISTRIBUTOR_ABI_V2,
    exit_penalties=EXIT_PENALTIES_ABI_V2,
    lido_locator=LIDO_LOCATOR_ABI_V2,
    staking_router=STAKING_ROUTER_ABI_V2,
    vebo=VEBO_ABI,
)

CONTRACT_ABIS_V3 = ContractABIs(
    module=MODULE_ABI_V3,
    accounting=ACCOUNTING_ABI_V3,
    parameters_registry=PARAMETERS_REGISTRY_ABI_V3,
    fee_distributor=FEE_DISTRIBUTOR_ABI_V3,
    exit_penalties=EXIT_PENALTIES_ABI_V3,
    lido_locator=LIDO_LOCATOR_ABI_V3,
    staking_router=STAKING_ROUTER_ABI_V3,
    vebo=VEBO_ABI,
)

CURATED_CONTRACT_ABIS = ContractABIs(
    module=CURATED_MODULE_ABI,
    accounting=ACCOUNTING_ABI_V3,
    parameters_registry=PARAMETERS_REGISTRY_ABI_V3,
    fee_distributor=FEE_DISTRIBUTOR_ABI_V3,
    exit_penalties=EXIT_PENALTIES_ABI_V3,
    lido_locator=LIDO_LOCATOR_ABI_V3,
    staking_router=STAKING_ROUTER_ABI_V3,
    vebo=VEBO_ABI,
)


def get_contract_abis(csm_version: int) -> ContractABIs:
    if csm_version == 3:
        return CONTRACT_ABIS_V3
    return CONTRACT_ABIS_V2


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
