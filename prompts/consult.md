# Consult: a divergence targeted repairs have not fixed

Targeted repairs of the AERMOD Python port (`aermod_py`) have failed several
times on the same Fortran variable. Each attempt changed at most two files and
was rejected because it either broke a case that passed or did not move the
first divergence. The input gives you the history of those attempts (each
hypothesis and why it was rejected), the current divergence, the complete
current package, and the complete packed Fortran for the tier, so you can
follow the data flow across units.

1. Trace the diverging variable back through every Fortran unit that
   contributes to it, and compare each step with the Python.
2. Identify the root cause; it may be upstream of the unit that printed the
   value, or a MODULE/SAVE value carried between calls or hours.
3. Fix it. You may change any number of files, but only for this cause.

Keep the contract's rules (`prompts/contract.md`). Return each changed file
complete. The same acceptance test applies: no passing case may fail, and the
first divergence must move later or disappear.

Respond in exactly this format:

```
=== ANALYSIS ===
<root-cause analysis: which values, which units, why the earlier patches failed>
=== FILE: aermod_py/<name>.py ===
<complete file>
```
