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

# Import from fileglancer-central
from fileglancer_central import database as db
from fileglancer_central.settings import get_settings


def update_file_share_paths(db_url: str) -> bool:
    """
    Update file share paths from wiki if needed.

    Args:
        db_url: Database URL to use

    Returns:
        True if update was performed, False otherwise
    """
    # Import wiki module from current package
    from fileglancer_janelia.wiki import get_file_share_paths

    with db.get_db_session(db_url) as session:
        # Get the last refresh time from the database
        last_refresh = db.get_last_refresh(session, "file_share_paths")

        logger.info("Checking for updates to file share paths...")

        try:
            # Get updated paths from the wiki
            new_paths, table_last_updated = get_file_share_paths()

            # Check if the wiki data has actually changed
            if last_refresh and table_last_updated == last_refresh.source_last_updated:
                logger.info("Wiki has not changed since last update, skipping refresh")
                return False

            logger.info("Wiki has changed, refreshing file share paths...")
            db.update_file_share_paths(session, new_paths, table_last_updated)
            logger.info(f"Successfully updated {len(new_paths)} file share paths")
            return True

        except Exception as e:
            logger.error(f"Error updating file share paths: {e}")
            raise


def update_external_buckets(db_url: str) -> bool:
    """
    Update external buckets from wiki if needed.

    Args:
        db_url: Database URL to use

    Returns:
        True if update was performed, False otherwise
    """
    # Import wiki module from current package
    from fileglancer_janelia.wiki import get_external_buckets

    with db.get_db_session(db_url) as session:
        # Get the last refresh time from the database
        last_refresh = db.get_last_refresh(session, "external_buckets")

        logger.info("Checking for updates to external buckets...")

        try:
            # Get updated buckets from the wiki
            new_buckets, table_last_updated = get_external_buckets()

            # Check if the wiki data has actually changed
            if last_refresh and table_last_updated == last_refresh.source_last_updated:
                logger.info("Wiki has not changed since last update, skipping refresh")
                return False

            logger.info("Wiki has changed, refreshing external buckets...")
            db.update_external_buckets(session, new_buckets, table_last_updated)
            logger.info(f"Successfully updated {len(new_buckets)} external buckets")
            return True

        except Exception as e:
            logger.error(f"Error updating external buckets: {e}")
            raise


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

    try:
        # Update file share paths
        fsp_updated = update_file_share_paths(settings.db_url)

        # Update external buckets
        buckets_updated = update_external_buckets(settings.db_url)

        if fsp_updated or buckets_updated:
            logger.info("Database update completed successfully")
        else:
            logger.info("No updates were necessary")

    except Exception as e:
        logger.exception(f"Failed to update database: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
