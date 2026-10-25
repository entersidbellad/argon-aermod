"""SUBROUTINE IBLVAL, METINI, LOCATE, ANYAVG (iblval.f)."""

from __future__ import annotations

import math
import numpy as xp

from .state import AermodState, f_idiv, f_int


def locate(parray: xp.ndarray, lvlblw: int, lvlabv: int, value: float) -> int:
    """SUBROUTINE LOCATE (iblval.f): returns 1-based index NDXBLW."""
    jl = lvlblw - 1
    ju = lvlabv + 1

    while (ju - jl) > 1:
        jm = f_idiv(ju + jl, 2)
        # Fortran PARRAY(JM) -> parray[jm - 1]
        if value >= float(parray[jm - 1]):
            jl = jm
        else:
            ju = jm

    ndxblw = min(jl, lvlabv - 1)
    return ndxblw


def anyavg(
    nlvls: int,
    hts: xp.ndarray,
    parray: xp.ndarray,
    zbot: float,
    ndxabv: int,
    ztop: float,
    ndxblw: int,
) -> float:
    """SUBROUTINE ANYAVG (iblval.f)."""
    from .metext import gintrp

    sum_val = 0.0

    # Check for minimum values of ZTOP and ZBOT
    if zbot < 0.5:
        zbot = 0.5
        ndxabv = 2
    if ztop < 0.51:
        ztop = 0.51
        ndxblw = 2

    if ndxblw < ndxabv:
        # Label 300: take interpolated value halfway between ZBOT and ZTOP
        # Fortran NDXABV-1 -> ndxabv - 2, NDXABV -> ndxabv - 1
        valavg = gintrp(
            float(hts[ndxabv - 2]),
            float(parray[ndxabv - 2]),
            float(hts[ndxabv - 1]),
            float(parray[ndxabv - 1]),
            0.5 * (zbot + ztop),
        )
        return valavg

    if ndxblw > ndxabv:
        # Sum using trapezoidal rule over intermediate profile layers
        # Fortran I = NDXABV+1, NDXBLW -> i in range(ndxabv, ndxblw)
        for i in range(ndxabv, ndxblw):
            sum_val = sum_val + (float(hts[i]) - float(hts[i - 1])) * 0.5 * (
                float(parray[i]) + float(parray[i - 1])
            )

    # Label 200: finish summation over partial layers at bottom (first), then top
    if ndxabv > 1:
        # Fortran NDXABV-1 -> ndxabv - 2, NDXABV -> ndxabv - 1
        valbot = gintrp(
            float(hts[ndxabv - 2]),
            float(parray[ndxabv - 2]),
            float(hts[ndxabv - 1]),
            float(parray[ndxabv - 1]),
            zbot,
        )
        sum_val = sum_val + (float(hts[ndxabv - 1]) - zbot) * 0.5 * (
            valbot + float(parray[ndxabv - 1])
        )
    else:
        sum_val = sum_val + (float(hts[0]) - zbot) * float(parray[0])

    if ndxblw < nlvls:
        # Fortran NDXBLW -> ndxblw - 1, NDXBLW+1 -> ndxblw
        valtop = gintrp(
            float(hts[ndxblw - 1]),
            float(parray[ndxblw - 1]),
            float(hts[ndxblw]),
            float(parray[ndxblw]),
            ztop,
        )
        sum_val = sum_val + (ztop - float(hts[ndxblw - 1])) * 0.5 * (
            valtop + float(parray[ndxblw - 1])
        )
    else:
        sum_val = sum_val + (ztop - float(hts[nlvls - 1])) * float(parray[nlvls - 1])

    valavg = sum_val / (ztop - zbot)
    return valavg


