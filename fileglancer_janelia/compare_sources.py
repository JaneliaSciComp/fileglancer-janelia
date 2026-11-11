#!/usr/bin/env python
"""
Dry run of switching FILEGLANCER_JANELIA_SOURCE from the wiki to the
file-paths-service, using the real update code on a scratch database.

    pixi run compare-sources
    pixi run compare-sources --reference-db-url <url of a database copy>

1. A scratch SQLite database is filled from the wiki, as a wiki-fed server's is.
2. The file-paths-service data is then applied with the same update functions.
3. The report lists shares added, changed and to be deleted (or refused by the
   delete limit), and buckets added, changed and removed.

Nothing outside the scratch database is written. With --reference-db-url, the
names that would be deleted are looked up, read-only, in that database's data
links, tickets, jobs and user preferences, so a cleanup doesn't orphan them.

Needs the wiki settings (FGC_ATLASSIAN_URL, FGC_ATLASSIAN_USERNAME,
FGC_ATLASSIAN_TOKEN) and the Janelia network.
"""

import argparse
import sys
import tempfile
from pathlib import Path

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from fileglancer.database import Base, ExternalBucketDB, FileSharePathDB

from fileglancer_janelia import file_paths_service, wiki
from fileglancer_janelia.update_db import update_external_buckets, update_file_share_paths

SHARE_FIELDS = ("zone", "group", "storage", "mount_path", "mac_path", "windows_path", "linux_path")

# Where other tables refer to a share by name.
NAME_REFERENCES = {
    "data links (proxied_paths.fsp_name)": "SELECT COUNT(*) FROM proxied_paths WHERE fsp_name = :name",
    "tickets (tickets.fsp_name)": "SELECT COUNT(*) FROM tickets WHERE fsp_name = :name",
    "jobs (jobs.work_dir_fsp_name)": "SELECT COUNT(*) FROM jobs WHERE work_dir_fsp_name = :name",
    "user preferences (value mentions it)": "SELECT COUNT(*) FROM user_preferences WHERE CAST(value AS TEXT) LIKE :quoted_name",
}


def snapshot(session) -> tuple[dict, dict]:
    shares = {
        record.name: {field: getattr(record, field) for field in SHARE_FIELDS}
        for record in session.query(FileSharePathDB)
    }
    buckets = {
        record.full_path: {"external_url": record.external_url, "fsp_name": record.fsp_name,
                           "relative_path": record.relative_path}
        for record in session.query(ExternalBucketDB)
    }
    return shares, buckets


def capture_warnings():
    captured = []
    handler_id = logger.add(lambda message: captured.append(message.record["message"]), level="WARNING")
    return captured, handler_id


def compare(scratch_db_path: Path) -> dict:
    engine = create_engine(f"sqlite:///{scratch_db_path}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    wiki_paths, wiki_updated = wiki.get_file_share_paths()
    update_file_share_paths(session, wiki_paths, wiki_updated)
    wiki_buckets, wiki_buckets_updated = wiki.get_external_buckets()
    update_external_buckets(session, wiki_buckets, wiki_buckets_updated)
    wiki_shares, wiki_bucket_rows = snapshot(session)

    warnings, handler_id = capture_warnings()
    service_paths, service_updated = file_paths_service.get_file_share_paths()
    update_file_share_paths(session, service_paths, service_updated)
    service_buckets, service_buckets_updated = file_paths_service.get_external_buckets()
    update_external_buckets(session, service_buckets, service_buckets_updated)
    logger.remove(handler_id)
    service_shares, service_bucket_rows = snapshot(session)
    session.close()

    service_names = {path["name"] for path in service_paths}
    return {
        "wiki_count": len(wiki_shares),
        "service_count": len(service_paths),
        "added": sorted(set(service_shares) - set(wiki_shares)),
        "changed": {
            name: {field: (wiki_shares[name][field], service_shares[name][field])
                   for field in SHARE_FIELDS if wiki_shares[name][field] != service_shares[name][field]}
            for name in sorted(set(wiki_shares) & set(service_shares))
            if wiki_shares[name] != service_shares[name]
        },
        # Wiki shares the service doesn't list: deleted, or kept if over the limit.
        "not_in_service": sorted(set(wiki_shares) - service_names),
        "deleted": sorted(set(wiki_shares) - set(service_shares)),
        "buckets_added": sorted(set(service_bucket_rows) - set(wiki_bucket_rows)),
        "buckets_removed": sorted(set(wiki_bucket_rows) - set(service_bucket_rows)),
        "buckets_changed": {
            full_path: (wiki_bucket_rows[full_path], service_bucket_rows[full_path])
            for full_path in sorted(set(wiki_bucket_rows) & set(service_bucket_rows))
            if wiki_bucket_rows[full_path] != service_bucket_rows[full_path]
        },
        "warnings": warnings,
        "wiki_shares": wiki_shares,
    }


def check_references(reference_db_url: str, names: list[str]) -> dict[str, dict[str, int]]:
    """Read-only: how often each name is referenced in another database."""
    engine = create_engine(reference_db_url)
    references = {}
    with engine.connect() as connection:
        for name in names:
            counts = {}
            for description, query in NAME_REFERENCES.items():
                try:
                    counts[description] = connection.execute(
                        text(query), {"name": name, "quoted_name": f'%"{name}"%'}
                    ).scalar()
                except Exception as query_error:  # a table this database doesn't have
                    counts[description] = f"not checked ({type(query_error).__name__})"
                    connection.rollback()
            references[name] = counts
    return references


def print_report(result: dict, references: dict | None) -> None:
    print(f"Shares: wiki {result['wiki_count']}, file-paths-service {result['service_count']}")

    print(f"\n## Shares the switch would add ({len(result['added'])})")
    for name in result["added"]:
        print(f"  {name}")

    print(f"\n## Shares the switch would change ({len(result['changed'])})")
    for name, changes in result["changed"].items():
        described = "; ".join(f"{field}: {before!r} -> {after!r}" for field, (before, after) in changes.items())
        print(f"  {name}: {described}")

    not_in_service = result["not_in_service"]
    print(f"\n## Wiki shares the file-paths-service doesn't list ({len(not_in_service)})")
    for name in not_in_service:
        status = "deleted" if name in result["deleted"] else "kept: over the delete limit"
        print(f"  {name} ({result['wiki_shares'][name]['mount_path']}): {status}")
        if references and name in references:
            for description, count in references[name].items():
                print(f"      {description}: {count}")

    print(f"\n## Buckets added ({len(result['buckets_added'])})")
    for full_path in result["buckets_added"]:
        print(f"  {full_path}")
    print(f"\n## Buckets removed ({len(result['buckets_removed'])})")
    for full_path in result["buckets_removed"]:
        print(f"  {full_path}")
    print(f"\n## Buckets changed ({len(result['buckets_changed'])})")
    for full_path, (before, after) in result["buckets_changed"].items():
        print(f"  {full_path}: {before} -> {after}")

    if result["warnings"]:
        print(f"\n## Warnings from the update ({len(result['warnings'])})")
        for warning in result["warnings"]:
            print(f"  {warning}")


def main():
    argument_parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    argument_parser.add_argument(
        "--reference-db-url",
        help="a database to check, read-only, for references to shares that would be deleted",
    )
    arguments = argument_parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="ERROR")

    with tempfile.TemporaryDirectory() as scratch_dir:
        result = compare(Path(scratch_dir) / "scratch.db")
    references = (
        check_references(arguments.reference_db_url, result["not_in_service"])
        if arguments.reference_db_url and result["not_in_service"]
        else None
    )
    print_report(result, references)


if __name__ == "__main__":
    main()
