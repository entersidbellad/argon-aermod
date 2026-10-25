"""SUBROUTINE COMPTG, TGINIT, GRDPTG, REFPTG, NTRPTG, XTRPTG, XTRPDN, GRDPT, GRDDEN (tempgrid.f)."""

from __future__ import annotations

import math

from .state import AermodState, f_nint
from .iblval import locate


def comptg(state: AermodState) -> None:
    """SUBROUTINE COMPTG (tempgrid.f)."""
    state.PATH = "MX"

    ndxblw = 1
    ndxabv = 2
    state.NTGLVL = 0

    while ndxabv <= state.NPLVLS:
        # Fortran NDXBLW, NDXABV -> ndxblw - 1, ndxabv - 1
        b_idx = ndxblw - 1
        a_idx = ndxabv - 1
        if state.PFLTA[b_idx] > 0.0:
            if state.PFLTA[a_idx] > 0.0:
                state.NTGLVL = state.NTGLVL + 1
                # Fortran NTGLVL -> state.NTGLVL - 1
                tg_idx = state.NTGLVL - 1
                state.PFLTG[tg_idx] = (
                    float(state.PFLTA[a_idx]) - float(state.PFLTA[b_idx])
                ) / (
                    float(state.PFLHT[a_idx]) - float(state.PFLHT[b_idx])
                ) + state.GOVRCP
                state.PFLTGZ[tg_idx] = (
                    float(state.PFLHT[a_idx]) + float(state.PFLHT[b_idx])
                ) / 2.0
                ndxblw = ndxabv
                ndxabv = ndxabv + 1
            else:
                ndxabv = ndxabv + 1
        else:
            ndxabv = ndxabv + 1
            ndxblw = ndxblw + 1

    if state.STABLE:
        # Fortran NLVL = 1..NTGLVL -> nlvl in range(state.NTGLVL)
        for nlvl in range(state.NTGLVL):
            state.PFLTG[nlvl] = max(state.SPTGMN, float(state.PFLTG[nlvl]))

    if state.NTGLVL == 0:
        state.NTGLVL = 1


def tginit(state: AermodState) -> None:
    """SUBROUTINE TGINIT (tempgrid.f)."""
    tgminht = 2.0
    tgmaxht = 100.0
    state.PATH = "MX"

    if state.STABLE:
        reflvl = -99.0
        lvl = 1
        while reflvl < 0.0 and lvl <= state.NTGLVL:
            # Fortran LVL -> lvl - 1
            if state.PFLTGZ[lvl - 1] > state.SFCZ0:
                reflvl = float(state.PFLTGZ[lvl - 1])
            else:
                lvl = lvl + 1

        if 0.0 < reflvl <= 100.0:
            # Fortran LVL -> lvl - 1
            l_idx = lvl - 1
            state.THSTAR = (
                float(state.PFLTG[l_idx])
                * state.VONKAR
                * float(state.PFLTGZ[l_idx])
                / (1.0 + 5.0 * float(state.PFLTGZ[l_idx]) / state.OBULEN)
            )
        else:
            state.THSTAR = state.USTAR**2 / (
                state.G * state.VONKAR * state.OBULEN / state.TA
            )

        if state.L_AdjUstar and state.L_BULKRN and reflvl < 0.0:
            ustarmax = 0.6 * (
                state.UREFHT / math.log((state.UREFHT - 5.0 * state.SFCZ0) / state.SFCZ0)
            ) ** 0.333333

            ncloud8 = float(f_nint(float(state.NCLOUD) * 0.8))

            thstar0 = 1.4 * (
                0.005 / (math.tan(0.17 * (2.0 * ncloud8 + 1.0))) + 0.05
            )

            thstarn = thstar0 * (1.0 - ((2.0 * state.USTAR / ustarmax) - 1.0) ** 2.0)

            state.THSTAR = thstarn
        elif state.L_AdjUstar and not state.L_BULKRN and reflvl < 0.0:
            state.THSTAR = 0.08
        elif reflvl < 0.0:
            state.THSTAR = state.USTAR**2 / (
                state.G * state.VONKAR * state.OBULEN / state.TA
            )

        if state.L_AdjUstar:
            state.TG4PFL = (state.THSTAR / (state.VONKAR * tgminht)) * (
                0.74 + 4.7 * tgminht / state.OBULEN
            )
            state.TG4XTR = (state.THSTAR / (state.VONKAR * tgmaxht)) * (
                0.74 + 4.7 * tgmaxht / state.OBULEN
            )
        else:
            state.TG4PFL = (state.THSTAR / (state.VONKAR * tgminht)) * (
                1.0 + 5.0 * tgminht / state.OBULEN
            )
            state.TG4XTR = (state.THSTAR / (state.VONKAR * tgmaxht)) * (
                1.0 + 5.0 * tgmaxht / state.OBULEN
            )
    else:
        state.THSTAR = -9.0
        state.TG4PFL = state.XVAL


