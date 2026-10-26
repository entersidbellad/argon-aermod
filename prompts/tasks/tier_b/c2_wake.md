Chunk 2 of 5. Write the new module `aermod_py/prime_wake.py`, complete:
WAKE_U_TURB, WAKE_TURB, WAKE_U, WAKE_SIG, WAKE_DFSN, WAKE_DFSN2, WAKE_FQC and
CAV_SRC (prime.f), following the plan's conventions. Call the chunk 1 functions
in `prime_base.py` and use `PrimeState` (`prime_state.py`) exactly as their
current code (shown) defines them; do not redefine them.

If these units need SAVEd locals or PrimeState fields that `prime_state.py`
lacks, also return `prime_state.py` complete with only those fields added.
Otherwise return only `prime_wake.py`. Do not change any other file.
