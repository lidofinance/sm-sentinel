import asyncio
import logging
import os
from dataclasses import dataclass

from sentinel.app.contracts import ContractAddresses, log_discovered_addresses

logger = logging.getLogger(__name__)


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for token in raw.replace(" ", ",").split(","):
        if not token:
            continue
        try:
            ids.add(int(token))
        except ValueError:
            # Ignore invalid entries silently at config load time
            continue
    return ids


@dataclass(frozen=True)
class Config:
    # Paths and tokens
    filestorage_path: str
    token: str | None
    web3_socket_provider: str
    healthcheck_host: str
    healthcheck_port: int

    contract_addresses: ContractAddresses

    # URLs
    etherscan_url: str | None
    beaconchain_url: str | None
    module_ui_url: str | None

    # Other
    block_batch_size: int
    process_blocks_requests_per_second: float | None
    block_from: int | None
    admin_ids: set[int]

    # Derived URL templates
    @property
    def etherscan_block_url_template(self) -> str | None:
        return None if not self.etherscan_url else f"{self.etherscan_url}/block/{{}}"

    @property
    def etherscan_tx_url_template(self) -> str | None:
        return None if not self.etherscan_url else f"{self.etherscan_url}/tx/{{}}"

    @property
    def beaconchain_url_template(self) -> str | None:
        return None if not self.beaconchain_url else f"{self.beaconchain_url}/validator/{{}}"


_CONFIG: Config | None = None
RPC_DISCOVERY_TIMEOUT_SECONDS = 30
RPC_DISCOVERY_RETRY_DELAY_SECONDS = 10


def _parse_healthcheck_port(raw: str | None) -> int:
    if not raw:
        return 8080
    port = int(raw)
    if port <= 0 or port > 65535:
        raise RuntimeError("HEALTHCHECK_PORT must be between 1 and 65535")
    return port


def get_healthcheck_bind_from_env() -> tuple[str, int]:
    return (
        os.getenv("HEALTHCHECK_HOST", "0.0.0.0"),
        _parse_healthcheck_port(os.getenv("HEALTHCHECK_PORT")),
    )


async def _build_config_from_env() -> Config:
    filestorage_path = os.getenv("FILESTORAGE_PATH", ".storage")
    token = os.getenv("TOKEN")
    web3_socket_provider = os.getenv("WEB3_SOCKET_PROVIDER")
    healthcheck_host, healthcheck_port = get_healthcheck_bind_from_env()
    module_address = os.getenv("MODULE_ADDRESS")

    if not web3_socket_provider:
        raise RuntimeError("WEB3_SOCKET_PROVIDER must be configured")
    if not module_address:
        raise RuntimeError("MODULE_ADDRESS must be configured")

    addresses = await _discover_contract_addresses_with_retry(
        web3_socket_provider,
        module_address,
    )

    process_blocks_requests_per_second = os.getenv("PROCESS_BLOCKS_REQUESTS_PER_SECOND")
    if process_blocks_requests_per_second:
        process_blocks_requests_per_second = float(process_blocks_requests_per_second)
        if process_blocks_requests_per_second <= 0:
            raise RuntimeError("PROCESS_BLOCKS_REQUESTS_PER_SECOND must be positive")
    else:
        process_blocks_requests_per_second = None

    raw_block_from = os.getenv("BLOCK_FROM")
    block_from = int(raw_block_from) if raw_block_from else None

    return Config(
        filestorage_path=filestorage_path,
        token=token,
        web3_socket_provider=web3_socket_provider,
        healthcheck_host=healthcheck_host,
        healthcheck_port=healthcheck_port,
        contract_addresses=addresses,
        etherscan_url=os.getenv("ETHERSCAN_URL"),
        beaconchain_url=os.getenv("BEACONCHAIN_URL"),
        module_ui_url=os.getenv("MODULE_UI_URL"),
        block_batch_size=int(os.getenv("BLOCK_BATCH_SIZE", 10_000)),
        process_blocks_requests_per_second=process_blocks_requests_per_second,
        block_from=block_from,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
    )


def get_config() -> Config:
    global _CONFIG
    if _CONFIG is None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            _CONFIG = asyncio.run(_build_config_from_env())
        else:
            raise RuntimeError(
                "get_config() cannot be called from an async context, use get_config_async() instead"
            )
    return _CONFIG


async def get_config_async() -> Config:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = await _build_config_from_env()
    return _CONFIG


def set_config(config: Config) -> None:
    global _CONFIG
    _CONFIG = config


def clear_config() -> None:
    """Basically for tests."""
    global _CONFIG
    _CONFIG = None


async def _discover_contract_addresses(provider_url: str, module_address: str):
    from sentinel.app.contracts import discover_contract_addresses_from_url

    return await discover_contract_addresses_from_url(provider_url, module_address)


async def _discover_contract_addresses_with_retry(provider_url: str, module_address: str):
    attempt = 1
    while True:
        try:
            addresses = await asyncio.wait_for(
                _discover_contract_addresses(provider_url, module_address),
                timeout=RPC_DISCOVERY_TIMEOUT_SECONDS,
            )
            log_discovered_addresses(addresses)
            return addresses
        except asyncio.TimeoutError:
            logger.warning(
                "Timed out discovering contract addresses from WEB3 provider after %ss "
                "(attempt %s). Retrying in %ss.",
                RPC_DISCOVERY_TIMEOUT_SECONDS,
                attempt,
                RPC_DISCOVERY_RETRY_DELAY_SECONDS,
            )
            attempt += 1
            await asyncio.sleep(RPC_DISCOVERY_RETRY_DELAY_SECONDS)