def grdptg(state: AermodState) -> None:
    """SUBROUTINE GRDPTG (tempgrid.f)."""
    gindex = 1
    pindex = 1
    vbelow = -999.0
    htbelo = 0.0

    while gindex <= state.MXGLVL:
        # Fortran GINDEX -> g_idx = gindex - 1
        g_idx = gindex - 1
        if state.STABLE:
            while state.GRIDTG[g_idx] < -90.0 and pindex <= state.NTGLVL:
                # Fortran PINDEX -> p_idx = pindex - 1
                p_idx = pindex - 1
                if state.PFLTG[p_idx] >= -50.0:
                    if (
                        abs(float(state.PFLTGZ[p_idx]) - float(state.GRIDHT[g_idx]))
                        <= 0.1
                    ):
                        state.GRIDTG[g_idx] = state.PFLTG[p_idx]
                    elif float(state.GRIDHT[g_idx]) > float(state.PFLTGZ[p_idx]):
                        if pindex < state.NTGLVL:
                            vbelow = float(state.PFLTG[p_idx])
                            htbelo = float(state.PFLTGZ[p_idx])
                        else:
                            state.GRIDTG[g_idx] = xtrptg(
                                state,
                                float(state.PFLTGZ[p_idx]),
                                float(state.PFLTG[p_idx]),
                                float(state.GRIDHT[g_idx]),
                            )
                    elif float(state.GRIDHT[g_idx]) < float(state.PFLTGZ[p_idx]):
                        if vbelow >= -50.0:
                            state.GRIDTG[g_idx] = ntrptg(
                                state,
                                htbelo,
                                vbelow,
                                float(state.PFLTGZ[p_idx]),
                                float(state.PFLTG[p_idx]),
                                float(state.GRIDHT[g_idx]),
                            )
                        else:
                            state.GRIDTG[g_idx] = xtrpdn(
                                state, float(state.GRIDHT[g_idx])
                            )
                else:
                    if pindex == state.NTGLVL:
                        if vbelow >= -50.0:
                            state.GRIDTG[g_idx] = xtrptg(
                                state,
                                float(state.PFLTGZ[p_idx]),
                                float(state.PFLTG[p_idx]),
                                float(state.GRIDHT[g_idx]),
                            )
                        else:
                            state.GRIDTG[g_idx] = refptg(
                                state, float(state.GRIDHT[g_idx])
                            )

                if state.GRIDTG[g_idx] < -50.0 and pindex < state.NTGLVL:
                    pindex = pindex + 1
        elif state.UNSTAB:
            state.GRIDTG[g_idx] = refptg(state, float(state.GRIDHT[g_idx]))

        gindex = gindex + 1

    # Apply lower limit of SPTGMN (=0.002 K/m) to lapse rate for stable layers
    # Fortran NDX = 1..MXGLVL -> ndx in range(state.MXGLVL)
    for ndx in range(state.MXGLVL):
        if state.STABLE or (state.UNSTAB and float(state.GRIDHT[ndx]) > state.ZI):
            state.GRIDTG[ndx] = max(state.SPTGMN, float(state.GRIDTG[ndx]))


def refptg(state: AermodState, htinp: float) -> float:
    """SUBROUTINE REFPTG (tempgrid.f)."""
    hdelth = 100.0
    height = htinp

    if state.UNSTAB:
        if height <= state.ZI:
            value = state.XVAL
        elif height <= state.ZI + 500.0:
            value = state.VPTGZI
        else:
            value = 0.005
    else:
        if height <= 2.0:
            value = state.TG4PFL
        elif height <= 100.0:
            if state.L_AdjUstar:
                value = (state.THSTAR / (state.VONKAR * height)) * (
                    0.74 + 4.7 * height / state.OBULEN
                )
            else:
                value = (state.THSTAR / (state.VONKAR * height)) * (
                    1.00 + 5.0 * height / state.OBULEN
                )
        else:
            exparg = -1.0 * (height - 100.0) / (
                state.EFOLDH * max(hdelth, state.ZI)
            )
            if exparg > state.EXPLIM:
                value = state.TG4XTR * math.exp(exparg)
            else:
                value = 0.0

        value = max(value, state.SPTGMN)

    return value


