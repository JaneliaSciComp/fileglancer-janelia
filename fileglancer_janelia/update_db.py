#!/usr/bin/env python
"""
Script to update the Fileglancer database with file share paths and external
buckets. This script is designed to be run on a schedule (e.g., every 5 minutes).

The source is chosen with FILEGLANCER_JANELIA_SOURCE:
    wiki                  the Janelia wiki pages (the default)
    file-paths-service    https://filepaths.int.janelia.org (see file_paths_service.py)

Each run compares the source's last-updated time with the one stored in the
database and only writes when the data has changed.
"""

import argparse
import os
import sys
from datetime import datetime
from types import ModuleType

from loguru import logger

from fileglancer.database import (
    FileSharePathDB,
    ExternalBucketDB,
    LastRefreshDB,
    get_db_session,
    get_last_refresh,
)
from fileglancer.settings import get_settings

SOURCES = ("wiki", "file-paths-service")


def get_source_name() -> str:
    source_name = os.environ.get("FILEGLANCER_JANELIA_SOURCE", "wiki").strip().lower()
    if source_name not in SOURCES:
        raise ValueError(f"FILEGLANCER_JANELIA_SOURCE must be one of {', '.join(SOURCES)}, not {source_name!r}")
    return source_name


def get_source(source_name: str | None = None) -> ModuleType:
    """The module providing get_file_share_paths() and get_external_buckets()"""
    if (source_name or get_source_name()) == "file-paths-service":
        from fileglancer_janelia import file_paths_service
        return file_paths_service
    from fileglancer_janelia import wiki
    return wiki


def _compare_datetimes(dt1, dt2):
    """Compare two datetimes, ignoring timezone information"""
    return dt1.replace(tzinfo=None) == dt2.replace(tzinfo=None)

from datetime import UTC

def update_file_share_paths(session, paths, table_last_updated, max_paths_to_delete=2):
    """Update database with new file share paths.

    Existing records are matched by name first, then by mount path. The name is
    what favourites, data links and tickets refer to, and two sources can spell
    the same share's path differently (the wiki once had /groups//zebrafishbbl/home),
    so matching by path alone could insert a duplicate name and fail.
    Records that no longer match anything are deleted, at most
    max_paths_to_delete per run.
    """
    existing_records = session.query(FileSharePathDB).all()
    records_by_name = {record.name: record for record in existing_records}
    records_by_mount_path = {record.mount_path: record for record in existing_records}
    matched_record_ids = set()
    num_existing = 0
    num_new = 0

    for path_dict in paths:
        existing_record = records_by_name.get(path_dict['name']) or records_by_mount_path.get(path_dict['mount_path'])
        if existing_record and existing_record.id in matched_record_ids:
            logger.warning(f"Skipping {path_dict['mount_path']}: its record was already updated by another entry")
            continue

        if existing_record:
            existing_record.name = path_dict['name']
            existing_record.zone = path_dict['zone']
            existing_record.group = path_dict['group']
            existing_record.storage = path_dict['storage']
            existing_record.mount_path = path_dict['mount_path']
            existing_record.mac_path = path_dict['mac_path']
            existing_record.windows_path = path_dict['windows_path']
            existing_record.linux_path = path_dict['linux_path']
            matched_record_ids.add(existing_record.id)
            num_existing += 1
        else:
            new_record = FileSharePathDB(
                name=path_dict['name'],
                zone=path_dict['zone'],
                group=path_dict['group'],
                storage=path_dict['storage'],
                mount_path=path_dict['mount_path'],
                mac_path=path_dict['mac_path'],
                windows_path=path_dict['windows_path'],
                linux_path=path_dict['linux_path']
            )
            session.add(new_record)
            # Later entries with the same name or path find this one, not a duplicate.
            session.flush()
            records_by_name[new_record.name] = new_record
            records_by_mount_path[new_record.mount_path] = new_record
            matched_record_ids.add(new_record.id)
            num_new += 1

    logger.debug(f"Updated {num_existing} file share paths, added {num_new} file share paths")

    # Delete records that no longer exist in the source
    records_to_delete = [record for record in existing_records if record.id not in matched_record_ids]
    if records_to_delete:
        defunct_paths = ", ".join(sorted(record.mount_path for record in records_to_delete))
        if len(records_to_delete) > max_paths_to_delete:
            logger.warning(f"Cannot delete {len(records_to_delete)} defunct file share paths from the database, only {max_paths_to_delete} are allowed: {defunct_paths}")
        else:
            logger.debug(f"Deleting {len(records_to_delete)} defunct file share paths from the database: {defunct_paths}")
            for record in records_to_delete:
                session.delete(record)

    # Update last refresh time
    table_name = "file_share_paths"
    session.query(LastRefreshDB).filter_by(table_name=table_name).delete()
    session.add(LastRefreshDB(table_name=table_name, source_last_updated=table_last_updated, db_last_updated=datetime.now(UTC)))

    session.commit()


