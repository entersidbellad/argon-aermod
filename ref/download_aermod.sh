#!/bin/bash
set -euo pipefail

# Download AERMOD 26135 source and test cases from EPA SCRAM
# https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models

AERMOD_VERSION="26135"
BASE_URL="https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod"

echo "Downloading AERMOD ${AERMOD_VERSION} source..."
curl -L -o aermod_source_26135.zip "${BASE_URL}/aermod_source_26135.zip"

echo "Downloading AERMOD ${AERMOD_VERSION} test cases..."
curl -L -o aermod_testcases_26135.zip "${BASE_URL}/aermod_testcases_26135.zip"

echo "Extracting source..."
unzip -q -o aermod_source_26135.zip -d aermod_source
# EPA zip files unpack read-only
chmod -R u+w aermod_source

echo "Extracting test cases..."
unzip -q -o aermod_testcases_26135.zip -d aermod_testcases
chmod -R u+w aermod_testcases

# Extract only the aermet26135_aermod26135 test set
echo "Organizing test cases..."
TEST_DIR="aermod_testcases/aermet26135_aermod26135"
if [ -d "$TEST_DIR" ]; then
    # Copy in-scope test cases to ../cases/epa/
    mkdir -p ../cases/epa
    
    # Tier A cases (no building downwash)
    for case in CAPPED_STACK2 CAPPED_STACK2C0 CAPPED_STACK2CE HRDOW_STACK1 FLATELEV_FLAT_STK; do
        if [ -d "$TEST_DIR/$case" ]; then
            echo "  Copying $case..."
            mkdir -p "../cases/epa/$case"
            # Copy input deck, met files, and reference POSTFILE
            cp "$TEST_DIR/$case"/*.inp "../cases/epa/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*.sfc "../cases/epa/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*.pfl "../cases/epa/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*_EPA.OUT "../cases/epa/$case/" 2>/dev/null || true
        fi
    done
    
    # Tier B cases (with PRIME)
    for case in AERTEST CAPPED_STACK1C0 ALLSRCS_STACKDW; do
        if [ -d "$TEST_DIR/$case" ]; then
            echo "  Copying $case..."
            mkdir -p "../cases/epa/$case"
            cp "$TEST_DIR/$case"/*.inp "../cases/epa/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*.sfc "../cases/epa/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*.pfl "../cases/epa/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*_EPA.OUT "../cases/epa/$case/" 2>/dev/null || true
        fi
    done
    
    # Holdout case
    for case in TESTPM10; do
        if [ -d "$TEST_DIR/$case" ]; then
            echo "  Copying $case..."
            mkdir -p "../cases/holdout/$case"
            cp "$TEST_DIR/$case"/*.inp "../cases/holdout/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*.sfc "../cases/holdout/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*.pfl "../cases/holdout/$case/" 2>/dev/null || true
            cp "$TEST_DIR/$case"/*_EPA.OUT "../cases/holdout/$case/" 2>/dev/null || true
        fi
    done
fi

# Generate checksums for verification
echo "Generating checksums..."
sha256sum aermod_source_26135.zip > aermod_source_26135.zip.sha256
sha256sum aermod_testcases_26135.zip > aermod_testcases_26135.zip.sha256

echo "Download complete!"
echo "Source: aermod_source/"
echo "Test cases: aermod_testcases/"
echo "EPA reference cases copied to ../cases/epa/ and ../cases/holdout/"
