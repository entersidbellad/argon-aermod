"""SUBROUTINE EMFACT, DISTF, WAKFLG, XYDIST, FTERM, FYPLM, FYPAN, MEANDR, CRITDS, PDF, SKCALC, CRCALC, ALCALC, BECALC, AACALC, BBCALC, LLCALC, DECAY, VRTSBL, VRTSBN, VRTCBL, PFRACT, ERFX, SUMVAL (calc2.f)."""

from __future__ import annotations

import math
import numpy as xp

from .state import AermodState
from .iblval import locate
from .prise import cblprd


def emfact(state: AermodState, qarg: float) -> None:
    """SUBROUTINE EMFACT (calc2.f)."""
    # Fortran ISRC (1-based) -> isrc_idx = state.ISRC - 1
    isrc_idx = state.ISRC - 1
    qflag = str(state.QFLAG[isrc_idx]).strip()

    if qflag == "":
        state.QTK = qarg
    elif qflag == "HOURLY":
        state.QTK = qarg
    elif qflag == "MONTH":
        # Fortran IMONTH -> state.IMONTH - 1
        state.QTK = qarg * float(state.QFACT[state.IMONTH - 1, isrc_idx])
    elif qflag == "HROFDY":
        # Fortran IHOUR -> state.IHOUR - 1
        state.QTK = qarg * float(state.QFACT[state.IHOUR - 1, isrc_idx])
    elif qflag == "WSPEED":
        # Fortran IUCAT -> state.IUCAT - 1
        state.QTK = qarg * float(state.QFACT[state.IUCAT - 1, isrc_idx])
    elif qflag == "SEASON":
        # Fortran ISEAS -> state.ISEAS - 1
        state.QTK = qarg * float(state.QFACT[state.ISEAS - 1, isrc_idx])
    elif qflag == "SEASHR":
        # Fortran IHOUR+(ISEAS-1)*24 -> (state.IHOUR + (state.ISEAS - 1)*24) - 1
        idx = state.IHOUR + (state.ISEAS - 1) * 24 - 1
        state.QTK = qarg * float(state.QFACT[idx, isrc_idx])
    elif qflag == "HRDOW":
        # Fortran IHOUR+(IDAY_OF_WEEK-1)*24 -> (state.IHOUR + (state.IDAY_OF_WEEK - 1)*24) - 1
        idx = state.IHOUR + (state.IDAY_OF_WEEK - 1) * 24 - 1
        state.QTK = qarg * float(state.QFACT[idx, isrc_idx])
    elif qflag == "HRDOW7":
        # Fortran IHOUR+(IDAY_OF_WEEK7-1)*24 -> (state.IHOUR + (state.IDAY_OF_WEEK7 - 1)*24) - 1
        idx = state.IHOUR + (state.IDAY_OF_WEEK7 - 1) * 24 - 1
        state.QTK = qarg * float(state.QFACT[idx, isrc_idx])
    elif qflag == "SHRDOW":
        idx = (
            state.IHOUR
            + (state.ISEAS - 1) * 24
            + (state.IDAY_OF_WEEK - 1) * 96
            - 1
        )
        state.QTK = qarg * float(state.QFACT[idx, isrc_idx])
    elif qflag == "SHRDOW7":
        idx = (
            state.IHOUR
            + (state.ISEAS - 1) * 24
            + (state.IDAY_OF_WEEK7 - 1) * 96
            - 1
        )
        state.QTK = qarg * float(state.QFACT[idx, isrc_idx])
    elif qflag == "MHRDOW":
        idx = (
            state.IHOUR
            + (state.IMONTH - 1) * 24
            + (state.IDAY_OF_WEEK - 1) * 288
            - 1
        )
        state.QTK = qarg * float(state.QFACT[idx, isrc_idx])
    elif qflag == "MHRDOW7":
        idx = (
            state.IHOUR
            + (state.IMONTH - 1) * 24
            + (state.IDAY_OF_WEEK7 - 1) * 288
            - 1
        )
        state.QTK = qarg * float(state.QFACT[idx, isrc_idx])


