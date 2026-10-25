# Repair AERMOD Port Divergence

A divergence was found between the reference AERMOD and the Python port.

## Failure Context

**Case**: {case_name}  
**Hour**: {hour}  
**First Divergent Variable**: {variable_name}

### Meteorology for This Hour

- Monin-Obukhov Length (L): {L:.2f} m  
- Friction velocity (u*): {ustar:.3f} m/s  
- Convective velocity (w*): {wstar:.3f} m/s  
- Mixing height (zi): {zi:.1f} m  
- Stability: {stability}

### Variable Values

**Reference**: {ref_value:.10e}  
**Port**: {port_value:.10e}  
**Relative Difference**: {rel_diff:.2e}

## Fortran Source for Divergent Subroutine

The variable `{variable_name}` is computed in:

```fortran
{fortran_source}
```

## Current Python Implementation

```python
{python_source}
```

## Your Task

Generate ONE hypothesis for why the port diverges and a targeted patch.

**Constraints**:
- Touch at most TWO functions in your patch
- Do not refactor unrelated code
- Preserve the overall structure
- Match Fortran's numeric behavior exactly

**Common Issues**:
- Index off-by-one (Fortran 1-based vs Python 0-based)
- Loop bounds incorrect (DO I=1,N vs range(N+1))
- Array slicing (Fortran inclusive upper bound)
- Sign error in formula
- Missing case in conditional logic
- Wrong intrinsic function (LOG vs LOG10)
- Operator precedence difference

## Output Format

```
=== HYPOTHESIS ===
<one-sentence hypothesis>

=== FILE: aermod_py/module.py ===
<complete corrected file>
```

If you need to patch two files, include both with FILE markers.

## Test Impact

After your patch:
- All tier A/B test cases will be re-run
- Patch is KEPT only if there are NO regressions
- If the same variable diverges 3 times, escalation to full-context consult

Focus on the specific subroutine that computes `{variable_name}`. Make surgical changes.
