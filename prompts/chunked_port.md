# Port part of AERMOD to Python (chunked baseline)

You are translating EPA AERMOD 26135's physics from Fortran into a Python
package, `aermod_py`, a few program units per request. You will not see the
whole Fortran at once. Each request gives you:

1. the contract (`prompts/contract.md`), which is binding;
2. `harness/glue.py`, the human-written replacement for SETUP and output
   (import it, don't port it);
3. the names of the SETUP inputs `run_case` receives in `setup`;
4. the DEBUGOPT catalogue, the only names allowed in debug rows;
5. an interface summary of the Python already written in earlier requests;
6. the Fortran units to translate now.

Translate exactly the units given, following the contract's translation
rules. Use the dataclasses and functions in the interface summary instead of
redefining them; if a unit you are translating calls something not yet written,
call it by the Python name the contract's conventions imply (the Fortran name
in lower case) and import it from the file the task names for that unit.

Respond with files only, each introduced by `=== FILE: aermod_py/<name>.py ===`,
using the file names the task gives. Never return a file listed in the
interface summary: you only see its interface, so rewriting it would lose code.
