"""SUBROUTINE GRDWS, REFWS, UNSTU, STBLU, NTRPWS, XTRPWS, GRDWD, REFWD1, NTRPWD, XTRPWD (windgrid.f)."""

from __future__ import annotations

import math

from .state import AermodState


def grdws(state: AermodState) -> None:
    """SUBROUTINE GRDWS (windgrid.f)."""
    state.PATH = "MX"

    gindex = 1
    pindex = 1
    vbelow = -999.0
    htbelo = 0.0

    while gindex <= state.MXGLVL:
        # Fortran GINDEX -> g_idx = gindex - 1
        g_idx = gindex - 1
        while state.GRIDWS[g_idx] < -90.0 and pindex <= state.NPLVLS:
            # Fortran PINDEX -> p_idx = pindex - 1
            p_idx = pindex - 1
            if state.PFLWS[p_idx] >= 0.0:
                if abs(float(state.PFLHT[p_idx]) - float(state.GRIDHT[g_idx])) <= 0.1:
                    state.GRIDWS[g_idx] = state.PFLWS[p_idx]
                elif float(state.GRIDHT[g_idx]) > float(state.PFLHT[p_idx]):
                    if pindex < state.NPLVLS:
                        vbelow = float(state.PFLWS[p_idx])
                        htbelo = float(state.PFLHT[p_idx])
                    else:
                        state.GRIDWS[g_idx] = xtrpws(
                            state,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLWS[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
                elif float(state.GRIDHT[g_idx]) < float(state.PFLHT[p_idx]):
                    if vbelow >= 0.0:
                        state.GRIDWS[g_idx] = ntrpws(
                            state,
                            htbelo,
                            vbelow,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLWS[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
                    else:
                        state.GRIDWS[g_idx] = xtrpws(
                            state,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLWS[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
            else:
                if pindex == state.NPLVLS:
                    if vbelow >= 0.0:
                        state.GRIDWS[g_idx] = xtrpws(
                            state, htbelo, vbelow, float(state.GRIDHT[g_idx])
                        )
                    else:
                        state.GRIDWS[g_idx] = xtrpws(
                            state,
                            state.UREFHT,
                            state.UREF,
                            float(state.GRIDHT[g_idx]),
                        )

            if state.GRIDWS[g_idx] < 0.0 and pindex < state.NPLVLS:
                pindex = pindex + 1

        state.GRIDWS[g_idx] = max(state.UMINGR, float(state.GRIDWS[g_idx]))
        gindex = gindex + 1


def refws(state: AermodState, prflht: float) -> float:
    """SUBROUTINE REFWS (windgrid.f)."""
    pivalu = state.PI
    kvalu = state.VONKAR

    vldlb = 7.0 * state.SFCZ0
    utheor = 0.0

    if (state.UREFHT > vldlb) and (state.UREFHT <= state.ZI):
        if (prflht > vldlb) and (prflht <= state.ZI):
            if state.OBULEN < 0.0:
                utheor = unstu(
                    state.USTAR, prflht, state.OBULEN, state.SFCZ0, pivalu, kvalu
                )
            else:
                utheor = stblu(
                    state.USTAR, prflht, state.OBULEN, state.SFCZ0, kvalu
                )
        elif prflht <= vldlb:
            ufact = prflht / vldlb
            if state.OBULEN < 0.0:
                utheor = (
                    unstu(
                        state.USTAR, vldlb, state.OBULEN, state.SFCZ0, pivalu, kvalu
                    )
                    * ufact
                )
            else:
                utheor = (
                    stblu(state.USTAR, vldlb, state.OBULEN, state.SFCZ0, kvalu)
                    * ufact
                )
        elif prflht > state.ZI:
            if state.OBULEN < 0.0:
                utheor = unstu(
                    state.USTAR, state.ZI, state.OBULEN, state.SFCZ0, pivalu, kvalu
                )
            else:
                utheor = stblu(
                    state.USTAR, state.ZI, state.OBULEN, state.SFCZ0, kvalu
                )
    elif state.UREFHT > state.ZI:
        if (prflht > vldlb) and (prflht <= state.ZI):
            if state.OBULEN < 0.0:
                utheor = unstu(
                    state.USTAR, prflht, state.OBULEN, state.SFCZ0, pivalu, kvalu
                )
            else:
                utheor = stblu(
                    state.USTAR, prflht, state.OBULEN, state.SFCZ0, kvalu
                )
        elif prflht < vldlb:
            if state.OBULEN < 0.0:
                utheor = unstu(
                    state.USTAR, vldlb, state.OBULEN, state.SFCZ0, pivalu, kvalu
                )
            else:
                utheor = stblu(
                    state.USTAR, vldlb, state.OBULEN, state.SFCZ0, kvalu
                )
        elif prflht > state.ZI:
            utheor = state.UREF
    elif state.UREFHT <= vldlb:
        ufact2 = state.UREFHT / vldlb
        if (prflht > vldlb) and (prflht <= state.ZI):
            if state.OBULEN < 0.0:
                utheor = unstu(
                    state.USTAR, prflht, state.OBULEN, state.SFCZ0, pivalu, kvalu
                )
            else:
                utheor = stblu(
                    state.USTAR, prflht, state.OBULEN, state.SFCZ0, kvalu
                )
        elif prflht <= vldlb:
            ufact = prflht / vldlb
            utheor = state.UREF * ufact / ufact2
        elif prflht > state.ZI:
            if state.OBULEN < 0.0:
                utheor = unstu(
                    state.USTAR, state.ZI, state.OBULEN, state.SFCZ0, pivalu, kvalu
                )
            else:
                utheor = stblu(
                    state.USTAR, state.ZI, state.OBULEN, state.SFCZ0, kvalu
                )

    return utheor


def unstu(
    ustr: float, z: float, oblen: float, z0: float, valpi: float, valk: float
) -> float:
    """DOUBLE PRECISION FUNCTION UNSTU (windgrid.f)."""
    x0 = (1.0 - 16.0 * z / oblen) ** 0.25
    xz0 = (1.0 - 16.0 * z0 / oblen) ** 0.25

    psim = (
        2.0 * math.log((1.0 + x0) / 2.0)
        + math.log((1.0 + x0 * x0) / 2.0)
        - 2.0 * math.atan(x0)
        + valpi / 2.0
    )
    psimz0 = (
        2.0 * math.log((1.0 + xz0) / 2.0)
        + math.log((1.0 + xz0 * xz0) / 2.0)
        - 2.0 * math.atan(xz0)
        + valpi / 2.0
    )

    return (ustr / valk) * (math.log(z / z0) - psim + psimz0)


def stblu(ustr: float, z: float, oblen: float, z0: float, valk: float) -> float:
    """DOUBLE PRECISION FUNCTION STBLU (windgrid.f)."""
    psim = -17.0 * (1.0 - math.exp(-0.29 * z / oblen))
    psimz0 = -17.0 * (1.0 - math.exp(-0.29 * z0 / oblen))
    return (ustr / valk) * (math.log(z / z0) - psim + psimz0)


def ntrpws(
    state: AermodState,
    htbelo: float,
    vbelow: float,
    htabov: float,
    vabove: float,
    reqdht: float,
) -> float:
    """SUBROUTINE NTRPWS (windgrid.f)."""
    from .metext import gintrp

    refblw = refws(state, htbelo)
    refabv = refws(state, htabov)
    refreq = refws(state, reqdht)

    valint = gintrp(htbelo, vbelow, htabov, vabove, reqdht)
    refint = gintrp(htbelo, refblw, htabov, refabv, reqdht)

    ratio = refreq / refint
    valout = ratio * valint
    return valout


def xtrpws(state: AermodState, pflz: float, pflval: float, grdz: float) -> float:
    """SUBROUTINE XTRPWS (windgrid.f)."""
    valobs = refws(state, pflz)
    valgrd = refws(state, grdz)
    ratio = valgrd / valobs
    valout = ratio * pflval
    return valout


def grdwd(state: AermodState) -> None:
    """SUBROUTINE GRDWD (windgrid.f)."""
    gindex = 1
    pindex = 1
    vbelow = -999.0
    htbelo = 0.0

    while gindex <= state.MXGLVL:
        # Fortran GINDEX -> g_idx = gindex - 1
        g_idx = gindex - 1
        while state.GRIDWD[g_idx] < -90.0 and pindex <= state.NPLVLS:
            # Fortran PINDEX -> p_idx = pindex - 1
            p_idx = pindex - 1
            if state.PFLWD[p_idx] >= 0.0:
                if abs(float(state.PFLHT[p_idx]) - float(state.GRIDHT[g_idx])) <= 0.1:
                    if state.PFLWD[p_idx] > 360.0:
                        state.PFLWD[p_idx] = state.PFLWD[p_idx] - 360.0
                    elif state.PFLWD[p_idx] <= 0.0:
                        state.PFLWD[p_idx] = state.PFLWD[p_idx] + 360.0
                    state.GRIDWD[g_idx] = state.PFLWD[p_idx]
                elif float(state.GRIDHT[g_idx]) > float(state.PFLHT[p_idx]):
                    if pindex < state.NPLVLS:
                        vbelow = float(state.PFLWD[p_idx])
                        htbelo = float(state.PFLHT[p_idx])
                    else:
                        state.GRIDWD[g_idx] = xtrpwd(
                            state, float(state.PFLWD[p_idx])
                        )
                elif float(state.GRIDHT[g_idx]) < float(state.PFLHT[p_idx]):
                    if vbelow >= 0.0:
                        state.GRIDWD[g_idx] = ntrpwd(
                            state,
                            htbelo,
                            vbelow,
                            float(state.PFLHT[p_idx]),
                            float(state.PFLWD[p_idx]),
                            float(state.GRIDHT[g_idx]),
                        )
                    else:
                        state.GRIDWD[g_idx] = xtrpwd(
                            state, float(state.PFLWD[p_idx])
                        )
            else:
                if pindex == state.NPLVLS:
                    if vbelow >= 0.0:
                        state.GRIDWD[g_idx] = xtrpwd(state, vbelow)
                    else:
                        state.GRIDWD[g_idx] = xtrpwd(state, state.WDREF)

            if state.GRIDWD[g_idx] < 0.0 and pindex < state.NPLVLS:
                pindex = pindex + 1

        gindex = gindex + 1


def refwd1(state: AermodState) -> float:
    """SUBROUTINE REFWD1 (windgrid.f)."""
    return state.WDREF


def ntrpwd(
    state: AermodState,
    htbelo: float,
    vbelow: float,
    htabov: float,
    vabove: float,
    reqdht: float,
) -> float:
    """SUBROUTINE NTRPWD (windgrid.f)."""
    from .metext import gintrp

    valabv = vabove

    refblw = refwd1(state)
    refabv = refwd1(state)
    refreq = refwd1(state)

    if (valabv - vbelow) < -180.0:
        valabv = valabv + 360.0
    elif (valabv - vbelow) > 180.0:
        valabv = valabv - 360.0

    valint = gintrp(htbelo, vbelow, htabov, valabv, reqdht)
    refint = gintrp(htbelo, refblw, htabov, refabv, reqdht)
    ratio = refreq / refint
    valout = ratio * valint

    if valout > 360.0:
        valout = valout - 360.0
    elif valout <= 0.0:
        valout = valout + 360.0

    return valout


def xtrpwd(state: AermodState, pflval: float) -> float:
    """SUBROUTINE XTRPWD (windgrid.f)."""
    valobs = refwd1(state)
    valgrd = refwd1(state)

    ratio = valgrd / valobs
    valout = ratio * pflval

    if valout > 360.0:
        valout = valout - 360.0
    elif valout <= 0.0:
        valout = valout + 360.0

    return valout