def metini(state: AermodState) -> None:
    """SUBROUTINE METINI (iblval.f)."""
    from .metext import gintrp

    # Fortran NDXSTK(ISRC) -> state.NDXSTK[state.ISRC - 1]
    ndxstk = int(state.NDXSTK[state.ISRC - 1])

    if ndxstk >= 1:
        # Fortran NDXSTK(ISRC) -> idx = ndxstk - 1, NDXSTK(ISRC)+1 -> idx + 1
        idx = ndxstk - 1
        ht_lo = float(state.GRIDHT[idx])
        ht_hi = float(state.GRIDHT[idx + 1])

        # Sigma_V at stack height
        state.SVS = gintrp(
            ht_lo,
            float(state.GRIDSV[idx]),
            ht_hi,
            float(state.GRIDSV[idx + 1]),
            state.HS,
        )

        # Sigma_W
        state.SWS = gintrp(
            ht_lo,
            float(state.GRIDSW[idx]),
            ht_hi,
            float(state.GRIDSW[idx + 1]),
            state.HS,
        )

        # Wind speed
        state.US = gintrp(
            ht_lo,
            float(state.GRIDWS[idx]),
            ht_hi,
            float(state.GRIDWS[idx + 1]),
            state.HS,
        )

        # Wind direction: check for 360 crossover and adjust if necessary
        valabv = float(state.GRIDWD[idx + 1])
        vbelow = float(state.GRIDWD[idx])

        if (valabv - vbelow) < -180.0:
            valabv = valabv + 360.0
        elif (valabv - vbelow) > 180.0:
            valabv = valabv - 360.0

        if vbelow == valabv:
            state.WDIR = vbelow
        else:
            state.WDIR = gintrp(ht_lo, vbelow, ht_hi, valabv, state.HS)

        if state.WDIR > 360.0:
            state.WDIR = state.WDIR - 360.0
        elif state.WDIR <= 0.0:
            state.WDIR = state.WDIR + 360.0

        # Potential temperature gradient
        state.TGS = gintrp(
            ht_lo,
            float(state.GRIDTG[idx]),
            ht_hi,
            float(state.GRIDTG[idx + 1]),
            state.HS,
        )

        # Potential temperature
        state.PTS = gintrp(
            ht_lo,
            float(state.GRIDPT[idx]),
            ht_hi,
            float(state.GRIDPT[idx + 1]),
            state.HS,
        )
    else:
        # Use GRID value for lowest level
        state.SVS = float(state.GRIDSV[0])
        state.SWS = float(state.GRIDSW[0])
        state.US = float(state.GRIDWS[0])
        state.WDIR = float(state.GRIDWD[0])
        state.TGS = float(state.GRIDTG[0])
        state.PTS = float(state.GRIDPT[0])

    # Modify the treatment of low wind/low turbulence cases
    state.SWS = max(state.SWS, state.SWMIN)
    state.SVS = max(state.SVS, state.SVMIN, state.SVUMIN * state.US)
    if state.L_VECTORWS:
        state.US = math.sqrt(state.US * state.US + 2.0 * state.SVS * state.SVS)
    state.US = max(state.US, state.WSMIN)

    if not state.CLMHR and not state.MSGHR:
        state.WDSIN = math.sin(state.WDIR * state.DTORAD)
        state.WDCOS = math.cos(state.WDIR * state.DTORAD)

        state.AFV = state.WDIR - 180.0
        if state.AFV < 0.0:
            state.AFV = state.AFV + 360.0
        state.IFVSEC = f_int(state.AFV * 0.10 + 0.4999)
        if state.IFVSEC == 0:
            state.IFVSEC = 36

    # Assign TGP as TGS initially
    state.TGP = state.TGS

    # Calculate stack height ambient temperature, TA
    state.TA = state.PTS - state.GOVRCP * (state.HS + state.ZBASE)

    # Assign wind speed to use for plume rise, UP = US
    state.UP = state.US
    state.SVP = state.SVS
    state.SWP = state.SWS

    # Compute the Brunt-Vaisala frequency, BVF, at stack height
    if (state.TGS > 0.0) and (
        state.STABLE or (state.UNSTAB and state.HS >= state.ZI)
    ):
        state.BVF = math.sqrt(state.G * state.TGS / state.PTS)
    else:
        state.BVF = 1.0e-10

    if state.BVF < 1.0e-10:
        state.BVF = 1.0e-10

    state.BVPRIM = 0.7 * state.BVF

    # Set temporarily assigned effective values
    state.UEFF = state.US
    state.SVEFF = state.SVS
    state.SWEFF = state.SWS
    state.TGEFF = state.TGS
    state.UEFFD = state.US
    state.SVEFFD = state.SVS
    state.SWEFFD = state.SWS
    state.UEFFN = state.US
    state.SVEFFN = state.SVS
    state.SWEFFN = state.SWS
    state.UEFF3 = state.US
    state.SVEFF3 = state.SVS
    state.SWEFF3 = state.SWS
    state.TGEFF3 = state.TGS

    # Define temporary values of CENTER and SURFAC based on HS
    state.CENTER = state.HS
    if state.CENTER < 0.1 * state.ZI:
        state.SURFAC = True
    else:
        state.SURFAC = False


