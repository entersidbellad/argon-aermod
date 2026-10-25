#!/usr/bin/env bash
# Build the AERMOD 26135 reference binary with gfortran.
# Compile order and flags come from EPA's own gfortran-aermod.bat shipped in
# the source zip (Fortran modules must compile before their users). -static is
# dropped because it needs static libgfortran, which many distros don't ship.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${HERE}/aermod_source/aermod_source_v26135"
OUT="${HERE}/build"
FLAGS=${AERMOD_FFLAGS:-"-fbounds-check -Wuninitialized -O2"}

[ -f "${SRC}/gfortran-aermod.bat" ] || { echo "missing ${SRC}; run python3 ref/fetch.py first" >&2; exit 1; }
command -v gfortran >/dev/null || { echo "gfortran not found (apt-get install gfortran)" >&2; exit 1; }

mapfile -t FILES < <(tr -d '\r' < "${SRC}/gfortran-aermod.bat" \
  | awk '$1=="gfortran" && $2=="-c" {print $NF}')
[ "${#FILES[@]}" -eq 29 ] || { echo "expected 29 files in gfortran-aermod.bat, got ${#FILES[@]}" >&2; exit 1; }

rm -rf "${OUT}" && mkdir -p "${OUT}"
cd "${OUT}"
OBJS=()
for f in "${FILES[@]}"; do
  gfortran -c ${FLAGS} "${SRC}/${f}" -o "${f%.f}.o" 2>>compile.log
  OBJS+=("${f%.f}.o")
done
gfortran -O2 -o aermod "${OBJS[@]}"
ln -sf build/aermod "${HERE}/aermod"
echo "built ${OUT}/aermod (gfortran $(gfortran -dumpfullversion), flags: ${FLAGS})"
