# Janelia customizations for Fileglancer

This repository hosts Janelia-specific scripts and integration tests for Fileglancer.

## Setup

Install the dependencies using Pixi:

```bash
pixi install
```

## Fetching updated data from the Janelia wiki

The Janelia wiki is used to populated the File Share Paths and External Buckets in the Fileglancer Central database. The update script for this is intended to be run on a schedule. We use [Systemd to run it](docs/SystemdTimer.md) on the Janelia dev and prod servers.

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
