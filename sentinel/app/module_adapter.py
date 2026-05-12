from typing import TYPE_CHECKING

from web3 import AsyncWeb3

from sentinel.app.contracts import ContractAddresses
from sentinel.chain import ConnectOnDemand
from sentinel.module_types import ModuleType
from sentinel.modules.base import ModuleAdapter
from sentinel.modules.community.adapter import CommunityModuleAdapter
from sentinel.modules.curated.adapter import CuratedModuleAdapter

if TYPE_CHECKING:
    from sentinel.config import Config

__all__ = [
    "build_module_adapter_from_addresses",
    "build_module_adapter_from_config",
]


def _adapter_class_for(module_type: ModuleType):
    if module_type == ModuleType.COMMUNITY:
        return CommunityModuleAdapter
    if module_type == ModuleType.CURATED:
        return CuratedModuleAdapter
    raise RuntimeError(f"Unsupported module type: {module_type!s}")


def build_module_adapter_from_addresses(
    addresses: ContractAddresses,
    w3: AsyncWeb3,
    module_ui_url: str | None,
    chain: ConnectOnDemand,
) -> ModuleAdapter:
    adapter_class = _adapter_class_for(addresses.module_type)
    contract_abis = adapter_class.contract_abis_for(addresses)
    contracts = adapter_class.build_contracts(w3, addresses, contract_abis)
    return adapter_class(
        addresses=addresses,
        contracts=contracts,
        contract_abis=contract_abis,
        module_ui_url=module_ui_url,
        chain=chain,
    )


def build_module_adapter_from_config(
    cfg: "Config",
    w3: AsyncWeb3,
    chain: ConnectOnDemand,
) -> ModuleAdapter:
    addresses = ContractAddresses(
        module=cfg.module_address,
        accounting=cfg.accounting_address,
        parameters_registry=cfg.parameters_registry_address,
        fee_distributor=cfg.fee_distributor_address,
        exit_penalties=cfg.exit_penalties_address,
        lido_locator=cfg.lido_locator_address,
        staking_router=cfg.staking_router_address,
        vebo=cfg.vebo_address,
        staking_module_id=cfg.staking_module_id,
        module_type=cfg.module_type,
        csm_version=cfg.csm_version,
    )
    return build_module_adapter_from_addresses(addresses, w3, cfg.module_ui_url, chain)
