from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import aiohttp

DistributionLogFetcher = Callable[[str], Awaitable[dict | list]]


@dataclass(frozen=True, slots=True)
class DistributionStrikeSummary:
    all_operator_ids: set[str]
    strikes_per_operator: dict[str, list[tuple[str, int]]]


async def default_distribution_log_fetcher(log_cid: str):
    ipfs_url = f"https://ipfs.io/ipfs/{log_cid}"
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(ipfs_url) as response:
            if response.status != 200:
                raise aiohttp.ClientError(f"HTTP {response.status} when fetching {ipfs_url}")
            return await response.json()


def validator_sort_key(validator_id: str) -> tuple[int, int | str]:
    validator_str = str(validator_id)
    if validator_str.isdigit():
        return 0, int(validator_str)
    return 1, validator_str


def parse_distribution_log(payload: dict | list) -> DistributionStrikeSummary:
    entries = payload if isinstance(payload, list) else [payload]
    all_operator_ids: set[str] = set()
    strikes_per_operator: dict[str, list[tuple[str, int]]] = {}

    for entry in entries:
        operators = entry.get("operators", {}) or {}
        for operator_id, operator_data in operators.items():
            operator_id_str = str(operator_id)
            all_operator_ids.add(operator_id_str)

            validators = operator_data.get("validators", {}) or {}
            for validator_id, validator_data in validators.items():
                strikes = int(validator_data.get("strikes", 0))
                if strikes <= 0:
                    continue
                strikes_per_operator.setdefault(operator_id_str, []).append(
                    (str(validator_id), strikes)
                )

    return DistributionStrikeSummary(
        all_operator_ids=all_operator_ids,
        strikes_per_operator=strikes_per_operator,
    )
