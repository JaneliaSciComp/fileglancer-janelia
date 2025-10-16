# Janelia customizations for Fileglancer

This repository hosts Janelia-specific scripts for Fileglancer. This code is necessary for running Fileglancer at Janelia and integrating with our other systems.

## Setup

Install the dependencies using Pixi:
```
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

You can then update your database with `update-db` task. Before running this command, ensure that your Fileglancer server is stopped, as it holds a lock on the Sqlite database file.

```
pixi run update-db
```