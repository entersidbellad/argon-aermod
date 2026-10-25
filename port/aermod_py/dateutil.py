"""SUBROUTINE CENT_DATE (meset.f) and SUBROUTINE JULIAN (aermod.f)."""

from __future__ import annotations

from .state import AermodState, f_idiv, f_mod_int


# Lookup tables for JULIAN (aermod.f:1563-1564)
_NDAY = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_IDYMAX = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def cent_date(iyear: int, istrt_wind: int = 50, istrt_cent: int = 19) -> tuple[int, int]:
    """SUBROUTINE CENT_DATE (meset.f): convert 2-digit or 4-digit year to (2-digit, 4-digit)."""
    if istrt_wind <= iyear <= 99:
        iyr = istrt_cent * 100 + iyear
    elif iyear < istrt_wind:
        iyr = (istrt_cent + 1) * 100 + iyear
    else:
        iyr = iyear
        iyear = iyr - 100 * f_idiv(iyr, 100)
    return iyear, iyr


def julian(state: AermodState, inyr: int, inmn: int, indy: int) -> int:
    """SUBROUTINE JULIAN (aermod.f)."""
    jdy = 0

    # Check for Invalid Month or Day
    if inmn < 1 or inmn > 12:
        state.RUNERR = True
        raise RuntimeError(f"AERMOD fatal error 203 in JULIAN: MONTH = {inmn:2d}")
    # Fortran IDYMAX(INMN) -> _IDYMAX[inmn - 1]
    elif indy > _IDYMAX[inmn - 1]:
        state.RUNERR = True
        raise RuntimeError(f"AERMOD fatal error 203 in JULIAN: DAY={indy:2d} MO={inmn:2d}")

    # Determine JULIAN Day Number; For Non-Leap Year First
    if (f_mod_int(inyr, 4) != 0) or (
        f_mod_int(inyr, 100) == 0 and f_mod_int(inyr, 400) != 0
    ):
        # Not a Leap Year
        if inmn != 2 or (inmn == 2 and indy <= 28):
            # Fortran NDAY(INMN) -> _NDAY[inmn - 1]
            jdy = indy + _NDAY[inmn - 1]
        else:
            jdy = 60
            state.RUNERR = True
            raise RuntimeError(f"AERMOD fatal error 370 in JULIAN: YR= {inyr:4d}")
    else:
        # Leap Year
        # Fortran NDAY(INMN) -> _NDAY[inmn - 1]
        jdy = indy + _NDAY[inmn - 1]
        if inmn > 2:
            jdy = jdy + 1

    return jdy
