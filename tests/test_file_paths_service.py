from datetime import datetime, UTC

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fileglancer.database import Base, ExternalBucketDB, FileSharePathDB, LastRefreshDB

from fileglancer_janelia import file_paths_service
from fileglancer_janelia.update_db import (
    find_owning_share,
    get_source,
    get_source_name,
    update_external_buckets,
    update_file_share_paths,
)

UPDATED_AT = "2026-11-06T14:35:39.292284+00:00"


def service_record(linux_path, zone="Zebrafish", group="zebrafishbbl", storage="home", name=None):
    """A record as GET /api/v1/paths returns it."""
    share_name = name or linux_path.strip("/").replace("/", "_")
    return {
        "name": share_name,
        "zone": zone,
        "group": group,
        "storage": storage,
        "mount_path": linux_path,
        "mac_path": f"smb://prfs.hhmi.org{linux_path}",
        "windows_path": "\\\\prfs.hhmi.org" + linux_path.replace("/", "\\"),
        "linux_path": linux_path,
        "system": "PRFS",
    }


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._body


@pytest.fixture
def fake_service(monkeypatch):
    """Replace requests.get; tests set responses by URL path."""
    responses = {}
    requested_urls = []

    def fake_get(url, timeout):
        requested_urls.append(url)
        for path, response in responses.items():
            if url.endswith(path):
                return response
        raise AssertionError(f"unexpected request to {url}")

    monkeypatch.setattr(file_paths_service.requests, "get", fake_get)
    monkeypatch.delenv("FILE_PATHS_SERVICE_URL", raising=False)
    return responses, requested_urls


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def as_path_dicts(records):
    """What file_paths_service.get_file_share_paths hands to update_file_share_paths."""
    return [{key: record[key] for key in (
        "name", "zone", "group", "storage", "mount_path", "mac_path", "windows_path", "linux_path"
    )} for record in records]


# ---------------------------------------------------------------- the service source


def test_paths_use_fileglancer_fields_and_blank_groups(fake_service):
    responses, requested_urls = fake_service
    responses["/api/v1/paths"] = FakeResponse(200, {
        "paths": [
            service_record("/groups/zebrafishbbl/home"),
            service_record("/nrs/alphafold", zone="Alphafold", group=None, storage="scratch"),
        ],
        "updated_at": UPDATED_AT,
    })
    paths, updated_at = file_paths_service.get_file_share_paths()
    assert requested_urls == ["https://filepaths.int.janelia.org/api/v1/paths"]
    assert updated_at == datetime(2026, 11, 6, 14, 35, 39, 292284, tzinfo=UTC)
    assert [path["name"] for path in paths] == ["groups_zebrafishbbl_home", "nrs_alphafold"]
    assert paths[1]["group"] == ""  # stored as '' like the wiki ingest
    assert set(paths[0]) == {"name", "zone", "group", "storage", "mount_path", "mac_path", "windows_path", "linux_path"}


def test_a_name_that_isnt_the_slugified_path_fails_the_fetch(fake_service):
    # Leaving the record out would make update_db delete the share.
    responses, _ = fake_service
    responses["/api/v1/paths"] = FakeResponse(200, {
        "paths": [
            service_record("/groups/abbott/abbottlab"),
            service_record("/groups/abbott/home", name="abbott-home"),
        ],
        "updated_at": UPDATED_AT,
    })
    with pytest.raises(ValueError, match="abbott-home"):
        file_paths_service.get_file_share_paths()


