#!/bin/bash
set -e

# Check if env file path was provided
if [ $# -eq 0 ]; then
    echo "Error: No .env file path provided"
    echo "Usage: $0 <path-to-env-file>"
    exit 1
fi

ENV_FILE="$1"

# Check if env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

# Source the env file and export all variables
set -a
source "$ENV_FILE"
set +a

# Change to script directory
cd "$(dirname "$0")"

# Run the update script
pixi run update-db