def distf(state: AermodState) -> None:
    """SUBROUTINE DISTF (calc2.f)."""
    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        state.XMAX = (
            state.UP
            * math.atan2(state.FM * state.BVPRIM, -state.FB)
            / state.BVPRIM
        )

        state.DHFAER = (
            2.66 * (state.FB / (state.BVF * state.BVF * state.UP)) ** state.THIRD
        )
        xln = state.FB / (state.UP * state.USTAR * state.USTAR)
        delhnn = 1.2 * xln**0.6 * (state.HSP + 1.2 * xln) ** 0.4
        state.DHFAER = min(state.DHFAER, delhnn)

        # Compute Neutral/Unstable Final Rise
        if state.FB <= 0.0:
            xmaxn = (
                4.0
                * state.DS
                * (state.VS + 3.0 * state.UP)
                * (state.VS + 3.0 * state.UP)
                / (state.VS * state.UP)
            )
            state.DHFAER = min(
                state.DHFAER, 3.0 * state.DS * state.VS / state.UP
            )
        else:
            if state.FB >= 55.0:
                xmaxn = 119.0 * state.FB**0.4
            else:
                xmaxn = 49.0 * state.FB**0.625
            cblprd(state, xmaxn)
            state.DHFAER = min(state.DHFAER, state.DHP1)

        # Apply calm, stable rise limit
        state.DHFAER = min(
            state.DHFAER,
            4.0 * state.FB**0.25 / (state.BVF * state.BVF) ** 0.375,
        )

        dhfsav = state.DHFAER

        if state.URBSTAB:
            if state.HSP + state.DHFAER >= state.ZI and state.HSP < state.ZI:
                bvzi2 = (state.G / state.PTATZI) * 0.005
                state.PSUBS = state.FB / (
                    state.UP
                    * bvzi2
                    * (state.ZI - state.HSP)
                    * (state.ZI - state.HSP)
                    * (state.ZI - state.HSP)
                )
                state.HEDHH = (17.576 * state.PSUBS + 0.296296) ** state.THIRD

                if state.HEDHH < (2.0 * state.THIRD):
                    state.PPF = 0.0
                elif state.HEDHH > 2.0:
                    state.PPF = 1.0
                else:
                    state.PPF = 1.5 - (1.0 / state.HEDHH)

                if state.PPF > 0.0:
                    if state.PPF == 1.0:
                        state.DHFAER = state.HEDHH * (state.ZI - state.HSP)
                    else:
                        state.DHFAER = (
                            0.75 * (state.ZI - state.HSP) * state.HEDHH
                            + 0.5 * (state.ZI - state.HSP)
                        )
                else:
                    state.DHFAER = dhfsav
    else:
        # Unstable plume
        if state.FB <= 0.0:
            state.XMAX = (
                4.0
                * state.DS
                * (state.VS + 3.0 * state.UP)
                * (state.VS + 3.0 * state.UP)
                / (state.VS * state.UP)
            )
            state.DHFAER = 3.0 * state.DS * state.VS / state.UP
        else:
            if state.FB >= 55.0:
                state.XMAX = 119.0 * state.FB**0.4
            else:
                state.XMAX = 49.0 * state.FB**0.625
            cblprd(state, state.XMAX)
            state.DHFAER = state.DHP1


def wakflg(state: AermodState) -> None:
    """SUBROUTINE WAKFLG (calc2.f)."""
    if state.IFVSEC <= state.NSEC and state.NSEC > 0:
        # Fortran (IFVSEC, ISRC) -> [state.IFVSEC - 1, state.ISRC - 1]
        sec_idx = state.IFVSEC - 1
        src_idx = state.ISRC - 1
        state.DSBH = float(state.ADSBH[sec_idx, src_idx])
        state.DSBW = float(state.ADSBW[sec_idx, src_idx])
        state.DSBL = float(state.ADSBL[sec_idx, src_idx])
        state.XADJ = float(state.ADSXADJ[sec_idx, src_idx])
        state.YADJ = float(state.ADSYADJ[sec_idx, src_idx])
        state.B_SUBS = min(state.DSBH, state.DSBW)
        state.B_SUBL = max(state.DSBH, state.DSBW)
        state.B_SUBL = min(state.B_SUBL, 8.0 * state.B_SUBS)
        state.RSCALE = (
            state.B_SUBS ** (2.0 * state.THIRD) * state.B_SUBL**state.THIRD
        )

    if state.DSBH <= 1.0e-5 or state.DSBW <= 1.0e-5:
        state.WAKE = False
    else:
        state.WAKE = True