def find_owning_share(full_path, file_share_paths):
    """The share whose mount path contains full_path, on whole directory names.

    The longest match wins, so /nrs/funkelab/bucket goes to /nrs/funkelab and
    never to /nrs/funke, and a share inside another share wins over its parent.
    """
    normalized_path = full_path.rstrip('/')
    containing_shares = [
        fsp for fsp in file_share_paths
        if normalized_path == fsp.mount_path.rstrip('/')
        or normalized_path.startswith(fsp.mount_path.rstrip('/') + '/')
    ]
    return max(containing_shares, key=lambda fsp: len(fsp.mount_path.rstrip('/')), default=None)


def update_external_buckets(session, buckets, table_last_updated):
    """Update database with new external buckets"""
    # Get all file share paths to determine fsp_name and relative_path
    all_fsp = session.query(FileSharePathDB).all()

    # Get all existing external buckets from database
    existing_buckets = {bucket[0] for bucket in session.query(ExternalBucketDB.full_path).all()}
    new_buckets = set()
    num_existing = 0
    num_new = 0

    # Update or insert records
    for bucket_dict in buckets:
        full_path = bucket_dict['full_path']
        external_url = bucket_dict['external_url']
        new_buckets.add(full_path)

        # Determine fsp_name and relative_path from the share that contains the bucket
        owning_fsp = find_owning_share(full_path, all_fsp)
        fsp_name = owning_fsp.name if owning_fsp else None
        relative_path = full_path[len(owning_fsp.mount_path.rstrip('/')):].lstrip('/') if owning_fsp else None

        if fsp_name is None:
            logger.warning(f"Could not find matching file share path for external bucket: {full_path}")
            continue  # Skip buckets without matching file share paths

        # Check if bucket exists
        existing_record = session.query(ExternalBucketDB).filter_by(full_path=full_path).first()

        if existing_record:
            # Update existing record
            existing_record.external_url = external_url
            existing_record.fsp_name = fsp_name
            existing_record.relative_path = relative_path
            num_existing += 1
        else:
            # Create new record with determined fsp_name and relative_path
            new_bucket = ExternalBucketDB(
                full_path=full_path,
                external_url=external_url,
                fsp_name=fsp_name,
                relative_path=relative_path
            )
            session.add(new_bucket)
            num_new += 1

    logger.debug(f"Updated {num_existing} external buckets, added {num_new} external buckets")

    # Delete records that no longer exist
    buckets_to_delete = existing_buckets - new_buckets
    if buckets_to_delete:
        logger.debug(f"Deleting {len(buckets_to_delete)} defunct external buckets from the database")
        session.query(ExternalBucketDB).filter(ExternalBucketDB.full_path.in_(buckets_to_delete)).delete(synchronize_session='fetch')

    # Update last refresh time
    table_name = "external_buckets"
    session.query(LastRefreshDB).filter_by(table_name=table_name).delete()
    session.add(LastRefreshDB(table_name=table_name, source_last_updated=table_last_updated, db_last_updated=datetime.now(UTC)))

    session.commit()


