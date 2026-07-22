import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BUILD_INFO_PATH = Path("build-info.json")
DEFAULT_BUILD_INFO = {
    "version": "dev",
    "branch": "unknown",
    "commit": "unknown",
}


def load_build_info(path: Path = BUILD_INFO_PATH) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        return DEFAULT_BUILD_INFO.copy()
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load build info from %s", path, exc_info=True)
        return DEFAULT_BUILD_INFO.copy()

    if not isinstance(payload, dict):
        logger.warning("Ignoring malformed build info from %s", path)
        return DEFAULT_BUILD_INFO.copy()

    return {key: str(payload.get(key, default)) for key, default in DEFAULT_BUILD_INFO.items()}
