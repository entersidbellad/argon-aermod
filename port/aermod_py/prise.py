"""SUBROUTINE DELTAH, HSPRIM, SBLRIS, CBLPRD, CBLPRN, CBLPR3 (prise.f)."""

from __future__ import annotations

import math

from .state import AermodState
from .iblval import locate
from .metext import gintrp


def deltah(state: AermodState, xarg: float) -> None:
    """SUBROUTINE DELTAH (prise.f)."""
    if (state.STABLE or (state.UNSTAB and (state.HS >= state.ZI))) and (
        xarg >= state.XMAX
    ):
        state.DHP = state.DHFAER

    elif (state.STABLE or (state.UNSTAB and (state.HS >= state.ZI))) and (
        xarg < state.XMAX
    ):
        xmaxtmp = (
            state.UP
            * math.atan2(state.FM * state.BVPRIM, -state.FB)
            / state.BVPRIM
        )
        xrise = min(xarg, xmaxtmp)
        sblris(state, xrise)
        kiter = 0

        isrc = state.ISRC
        irec = state.IREC
        comp = state.debug_comp

        while True:
            zplm = state.HSP + 0.5 * state.DHP
            dhpold = state.DHP

            # Locate index below ZPLM
            ndxzpl = locate(state.GRIDHT, 1, state.MXGLVL, zplm)
            # Fortran NDXZPL -> idx = ndxzpl - 1, NDXZPL+1 -> idx + 1
            idx = ndxzpl - 1
            ht_lo = float(state.GRIDHT[idx])
            ht_hi = float(state.GRIDHT[idx + 1])

            svpm = gintrp(
                ht_lo,
                float(state.GRIDSV[idx]),
                ht_hi,
                float(state.GRIDSV[idx + 1]),
                zplm,
            )
            upm = gintrp(
                ht_lo,
                float(state.GRIDWS[idx]),
                ht_hi,
                float(state.GRIDWS[idx + 1]),
                zplm,
            )

            svpm = max(svpm, state.SVMIN, state.SVUMIN * upm)
            if state.L_VECTORWS:
                upm = math.sqrt(upm * upm + 2.0 * svpm * svpm)
            upm = max(upm, state.WSMIN)

            state.UP = 0.5 * (state.US + upm)

            tgpm = gintrp(
                ht_lo,
                float(state.GRIDTG[idx]),
                ht_hi,
                float(state.GRIDTG[idx + 1]),
                zplm,
            )
            ptpm = gintrp(
                ht_lo,
                float(state.GRIDPT[idx]),
                ht_hi,
                float(state.GRIDPT[idx + 1]),
                zplm,
            )

            state.TGP = 0.5 * (state.TGS + tgpm)
            ptp = 0.5 * (state.PTS + ptpm)
            state.BVF = math.sqrt(state.G * state.TGP / ptp)
            if state.BVF < 1.0e-10:
                state.BVF = 1.0e-10
            state.BVPRIM = 0.7 * state.BVF

            xmaxtmp = (
                state.UP
                * math.atan2(state.FM * state.BVPRIM, -state.FB)
                / state.BVPRIM
            )
            xrise = min(xarg, xmaxtmp)
            sblris(state, xrise)

            kiter = kiter + 1

            if state.DEBUG:
                # WRITE(DBGUNT,6001) KITER, DHPOLD, DHP, ZPLM, UP, TGP
                state.emit_debug(isrc, irec, comp, "DELTAH", "DHPOLD", dhpold)
                state.emit_debug(isrc, irec, comp, "DELTAH", "DHP", state.DHP)
                state.emit_debug(isrc, irec, comp, "DELTAH", "ZPLM", zplm)
                state.emit_debug(isrc, irec, comp, "DELTAH", "UP", state.UP)
                state.emit_debug(isrc, irec, comp, "DELTAH", "TGP", state.TGP)

            # Check for convergence
            if (
                state.DHP > 0.0
                and abs((dhpold - state.DHP) / state.DHP) < 0.001
                and kiter >= 5
            ):
                if state.DHP <= 1.0e-5:
                    state.DHP = 1.0e-5
                break
            elif kiter < 10:
                continue

            if kiter >= 5:
                state.DHP = 0.5 * (state.DHP + dhpold)
                break

        # After completing iteration, reset UP and TGP to stack top values
        state.UP = state.US
        state.TGP = state.TGS
        ptp = state.PTS
        state.BVF = math.sqrt(state.G * state.TGP / ptp)
        if state.BVF < 1.0e-10:
            state.BVF = 1.0e-10
        state.BVPRIM = 0.7 * state.BVF

        # Make sure SBL rise is not greater than CBL rise
        cblprd(state, xarg)
        state.DHP = min(state.DHP, state.DHP1)
        state.DHP = min(state.DHP, state.DHFAER)

    elif state.UNSTAB:
        # Compute plume rise for the direct plume --- CALL CBLPRD
        cblprd(state, xarg)

        # Compute plume rise for the indirect plume --- CALL CBLPRN
        cblprn(state, xarg)

        if state.PPF > 0.0:
            cblpr3(state)
        else:
            state.DHP3 = 0.0