def ntrptg(
    state: AermodState,
    htbelo: float,
    vbelow: float,
    htabov: float,
    vabove: float,
    reqdht: float,
) -> float:
    """SUBROUTINE NTRPTG (tempgrid.f)."""
    from .metext import gintrp

    refblw = refptg(state, htbelo)
    refabv = refptg(state, htabov)
    refreq = refptg(state, reqdht)

    if abs(refabv - refblw) > 0.0001:
        valint = gintrp(htbelo, vbelow, htabov, vabove, reqdht)
        refint = gintrp(htbelo, refblw, htabov, refabv, reqdht)
        ratio = refreq / refint
        value = ratio * valint
    else:
        value = gintrp(htbelo, vbelow, htabov, vabove, reqdht)

    return value


def xtrptg(state: AermodState, pflz: float, pflval: float, grdz: float) -> float:
    """SUBROUTINE XTRPTG (tempgrid.f)."""
    hdelth = 100.0

    valobs = refptg(state, pflz)
    valgrd = refptg(state, grdz)

    if abs(valobs) < 0.0001:
        ratio = 1.0
    else:
        ratio = valgrd / valobs

    if pflz <= 100.0:
        value = ratio * pflval
    else:
        value = pflval * math.exp(
            -(grdz - pflz) / (state.EFOLDH * max(hdelth, state.ZI))
        )

    return value


def xtrpdn(state: AermodState, grdz: float) -> float:
    """SUBROUTINE XTRPDN (tempgrid.f)."""
    if state.UNSTAB:
        if grdz <= state.ZI:
            value = state.XVAL
        elif grdz <= state.ZI + 500.0:
            value = state.VPTGZI
        else:
            value = 0.005
    else:
        if grdz < 2.0:
            value = state.TG4PFL
        else:
            if state.L_AdjUstar:
                value = (state.THSTAR / (state.VONKAR * grdz)) * (
                    0.74 + 4.7 * grdz / state.OBULEN
                )
            else:
                value = (state.THSTAR / (state.VONKAR * grdz)) * (
                    1.0 + 5.0 * grdz / state.OBULEN
                )

    return value


def grdpt(state: AermodState) -> None:
    """SUBROUTINE GRDPT (tempgrid.f)."""
    nbelow = locate(state.GRIDHT, 1, state.MXGLVL, state.TREFHT)

    ptref = state.TA + state.GOVRCP * (state.TREFHT + state.ZBASE)

    # Fortran NBELOW -> nb_idx = nbelow - 1
    nb_idx = nbelow - 1
    state.GRIDPT[nb_idx] = ptref - 0.5 * (
        float(state.GRIDTG[nb_idx + 1]) + float(state.GRIDTG[nb_idx])
    ) * (state.TREFHT - float(state.GRIDHT[nb_idx]))

    # Compute Potential Temp Values for Grid Levels Below Reference Ht.
    # Fortran L = NBELOW-1, 1, -1 -> l_idx in range(nbelow - 2, -1, -1)
    for l_idx in range(nbelow - 2, -1, -1):
        state.GRIDPT[l_idx] = float(state.GRIDPT[l_idx + 1]) - 0.5 * (
            float(state.GRIDTG[l_idx + 1]) + float(state.GRIDTG[l_idx])
        ) * (float(state.GRIDHT[l_idx + 1]) - float(state.GRIDHT[l_idx]))

    # Compute Potential Temp Values for Grid Levels Above Reference Ht.
    # Fortran L = NBELOW+1, MXGLVL -> l_idx in range(nbelow, state.MXGLVL)
    for l_idx in range(nbelow, state.MXGLVL):
        state.GRIDPT[l_idx] = float(state.GRIDPT[l_idx - 1]) + 0.5 * (
            float(state.GRIDTG[l_idx]) + float(state.GRIDTG[l_idx - 1])
        ) * (float(state.GRIDHT[l_idx]) - float(state.GRIDHT[l_idx - 1]))


def grdden(state: AermodState) -> None:
    """SUBROUTINE GRDDEN (tempgrid.f)."""
    tamb0 = state.TA
    ramb0 = 1.2
    rgasm = 287.026

    # Fortran I = 1..MXGLVL -> i in range(state.MXGLVL)
    for i in range(state.MXGLVL):
        gridht_i = float(state.GRIDHT[i])
        tamb = float(state.GRIDPT[i]) - state.GOVRCP * (gridht_i + state.ZBASE)
        tbar = 0.5 * (tamb + tamb0)
        state.GRIDRHO[i] = (
            ramb0
            * (tamb0 / tamb)
            * math.exp(-state.G * gridht_i / (rgasm * tbar))
        )
