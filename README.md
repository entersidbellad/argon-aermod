# AERMOD Python Port

**Legacy Fortran migration verified against the government's own test suite. Zero hand edits.**

Gemini 4 Argon (1,048,576-token context) ports EPA's AERMOD air-dispersion model from Fortran to Python in one full-context pass, then an automated repair loop fixes divergences until the port matches EPA's official test cases with strict numerical criteria.

## What This Is

AERMOD is the EPA's regulatory air quality dispersion model—30 years of Fortran, ~98K lines, used nationwide for permitting. This project demonstrates:

1. **Full-context porting**: Gemini 4 Argon sees all ~149K tokens of scoped physics in one pass
2. **Automated verification**: Tested against EPA's test suite with strict numerical criteria
3. **Automated repair**: Agent-driven repair loop fixes divergences with targeted patches
4. **Zero hand edits**: `port/aermod_py/` is written entirely by Argon—no human code

## Quickstart

```bash
# 1. Download and build reference AERMOD
cd ref
./download_aermod.sh
./build_aermod.sh

# 2. Pack Fortran source for porting
python pack.py --tier A --count-tokens

# 3. Set up Gemini API key
export GEMINI_API_KEY=your_key_here

# 4. Run the port (requires API key)
agent/port.py --tier A --thinking high

# 5. Split Argon's output into files
./split.py agent/runs/<timestamp>/raw_output.txt

# 6. Run tests
harness/run_port.py AERTEST --verbose

# 7. Compare against reference
harness/compare.py \
    cases/epa/AERTEST/AERTEST_EPA.OUT \
    /tmp/aermod_port_AERTEST/POSTFILE.OUT

# 8. If divergent, run repair loop
agent/repair_loop.py --tier A --max-iterations 10
```

## Verification Rules

All ports must pass:

### 1. EPA Regulatory Parity
Best-fit slope through origin within **1 ± 0.001** (via `pyaermod.regulatory_parity.score_postfile_pair`)

### 2. Strict Numerical Criteria
- Zero/nonzero agreement ≥ **99.9%**
- P99 relative error ≤ **1e-4** on values ≥ 1% of case max
- Per-receptor H4H design value difference ≤ **1e-4**

### 3. Comparison Baseline
All strict comparisons are against **our compiled binary**, not EPA's shipped reference files, because two builds already differ at 1e-4 precision (CAPPED_STACK1C0: 362/27,648 values; TESTPM10: 1,243/1,577,664 values).

See `harness/compare.py` for implementation.

## Port Scope

**Physics ported**:
- Point sources only (SRCTYP = POINT)
- Flat terrain (FLAT option)
- Rural mode
- Concentration output only (not deposition)
- 1-hour averages (AVERTIME 1)

**Tier A**: No building downwash (~111K tokens)  
**Tier B**: Adds PRIME building downwash algorithm (~149K tokens)

**Not ported**: Input parsing, output formatting (use `pyaermod` instead)

## Test Cases

### Tier A (No Building Downwash)
- `aertest_nobldg` (derived from AERTEST with buildings removed)
- `CAPPED_STACK2`, `CAPPED_STACK2C0`, `CAPPED_STACK2CE`
- `HRDOW_STACK1`
- `FLATELEV_FLAT_STK`

### Tier B (With PRIME)
- `AERTEST` (hero case: aertest_01H)
- `CAPPED_STACK1C0`
- `ALLSRCS_STACKDW`

### Holdout
- `TESTPM10` (5-year Salem met, not used in repair loop)
- Derived no-PRIME companion (stack 2 only)

Plus fuzz-generated random decks (oracle = our compiled binary).

## Project Structure

