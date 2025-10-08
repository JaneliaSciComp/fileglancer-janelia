# fileglancer-janelia

This repository hosts Janelia-specific scripts for Fileglancer. This code is necessary to running Fileglancer at Janelia, but would need to be customized if deploying Fileglancer at another institution.

## Setup

Install the dependencies using Pixi:
```
pixi install
```

## Fetching updated data from the Janelia wiki

The Janelia wiki is used to populated the File Share Paths and External Buckets in the Fileglancer Central database. The update script for this is intended to be run on a schedule. We use [Systemd to run it](docs/SystemdTimer.md) on the Janelia dev and prod servers.

You can test it by passing an `.env` file containing your Database setup and Atlassian Cloud credentials:
```
/run_update_db.sh .env.central
```
