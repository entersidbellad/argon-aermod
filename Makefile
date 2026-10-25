PY ?= python3

.PHONY: help freeze ref refs debug-refs dumps context test test-fast fuzz suite-port verify serve clean

help:
	@echo "ref         fetch EPA source + test cases, build ref/aermod and ref/aermod_dump"
	@echo "refs        run every case through ref/aermod into out/ref (the oracles)"
	@echo "debug-refs  DEBUGOPT runs of AERTEST and aertest_nobldg into out/ref_debug"
	@echo "dumps       SETUP.DMP for every case into out/setup_dump (ground truth for glue)"
	@echo "context     pack the Fortran slice into context/ and count tokens"
	@echo "test        full pytest suite (needs ref, refs, debug-refs, dumps)"
	@echo "test-fast   pytest without the slow DEBUGOPT and end-to-end tests"
	@echo "fuzz        40 random in-scope decks per tier against the binary and the dump"
	@echo "suite-port  run the port on every case and score it into out/suite_port.json"
	@echo "verify      check every file in port/aermod_py came from a recorded model reply"
	@echo "freeze      print sha256 of harness/compare.py"
	@echo "serve       read-only dashboard on http://127.0.0.1:8000"

freeze:
	@sha256sum harness/compare.py | cut -d' ' -f1

ref:
	$(PY) ref/fetch.py
	ref/build.sh
	ref/build_dump.sh

refs:
	$(PY) harness/run_ref.py --all

debug-refs:
	$(PY) harness/run_ref.py --debug AERTEST aertest_nobldg

dumps:
	$(PY) harness/run_ref.py --all --binary ref/aermod_dump --who setup_dump

context:
	$(PY) pack.py

test:
	$(PY) -m pytest -q -rs

test-fast:
	$(PY) -m pytest -q -rs -m "not slow"

fuzz:
	$(PY) harness/fuzz.py -n 40 --tier A --seed 1
	$(PY) harness/fuzz.py -n 40 --tier B --seed 2

suite-port:
	$(PY) harness/run_port.py --all
	$(PY) harness/suite.py --who port --tier all

verify:
	$(PY) split.py --verify

serve:
	$(PY) server.py

clean:
	rm -rf out/port out/port_debug out/fuzz out/test_* out/suite_*.json
