"""
Fetch file share paths and external buckets from the file-paths-service.

https://github.com/JaneliaScientificComputingSystems/file-paths-service curates
the share list from vaststats (lab names, AD groups, hidden shares) and
replaces the wiki page "Lab and Project File Share Paths". Its records already
use Fileglancer's field names, so this module returns the same shapes as
wiki.py and update_db.py doesn't care which one it is reading.

Settings, from the environment (deliberately not FGC_*, which Fileglancer's
own settings read from the shared .env file):
    FILE_PATHS_SERVICE_URL       default https://filepaths.int.janelia.org
    FILE_PATHS_SERVICE_TIMEOUT   seconds, default 60
"""

import os
from datetime import datetime
from urllib.parse import urlparse

import requests
from loguru import logger

from fileglancer.utils import slugify_path

DEFAULT_SERVICE_URL = "https://filepaths.int.janelia.org"


def service_url() -> str:
    """The service's base URL. The service decides which directories Fileglancer
    serves, so it is only read over https (or from this machine)."""
    configured_url = os.environ.get("FILE_PATHS_SERVICE_URL", DEFAULT_SERVICE_URL).rstrip("/")
    parsed_url = urlparse(configured_url)
    is_local = parsed_url.scheme == "http" and parsed_url.hostname in ("localhost", "127.0.0.1")
    if parsed_url.scheme != "https" and not is_local:
        raise ValueError(f"FILE_PATHS_SERVICE_URL must use https, not {configured_url!r}")
    return configured_url


def _validate_share(record: dict) -> None:
    """Raise if a share record isn't safe to store. One bad record fails the
    whole fetch: leaving it out would make update_db delete the share."""
    linux_path = record["linux_path"]
    # Favourites, data links and tickets refer to a share by name, and the
    # wiki ingest has always named shares slugify_path(linux_path). Never
    # let a different naming scheme from upstream rename shares.
    expected_name = slugify_path(linux_path)
    if record["name"] != expected_name:
        raise ValueError(f"{linux_path}: service name {record['name']!r} is not the expected {expected_name!r}")
    # mount_path is the directory Fileglancer serves. Like the wiki ingest,
    # only accept the share's own linux_path, as a plain absolute path.
    mount_path = record["mount_path"]
    is_plain_absolute_path = (
        mount_path.startswith("/") and mount_path != "/" and os.path.normpath(mount_path) == mount_path
    )
    if mount_path != linux_path or not is_plain_absolute_path:
        raise ValueError(f"{linux_path}: mount path {mount_path!r} is not the share's plain absolute linux path")


def _get_dataset(api_path: str, records_key: str) -> tuple[list[dict], datetime]:
    """GET a dataset envelope. Raises on any HTTP error, including the 503 the
    service returns before its first load, so the caller keeps what it has."""
    timeout_seconds = float(os.environ.get("FILE_PATHS_SERVICE_TIMEOUT", "60"))
    response = requests.get(f"{service_url()}{api_path}", timeout=timeout_seconds)
    response.raise_for_status()
    envelope = response.json()
    # `updated_at` changes only when the published data changes, so it plays
    # the part of the wiki's lastUpdated in update_db's change check.
    return envelope[records_key], datetime.fromisoformat(envelope["updated_at"])


def get_file_share_paths() -> tuple[list[dict], datetime]:
    """Fetch the curated file share paths, in the shape wiki.get_file_share_paths returns"""
    records, updated_at = _get_dataset("/api/v1/paths", "paths")

    paths = []
    for record in records:
        _validate_share(record)
        paths.append({
            'name': record['name'],
            'zone': record['zone'],
            # The wiki ingest stores a missing group as ''.
            'group': record['group'] or '',
            'storage': record['storage'],
            'mount_path': record['mount_path'],
            'mac_path': record['mac_path'],
            'windows_path': record['windows_path'],
            'linux_path': record['linux_path'],
        })

    logger.debug(f"Found {len(paths)} file share paths in the file-paths-service")
    return paths, updated_at


def get_external_buckets() -> tuple[list[dict], datetime]:
    """Fetch the external buckets, in the shape wiki.get_external_buckets returns.

    These are the datasets published on s3.janelia.org. `listed=true` leaves
    out the ones the proxy serves but doesn't show in its listing (aliases and
    tests). Every record has a full_path, which update_db needs to find the
    owning share.
    """
    records, updated_at = _get_dataset("/api/v1/external-buckets?listed=true", "buckets")
    buckets = [
        {'full_path': record['full_path'], 'external_url': record['external_url']}
        for record in records
        if record.get('full_path') and record.get('external_url')
    ]
    logger.debug(f"Found {len(buckets)} external buckets in the file-paths-service")
    return buckets, updated_at
