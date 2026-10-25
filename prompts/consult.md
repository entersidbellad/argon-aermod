# Consult: Persistent Divergence

The variable `{variable_name}` has diverged 3 times despite targeted patches.

## Divergence History

{divergence_history}

## Full Context

Below is the complete packed Fortran source for your reference.

Your task: 
1. Analyze why this variable keeps diverging
2. Identify the root cause (may involve multiple subroutines)
3. Generate a comprehensive fix

The full Python port is available. Consider:
- Data flow leading to this variable
- Upstream calculations that feed into it
- Interactions between modules
- Subtle numeric or logical differences

## Output Format

```
=== ANALYSIS ===
<multi-paragraph root cause analysis>

=== FILE: aermod_py/module1.py ===
<corrected file>

=== FILE: aermod_py/module2.py ===
<corrected file>
```

You may patch multiple files if needed, but keep changes focused on the issue.

---

{packed_fortran_context}