@pytest.mark.parametrize("linux_path, mount_path", [
    ("/groups/abbott/home", "/"),                       # not the share's own path
    ("/groups/abbott/home", "/groups/abbott"),
    ("/groups/abbott/../../etc", "/groups/abbott/../../etc"),
    ("/groups//abbott/home", "/groups//abbott/home"),
    ("~", "~"),
    ("groups/abbott/home", "groups/abbott/home"),
    ("/", "/"),
])
def test_a_mount_path_that_isnt_the_plain_linux_path_fails_the_fetch(fake_service, linux_path, mount_path):
    responses, _ = fake_service
    record = service_record(linux_path)
    record.update(name=file_paths_service.slugify_path(linux_path), mount_path=mount_path)
    responses["/api/v1/paths"] = FakeResponse(200, {"paths": [record], "updated_at": UPDATED_AT})
    with pytest.raises(ValueError, match="mount path"):
        file_paths_service.get_file_share_paths()


@pytest.mark.parametrize("configured_url, is_accepted", [
    ("https://filepaths-test.example", True),
    ("http://localhost:8000", True),
    ("http://filepaths.int.janelia.org", False),
    ("filepaths.int.janelia.org", False),
])
def test_service_url_must_be_https_or_local(monkeypatch, configured_url, is_accepted):
    monkeypatch.setenv("FILE_PATHS_SERVICE_URL", configured_url)
    if is_accepted:
        assert file_paths_service.service_url() == configured_url
    else:
        with pytest.raises(ValueError, match="https"):
            file_paths_service.service_url()


def test_service_not_ready_raises(fake_service):
    responses, _ = fake_service
    responses["/api/v1/paths"] = FakeResponse(503)
    with pytest.raises(requests.HTTPError):
        file_paths_service.get_file_share_paths()


def test_service_url_comes_from_the_environment(fake_service, monkeypatch):
    responses, requested_urls = fake_service
    monkeypatch.setenv("FILE_PATHS_SERVICE_URL", "https://filepaths-test.example/")
    responses["/api/v1/external-buckets?listed=true"] = FakeResponse(200, {"buckets": [], "updated_at": UPDATED_AT})
    file_paths_service.get_external_buckets()
    assert requested_urls == ["https://filepaths-test.example/api/v1/external-buckets?listed=true"]


def test_buckets_need_a_filesystem_path(fake_service):
    responses, _ = fake_service
    responses["/api/v1/external-buckets?listed=true"] = FakeResponse(200, {
        "buckets": [
            {"name": "janelia-mouselight", "external_url": "https://s3.janelia.org/janelia-mouselight/",
             "full_path": "/groups/mousebrainmicro/mousebrainmicro/s3", "bucket": "b", "system": "PRFS", "prefix": "",
             "listed": True},
            {"name": "unmatched", "external_url": "https://s3.janelia.org/unmatched/",
             "full_path": None, "bucket": None, "system": None, "prefix": None},
        ],
        "updated_at": UPDATED_AT,
    })
    buckets, _ = file_paths_service.get_external_buckets()
    assert buckets == [{
        "full_path": "/groups/mousebrainmicro/mousebrainmicro/s3",
        "external_url": "https://s3.janelia.org/janelia-mouselight/",
    }]


# ---------------------------------------------------------------- choosing the source


def test_source_defaults_to_the_wiki(monkeypatch):
    monkeypatch.delenv("FILEGLANCER_JANELIA_SOURCE", raising=False)
    assert get_source_name() == "wiki"


def test_source_can_be_the_file_paths_service(monkeypatch):
    monkeypatch.setenv("FILEGLANCER_JANELIA_SOURCE", "file-paths-service")
    assert get_source() is file_paths_service


def test_unknown_source_is_refused(monkeypatch):
    monkeypatch.setenv("FILEGLANCER_JANELIA_SOURCE", "confluence")
    with pytest.raises(ValueError):
        get_source_name()


# ---------------------------------------------------------------- updating the database


