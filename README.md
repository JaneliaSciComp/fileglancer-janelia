# fileglancer-janelia

This repository hosts Janelia-specific scripts for Fileglancer. This code is necessary to running Fileglancer at Janelia, but would need to be customized if deploying Fileglancer at another institution.

## Setup

Install the dependencies using Pixi:
```
pixi install
```

## Fetching updated data from the Janelia wiki

The Janelia wiki is used to populated the File Share Paths and External Buckets in the Fileglancer Central database. The update script for this is intended to be run in a crontab. It requires environment variables that configure the FGC_* environment (usually the `.env.central` file configured for fileglancer-hub). Then configure crontab like this:

```
# every 5 minutes
*/5 * * * * cd /path/to/fileglancer-janelia && ./run_update_db.sh /path/to/.env.central
```