def xydist(state: AermodState, indx: int) -> None:
    """SUBROUTINE XYDIST (calc2.f)."""
    # Fortran INDX (1-based) -> idx = indx - 1
    idx = indx - 1
    state.XR = float(state.AXR[idx])
    state.YR = float(state.AYR[idx])
    state.ZELEV = float(state.AZELEV[idx])
    state.ZHILL = float(state.AZHILL[idx])
    state.ZFLAG = float(state.AZFLAG[idx])

    # Calculate Downwind (X) and Crosswind (Y) Distances
    state.X = -(
        (state.XR - state.XS) * state.WDSIN
        + (state.YR - state.YS) * state.WDCOS
    )
    state.Y = (state.XR - state.XS) * state.WDCOS - (
        state.YR - state.YS
    ) * state.WDSIN

    # Calculate Source-Receptor (Radial) Distance, DISTR
    state.DISTR = math.sqrt(state.X * state.X + state.Y * state.Y)

    # Calculate height of receptor above stack base, ZRT
    # Fortran L_FLATSRC(ISRC) -> state.L_FLATSRC[state.ISRC - 1]
    if state.L_FLATSRC[state.ISRC - 1]:
        state.ZRT = state.ZFLAG
    else:
        state.ZRT = state.ZELEV - state.ZS + state.ZFLAG

    if state.SCREEN:
        state.X = state.DISTR
        state.Y = 0.0


def fterm(state: AermodState) -> None:
    """SUBROUTINE FTERM (calc2.f)."""
    state.FOPT = 0.5 * (1.0 + state.PHEE)


def fyplm(state: AermodState, syarg: float) -> float:
    """SUBROUTINE FYPLM (calc2.f)."""
    exparg = -(state.Y * state.Y / (2.0 * syarg * syarg))
    if exparg > state.EXPLIM:
        fyout = math.exp(exparg) / (state.SRT2PI * syarg)
    else:
        fyout = 0.0
    return fyout


def fypan(state: AermodState) -> float:
    """SUBROUTINE FYPAN (calc2.f)."""
    return 1.0 / (state.TWOPI * state.DISTR)


def meandr(state: AermodState, uef: float, svef: float) -> float:
    """SUBROUTINE MEANDR (calc2.f)."""
    tran = state.BIGT * 3600.0

    sqrtarg = uef * uef - 2.0 * svef * svef
    if sqrtarg >= 0.01:
        umean = math.sqrt(sqrtarg)
    else:
        umean = 0.1

    totkin = uef * uef
    ttrav = state.DISTR / uef
    sigran = 2.0 * svef * svef + umean * umean * (1.0 - math.exp(-ttrav / tran))
    fran = sigran / totkin

    if state.L_PBal:
        fran = math.sqrt(fran)

    fran = min(fran, state.FRANMAX)
    fran = max(fran, state.FRANMIN)

    if state.DEBUG:
        isrc = state.ISRC
        irec = state.IREC
        comp = state.debug_comp
        # WRITE(DBGUNT,*) SVEF, UEF, UMEAN / DISTR, TTRAV, TRAN / TOTKIN, SIGRAN, FRAN
        state.emit_debug(isrc, irec, comp, "MEANDR", "SVEF", svef)
        state.emit_debug(isrc, irec, comp, "MEANDR", "UEF", uef)
        state.emit_debug(isrc, irec, comp, "MEANDR", "UMEAN", umean)
        state.emit_debug(isrc, irec, comp, "MEANDR", "DISTR", state.DISTR)
        state.emit_debug(isrc, irec, comp, "MEANDR", "TTRAV", ttrav)
        state.emit_debug(isrc, irec, comp, "MEANDR", "TRAN", tran)
        state.emit_debug(isrc, irec, comp, "MEANDR", "TOTKIN", totkin)
        state.emit_debug(isrc, irec, comp, "MEANDR", "SIGRAN", sigran)
        state.emit_debug(isrc, irec, comp, "MEANDR", "FRAN", fran)

    return fran


