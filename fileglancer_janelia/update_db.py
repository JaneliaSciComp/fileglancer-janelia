#!/usr/bin/env python
"""
Script to update the Fileglancer database with information from the Janelia wiki.
This script is designed to be run on a cron schedule (e.g., every 5 minutes)
to keep the database up to date with FSPs and external buckets from the wiki.

The script checks if data is older than 1 day and updates if necessary.
"""

import sys
from datetime import datetime
from loguru import logger

from fileglancer.database import (
    FileSharePathDB,
    ExternalBucketDB,
    LastRefreshDB,
    get_db_session,
    get_last_refresh,
)
from fileglancer.settings import get_settings

def _compare_datetimes(dt1, dt2):
    """Compare two datetimes, ignoring timezone information"""
    return dt1.replace(tzinfo=None) == dt2.replace(tzinfo=None)

from datetime import UTC

def update_file_share_paths(session, paths, table_last_updated, max_paths_to_delete=2):
    """Update database with new file share paths"""
    # Get all existing mount_paths from database
    existing_paths = {path[0] for path in session.query(FileSharePathDB.mount_path).all()}
    new_paths = set()
    num_existing = 0
    num_new = 0

    # Update or insert records
    for path_dict in paths:
        mount_path = path_dict['mount_path']
        new_paths.add(mount_path)

        # Check if path exists
        existing_record = session.query(FileSharePathDB).filter_by(mount_path=mount_path).first()

        if existing_record:
            # Update existing record
            existing_record.name = path_dict['name']
            existing_record.zone = path_dict['zone']
            existing_record.group = path_dict['group']
            existing_record.storage = path_dict['storage']
            existing_record.mount_path = path_dict['mount_path']
            existing_record.mac_path = path_dict['mac_path']
            existing_record.windows_path = path_dict['windows_path']
            existing_record.linux_path = path_dict['linux_path']
            num_existing += 1
        else:
            # Create new record from dictionary
            new_path = FileSharePathDB(
                name=path_dict['name'],
                zone=path_dict['zone'],
                group=path_dict['group'],
                storage=path_dict['storage'],
                mount_path=path_dict['mount_path'],
                mac_path=path_dict['mac_path'],
                windows_path=path_dict['windows_path'],
                linux_path=path_dict['linux_path']
            )
            session.add(new_path)
            num_new += 1

    logger.debug(f"Updated {num_existing} file share paths, added {num_new} file share paths")

    # Delete records that no longer exist in the source
    paths_to_delete = existing_paths - new_paths
    if paths_to_delete:
        if len(paths_to_delete) > max_paths_to_delete:
            logger.warning(f"Cannot delete {len(paths_to_delete)} defunct file share paths from the database, only {max_paths_to_delete} are allowed")
        else:
            logger.debug(f"Deleting {len(paths_to_delete)} defunct file share paths from the database")
            session.query(FileSharePathDB).filter(FileSharePathDB.linux_path.in_(paths_to_delete)).delete(synchronize_session='fetch')

    # Update last refresh time
    table_name = "file_share_paths"
    session.query(LastRefreshDB).filter_by(table_name=table_name).delete()
    session.add(LastRefreshDB(table_name=table_name, source_last_updated=table_last_updated, db_last_updated=datetime.now(UTC)))

    session.commit()


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

        # Determine fsp_name and relative_path by finding matching FileSharePathDB
        fsp_name = None
        relative_path = None

        for fsp in all_fsp:
            if full_path.startswith(fsp.mount_path):
                fsp_name = fsp.name
                # Remove the mount_path prefix and any leading slash
                relative_path = full_path[len(fsp.mount_path):].lstrip('/')
                break

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


def check_file_share_paths(db_url: str) -> bool:
    """
    Update file share paths from wiki if needed.

    Args:
        db_url: Database URL to use

    Returns:
        True if update was performed, False otherwise
    """
    # Import wiki module from current package
    from fileglancer_janelia.wiki import get_file_share_paths

    with get_db_session(db_url) as session:
        # Get the last refresh time from the database
        last_refresh = get_last_refresh(session, "file_share_paths")
        # Get updated paths from the wiki
        new_paths, table_last_updated = get_file_share_paths()

        # Check if the wiki data has actually changed
        if last_refresh and _compare_datetimes(table_last_updated, last_refresh.source_last_updated):
            logger.info("File share paths have not changed, skipping update")
            return False

        logger.info("File share paths have changed, updating...")
        update_file_share_paths(session, new_paths, table_last_updated)
        logger.info(f"Successfully updated {len(new_paths)} file share paths")
        return True


def check_external_buckets(db_url: str) -> bool:
    """
    Update external buckets from wiki if needed.

    Args:
        db_url: Database URL to use

    Returns:
        True if update was performed, False otherwise
    """
    # Import wiki module from current package
    from fileglancer_janelia.wiki import get_external_buckets

    with get_db_session(db_url) as session:
        # Get the last refresh time from the database
        last_refresh = get_last_refresh(session, "external_buckets")
        # Get updated buckets from the wiki
        new_buckets, table_last_updated = get_external_buckets()

        # Check if the wiki data has actually changed
        if last_refresh and _compare_datetimes(table_last_updated, last_refresh.source_last_updated):
            logger.info("External buckets have not changed, skipping update")
            return False

        logger.info("External buckets have changed, updating...")
        update_external_buckets(session, new_buckets, table_last_updated)
        logger.info(f"Successfully updated {len(new_buckets)} external buckets")
        return True


def main():
    """Main entry point for the update script"""
    # Configure logging
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    # Get settings
    settings = get_settings()

    if not settings.atlassian_url:
        logger.error("Atlassian URL is not configured. Cannot update from wiki.")
        sys.exit(1)

    logger.info("Starting database update from wiki")
    logger.info(f"Database URL: {settings.db_url}")

    error = False
    try:
        check_file_share_paths(settings.db_url)
    except Exception as e:
        logger.exception(f"Error updating file share paths: {e}")
        error = True

    try:
        check_external_buckets(settings.db_url)
    except Exception as e:
        logger.exception(f"Error updating external buckets: {e}")
        error = True

    if error:
        sys.exit(1)

if __name__ == "__main__":
    main()
