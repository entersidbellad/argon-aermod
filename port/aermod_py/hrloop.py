"""SUBROUTINE HRLOOP and SUBROUTINE JULIAN (aermod.f)."""

from __future__ import annotations

from .state import AermodState, f_idiv, f_mod_int
from .metext import metext
from .calc1 import calc


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


def hrloop(state: AermodState) -> None:
    """SUBROUTINE HRLOOP (aermod.f)."""
    state.EOF = False
    if state.L_MorningTrans is not None:
        state.L_MorningTrans[:] = False
    state.KURDAT = 0
    state.KURPFL = 0
    state.FULLDATE = 0

    # Begin Hourly LOOP
    while state.FULLDATE <= state.IEDATE and not state.EOF:
        # Retrieve One Hour of Meteorology --- CALL METEXT
        metext(state)

        # Check for runtime error generated in call to METEXT
        if state.RUNERR:
            break

        # Fortran IPROC(JDAY) / IPROCL(JDAY) -> state.IPROC[state.JDAY - 1]
        jday_idx = state.JDAY - 1
        in_day_range = (
            (not state.L_LeapYear and state.IPROC[jday_idx] == 1)
            or (state.L_LeapYear and state.IPROCL[jday_idx] == 1)
        ) if 1 <= state.JDAY <= 366 else False

        if (
            state.FULLDATE >= state.ISDATE
            and state.FULLDATE <= state.IEDATE
            and in_day_range
            and not state.EOF
        ):
            if not state.L_SkipMessages:
                state.NTOTHRS = state.NTOTHRS + 1
        elif (
            state.FULLDATE < state.IEDATE
            and state.IEDATE < 2147123124
            and state.EOF
        ):
            # End of met data file(s) reached before user-specified End Date
            raise RuntimeError("AERMOD fatal error 580 in HRLOOP: MET-DATA")
        elif state.EOF or state.FULLDATE > state.IEDATE:
            # End of File or data period has been reached; EXIT hour loop
            break

        ilsave = state.ILINE

        if state.HOURLY:
            raise RuntimeError("HOURLY emissions out of scope")

        if state.RUNERR:
            break

        ilsave = state.ILINE

        if state.L_BACKGRND:
            if state.L_BGHourly:
                raise RuntimeError("Hourly BACKGRND out of scope")
            else:
                if state.IBGSECT > 0:
                    # Fortran L_BGValues(IBGSECT) -> state.L_BGValues[state.IBGSECT - 1]
                    if state.L_BGValues[state.IBGSECT - 1]:
                        raise RuntimeError("BGVAL out of scope")
                    else:
                        state.BGCONC = 0.0
                else:
                    state.BGCONC = 0.0

        if state.RUNERR:
            break

        state.ILINE = ilsave

        if state.PVMRM or state.OLM or state.RUNTTRM or state.GRSM:
            if state.L_O3Hourly:
                raise RuntimeError("Hourly O3 out of scope")
            elif state.IO3SECT > 0:
                # Fortran IO3SECT -> state.IO3SECT - 1
                if state.L_O3VALUES[state.IO3SECT - 1]:
                    raise RuntimeError("OZONVALS out of scope")
                elif state.L_O3VAL[state.IO3SECT - 1]:
                    state.O3CONC = float(state.O3BACK[state.IO3SECT - 1])
                else:
                    state.O3CONC = 0.0
            else:
                state.O3CONC = 0.0

        if state.GRSM:
            if state.L_NOxHourly:
                raise RuntimeError("Hourly NOx out of scope")
            elif state.INOXSECT > 0:
                # Fortran INOXSECT -> state.INOXSECT - 1
                if state.L_NOX_VALS[state.INOXSECT - 1]:
                    raise RuntimeError("VARYNOXVALS out of scope")
                elif state.L_NOXVALUE[state.INOXSECT - 1]:
                    state.NOXBGCONC = float(state.NOXBACK[state.INOXSECT - 1])
                else:
                    state.NOXBGCONC = 0.0
            else:
                state.NOXBGCONC = 0.0

        if state.RUNERR:
            break

        state.ILINE = ilsave

        if state.SCIM and not state.EOF:
            state.SCIMHR = False
            state.NSKIPTOT = state.NSKIPTOT + 1
            if state.ILINE <= 24 and state.IHOUR == state.NREGSTART:
                state.IFIRSTHR = state.ILINE
                state.SCIMHR = True
            elif (
                state.ILINE > state.NREGSTART
                and f_mod_int(state.ILINE - state.IFIRSTHR, state.NREGINT) == 0
            ):
                state.SCIMHR = True
            else:
                continue

        if (
            (
                (not state.RSTINP and state.FULLDATE >= state.ISDATE)
                or (state.RSTINP and not state.MULTYR and state.FULLDATE > state.ISDATE)
                or (state.MULTYR and state.FULLDATE >= state.ISDATE)
            )
            and state.FULLDATE <= state.IEDATE
            and in_day_range
            and not state.EOF
            and not state.RUNERR
        ):
            state.hr_conc[:] = 0.0

            if state.CLMHR and state.CLMPRO:
                # Check for Calm Hr & Processing and Increment Counters
                # Fortran IAVE = 1..NUMAVE -> iave in range(state.NUMAVE)
                for iave in range(state.NUMAVE):
                    state.NUMHRS[iave] = state.NUMHRS[iave] + 1
                    state.NUMCLM[iave] = state.NUMCLM[iave] + 1
                if state.PERIOD or state.ANNUAL:
                    if not state.SCIM or (state.SCIM and state.SCIMHR):
                        state.IANHRS = state.IANHRS + 1
                        state.IANCLM = state.IANCLM + 1
                if state.SEASONHR:
                    # Fortran NSEAHR(ISEAS, IHOUR) -> state.NSEAHR[state.ISEAS - 1, state.IHOUR - 1]
                    state.NSEAHR[state.ISEAS - 1, state.IHOUR - 1] += 1
                    state.NSEACM[state.ISEAS - 1, state.IHOUR - 1] += 1
            elif state.MSGHR and state.MSGPRO:
                # Check for Missing Hour & Processing and Increment Counters
                # Fortran IAVE = 1..NUMAVE -> iave in range(state.NUMAVE)
                for iave in range(state.NUMAVE):
                    state.NUMHRS[iave] = state.NUMHRS[iave] + 1
                    state.NUMMSG[iave] = state.NUMMSG[iave] + 1
                if state.PERIOD or state.ANNUAL:
                    if not state.SCIM or (state.SCIM and state.SCIMHR):
                        state.IANHRS = state.IANHRS + 1
                        state.IANMSG = state.IANMSG + 1
                if state.SEASONHR:
                    # Fortran NSEAHR(ISEAS, IHOUR) -> state.NSEAHR[state.ISEAS - 1, state.IHOUR - 1]
                    state.NSEAHR[state.ISEAS - 1, state.IHOUR - 1] += 1
                    state.NSEACM[state.ISEAS - 1, state.IHOUR - 1] += 1
            elif state.ZI <= 0.0:
                # Write Out The Informational Message & Increment Counters
                # Fortran IAVE = 1..NUMAVE -> iave in range(state.NUMAVE)
                for iave in range(state.NUMAVE):
                    state.NUMHRS[iave] = state.NUMHRS[iave] + 1
                if state.PERIOD or state.ANNUAL:
                    if not state.SCIM or (state.SCIM and state.SCIMHR):
                        state.IANHRS = state.IANHRS + 1
                if state.SEASONHR:
                    # Fortran NSEAHR(ISEAS, IHOUR) -> state.NSEAHR[state.ISEAS - 1, state.IHOUR - 1]
                    state.NSEAHR[state.ISEAS - 1, state.IHOUR - 1] += 1
            else:
                # Set CALCS Flag, Increment Counters & Calculate HRVAL
                state.CALCS = True
                # Fortran IAVE = 1..NUMAVE -> iave in range(state.NUMAVE)
                for iave in range(state.NUMAVE):
                    state.NUMHRS[iave] = state.NUMHRS[iave] + 1
                if state.PERIOD or state.ANNUAL:
                    if not state.SCIM or (state.SCIM and state.SCIMHR):
                        state.IANHRS = state.IANHRS + 1
                if state.SEASONHR:
                    # Fortran NSEAHR(ISEAS, IHOUR) -> state.NSEAHR[state.ISEAS - 1, state.IHOUR - 1]
                    state.NSEAHR[state.ISEAS - 1, state.IHOUR - 1] += 1

                # Calculate CONC or DEPOS Values --- CALL CALC
                calc(state)

            # Record 1-hour POSTFILE concentration for this processed hour
            state.dates_out.append(int(state.KURDAT))
            state.conc_out.append(state.hr_conc.copy())

            # Begin Averaging Period LOOP
            # Fortran IAVE = 1..NUMAVE -> iave in range(state.NUMAVE)
            for iave in range(state.NUMAVE):
                state.IAVE = iave + 1
                kave_val = int(state.KAVE[iave])
                if f_mod_int(state.IHOUR, kave_val) == 0 or (
                    kave_val == 720 and state.ENDMON
                ):
                    # Flush Block Average Values in AVEVAL Array for This IAVE
                    state.AVEVAL[:, :, iave, :] = 0.0

            # Flush HRVAL Arrays (1:NUMTYP)
            state.HRVAL[:] = 0.0
            state.AERVAL[:] = 0.0
            state.PRMVAL[:] = 0.0

        if (
            state.FULLDATE == state.ISDATE
            and not state.EOF
            and not state.NOCHKD
            and not state.L_WARNCHKD
            and (
                state.PM25AVE
                or state.NO2AVE
                or state.SO2AVE
                or state.ANNUAL
                or state.MULTYR
            )
        ):
            state.NREMAIN = state.NREMAIN + 1

        # Reset CALCS and ENDMON Flags
        state.CALCS = False
        state.ENDMON = False

        # Save precipitation rates for two previous hours
        state.PREC2 = state.PREC1
        state.PREC1 = state.PRATE