def critds(state: AermodState, hearg: float) -> None:
    """SUBROUTINE CRITDS (calc2.f)."""
    from .metext import gintrp

    zmid = 0.0
    topht = 0.0
    tghc = 0.0
    pthc = 0.0

    # Fortran L_FLATSRC(ISRC) -> state.L_FLATSRC[state.ISRC - 1]
    isrc_idx = state.ISRC - 1
    if state.L_FLATSRC[isrc_idx]:
        state.HCRIT = 0.0
        return
    else:
        hhill = min(state.ZHILL - state.ZS, state.ZELEV - state.ZS + hearg)

    if state.STABLE and state.ELEV and hhill > 0.0:
        ndx4hc = locate(state.GRIDHT, 1, state.MXGLVL, hhill)
        nlev = ndx4hc + 1

        # Fortran NDX4HC -> idx_hc = ndx4hc - 1, NDX4HC+1 -> idx_hc + 1
        idx_hc = ndx4hc - 1
        srctyp = str(state.SRCTYP[isrc_idx]).strip()
        if srctyp in ("RLINE", "RLINEXT"):
            uathh = gintrp(
                float(state.GRIDHT[idx_hc]),
                float(state.RL_GRIDWS[idx_hc, state.I_ALPHA - 1]),
                float(state.GRIDHT[idx_hc + 1]),
                float(state.RL_GRIDWS[idx_hc + 1, state.I_ALPHA - 1]),
                hhill,
            )
        else:
            uathh = gintrp(
                float(state.GRIDHT[idx_hc]),
                float(state.GRIDWS[idx_hc]),
                float(state.GRIDHT[idx_hc + 1]),
                float(state.GRIDWS[idx_hc + 1]),
                hhill,
            )

        ptathh = gintrp(
            float(state.GRIDHT[idx_hc]),
            float(state.GRIDPT[idx_hc]),
            float(state.GRIDHT[idx_hc + 1]),
            float(state.GRIDPT[idx_hc + 1]),
            hhill,
        )
        tgathh = gintrp(
            float(state.GRIDHT[idx_hc]),
            float(state.GRIDTG[idx_hc]),
            float(state.GRIDHT[idx_hc + 1]),
            float(state.GRIDTG[idx_hc + 1]),
            hhill,
        )

        ls = xp.zeros(state.MXGLVL, dtype=xp.float64)
        rs = xp.zeros(state.MXGLVL, dtype=xp.float64)
        xn2 = xp.zeros(state.MXGLVL, dtype=xp.float64)

        # Fortran NL = 1..NLEV-1 -> nl in range(nlev - 1)
        for nl in range(nlev - 1):
            if srctyp in ("RLINE", "RLINEXT"):
                ws_nl = float(state.RL_GRIDWS[nl, state.I_ALPHA - 1])
                ls[nl] = 0.5 * ws_nl * ws_nl
            else:
                ws_nl = float(state.GRIDWS[nl])
                ls[nl] = 0.5 * ws_nl * ws_nl

        # Fortran LS(NLEV) -> ls[nlev - 1]
        ls[nlev - 1] = 0.5 * uathh * uathh
        rs[nlev - 1] = 0.0

        # Fortran NL = NLEV-1, 1, -1 -> nl_1b in range(nlev - 1, 0, -1)
        for nl_1b in range(nlev - 1, 0, -1):
            nl = nl_1b - 1
            if nl_1b < nlev - 1:
                zmid = 0.5 * (
                    float(state.GRIDHT[nl + 1]) + float(state.GRIDHT[nl])
                )
                pthc = 0.5 * (
                    float(state.GRIDPT[nl + 1]) + float(state.GRIDPT[nl])
                )
                tghc = 0.5 * (
                    float(state.GRIDTG[nl + 1]) + float(state.GRIDTG[nl])
                )
                topht = float(state.GRIDHT[nl + 1])
            elif nl_1b == nlev - 1:
                zmid = 0.5 * (hhill + float(state.GRIDHT[nl]))
                pthc = 0.5 * (ptathh + float(state.GRIDPT[nl]))
                tghc = 0.5 * (tgathh + float(state.GRIDTG[nl]))
                topht = hhill

            xn2[nl] = (state.G / pthc) * tghc
            rs[nl] = float(rs[nl + 1]) + float(xn2[nl]) * (
                (hhill - zmid) * (topht - float(state.GRIDHT[nl]))
            )

        it = 1
        # Fortran NL = NLEV, 1, -1 -> nl_1b in range(nlev, 0, -1)
        for nl_1b in range(nlev, 0, -1):
            if ls[nl_1b - 1] >= rs[nl_1b - 1]:
                it = nl_1b

        if it > 1:
            if it == nlev:
                wstop = uathh
                htop = hhill
            else:
                # Fortran IT -> it - 1
                if srctyp in ("RLINE", "RLINEXT"):
                    wstop = float(state.RL_GRIDWS[it - 1, state.I_ALPHA - 1])
                    htop = float(state.GRIDHT[it - 1])
                else:
                    wstop = float(state.GRIDWS[it - 1])
                    htop = float(state.GRIDHT[it - 1])

            ib = it - 1
            # Fortran IB -> ib - 1
            hbot = float(state.GRIDHT[ib - 1])
            if srctyp in ("RLINE", "RLINEXT"):
                dws = (
                    wstop - float(state.RL_GRIDWS[ib - 1, state.I_ALPHA - 1])
                ) / (htop - hbot)
            else:
                dws = (wstop - float(state.GRIDWS[ib - 1])) / (htop - hbot)

            dws2 = dws * dws
            n2 = float(xn2[ib - 1])

            a = 0.5 * (n2 - dws2)
            b = htop * dws2 - wstop * dws - n2 * hhill
            c = (
                (n2 * hhill * htop)
                - 0.5 * (n2 * htop * htop)
                - 0.5 * (dws2 * htop * htop)
                + wstop * dws * htop
                - (float(ls[it - 1]) - float(rs[it - 1]))
            )
            b2 = b * b
            ac4 = 4.0 * a * c
            if -0.001 < (b2 - ac4) / b2 < 0.0:
                ac4 = b2
            deter = math.sqrt(b2 - ac4)
            state.HCRIT = (-b - deter) / (2.0 * a)
        else:
            state.HCRIT = 0.0
    else:
        state.HCRIT = 0.0


