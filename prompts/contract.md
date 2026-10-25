# AERMOD Python Port Contract

You are porting EPA's AERMOD air dispersion model from Fortran to Python. This contract defines the exact interface and requirements.

## Entry Point

```python
def run_case(
    project: Project,
    met: Dict[str, Path],
    sources: Optional[List[Source]] = None,
    debug: bool = False
) -> Result:
    """
    Run AERMOD calculation for one case.
    
    Args:
        project: Parsed AERMOD project (from pyaermod.input_reader)
        met: Dict with 'sfc' and 'pfl' paths to met files
        sources: List of point sources (filters from project if None)
        debug: If True, return intermediate variables matching DEBUGOPT output
        
    Returns:
        Result dict with:
            - conc: ndarray shape (hours, receptors) in μg/m³
            - hours: int, number of hours processed
            - receptors: int, number of receptors
            - intermediates: dict of debug variables (if debug=True)
    """
```

## Implementation Requirements

### 1. Vectorization
- **Vectorize over receptors** within each hour
- Use explicit **hour loop** (not vectorized over time)
- All receptor calculations for one hour should be in a single vectorized operation

### 2. Numeric Types
- Use **float64** (np.float64) for all DOUBLE PRECISION equivalents
- Match Fortran's numeric behavior exactly

### 3. Indexing
- **Comment every 1-to-0-based index change explicitly**
- Example: `# Fortran 1-based: DO I=1,N becomes range(N)`
- Verify array accesses match Fortran bounds

### 4. State Management
- Convert Fortran MODULE variables with SAVE into **explicit dataclasses**
- No global mutable state
- Pass state explicitly between functions

### 5. Documentation
- **Every Python function docstring must name its source Fortran subroutine**
- Example:
  ```python
  def calc_plume_rise(stack_height, exit_vel, exit_temp):
      """
      Calculate plume rise using Briggs equations.
      
      Source: SUBROUTINE PRISE in prise.f
      """
  ```

### 6. Code Fidelity
- Preserve **constants verbatim** (no rounding)
- Preserve **branch order** exactly as in Fortran
- Preserve **algorithm structure** - don't refactor for "Pythonic" style
- If Fortran has nested IFs, use nested ifs in Python
- If Fortran has GOTO, use equivalent control flow (while/break/continue)

### 7. Debug Mode
- When `debug=True`, return **intermediates dict** with variable names **exactly matching DEBUGOPT output**
- Variables should match the names printed by:
  - `CO DEBUGOPT MODEL`
  - `CO DEBUGOPT METEOR`
  - `CO DEBUGOPT PRIME`
- This enables debugdiff.py to find divergence points

### 8. NumPy Namespace
- Import NumPy as `xp` for future JAX compatibility:
  ```python
  import numpy as xp
  ```
- Use `xp.array`, `xp.zeros`, etc.

### 9. Scope Limitations
This port covers:
- **Point sources only** (SRCTYP = POINT)
- **Flat terrain** (FLAT option)
- **Rural mode**
- **Concentration output only** (not deposition)
- **1-hour averages** (AVERTIME 1)
- **Default physics** with FLAT option

**Tier A**: No building downwash  
**Tier B**: Adds PRIME building downwash algorithm

## Critical Fortran Subroutines

### Core Flow (aermod.f)
- Main hourly loop structure
- Calls to METEXT, PCALC, output

### Meteorology (metext.f, iblval.f, siggrid.f, tempgrid.f, windgrid.f)
- METEXT: extract met data for current hour
- IBLVAL: convective boundary layer interpolation
- SIGGRID: sigma_y and sigma_z interpolation
- TEMPGRID: temperature profile
- WINDGRID: wind profile

### Point Source Calculation (calc1.f PCALC path, calc2.f)
- PCALC: point source concentration calculation
- Plume rise calculations
- Dispersion parameter lookups

### Plume Rise (prise.f)
- PRISE: Briggs plume rise formulas
- Buoyancy and momentum rise

### Dispersion Parameters (sigmas.f)
- Sigma_y and sigma_z from stability and distance
- Rural vs urban formulas

### Building Downwash (prime.f) - Tier B only
- PRIME algorithm for building wake effects
- Cavity and wake calculations

## DEBUGOPT Variable Names

Run AERMOD with these flags to see intermediate variable names:
```
CO DEBUGOPT MODEL
CO DEBUGOPT METEOR
CO DEBUGOPT PRIME
```

Inspect the reference output on AERTEST to determine the exact variable names that must be returned in `intermediates` dict.

Example variables (verify these from actual DEBUGOPT output):
- Meteorological: `USTAR`, `WSTAR`, `L`, `ZI`
- Plume rise: `DHF`, `DHCRIT`, `XFINAL`
- Dispersion: `SY`, `SZ`, `SZEFF`
- Concentration: `QTK`, `QSUBC`, `CHI`

## Testing Verification

Your port will be verified against:
1. **EPA regulatory parity**: best-fit slope 1 ± 0.001
2. **Strict criteria**:
   - Zero/nonzero agreement ≥ 99.9%
   - P99 relative error ≤ 1e-4 on values ≥ 1% of case max
   - H4H design value difference ≤ 1e-4

See `harness/compare.py` for implementation.

## Output Format Example

```python
result = {
    'conc': np.array([...]),  # shape (hours, receptors)
    'hours': 8760,
    'receptors': 121,
    'intermediates': {  # only if debug=True
        'USTAR': [...],
        'L': [...],
        'CHI': [...],
        # ... all DEBUGOPT variables
    }
}
```

---

**Remember**: This is a verification port, not a rewrite. Match Fortran's behavior exactly, even if it seems non-idiomatic in Python. The goal is mathematical equivalence proven by passing strict numerical tests.
