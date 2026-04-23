#!/bin/bash

# Script location: climatechange/scripts/
# Target:          climatechange/done/{region}/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")/done"

for region_dir in "$BASE_DIR"/*/; do
    echo "Cleaning: $region_dir"
    rm -fv "${region_dir}regions_done.csv" "${region_dir}regions_done.csv.lock"
done