def pdf(state: AermodState) -> None:
    """SUBROUTINE PDF (calc2.f)."""
    skcalc(state)
    crcalc(state)
    alcalc(state)
    becalc(state)
    aacalc(state)
    bbcalc(state)
    llcalc(state)


def skcalc(state: AermodState) -> None:
    """SUBROUTINE SKCALC (calc2.f)."""
    if state.SURFAC:
        wbar3 = 1.25 * (state.WSTAR**3) * (state.CENTER / state.ZI)
    else:
        wbar3 = 0.125 * (state.WSTAR**3)

    state.SKEW = wbar3 / (state.SWEFFD * state.SWEFFD * state.SWEFFD)


def crcalc(state: AermodState) -> None:
    """SUBROUTINE CRCALC (calc2.f)."""
    state.R = 2.0


def alcalc(state: AermodState) -> None:
    """SUBROUTINE ALCALC (calc2.f)."""
    state.ALPHPD = (1.0 + state.R * state.R) / (1.0 + 3.0 * state.R * state.R)


def becalc(state: AermodState) -> None:
    """SUBROUTINE BECALC (calc2.f)."""
    state.BETAPD = 1.0 + state.R * state.R


def aacalc(state: AermodState) -> None:
    """SUBROUTINE AACALC (calc2.f)."""
    determ = (state.ALPHPD * state.ALPHPD) * (state.SKEW * state.SKEW) + (
        4.0 / state.BETAPD
    )
    swratio = state.SWEFFD / state.WSTAR
    state.ASUB1 = swratio * (
        0.5 * state.ALPHPD * state.SKEW + 0.5 * math.sqrt(determ)
    )
    state.ASUB2 = swratio * (
        0.5 * state.ALPHPD * state.SKEW - 0.5 * math.sqrt(determ)
    )


def bbcalc(state: AermodState) -> None:
    """SUBROUTINE BBCALC (calc2.f)."""
    state.BSUB1 = state.R * state.ASUB1
    state.BSUB2 = -state.R * state.ASUB2


def llcalc(state: AermodState) -> None:
    """SUBROUTINE LLCALC (calc2.f)."""
    state.LAMDA1 = state.ASUB2 / (state.ASUB2 - state.ASUB1)
    state.LAMDA2 = 1.0 - state.LAMDA1


