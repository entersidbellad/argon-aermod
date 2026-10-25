# Reference AERMOD Build

This directory contains scripts to download and build EPA's AERMOD reference implementation.

## Files Ignored by Git

The following large files are downloaded and built locally but not committed:
- `aermod_source_26135.zip` - AERMOD source code archive
- `aermod_testcases_26135.zip` - AERMOD test cases archive
- `aermod_source/` - Extracted source code
- `aermod_testcases/` - Extracted test cases
- `build/` - Build artifacts
- `aermod` - Compiled binary (symlink)

Checksums are committed for verification:
- `aermod_source_26135.zip.sha256`
- `aermod_testcases_26135.zip.sha256`

## Usage

1. Download AERMOD source and test cases:
   ```bash
   ./download_aermod.sh
   ```

2. Build the reference binary:
   ```bash
   ./build_aermod.sh
   ```

3. Run test cases:
   ```bash
   ../harness/run_ref.py <case_name>
   ```