```
ref/                      # Reference AERMOD build
  download_aermod.sh      # Download EPA source & test cases
  build_aermod.sh         # Compile with gfortran
  aermod                  # Compiled binary (symlink)

cases/
  epa/                    # EPA reference test cases
  derived/                # Modified test cases (e.g., aertest_nobldg)
  holdout/                # Holdout cases (never in repair loop)

harness/                  # Test harness
  run_ref.py              # Run reference binary
  run_port.py             # Run Python port
  compare.py              # Compare outputs (EPA + strict criteria)
  debugdiff.py            # Find first divergent debug variable
  fuzz.py                 # Generate random test cases

context/                  # Packed Fortran for Argon
  tier_A_packed.txt       # Tier A Fortran (~111K tokens)
  tier_B_packed.txt       # Tier B with PRIME (~149K tokens)

prompts/                  # Prompts for Argon
  contract.md             # Port contract specification
  port.md                 # One-pass port prompt
  repair.md               # Targeted repair prompt
  consult.md              # Full-context escalation prompt
  chunked_port.md         # Baseline: chunked approach

agent/                    # Agent scripts
  port.py                 # One-pass Gemini 4 Argon port
  repair_loop.py          # Automated repair loop
  baselines/
    chunked.py            # Baseline: file-at-a-time approach

port/aermod_py/           # Generated Python port
  README.md               # (This directory is Argon-only)
  # DO NOT hand-edit any code here

ui/                       # Minimal web UI
  index.html              # Port/Proof/Decision screens

pack.py                   # Pack Fortran source
split.py                  # Split Argon output into files
server.py                 # Minimal FastAPI server
```

## Port Contract

From `prompts/contract.md`:

```python
def run_case(
    project: Project,
    met: Dict[str, Path],
    sources: Optional[List[Source]] = None,
    debug: bool = False
) -> Result:
    """
    Returns:
        Result dict with:
            - conc: ndarray shape (hours, receptors) in μg/m³
            - hours, receptors: int
            - intermediates: dict (if debug=True)
    """
```

Key requirements:
- Vectorized over receptors, explicit hour loop
- Float64 for DOUBLE PRECISION
- Comment every 1-to-0-based index change
- Preserve Fortran constants, branch order, algorithm structure verbatim
- Each function docstring names its Fortran subroutine source
- `debug=True` returns intermediates matching DEBUGOPT variable names
- NumPy via `xp` namespace for future JAX compatibility

## Repair Loop Strategy

When tests fail:

1. Run failing case with `debug=True` (ref + port)
2. Find first divergent variable via `debugdiff.py`
3. Generate failure packet (<= 30K tokens):
   - Case, hour, met summary (L, u*, w*, zi)
   - Ref vs port values, relative difference
   - Fortran source for divergent subroutine
   - Python function implementation
4. Call Gemini 4 Argon with `repair.md` prompt
5. Apply patch (at most 2 functions)
6. Re-run all tier A/B cases
7. **Keep patch only if no regressions**
8. Commit as agent-authored: `repair N: <subroutine>: <hypothesis>`
9. Escalate to full-context consult after 3 failures on same variable
10. Budget: 10 iterations or 60 minutes per tier

## Dependencies

```bash
# Required
pip install numpy 'google-generativeai>=2.3.0' tiktoken

# For input parsing and regulatory parity checks
pip install pyaermod==2.2.0

# For server (optional)
pip install fastapi uvicorn

# System
sudo apt install gfortran  # or equivalent for your platform
```

## Token Counts

Run `pack.py --count-tokens` to see actual token counts. Expected (o200k proxy):

- **Tier A** (no PRIME): ~111K tokens
- **Tier B** (with PRIME): ~149K tokens

Gemini 4 Argon has 1,048,576-token context, so both fit comfortably with room for contract and prompts.

## Verification Hash

```bash
make freeze
```

Prints the SHA256 of `harness/compare.py` so verification criteria can be proven immutable during testing.

## License

MIT

## Credits

- EPA AERMOD: https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models
- Gemini 4 Argon: Google DeepMind
- pyaermod: https://pypi.org/project/pyaermod/