def decay(state: AermodState, xarg: float) -> None:
    """SUBROUTINE DECAY (calc2.f)."""
    state.D = 1.0
    dc1 = state.DECOEF

    # Fortran ISRC -> state.ISRC - 1, ICSTAT(7) -> state.ICSTAT[6], ICSTAT(8) -> state.ICSTAT[7]
    isrc_idx = state.ISRC - 1
    urbsrc_flag = str(state.URBSRC[isrc_idx]).strip()
    pollut = state.POLLUT.strip()

    if (
        state.URBAN
        and pollut == "SO2"
        and urbsrc_flag == "Y"
        and ((state.ICSTAT[6] == 0 and state.ICSTAT[7] == 0) or state.DFAULT)
    ):
        state.DECOEF = 4.81e-5
    elif (pollut == "SO2" and urbsrc_flag == "N") or state.DFAULT:
        state.DECOEF = 0.0

    if state.DECOEF > 0.0:
        if state.STABLE or (state.UNSTAB and state.HS >= state.ZI):
            state.D = math.exp(
                max(state.EXPLIM, -state.DECOEF * xarg / state.UEFF)
            )
        else:
            state.D = math.exp(
                max(state.EXPLIM, -state.DECOEF * xarg / state.UEFFD)
            )

    state.DECOEF = dc1


def vrtsbl(
    state: AermodState, szarg: float, hearg: float, ziarg: float
) -> None:
    """SUBROUTINE VRTSBL (calc2.f)."""
    v = 0.0

    if state.ZR == 0.0:
        a1 = (-0.5 / (szarg * szarg)) * hearg * hearg
        if a1 > state.EXPLIM:
            v = math.exp(a1)
        sum_val = 0.0
        # Fortran DO I = 1, 100 -> i in range(1, 101)
        for i in range(1, 101):
            t = 0.0
            twoizi = 2.0 * float(i) * ziarg
            a2 = (-0.5 / (szarg * szarg)) * (twoizi - hearg) * (twoizi - hearg)
            a3 = (-0.5 / (szarg * szarg)) * (twoizi + hearg) * (twoizi + hearg)
            if a2 > state.EXPLIM:
                t = math.exp(a2)
            if a3 > state.EXPLIM:
                t = t + math.exp(a3)
            sum_val = sum_val + t

            if abs(t) <= 5.0e-7 * abs(sum_val):
                break
        v = 2.0 * (v + sum_val)
    elif state.ZR <= ziarg:
        hetmp = max(hearg, hearg - state.ZR)
        zitmp = max(ziarg, ziarg - state.ZR)

        a1 = (-0.5 / (szarg * szarg)) * (state.ZR - hetmp) * (state.ZR - hetmp)
        a2 = (-0.5 / (szarg * szarg)) * (state.ZR + hetmp) * (state.ZR + hetmp)
        if a1 > state.EXPLIM:
            v = math.exp(a1)
        if a2 > state.EXPLIM:
            v = v + math.exp(a2)
        sum_val = 0.0
        # Fortran DO I = 1, 100 -> i in range(1, 101)
        for i in range(1, 101):
            t = 0.0
            twoizi = 2.0 * float(i) * zitmp
            a3 = (
                (-0.5 / (szarg * szarg))
                * (state.ZR - (twoizi - hetmp))
                * (state.ZR - (twoizi - hetmp))
            )
            a4 = (
                (-0.5 / (szarg * szarg))
                * (state.ZR + (twoizi - hetmp))
                * (state.ZR + (twoizi - hetmp))
            )
            a5 = (
                (-0.5 / (szarg * szarg))
                * (state.ZR - (twoizi + hetmp))
                * (state.ZR - (twoizi + hetmp))
            )
            a6 = (
                (-0.5 / (szarg * szarg))
                * (state.ZR + (twoizi + hetmp))
                * (state.ZR + (twoizi + hetmp))
            )
            if a3 > state.EXPLIM:
                t = t + math.exp(a3)
            if a4 > state.EXPLIM:
                t = t + math.exp(a4)
            if a5 > state.EXPLIM:
                t = t + math.exp(a5)
            if a6 > state.EXPLIM:
                t = t + math.exp(a6)
            sum_val = sum_val + t

            if abs(t) <= 1.0e-6 * abs(sum_val):
                break
        v = v + sum_val
    else:
        v = 0.0

    state.FSUBZ = v / (state.SRT2PI * szarg)