def check_file_share_paths(db_url: str, source: ModuleType | None = None,
                           max_paths_to_delete: int = 2, force: bool = False) -> bool:
    """
    Update file share paths from the source if needed.

    Args:
        db_url: Database URL to use
        source: Module to read from (default: the one FILEGLANCER_JANELIA_SOURCE selects)
        max_paths_to_delete: Most defunct paths one run may delete
        force: Update even if the source's last-updated time hasn't changed

    Returns:
        True if update was performed, False otherwise
    """
    source = source or get_source()

    with get_db_session(db_url) as session:
        # Get the last refresh time from the database
        last_refresh = get_last_refresh(session, "file_share_paths")
        # Get updated paths from the source
        new_paths, table_last_updated = source.get_file_share_paths()

        # Check if the source data has actually changed
        if not force and last_refresh and _compare_datetimes(table_last_updated, last_refresh.source_last_updated):
            logger.info("File share paths have not changed, skipping update")
            return False

        logger.info("File share paths have changed, updating..." if not force else "Updating file share paths (forced)...")
        update_file_share_paths(session, new_paths, table_last_updated, max_paths_to_delete=max_paths_to_delete)
        logger.info(f"Successfully updated {len(new_paths)} file share paths")
        return True


def check_external_buckets(db_url: str, source: ModuleType | None = None) -> bool:
    """
    Update external buckets from the source if needed.

    Args:
        db_url: Database URL to use
        source: Module to read from (default: the one FILEGLANCER_JANELIA_SOURCE selects)

    Returns:
        True if update was performed, False otherwise
    """
    source = source or get_source()

    with get_db_session(db_url) as session:
        # Get the last refresh time from the database
        last_refresh = get_last_refresh(session, "external_buckets")
        # Get updated buckets from the source
        new_buckets, table_last_updated = source.get_external_buckets()

        # Check if the source data has actually changed
        if last_refresh and _compare_datetimes(table_last_updated, last_refresh.source_last_updated):
            logger.info("External buckets have not changed, skipping update")
            return False

        logger.info("External buckets have changed, updating...")
        update_external_buckets(session, new_buckets, table_last_updated)
        logger.info(f"Successfully updated {len(new_buckets)} external buckets")
        return True


def main():
    """Main entry point for the update script"""
    argument_parser = argparse.ArgumentParser(description="Update Fileglancer's file share paths and external buckets")
    argument_parser.add_argument(
        "--max-deletes", type=int, default=2,
        help="most defunct file share paths to delete in this run (default 2). Raise it only for a "
             "one-off cleanup, after checking the names aren't referenced (see compare_sources).",
    )
    argument_parser.add_argument(
        "--force", action="store_true",
        help="update file share paths even if the source hasn't changed (e.g. for a cleanup run)",
    )
    arguments = argument_parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    # Get settings
    settings = get_settings()

    try:
        source_name = get_source_name()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    if source_name == "wiki" and not settings.atlassian_url:
        logger.error("Atlassian URL is not configured. Cannot update from wiki.")
        sys.exit(1)

    source = get_source(source_name)
    logger.info(f"Starting database update from {source_name}")
    logger.info(f"Database URL: {settings.db_url}")

    error = False
    try:
        check_file_share_paths(settings.db_url, source,
                               max_paths_to_delete=arguments.max_deletes, force=arguments.force)
    except Exception as e:
        logger.exception(f"Error updating file share paths: {e}")
        error = True

    try:
        check_external_buckets(settings.db_url, source)
    except Exception as e:
        logger.exception(f"Error updating external buckets: {e}")
        error = True

    if error:
        sys.exit(1)

if __name__ == "__main__":
    main()
