#!/bin/bash
# Setup derived test cases

echo "Setting up derived test cases..."

# aertest_nobldg: AERTEST with building data removed
# This will be created by stripping building downwash parameters from AERTEST
# once the EPA test cases are downloaded

mkdir -p cases/derived/aertest_nobldg

cat > cases/derived/README.md << 'EOF'
# Derived Test Cases

These test cases are derived from EPA cases with modifications to fit the port scope.

## aertest_nobldg

Derived from AERTEST by removing all building downwash parameters.

**Why**: Tier A does not include PRIME building downwash, so we need a PRIME-free version of the hero test case.

**Oracle**: Our compiled reference binary (ref/aermod) run on the modified input deck.

**Generation**: 
1. Copy AERTEST.inp
2. Remove all `SO BUILDHGT`, `SO BUILDWID`, `SO BUILDLEN`, `SO XBADJ`, `SO YBADJ` lines
3. Remove `MODELOPT PRIME` from CO pathway
4. Run our reference binary to generate oracle output

## Holdout no-PRIME companion

Companion to TESTPM10 with only stack 2 (no building downwash).

**Why**: Holdout case for final verification that was never seen during repair.

**Generation**:
1. Copy testpm10.inp
2. Keep only STACK2 source
3. Run our reference binary to generate oracle output
EOF

echo "✓ Derived cases directory structure created"
echo ""
echo "To complete setup:"
echo "1. Run ref/download_aermod.sh to get EPA test cases"
echo "2. Run this script to generate derived inputs from AERTEST"
echo "3. Run ref/build_aermod.sh to compile reference binary"
echo "4. Run reference binary on derived cases to generate oracles"