def vrtsbn(state: AermodState, szarg: float, hearg: float) -> None:
    """SUBROUTINE VRTSBN (calc2.f)."""
    v = 0.0

    if state.ZR == 0.0:
        a1 = (-0.5 / (szarg * szarg)) * hearg * hearg
        if a1 > state.EXPLIM:
            v = math.exp(a1)
        v = 2.0 * v
    else:
        hetmp = max(hearg, hearg - state.ZR)
        a1 = (-0.5 / (szarg * szarg)) * (state.ZR - hetmp) * (state.ZR - hetmp)
        a2 = (-0.5 / (szarg * szarg)) * (state.ZR + hetmp) * (state.ZR + hetmp)
        if a1 > state.EXPLIM:
            v = math.exp(a1)
        if a2 > state.EXPLIM:
            v = v + math.exp(a2)

    state.FSUBZ = v / (state.SRT2PI * szarg)


def vrtbl_cbl(
    state: AermodState,
    he1: float,
    he2: float,
    sz1: float,
    sz2: float,
    fact: float,
) -> None:
    """SUBROUTINE VRTCBL (calc2.f)."""
    v = 0.0

    if abs(state.ZR - 0.0) < 1.0e-10:
        sum_val = 0.0
        # Fortran DO I = 0, 1000 -> i in range(0, 1001)
        for i in range(0, 1001):
            t1 = 0.0
            t2 = 0.0
            twoizi = 2.0 * float(i) * state.ZI * fact
            if fact < 0.0 and i == 0:
                continue

            hearg1 = twoizi + he1
            hearg2 = twoizi + he2
            a1 = (-0.5 / (sz1 * sz1)) * hearg1 * hearg1
            if a1 > state.EXPLIM:
                t1 = math.exp(a1)
            a2 = (-0.5 / (sz2 * sz2)) * hearg2 * hearg2
            if a2 > state.EXPLIM:
                t2 = math.exp(a2)

            term = (state.LAMDA1 / sz1) * t1 + (state.LAMDA2 / sz2) * t2
            sum_val = sum_val + term

            if abs(term) <= 5.0e-7 * abs(sum_val):
                break
        v = 2.0 * sum_val
    elif state.ZR <= state.ZI:
        he1tmp = max(he1, he1 - state.ZR)
        he2tmp = max(he2, he2 - state.ZR)
        zitmp = max(state.ZI, state.ZI - state.ZR)

        sum_val = 0.0
        # Fortran DO I = 0, 1000 -> i in range(0, 1001)
        for i in range(0, 1001):
            t1 = 0.0
            t2 = 0.0
            twoizi = 2.0 * float(i) * zitmp * fact
            if fact < 0.0 and i == 0:
                continue

            hearg1 = twoizi + he1tmp
            hearg2 = twoizi + he2tmp
            a1 = (
                (-0.5 / (sz1 * sz1))
                * (state.ZR - hearg1)
                * (state.ZR - hearg1)
            )
            a2 = (
                (-0.5 / (sz1 * sz1))
                * (state.ZR + hearg1)
                * (state.ZR + hearg1)
            )
            if a1 > state.EXPLIM:
                t1 = math.exp(a1)
            if a2 > state.EXPLIM:
                t1 = t1 + math.exp(a2)
            a3 = (
                (-0.5 / (sz2 * sz2))
                * (state.ZR - hearg2)
                * (state.ZR - hearg2)
            )
            a4 = (
                (-0.5 / (sz2 * sz2))
                * (state.ZR + hearg2)
                * (state.ZR + hearg2)
            )
            if a3 > state.EXPLIM:
                t2 = math.exp(a3)
            if a4 > state.EXPLIM:
                t2 = t2 + math.exp(a4)

            term = (state.LAMDA1 / sz1) * t1 + (state.LAMDA2 / sz2) * t2
            sum_val = sum_val + term

            if abs(term) <= 1.0e-6 * abs(sum_val):
                break
        v = sum_val
    else:
        v = 0.0

    state.FSUBZ = v / state.SRT2PI


