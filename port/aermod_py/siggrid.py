"""SUBROUTINE GRDSV, REFSV, REFSVC, REFSVM, NTRPSV, XTRPSV, GRDSW, REFSW, REFSWC, REFSWM, NTRPSW, XTRPSW (siggrid.f)."""

from __future__ import annotations

import math

from .state import AermodState


def grdsv(state: AermodState) -> None:
    """SUBROUTINE GRDSV (siggrid.f)."""
    gindex = 1
    pindex = 1
    vbelow = -999.0
    htbelo = 0.0

    while gindex <= state.MXGLVL:
        # Fortran GINDEX -> g_idx = gindex - 1
        g_idx = gindex - 1
        while state.GRIDSV[g_idx] < -90.0 and pindex <= state.NPLVLS:
            # Fortran PINDEX -> p_idx = pindex - 1
            p_idx = pindex - 1
            if state.PFLSV[p_idx] >= 0.0:
                if abs(float(state.PFLHT[p_idx]) - float(state.GRIDHT[g_idx])) <= 0.1:
                    state.GRIDSV[g_idx] = state.PFLSV[p_idx]
                elif float(state.GRIDHT[g_idx]) > float(state.PFLHT[p_idx]):
                    if pindex < state.NPLVLS:
                        vbelow = float(state.PFLSV[p_idx])
                        htbelo = float(state.PFLHT[p_idx])
                    else:
                        state.GRIDSV[g_idx] = xtrpsv(
                            state,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLSV[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
                elif float(state.GRIDHT[g_idx]) < float(state.PFLHT[p_idx]):
                    if vbelow >= 0.0:
                        state.GRIDSV[g_idx] = ntrpsv(
                            state,
                            htbelo,
                            vbelow,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLSV[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
                    else:
                        state.GRIDSV[g_idx] = xtrpsv(
                            state,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLSV[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
            else:
                if pindex == state.NPLVLS:
                    if vbelow >= 0.0:
                        state.GRIDSV[g_idx] = xtrpsv(
                            state, htbelo, vbelow, float(state.GRIDHT[g_idx])
                        )
                    else:
                        state.GRIDSV[g_idx] = refsv(
                            state, float(state.GRIDHT[g_idx])
                        )

            if state.GRIDSV[g_idx] < 0.0 and pindex < state.NPLVLS:
                pindex = pindex + 1

        gindex = gindex + 1


def refsv(state: AermodState, htinp: float) -> float:
    """SUBROUTINE REFSV (siggrid.f)."""
    height = htinp
    value = 0.0

    if state.UNSTAB:
        svc = refsvc(state, height)
        svm = refsvm(state, height)
        value = math.sqrt(svc * svc + svm * svm)
    elif state.STABLE:
        svm = refsvm(state, height)
        value = svm

    return value


def refsvc(state: AermodState, htinp: float) -> float:
    """SUBROUTINE REFSVC (siggrid.f)."""
    from .metext import gintrp

    height = htinp
    zdcrs = state.AT1PT2 * state.ZICONV

    sv2 = 0.35 * state.WSTAR**2

    if height <= state.ZICONV:
        value = math.sqrt(sv2)
    elif state.ZICONV < height <= zdcrs:
        sv2dcr = min(sv2, 0.25)
        val2 = gintrp(state.ZICONV, sv2, zdcrs, sv2dcr, height)
        value = math.sqrt(val2)
    else:
        atzi = math.sqrt(sv2)
        value = min(atzi, 0.5)

    return value


def refsvm(state: AermodState, htinp: float) -> float:
    """SUBROUTINE REFSVM (siggrid.f)."""
    from .metext import gintrp

    height = htinp

    sv02 = 3.6 * state.USTAR**2
    sv2zi = min(sv02, 0.25)

    if height <= state.ZIMECH:
        varv = gintrp(0.0, sv02, state.ZIMECH, sv2zi, height)
        value = math.sqrt(varv)
    else:
        value = math.sqrt(sv2zi)

    return value


def ntrpsv(
    state: AermodState,
    htbelo: float,
    vbelow: float,
    htabov: float,
    vabove: float,
    reqdht: float,
) -> float:
    """SUBROUTINE NTRPSV (siggrid.f)."""
    from .metext import gintrp

    refblw = refsv(state, htbelo)
    refabv = refsv(state, htabov)
    refreq = refsv(state, reqdht)

    valint = gintrp(htbelo, vbelow, htabov, vabove, reqdht)
    refint = gintrp(htbelo, refblw, htabov, refabv, reqdht)
    ratio = refreq / refint
    value = ratio * valint
    return value


def xtrpsv(state: AermodState, pflz: float, pflval: float, grdz: float) -> float:
    """SUBROUTINE XTRPSV (siggrid.f)."""
    valobs = refsv(state, pflz)
    valgrd = refsv(state, grdz)
    ratio = valgrd / valobs
    value = ratio * pflval
    return value


def grdsw(state: AermodState) -> None:
    """SUBROUTINE GRDSW (siggrid.f)."""
    gindex = 1
    pindex = 1
    vbelow = -999.0
    htbelo = 0.0

    while gindex <= state.MXGLVL:
        # Fortran GINDEX -> g_idx = gindex - 1
        g_idx = gindex - 1
        while state.GRIDSW[g_idx] < -90.0 and pindex <= state.NPLVLS:
            # Fortran PINDEX -> p_idx = pindex - 1
            p_idx = pindex - 1
            if state.PFLSW[p_idx] >= 0.0:
                if abs(float(state.PFLHT[p_idx]) - float(state.GRIDHT[g_idx])) <= 0.1:
                    state.GRIDSW[g_idx] = state.PFLSW[p_idx]
                elif float(state.GRIDHT[g_idx]) > float(state.PFLHT[p_idx]):
                    if pindex < state.NPLVLS:
                        vbelow = float(state.PFLSW[p_idx])
                        htbelo = float(state.PFLHT[p_idx])
                    else:
                        state.GRIDSW[g_idx] = xtrpsw(
                            state,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLSW[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
                elif float(state.GRIDHT[g_idx]) < float(state.PFLHT[p_idx]):
                    if vbelow >= 0.0:
                        state.GRIDSW[g_idx] = ntrpsw(
                            state,
                            htbelo,
                            vbelow,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLSW[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
                    else:
                        state.GRIDSW[g_idx] = xtrpsw(
                            state,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLSW[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
            else:
                if pindex == state.NPLVLS:
                    if vbelow >= 0.0:
                        state.GRIDSW[g_idx] = xtrpsw(
                            state, htbelo, vbelow, float(state.GRIDHT[g_idx])
                        )
                    else:
                        state.GRIDSW[g_idx] = refsw(
                            state, float(state.GRIDHT[g_idx])
                        )

            if state.GRIDSW[g_idx] < 0.0 and pindex < state.NPLVLS:
                pindex = pindex + 1

        gindex = gindex + 1


def refsw(state: AermodState, htinp: float) -> float:
    """SUBROUTINE REFSW (siggrid.f)."""
    height = htinp
    value = 0.0

    if state.UNSTAB:
        swc = refswc(state, height)
        swm = refswm(state, height)
        swc = max(swc, 0.0001)
        swm = max(swm, 0.0001)
        value = math.sqrt(swc * swc + swm * swm)
    elif state.STABLE:
        swm = refswm(state, height)
        value = max(swm, 0.0001)

    return value


def refswc(state: AermodState, htinp: float) -> float:
    """SUBROUTINE REFSWC (siggrid.f)."""
    height = htinp
    value = 0.0

    if height <= 0.1 * state.ZICONV:
        sw2 = (
            1.6
            * (height / state.ZICONV) ** (2.0 * state.THIRD)
            * state.WSTAR**2
        )
        value = math.sqrt(sw2)
    elif 0.1 * state.ZICONV < height <= state.ZICONV:
        value = math.sqrt(0.35 * state.WSTAR**2)
    elif height > state.ZICONV:
        exparg = -6.0 * (height - state.ZICONV) / state.ZICONV
        if exparg > state.EXPLIM:
            sw2 = 0.35 * state.WSTAR**2 * math.exp(exparg)
            value = math.sqrt(sw2)
        else:
            value = 0.0

    return value


def refswm(state: AermodState, htinp: float) -> float:
    """SUBROUTINE REFSWM (siggrid.f)."""
    height = htinp

    swr = state.SWRMAX * min(1.0, height / state.ZI)
    if height < state.ZI:
        swbl = 1.3 * state.USTAR * math.sqrt(1.0 - height / state.ZI)
    else:
        swbl = 0.0

    value = math.sqrt(swr * swr + swbl * swbl)
    return value


def ntrpsw(
    state: AermodState,
    htbelo: float,
    vbelow: float,
    htabov: float,
    vabove: float,
    reqdht: float,
) -> float:
    """SUBROUTINE NTRPSW (siggrid.f)."""
    from .metext import gintrp

    refblw = refsw(state, htbelo)
    refabv = refsw(state, htabov)
    refreq = refsw(state, reqdht)

    valint = gintrp(htbelo, vbelow, htabov, vabove, reqdht)
    refint = gintrp(htbelo, refblw, htabov, refabv, reqdht)
    ratio = refreq / refint
    value = ratio * valint
    return value


def xtrpsw(state: AermodState, pflz: float, pflval: float, grdz: float) -> float:
    """SUBROUTINE XTRPSW (siggrid.f)."""
    valobs = refsw(state, pflz)
    valgrd = refsw(state, grdz)
    ratio = valgrd / valobs
    value = ratio * pflval
    return value
