import hashlib
import json
from functools import lru_cache

from config import settings
from config.logging import logger

manifest_data = {}
manifest_path = settings.root / "static" / "build" / ".vite" / "manifest.json"
if manifest_path.exists():
    with open(manifest_path) as file:
        manifest_data = json.load(file)
elif not settings.asset_building_enabled:
    logger.warning(f"Vite manifest is missing! Expected at {manifest_path}")


@lru_cache(maxsize=1)
def asset_version_hash() -> str:
    if not manifest_data:
        return settings.github_sha or "development"

    sorted_files = sorted((entry.get("file", "") for entry in manifest_data.values() if entry.get("file")), key=str)
    combined = "".join(sorted_files)
    return hashlib.sha256(combined.encode()).hexdigest()[:12]