def iblval(state: AermodState, xarg: float) -> None:
    """SUBROUTINE IBLVAL (iblval.f)."""
    from .metext import gintrp
    from .calc1 import pdis, vdis, adisz

    if state.HBPLUME:
        state.PPFN = 1.0

    isrc = state.ISRC
    irec = state.IREC
    comp = state.debug_comp

    # Initialize the effective parameters based on values at plume height
    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        state.HTEFF = state.HE
        ndxeff = locate(state.GRIDHT, 1, state.MXGLVL, state.HTEFF)
        # Fortran NDXEFF -> idx = ndxeff - 1, NDXEFF+1 -> idx + 1
        idx = ndxeff - 1
        ht_lo = float(state.GRIDHT[idx])
        ht_hi = float(state.GRIDHT[idx + 1])

        state.UEFF = gintrp(
            ht_lo,
            float(state.GRIDWS[idx]),
            ht_hi,
            float(state.GRIDWS[idx + 1]),
            state.HTEFF,
        )
        state.SVEFF = gintrp(
            ht_lo,
            float(state.GRIDSV[idx]),
            ht_hi,
            float(state.GRIDSV[idx + 1]),
            state.HTEFF,
        )
        state.SWEFF = gintrp(
            ht_lo,
            float(state.GRIDSW[idx]),
            ht_hi,
            float(state.GRIDSW[idx + 1]),
            state.HTEFF,
        )
        state.TGEFF = gintrp(
            ht_lo,
            float(state.GRIDTG[idx]),
            ht_hi,
            float(state.GRIDTG[idx + 1]),
            state.HTEFF,
        )
        if state.PVMRM or state.GRSM:
            state.EPSEFF = gintrp(
                ht_lo,
                float(state.GRIDEPS[idx]),
                ht_hi,
                float(state.GRIDEPS[idx + 1]),
                state.HTEFF,
            )

        state.SWEFF = max(state.SWEFF, state.SWMIN)
        state.SVEFF = max(state.SVEFF, state.SVMIN, state.SVUMIN * state.UEFF)
        if state.L_VECTORWS:
            state.UEFF = math.sqrt(
                state.UEFF * state.UEFF + 2.0 * state.SVEFF * state.SVEFF
            )
        state.UEFF = max(state.UEFF, state.WSMIN)

        if state.DEBUG:
            # WRITE(DBGUNT, 6014) UEFF, SVEFF, SWEFF
            state.emit_debug(isrc, irec, comp, "IBLVAL", "UEFF", state.UEFF)
            state.emit_debug(isrc, irec, comp, "IBLVAL", "SVEFF", state.SVEFF)
            state.emit_debug(isrc, irec, comp, "IBLVAL", "SWEFF", state.SWEFF)

    elif state.UNSTAB and (state.HS < state.ZI):
        # Direct and Indirect Source
        if state.PPF < 1.0:
            state.HTEFF = state.CENTER
            ndxeff = locate(state.GRIDHT, 1, state.MXGLVL, state.HTEFF)
            # Fortran NDXEFF -> idx = ndxeff - 1, NDXEFF+1 -> idx + 1
            idx = ndxeff - 1
            ht_lo = float(state.GRIDHT[idx])
            ht_hi = float(state.GRIDHT[idx + 1])

            state.UEFFD = gintrp(
                ht_lo,
                float(state.GRIDWS[idx]),
                ht_hi,
                float(state.GRIDWS[idx + 1]),
                state.HTEFF,
            )
            state.SVEFFD = gintrp(
                ht_lo,
                float(state.GRIDSV[idx]),
                ht_hi,
                float(state.GRIDSV[idx + 1]),
                state.HTEFF,
            )
            state.SWEFFD = gintrp(
                ht_lo,
                float(state.GRIDSW[idx]),
                ht_hi,
                float(state.GRIDSW[idx + 1]),
                state.HTEFF,
            )
            if state.PVMRM or state.GRSM:
                state.EPSEFFD = gintrp(
                    ht_lo,
                    float(state.GRIDEPS[idx]),
                    ht_hi,
                    float(state.GRIDEPS[idx + 1]),
                    state.HTEFF,
                )

            state.SWEFFD = max(state.SWEFFD, state.SWMIN)
            state.SVEFFD = max(
                state.SVEFFD, state.SVMIN, state.SVUMIN * state.UEFFD
            )
            if state.L_VECTORWS:
                state.UEFFD = math.sqrt(
                    state.UEFFD * state.UEFFD + 2.0 * state.SVEFFD * state.SVEFFD
                )
            state.UEFFD = max(state.UEFFD, state.WSMIN)

            if state.DEBUG:
                # WRITE(DBGUNT, 6015) UEFFD, SVEFFD, SWEFFD
                state.emit_debug(isrc, irec, comp, "IBLVAL", "UEFFD", state.UEFFD)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SVEFFD", state.SVEFFD)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SWEFFD", state.SWEFFD)

        # Penetrated source
        if state.PPF > 0.0:
            state.HTEFF = state.HE3
            ndxeff = locate(state.GRIDHT, 1, state.MXGLVL, state.HTEFF)
            # Fortran NDXEFF -> idx = ndxeff - 1, NDXEFF+1 -> idx + 1
            idx = ndxeff - 1
            ht_lo = float(state.GRIDHT[idx])
            ht_hi = float(state.GRIDHT[idx + 1])

            state.UEFF3 = gintrp(
                ht_lo,
                float(state.GRIDWS[idx]),
                ht_hi,
                float(state.GRIDWS[idx + 1]),
                state.HTEFF,
            )
            state.SVEFF3 = gintrp(
                ht_lo,
                float(state.GRIDSV[idx]),
                ht_hi,
                float(state.GRIDSV[idx + 1]),
                state.HTEFF,
            )
            state.SWEFF3 = gintrp(
                ht_lo,
                float(state.GRIDSW[idx]),
                ht_hi,
                float(state.GRIDSW[idx + 1]),
                state.HTEFF,
            )
            state.TGEFF3 = gintrp(
                ht_lo,
                float(state.GRIDTG[idx]),
                ht_hi,
                float(state.GRIDTG[idx + 1]),
                state.HTEFF,
            )
            if state.PVMRM or state.GRSM:
                state.EPSEFF3 = gintrp(
                    ht_lo,
                    float(state.GRIDEPS[idx]),
                    ht_hi,
                    float(state.GRIDEPS[idx + 1]),
                    state.HTEFF,
                )

            state.SWEFF3 = max(state.SWEFF3, state.SWMIN)
            state.SVEFF3 = max(
                state.SVEFF3, state.SVMIN, state.SVUMIN * state.UEFF3
            )
            if state.L_VECTORWS:
                state.UEFF3 = math.sqrt(
                    state.UEFF3 * state.UEFF3 + 2.0 * state.SVEFF3 * state.SVEFF3
                )
            state.UEFF3 = max(state.UEFF3, state.WSMIN)

            if state.DEBUG:
                # WRITE(DBGUNT, 6016) PPF, UEFF3, SVEFF3, SWEFF3
                state.emit_debug(isrc, irec, comp, "IBLVAL", "PPF", state.PPF)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "UEFF3", state.UEFF3)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SVEFF3", state.SVEFF3)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SWEFF3", state.SWEFF3)

    # End initialization. Next compute averages across plume layer.
    # Fortran SRCTYP(ISRC) -> state.SRCTYP[state.ISRC - 1]
    srctyp = str(state.SRCTYP[state.ISRC - 1]).strip()
    if srctyp[:5] == "POINT":
        pdis(state, xarg)
    elif srctyp == "VOLUME":
        vdis(state, xarg)
    elif srctyp in ("AREA", "AREAPOLY", "AREACIRC", "LINE", "OPENPIT"):
        adisz(state, xarg)

    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        sznew = state.SZ
        state.CENTER = state.HE
        if state.CENTER <= 5.0 and state.ZRT <= 5.0:
            zhi = 5.0
            zhi = min(zhi, state.ZI)
            zlo = 0.0
        elif state.CENTER > state.ZRT:
            zhi = state.CENTER
            zlo = max(state.CENTER - state.SZCOEF * sznew, state.ZRT)
        else:
            zhi = min(state.CENTER + state.SZCOEF * sznew, state.ZRT)
            zlo = state.CENTER

        if state.DEBUG:
            # WRITE(DBGUNT, 6031) IREC, CENTER, SZNEW, ZRT, ZLO, ZHI
            state.emit_debug(isrc, irec, comp, "IBLVAL", "CENTER", state.CENTER)
            state.emit_debug(isrc, irec, comp, "IBLVAL", "SZNEW", sznew)
            state.emit_debug(isrc, irec, comp, "IBLVAL", "ZRT", state.ZRT)
            state.emit_debug(isrc, irec, comp, "IBLVAL", "ZLO", zlo)
            state.emit_debug(isrc, irec, comp, "IBLVAL", "ZHI", zhi)

        ndxbhi = locate(state.GRIDHT, 1, state.MXGLVL, zhi)
        ndxblo = locate(state.GRIDHT, 1, state.MXGLVL, zlo)
        ndxalo = ndxblo + 1
        state.UEFF = anyavg(
            state.MXGLVL, state.GRIDHT, state.GRIDWS, zlo, ndxalo, zhi, ndxbhi
        )
        state.SVEFF = anyavg(
            state.MXGLVL, state.GRIDHT, state.GRIDSV, zlo, ndxalo, zhi, ndxbhi
        )
        state.SWEFF = anyavg(
            state.MXGLVL, state.GRIDHT, state.GRIDSW, zlo, ndxalo, zhi, ndxbhi
        )
        state.TGEFF = anyavg(
            state.MXGLVL, state.GRIDHT, state.GRIDTG, zlo, ndxalo, zhi, ndxbhi
        )
        if state.PVMRM or state.GRSM:
            state.EPSEFF = anyavg(
                state.MXGLVL, state.GRIDHT, state.GRIDEPS, zlo, ndxalo, zhi, ndxbhi
            )

        state.SWEFF = max(state.SWEFF, state.SWMIN)
        state.SVEFF = max(state.SVEFF, state.SVMIN, state.SVUMIN * state.UEFF)
        if state.L_VECTORWS:
            state.UEFF = math.sqrt(
                state.UEFF * state.UEFF + 2.0 * state.SVEFF * state.SVEFF
            )
        state.UEFF = max(state.UEFF, state.WSMIN)

        if state.DEBUG:
            # WRITE(DBGUNT, 6032) UEFF, SVEFF, SWEFF
            state.emit_debug(isrc, irec, comp, "IBLVAL", "UEFF", state.UEFF)
            state.emit_debug(isrc, irec, comp, "IBLVAL", "SVEFF", state.SVEFF)
            state.emit_debug(isrc, irec, comp, "IBLVAL", "SWEFF", state.SWEFF)

    elif state.UNSTAB and (state.HS < state.ZI):
        # First, process the penetrated plume, then the direct plumes
        if state.PPF > 0.0:
            sz3new = state.SZ3

            if state.HE3 > state.ZRT:
                zhi = state.HE3
                zlo = max(state.HE3 - state.SZCOEF * sz3new, state.ZRT)
            else:
                zhi = min(state.HE3 + state.SZCOEF * sz3new, state.ZRT)
                zlo = state.HE3

            if state.DEBUG:
                # WRITE(DBGUNT, 6041) IREC, HE3, SZ3NEW, ZRT, ZLO, ZHI
                state.emit_debug(isrc, irec, comp, "IBLVAL", "HE3", state.HE3)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SZ3NEW", sz3new)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "ZRT", state.ZRT)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "ZLO", zlo)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "ZHI", zhi)

            ndxbhi = locate(state.GRIDHT, 1, state.MXGLVL, zhi)
            ndxblo = locate(state.GRIDHT, 1, state.MXGLVL, zlo)
            ndxalo = ndxblo + 1
            state.UEFF3 = anyavg(
                state.MXGLVL, state.GRIDHT, state.GRIDWS, zlo, ndxalo, zhi, ndxbhi
            )
            state.SVEFF3 = anyavg(
                state.MXGLVL, state.GRIDHT, state.GRIDSV, zlo, ndxalo, zhi, ndxbhi
            )
            state.SWEFF3 = anyavg(
                state.MXGLVL, state.GRIDHT, state.GRIDSW, zlo, ndxalo, zhi, ndxbhi
            )
            state.TGEFF3 = anyavg(
                state.MXGLVL, state.GRIDHT, state.GRIDTG, zlo, ndxalo, zhi, ndxbhi
            )
            if state.PVMRM or state.GRSM:
                state.EPSEFF3 = anyavg(
                    state.MXGLVL,
                    state.GRIDHT,
                    state.GRIDEPS,
                    zlo,
                    ndxalo,
                    zhi,
                    ndxbhi,
                )

            state.SWEFF3 = max(state.SWEFF3, state.SWMIN)
            state.SVEFF3 = max(
                state.SVEFF3, state.SVMIN, state.SVUMIN * state.UEFF3
            )
            if state.L_VECTORWS:
                state.UEFF3 = math.sqrt(
                    state.UEFF3 * state.UEFF3 + 2.0 * state.SVEFF3 * state.SVEFF3
                )
            state.UEFF3 = max(state.UEFF3, state.WSMIN)

            if state.DEBUG:
                # WRITE(DBGUNT, 6042) UEFF3, SVEFF3, SWEFF3
                state.emit_debug(isrc, irec, comp, "IBLVAL", "UEFF3", state.UEFF3)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SVEFF3", state.SVEFF3)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SWEFF3", state.SWEFF3)

        if state.PPF < 1.0:
            # Process the direct plume components here
            szdavg = 0.5 * (state.SZD1 + state.SZD2)
            szdnew = szdavg

            if state.CENTER <= 5.0 and state.ZRT <= 5.0:
                zhi = min(5.0, state.ZI)
                zhi = min(zhi, state.ZI)
                zlo = 0.0
            elif state.CENTER > state.ZRT:
                zhi = min(state.CENTER, state.ZI)
                zlo = max(state.CENTER - state.SZCOEF * szdnew, state.ZRT)
            else:
                zhi = min(state.CENTER + state.SZCOEF * szdnew, state.ZRT)
                zhi = min(zhi, state.ZI)
                zlo = state.CENTER

            if state.DEBUG:
                # WRITE(DBGUNT, 6051) IREC, CENTER, SZDNEW, ZRT, ZLO, ZHI
                state.emit_debug(isrc, irec, comp, "IBLVAL", "CENTER", state.CENTER)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SZDNEW", szdnew)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "ZRT", state.ZRT)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "ZLO", zlo)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "ZHI", zhi)

            if zhi > zlo:
                ndxbhi = locate(state.GRIDHT, 1, state.MXGLVL, zhi)
                ndxblo = locate(state.GRIDHT, 1, state.MXGLVL, zlo)
                ndxalo = ndxblo + 1
                state.UEFFD = anyavg(
                    state.MXGLVL,
                    state.GRIDHT,
                    state.GRIDWS,
                    zlo,
                    ndxalo,
                    zhi,
                    ndxbhi,
                )
                state.SVEFFD = anyavg(
                    state.MXGLVL,
                    state.GRIDHT,
                    state.GRIDSV,
                    zlo,
                    ndxalo,
                    zhi,
                    ndxbhi,
                )
                state.SWEFFD = anyavg(
                    state.MXGLVL,
                    state.GRIDHT,
                    state.GRIDSW,
                    zlo,
                    ndxalo,
                    zhi,
                    ndxbhi,
                )
                if state.PVMRM or state.GRSM:
                    state.EPSEFFD = anyavg(
                        state.MXGLVL,
                        state.GRIDHT,
                        state.GRIDEPS,
                        zlo,
                        ndxalo,
                        zhi,
                        ndxbhi,
                    )
            else:
                state.HTEFF = state.ZI
                ndxeff = locate(state.GRIDHT, 1, state.MXGLVL, state.HTEFF)
                # Fortran NDXEFF -> idx = ndxeff - 1
                idx = ndxeff - 1
                ht_lo = float(state.GRIDHT[idx])
                ht_hi = float(state.GRIDHT[idx + 1])

                state.UEFFD = gintrp(
                    ht_lo,
                    float(state.GRIDWS[idx]),
                    ht_hi,
                    float(state.GRIDWS[idx + 1]),
                    state.HTEFF,
                )
                state.SVEFFD = gintrp(
                    ht_lo,
                    float(state.GRIDSV[idx]),
                    ht_hi,
                    float(state.GRIDSV[idx + 1]),
                    state.HTEFF,
                )
                state.SWEFFD = gintrp(
                    ht_lo,
                    float(state.GRIDSW[idx]),
                    ht_hi,
                    float(state.GRIDSW[idx + 1]),
                    state.HTEFF,
                )
                if state.PVMRM or state.GRSM:
                    state.EPSEFFD = gintrp(
                        ht_lo,
                        float(state.GRIDEPS[idx]),
                        ht_hi,
                        float(state.GRIDEPS[idx + 1]),
                        state.HTEFF,
                    )

            state.SWEFFD = max(state.SWEFFD, state.SWMIN)
            state.SVEFFD = max(
                state.SVEFFD, state.SVMIN, state.SVUMIN * state.UEFFD
            )
            if state.L_VECTORWS:
                state.UEFFD = math.sqrt(
                    state.UEFFD * state.UEFFD + 2.0 * state.SVEFFD * state.SVEFFD
                )
            state.UEFFD = max(state.UEFFD, state.WSMIN)

            if state.DEBUG:
                # WRITE(DBGUNT, 6052) UEFFD, SVEFFD, SWEFFD
                state.emit_debug(isrc, irec, comp, "IBLVAL", "UEFFD", state.UEFFD)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SVEFFD", state.SVEFFD)
                state.emit_debug(isrc, irec, comp, "IBLVAL", "SWEFFD", state.SWEFFD)

    # Set effective parameters for indirect source = direct source
    if state.UNSTAB and state.HS < state.ZI:
        state.UEFFN = state.UEFFD
        state.SVEFFN = state.SVEFFD
        state.SWEFFN = state.SWEFFD