def test_a_share_is_matched_by_name_when_its_path_is_spelled_differently(db_session):
    # The wiki spelled this share's path with a double slash; the service spells
    # it correctly. Both slugify to the same name, which is unique in the table.
    wiki_spelling = service_record("/groups/zebrafishbbl/home")
    wiki_spelling.update(mount_path="/groups//zebrafishbbl/home", linux_path="/groups//zebrafishbbl/home")
    update_file_share_paths(db_session, as_path_dicts([wiki_spelling]), datetime.now(UTC))
    original_id = db_session.query(FileSharePathDB).one().id

    update_file_share_paths(db_session, as_path_dicts([service_record("/groups/zebrafishbbl/home")]), datetime.now(UTC))
    record = db_session.query(FileSharePathDB).one()
    assert record.id == original_id  # same row, so favourites and data links still point at it
    assert record.mount_path == "/groups/zebrafishbbl/home"


def test_defunct_shares_are_deleted_only_within_the_limit(db_session):
    first_paths = [service_record(f"/groups/lab{number}/home") for number in range(5)]
    update_file_share_paths(db_session, as_path_dicts(first_paths), datetime.now(UTC))

    # Three gone at once: more than the limit of 2, so nothing is deleted.
    update_file_share_paths(db_session, as_path_dicts(first_paths[:2]), datetime.now(UTC))
    assert db_session.query(FileSharePathDB).count() == 5

    # Two gone: within the limit.
    update_file_share_paths(db_session, as_path_dicts(first_paths[:3]), datetime.now(UTC))
    assert {record.mount_path for record in db_session.query(FileSharePathDB)} == {
        "/groups/lab0/home", "/groups/lab1/home", "/groups/lab2/home",
    }


def test_defunct_buckets_are_deleted_only_within_the_limit(db_session):
    update_file_share_paths(db_session, as_path_dicts([service_record("/groups/lab/home")]), datetime.now(UTC))
    first_buckets = [
        {"full_path": f"/groups/lab/home/bucket{number}", "external_url": f"https://s3.janelia.org/bucket{number}/"}
        for number in range(5)
    ]
    update_external_buckets(db_session, first_buckets, datetime.now(UTC))

    # Three gone at once (or all of them, if the source's mapping broke): nothing is deleted.
    update_external_buckets(db_session, first_buckets[:2], datetime.now(UTC))
    assert db_session.query(ExternalBucketDB).count() == 5
    update_external_buckets(db_session, [], datetime.now(UTC))
    assert db_session.query(ExternalBucketDB).count() == 5

    # Two gone: within the limit.
    update_external_buckets(db_session, first_buckets[:3], datetime.now(UTC))
    assert {record.full_path for record in db_session.query(ExternalBucketDB)} == {
        "/groups/lab/home/bucket0", "/groups/lab/home/bucket1", "/groups/lab/home/bucket2",
    }


def test_last_refresh_records_the_source_time(db_session):
    source_time = datetime(2026, 11, 6, 14, 35, tzinfo=UTC)
    update_file_share_paths(db_session, as_path_dicts([service_record("/groups/abbott/home")]), source_time)
    last_refresh = db_session.query(LastRefreshDB).filter_by(table_name="file_share_paths").one()
    assert last_refresh.source_last_updated.replace(tzinfo=None) == source_time.replace(tzinfo=None)


# ---------------------------------------------------------------- matching buckets to shares


class Share:
    def __init__(self, name, mount_path):
        self.name = name
        self.mount_path = mount_path


def test_bucket_goes_to_the_longest_containing_share_on_directory_boundaries():
    shares = [Share("nrs_funke", "/nrs/funke"), Share("nrs_funkelab", "/nrs/funkelab"),
              Share("groups_lab", "/groups/lab"), Share("groups_lab_data", "/groups/lab/data/")]
    assert find_owning_share("/nrs/funkelab/bucket", shares).name == "nrs_funkelab"
    assert find_owning_share("/nrs/funke/bucket", shares).name == "nrs_funke"
    assert find_owning_share("/groups/lab/data/s3", shares).name == "groups_lab_data"
    assert find_owning_share("/groups/lab/other", shares).name == "groups_lab"
    assert find_owning_share("/nrs/funkelab", shares).name == "nrs_funkelab"
    assert find_owning_share("/nrs/funk", shares) is None
