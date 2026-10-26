# Reference AERMOD 26135

```bash
python3 ref/fetch.py     # source zip + in-scope test-case members, checksum-verified
ref/build.sh             # gfortran build -> ref/aermod
```

`fetch.py` downloads `aermod_source.zip` (0.7 MB) from EPA SCRAM and pulls only
the members listed in `testcase_manifest.txt` out of `aermod_test_cases.zip`
(489 MB) with HTTP range requests, so a fresh checkout fetches about 10 MB
compressed instead of the whole package. Everything is unpacked user-writable
(EPA's zips are read-only).

`build.sh` reads the compile order and flags from EPA's own
`gfortran-aermod.bat` (29 files), minus `-static`.

Committed: `fetch.py`, `build.sh`, `testcase_manifest.txt`, and
`checksums.sha256` (the source zip, all 29 `.f` files, and every fetched
test-case member). `fetch.py` fails if anything differs; `--update-checksums`
rewrites the file and should only be used when moving to a new EPA release.

Not committed (gitignored): `aermod_source.zip`, `aermod_source/`,
`epa_testcases/`, `build/`, `aermod`.

Verified on Ubuntu 24.04 with gfortran 13.3.0: the build is warning-clean at
the default flags, and the binary reproduces EPA's shipped 1-hr POSTFILEs
exactly for 7 of the 9 EPA cases (see `python3 harness/suite.py --vs-epa`).
