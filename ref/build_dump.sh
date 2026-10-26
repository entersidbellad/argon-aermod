#!/usr/bin/env bash
# Build ref/aermod_dump: our AERMOD build plus a DUMP_SETUP call right before
# HRLOOP that writes every SETUP-assigned module variable the port reads
# (harness/setup_inputs.py) to SETUP.DMP. Reuses the objects and .mod files
# from ref/build.sh; only aermod.f is recompiled, with one CALL added.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${HERE}/aermod_source/aermod_source_v26135"
BUILD="${HERE}/build"
OUT="${HERE}/build_dump"
FLAGS=${AERMOD_FFLAGS:-"-fbounds-check -Wuninitialized -O2"}

[ -f "${BUILD}/aermod.o" ] || { echo "run ref/build.sh first" >&2; exit 1; }
rm -rf "${OUT}" && mkdir -p "${OUT}"
python3 "${HERE}/../harness/setup_inputs.py" --fortran "${OUT}/dump_setup.f90"

tr -d "\r" < "${SRC}/aermod.f" | grep -c "^         CALL HRLOOP$" | grep -qx 1 \
  || { echo "expected exactly one '         CALL HRLOOP' in aermod.f" >&2; exit 1; }
tr -d "\r" < "${SRC}/aermod.f" | sed "s/^         CALL HRLOOP$/         CALL DUMP_SETUP\n         CALL HRLOOP/" > "${OUT}/aermod.f"

cd "${OUT}"
gfortran -c ${FLAGS} -I"${BUILD}" dump_setup.f90 -o dump_setup.o
gfortran -c ${FLAGS} -I"${BUILD}" aermod.f -o aermod.o
OBJS=()
for o in "${BUILD}"/*.o; do
  [ "$(basename "$o")" = aermod.o ] || OBJS+=("$o")
done
gfortran -O2 -o aermod_dump aermod.o dump_setup.o "${OBJS[@]}"
ln -sf build_dump/aermod_dump "${HERE}/aermod_dump"
echo "built ${OUT}/aermod_dump"
