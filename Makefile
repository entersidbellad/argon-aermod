VENV ?= .venv
PY ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
HOST ?= 127.0.0.1
PORT ?= 8000

# The Tier A training cases plus every holdout whose deck needs no PRIME (server._case_info).
TIER_A_CASES = $(shell $(PY) -c 'import server; print(" ".join(n for n, c in server._case_info().items() if c["tests_tier"] == "A"))')

.PHONY: help install demo freeze check-frozen ref refs debug-refs dumps context test test-fast fuzz suite-port suite-tier-a verify whatif serve export-static readme readme-check screenshots clean

help:
	@echo "install     create $(VENV) and install requirements.txt into it"
	@echo "demo        install if needed, verify provenance, then serve the dashboard on http://$(HOST):$(PORT)"
	@echo "ref         fetch EPA source + test cases, build ref/aermod and ref/aermod_dump"
	@echo "refs        run every case through ref/aermod into out/ref (the oracles)"
	@echo "debug-refs  DEBUGOPT runs of the five catalogue cases into out/ref_debug"
	@echo "dumps       SETUP.DMP for every case into out/setup_dump (ground truth for glue)"
	@echo "context     pack the Fortran slice into context/ and count tokens"
	@echo "test        full pytest suite (needs ref, refs, debug-refs, dumps)"
	@echo "test-fast   pytest without the slow DEBUGOPT and end-to-end tests"
	@echo "fuzz        40 random in-scope decks per tier against the binary and the dump"
	@echo "suite-tier-a  run the port on the Tier A cases and holdout, score them into out/suite_port.json"
	@echo "suite-port  run the port on every case (Tier B too) and score it into out/suite_port.json"
	@echo "verify      check every file in port/aermod_py came from a recorded model reply"
	@echo "freeze      print sha256 of harness/compare.py"
	@echo "check-frozen  fail unless compare.py matches harness/compare.sha256"
	@echo "whatif      precompute the kiln what-if stack grid with the port into whatif/cache"
	@echo "serve       read-only dashboard on http://$(HOST):$(PORT)"
	@echo "export-static  static read-only copy of the dashboard into site/ (what vercel.json deploys)"
	@echo "readme      regenerate README.md's results block from results/, agent/runs/, context/, port/"
	@echo "readme-check  fail if README.md's results block is stale"
	@echo "screenshots full-page PNGs of every dashboard tab into docs/screenshots (needs playwright)"

$(VENV)/.installed: requirements.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -r requirements.txt
	touch $@

install: $(VENV)/.installed

demo: $(VENV)/.installed
	$(VENV)/bin/python split.py --verify
	@echo "Dashboard: http://$(HOST):$(PORT)   (Ctrl-C to stop)"
	$(VENV)/bin/python server.py --host $(HOST) --port $(PORT)

freeze:
	@sha256sum harness/compare.py | cut -d' ' -f1

# Fails if compare.py differs from the approved digest in harness/compare.sha256.
check-frozen:
	sha256sum --check harness/compare.sha256

ref:
	$(PY) ref/fetch.py
	ref/build.sh
	ref/build_dump.sh

refs:
	$(PY) harness/run_ref.py --all

debug-refs:
	$(PY) harness/run_ref.py --debug aertest_nobldg CAPPED_STACK2CE AERTEST CAPPED_STACK1C0 ALLSRCS_STACKDW

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

suite-tier-a:
	$(PY) harness/run_port.py $(TIER_A_CASES)
	$(PY) harness/suite.py --who port $(addprefix --case ,$(TIER_A_CASES))

suite-port:
	$(PY) harness/run_port.py --all
	$(PY) harness/suite.py --who port --tier all

verify:
	$(PY) split.py --verify

whatif:
	$(PY) whatif/precompute.py

serve:
	$(PY) server.py --host $(HOST) --port $(PORT)

export-static:
	$(PY) tools/export_static.py

readme:
	$(PY) tools/readme_results.py

readme-check:
	$(PY) tools/readme_results.py --check

screenshots:
	$(PY) tools/screenshots.py --url http://$(HOST):$(PORT)

clean:
	rm -rf out/port out/port_debug out/fuzz out/test_* out/suite_*.json
