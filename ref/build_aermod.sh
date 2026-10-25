#!/bin/bash
set -euo pipefail

# Build AERMOD with gfortran
# Based on pyaermod's scripts/build_aermod.sh pattern

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SCRIPT_DIR}/aermod_source"
BUILD_DIR="${SCRIPT_DIR}/build"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: AERMOD source not found at $SOURCE_DIR"
    echo "Run download_aermod.sh first"
    exit 1
fi

# Find the source files
AERMOD_SRC=""
if [ -d "$SOURCE_DIR/source" ]; then
    AERMOD_SRC="$SOURCE_DIR/source"
elif [ -d "$SOURCE_DIR/src" ]; then
    AERMOD_SRC="$SOURCE_DIR/src"
else
    # Source files might be directly in aermod_source
    AERMOD_SRC="$SOURCE_DIR"
fi

if [ ! -f "$AERMOD_SRC/modules.f" ]; then
    echo "Error: Cannot find modules.f in source directory"
    echo "Checked: $AERMOD_SRC"
    exit 1
fi

echo "Building AERMOD from $AERMOD_SRC..."
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Compile AERMOD with gfortran
# Use flags compatible with modern Fortran standards
# -O2: optimization level 2
# -fno-automatic: honor SAVE statements
# -fbacktrace: enable backtraces for debugging
# -std=legacy: allow legacy Fortran features

echo "Compiling..."
gfortran -O2 -fno-automatic -fbacktrace -std=legacy \
    -o aermod \
    "$AERMOD_SRC"/modules.f \
    "$AERMOD_SRC"/aermod.f \
    "$AERMOD_SRC"/setup.f \
    "$AERMOD_SRC"/coset.f \
    "$AERMOD_SRC"/soset.f \
    "$AERMOD_SRC"/reset.f \
    "$AERMOD_SRC"/meset.f \
    "$AERMOD_SRC"/ouset.f \
    "$AERMOD_SRC"/inpsum.f \
    "$AERMOD_SRC"/metext.f \
    "$AERMOD_SRC"/iblval.f \
    "$AERMOD_SRC"/siggrid.f \
    "$AERMOD_SRC"/tempgrid.f \
    "$AERMOD_SRC"/windgrid.f \
    "$AERMOD_SRC"/calc1.f \
    "$AERMOD_SRC"/calc2.f \
    "$AERMOD_SRC"/prise.f \
    "$AERMOD_SRC"/prime.f \
    "$AERMOD_SRC"/sigmas.f \
    "$AERMOD_SRC"/pitarea.f \
    "$AERMOD_SRC"/uninam.f \
    "$AERMOD_SRC"/output.f \
    "$AERMOD_SRC"/evset.f \
    "$AERMOD_SRC"/evcalc.f \
    "$AERMOD_SRC"/evoutput.f \
    "$AERMOD_SRC"/rline.f \
    "$AERMOD_SRC"/bline.f \
    "$AERMOD_SRC"/grsm.f \
    "$AERMOD_SRC"/awmadw.f \
    2>&1 | tee compile.log

if [ -f "aermod" ]; then
    echo "Build successful!"
    echo "Binary: $BUILD_DIR/aermod"
    ./aermod --version 2>&1 || echo "Version check complete"
    
    # Create a symlink in ref/ for easy access
    ln -sf "$BUILD_DIR/aermod" "$SCRIPT_DIR/aermod"
    echo "Symlink created: $SCRIPT_DIR/aermod"
else
    echo "Build failed! Check compile.log for errors."
    exit 1
fi