def pfract(state: AermodState, hearg: float) -> None:
    """SUBROUTINE PFRACT (calc2.f)."""
    state.PHEE = 0.0

    if state.STABLE and (state.HCRIT > 0.0):
        hcint = min(state.HSBL, state.HCRIT)

        a1 = (hcint - hearg) / (state.RTOF2 * state.SZ)
        a2 = (hcint + hearg) / (state.RTOF2 * state.SZ)
        b1 = erfx(a1)
        b2 = erfx(a2)

        sum_val = 0.0
        # Fortran DO I = 1, 100 -> i in range(1, 101)
        for i in range(1, 101):
            t = 0.0
            twoizi = 2.0 * float(i) * state.HSBL
            a3 = (hcint - hearg + twoizi) / (state.RTOF2 * state.SZ)
            a4 = (hcint + hearg + twoizi) / (state.RTOF2 * state.SZ)
            a5 = (hcint - hearg - twoizi) / (state.RTOF2 * state.SZ)
            a6 = (hcint + hearg - twoizi) / (state.RTOF2 * state.SZ)
            b3 = erfx(a3)
            b4 = erfx(a4)
            b5 = erfx(a5)
            b6 = erfx(a6)

            t = b3 + b4 + b5 + b6
            sum_val = sum_val + t

            if abs(t) <= 1.0e-6 * abs(sum_val):
                if i >= 5:
                    break

        state.PHEE = 0.5 * (b1 + b2 + sum_val)

        if state.PHEE > 1.01 and not state.L_SkipMessages:
            state.PHEE = 1.0


def erfx(arg: float) -> float:
    """FUNCTION ERFX (calc2.f)."""
    if arg > 4.0:
        res = 1.0
    elif arg < -4.0:
        res = -1.0
    elif abs(arg) < 1.0e-10:
        res = 0.0
    else:
        x = abs(arg)
        res = (
            1.0
            - 1.0
            / (
                1.0
                + x
                * (
                    0.705230784e-1
                    + x
                    * (
                        0.422820123e-1
                        + x
                        * (
                            0.92705272e-2
                            + x
                            * (
                                0.1520143e-3
                                + x * (0.2765672e-3 + x * 0.430638e-4)
                            )
                        )
                    )
                )
            )
            ** 16.0
        )
        if arg < 0.0:
            res = -res
    return res


def sumval(state: AermodState) -> None:
    """SUBROUTINE SUMVAL (calc2.f)."""
    # Fortran IREC, ISRC, IGRP (1-based) -> 0-based indices
    irec_idx = state.IREC - 1
    isrc_idx = state.ISRC - 1
    igrp_idx = state.IGRP - 1

    # Fortran DO ITYP = 1, NUMTYP -> ityp in range(state.NUMTYP)
    for ityp in range(state.NUMTYP):
        hrval_t = float(state.HRVAL[ityp])
        if hrval_t != 0.0:
            if state.IGROUP[isrc_idx, igrp_idx] == 1:
                if igrp_idx == 0 and ityp == 0:
                    state.hr_conc[irec_idx] = state.hr_conc[irec_idx] + hrval_t

                # Fortran DO IAVE = 1, NUMAVE -> iave in range(state.NUMAVE)
                for iave in range(state.NUMAVE):
                    state.AVEVAL[irec_idx, igrp_idx, iave, ityp] = (
                        hrval_t
                        + float(state.AVEVAL[irec_idx, igrp_idx, iave, ityp])
                    )

                if state.PERIOD or state.ANNUAL:
                    state.ANNVAL[irec_idx, igrp_idx, ityp] = (
                        hrval_t + float(state.ANNVAL[irec_idx, igrp_idx, ityp])
                    )

                if state.SHVALS is not None and state.ISEAHR[igrp_idx] == 1:
                    # Fortran (ISEAS, IHOUR) -> (state.ISEAS - 1, state.IHOUR - 1)
                    state.SHVALS[
                        irec_idx,
                        igrp_idx,
                        state.ISEAS - 1,
                        state.IHOUR - 1,
                        ityp,
                    ] = hrval_t + float(
                        state.SHVALS[
                            irec_idx,
                            igrp_idx,
                            state.ISEAS - 1,
                            state.IHOUR - 1,
                            ityp,
                        ]
                    )
