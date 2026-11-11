# Janelia customizations for Fileglancer

This repository hosts Janelia-specific scripts and integration tests for Fileglancer.

## Setup

Install the dependencies using Pixi:

```bash
pixi install
```

## Fetching updated data from the Janelia wiki

By default, the Janelia wiki is used to populate the File Share Paths and External Buckets in the Fileglancer Central database. The update script for this is intended to be run on a schedule. We use [Systemd to run it](docs/SystemdTimer.md) on the Janelia dev and prod servers.

To run it on your dev server, check this repo out at the same level as the [fileglancer repo](https://github.com/JaneliaSciComp/fileglancer):

```
.
├── fileglancer
└── fileglancer-janelia
```

You can then update your database with `dev-update-db` task. Before running this command, ensure that your Fileglancer server is stopped, as it holds a lock on the Sqlite database file.

```bash
pixi run dev-update-db
```

## Fetching data from the file-paths-service

The [file-paths-service](https://github.com/JaneliaScientificComputingSystems/file-paths-service)
at <https://filepaths.int.janelia.org> replaces the wiki page "Lab and Project File Share Paths".
It builds the share list from vaststats (the VAST storage API), with lab names, AD groups and
hidden shares curated by its admins, and it also serves the external S3 buckets. The update
script can read from it instead of the wiki:

| Variable | Default | |
|---|---|---|
| `FILEGLANCER_JANELIA_SOURCE` | `wiki` | `wiki`, or `file-paths-service` |
| `FILE_PATHS_SERVICE_URL` | `https://filepaths.int.janelia.org` | The service to read. Must be `https`, or `http://localhost` |
| `FILE_PATHS_SERVICE_TIMEOUT` | `60` | Seconds per request |

These deliberately don't start with `FGC_`: Fileglancer reads `FGC_*` keys from the shared
`.env` file, and doesn't accept keys it doesn't know.

The service's share names are exactly `slugify_path(linux_path)`, the names the wiki ingest
has always used, so favourites, data links and tickets keep pointing at the same shares. The
update script refuses the whole update, and logs why, if any record's name isn't, or if its
`mount_path` isn't its `linux_path` as a plain absolute path. Existing records are matched by
name first, then by mount path, so a share whose path the wiki spelled differently (such as
`/groups//zebrafishbbl/home`) is corrected in place, not duplicated. If the service is down or
not ready it returns an error, and the database is left as it is.

Shares and buckets the source no longer lists are deleted, at most 2 of each per run
(`--max-deletes`). A larger set is kept and logged.

### Before switching: a dry run

```bash
FGC_ATLASSIAN_URL=... FGC_ATLASSIAN_USERNAME=... FGC_ATLASSIAN_TOKEN=... pixi run compare-sources
```

This fills a scratch SQLite database from the wiki, applies the file-paths-service data with
the real update code, and reports the shares and buckets that would be added, changed or
deleted. Nothing else is written. Add `--reference-db-url <url>` to check, read-only, whether
the shares that would be deleted are referenced by data links, tickets, jobs or user
preferences in that database (a copy of the server's, ideally).

### Switching

1. Set `FILEGLANCER_JANELIA_SOURCE=file-paths-service` in the `.env` file the systemd service
   loads (`EnvironmentFile=`). The next timer run updates from the service.
2. Wiki shares the service doesn't list are deleted, at most 2 per run, so a larger set is kept
   and logged. After checking with `compare-sources --reference-db-url` that nothing refers to
   them, remove them once:

   ```bash
   pixi run update-db --max-deletes 6 --force
   ```

To switch back, set `FILEGLANCER_JANELIA_SOURCE=wiki`.

## Integration Tests (Playwright)

The `playwright/` directory contains end-to-end tests that run against the live Fileglancer dev server at `https://fileglancer-dev.int.janelia.org`. Tests require Janelia network access (VPN or on-site).

### Prerequisites

1. Ensure the version of Fileglancer you wish to test is deployed at `https://fileglancer-dev.int.janelia.org`, following the release instructions for [fileglancer-hub](https://github.com/JaneliaSciComp/fileglancer-hub/blob/main/RELEASE.md).

2. On your local computer or test server, install the playwright pixi environment and Playwright browsers (one-time setup):

```bash
pixi install -e playwright
pixi run npm-install-tests-ui
pixi run -e playwright npx --prefix playwright playwright install chromium
```

### Authentication

Tests authenticate via a session cookie. To obtain one, copy `playwright/.env.example` to `playwright/.env` and fill the value of `FCG_TEST_API_KEY`. The server must have a matching `test_api_key` set in its config. The session is created automatically on the first run and cached in `playwright/.auth/user.json` until it expires.

```bash
cp playwright/.env.example playwright/.env
```

```yaml
FGC_TEST_API_KEY=<key configured on the fileglancer-dev server>
```

### Running the tests

```bash
pixi run test-ui
```

Global setup runs before any tests and global teardown runs after. Both manage database state automatically:

- **Setup** saves all of your existing data links and the `areDataLinksAutomatic` preference, then removes them so tests start from a clean slate.
- **Teardown** deletes any data links created during the run, recreates the ones that were saved, and restores the preference to its original value.

> **Note:** If a test run is interrupted before teardown completes, `playwright/.auth/test-state.json` will remain on disk. Setup detects this and skips overwriting the saved state, so your original data links are preserved. Delete `test-state.json` manually once you have verified the database is in the correct state.

### Cached session

The session cookie is saved to `playwright/.auth/user.json` and reused across runs. To force a fresh login, delete that file:

```bash
rm playwright/.auth/user.json
```
