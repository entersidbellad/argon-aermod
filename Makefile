.PHONY: freeze help test clean

help:
	@echo "AERMOD Port Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  freeze - Print SHA256 of compare.py for verification"
	@echo "  test   - Run all test cases"
	@echo "  clean  - Remove temporary test outputs"

freeze:
	@echo "Verification criteria hash:"
	@sha256sum harness/compare.py | cut -d' ' -f1
	@echo ""
	@echo "This hash proves compare.py was frozen during testing."

test:
	@echo "Running test suite..."
	@python -m pytest tests/ -v

clean:
	@echo "Cleaning temporary outputs..."
	@rm -rf /tmp/aermod_ref_*
	@rm -rf /tmp/aermod_port_*
	@echo "Done"