def hsprim(us: float, vs: float, hs: float, ds: float) -> float:
    """FUNCTION HSPRIM (prise.f)."""
    if vs < 1.5 * us:
        res = hs - 2.0 * ds * (1.5 - vs / us)
    else:
        res = hs

    if res < 0.0:
        res = 0.0

    return res


def sblris(state: AermodState, xarg: float) -> None:
    """SUBROUTINE SBLRIS (prise.f)."""
    terma = state.FB / (state.BVF * state.BVF * state.UP)
    termb = state.BVPRIM * state.FM / state.FB
    termc = math.sin(state.BVPRIM * xarg / state.UP)
    termd = math.cos(state.BVPRIM * xarg / state.UP)

    terme = termb * termc + 1.0 - termd

    if terme > 0.0:
        state.DHP = 2.66 * (terma * (termb * termc + 1.0 - termd)) ** state.THIRD
    else:
        state.DHP = 2.66 * max(0.0, terma * termb * termc) ** state.THIRD

    xln = state.FB / (state.UP * state.USTAR * state.USTAR)
    delhnn = 1.2 * xln**0.6 * (state.HSP + 1.2 * xln) ** 0.4

    state.DHP = min(state.DHP, state.DHFAER, delhnn)


def cblprd(state: AermodState, xarg: float) -> None:
    """SUBROUTINE CBLPRD (prise.f)."""
    state.DHP1 = (
        3.0 * state.FM * xarg / (state.BETA1 * state.BETA1 * state.UP * state.UP)
        + 3.0
        * state.FB
        * xarg
        * xarg
        / (2.0 * state.BETA1 * state.BETA1 * state.UP * state.UP * state.UP)
    ) ** state.THIRD


def cblprn(state: AermodState, xarg: float) -> None:
    """SUBROUTINE CBLPRN (prise.f)."""
    rsubh = state.BETA2 * (state.ZI - state.HSP)
    ryrz = (
        rsubh * rsubh
        + 0.25
        * state.ASUBE
        * (state.LAMDAY**1.5)
        * state.WSTAR
        * state.WSTAR
        * xarg
        * xarg
        / (state.UP * state.UP)
    )
    delhi = (
        math.sqrt((2.0 * state.FB * state.ZI) / (state.ALPHAR * state.UP * ryrz))
        * (xarg / state.UP)
    )
    state.DHP2 = delhi


def cblpr3(state: AermodState) -> None:
    """SUBROUTINE CBLPR3 (prise.f)."""
    if state.PPF == 1.0:
        state.DHP3 = state.HEDHH * (state.ZI - state.HSP)
    else:
        state.DHP3 = (
            0.75 * (state.ZI - state.HSP) * state.HEDHH
            + 0.5 * (state.ZI - state.HSP)
        )
