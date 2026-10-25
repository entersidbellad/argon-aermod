Fix the circular import between `aermod_py.hrloop` and `aermod_py.metext` properly.

Today `hrloop.py` imports `metext` from `.metext`, and `metext.py` imports
`cent_date, julian` from `.hrloop`. An earlier repair worked around the cycle in
`__init__.py` by loading submodules by hand with a module `__getattr__` and
forwarding proxies. Replace that workaround with a clean module structure:

1. Create a new module `aermod_py/dateutil.py` holding the shared date helpers
   `cent_date` (SUBROUTINE CENT_DATE) and `julian` (SUBROUTINE JULIAN) and their
   lookup tables `_NDAY` and `_IDYMAX`, moved verbatim from `hrloop.py`
   (same bodies, same docstrings). It may import only from `.state`.
2. `hrloop.py`: remove those definitions and tables and import `cent_date`,
   `julian` from `.dateutil` instead (keep them importable from `.hrloop` through
   that import, since other code may use them). Everything else unchanged.
3. `metext.py`: change only the import line so it reads
   `from .dateutil import cent_date, julian`. Every other line must stay
   byte-identical.
4. `__init__.py`: delete `_load_package` and all the preloading, `__getattr__`
   and proxy machinery. Use plain imports: `from .state import AermodState` and
   `from .hrloop import hrloop`. Keep `run_case` exactly as it is.

After the change, `import aermod_py.metext` and `import aermod_py.hrloop` must work
in a fresh interpreter in either order, with no import cycle anywhere in the
package. Return the four files `dateutil.py`, `hrloop.py`, `metext.py` and
`__init__.py` complete.
