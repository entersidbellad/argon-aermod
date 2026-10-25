"""SUBROUTINE CALC, PCALC, AERCALC, CENTROID, REFL_HT, PSRDEB, SETSRC, FLUXES, HEFF, PDIS, VDIS, ADISZ, AER_PCHI, DEBOUT, PENFCT, CPLUME, LTOPG (calc1.f)."""

from __future__ import annotations

import math
import numpy as xp

from .state import AermodState, f_int
from .iblval import iblval, locate, metini
from .metext import gintrp, metdeb
from .calc2 import (
    critds,
    decay,
    distf,
    emfact,
    fterm,
    fypan,
    fyplm,
    meandr,
    pdf,
    pfract,
    sumval,
    vrtbl_cbl as vrtcbl,
    vrtsbl,
    vrtsbn,
    wakflg,
    xydist,
)
from .prise import cblpr3, cblprd, deltah, hsprim
from .sigmas import bid, rmssig, sigy, sigz
from .prime_base import wake_ini


def calc(state: AermodState) -> None:
    """SUBROUTINE CALC (calc1.f)."""
    state.PATH = "CN"
    state.RLPROCESSED = False
    state.METHDR = True
    state.prev_active_isrc = 0

    # Begin Source LOOP
    # Fortran ISRC = 1..NUMSRC -> isrc in range(state.NUMSRC)
    for isrc in range(state.NUMSRC):
        state.ISRC = isrc + 1
        srctyp = str(state.SRCTYP[isrc]).strip()
        if srctyp[:5] == "POINT":
            pcalc(state)
        else:
            raise RuntimeError(f"Out of scope SRCTYP {srctyp!r} in CALC")

        if state.RUNERR:
            break


def pcalc(state: AermodState) -> None:
    """SUBROUTINE PCALC (calc1.f)."""
    # Initialize __VAL arrays (1:NUMTYP)
    state.HRVAL[:] = 0.0
    state.AERVAL[:] = 0.0
    aerplm = xp.zeros(state.NUMTYP, dtype=xp.float64)
    aerpan = xp.zeros(state.NUMTYP, dtype=xp.float64)
    state.PRMVAL[:] = 0.0

    fran = 0.0
    fran3 = 0.0

    # Set the Source Variables for This Source --- CALL SETSRC
    setsrc(state)

    # Apply Variable Emission Rate Factors --- CALL EMFACT
    emfact(state, state.QS)

    if state.QTK != 0.0:
        # Fortran ISRC (1-based) -> isrc_idx = state.ISRC - 1
        isrc_idx = state.ISRC - 1
        urbsrc_flag = str(state.URBSRC[isrc_idx]).strip()

        # Set Mixing Height and Profiles for Urban Option if Needed
        if urbsrc_flag == "Y":
            # Fortran I = 1..NUMURB -> i in range(state.NUMURB)
            for i in range(state.NUMURB):
                if state.IURBGRP[isrc_idx, i] == 1:
                    state.IURB = i + 1
                    break
            iurb_idx = state.IURB - 1
            if state.STABLE or state.L_MorningTrans[iurb_idx]:
                state.URBSTAB = True
                state.ZI = max(float(state.ZIURB[iurb_idx]), state.ZIMECH)
                state.GRIDSV[:] = state.GRDSVU[:, iurb_idx]
                state.GRIDSW[:] = state.GRDSWU[:, iurb_idx]
                state.GRIDTG[:] = state.GRDTGU[:, iurb_idx]
                state.GRIDPT[:] = state.GRDPTU[:, iurb_idx]
                state.OBULEN = float(state.URBOBULEN[iurb_idx])
                state.USTAR = float(state.URBUSTR[iurb_idx])
            else:
                state.URBSTAB = False
                state.ZI = state.ZIRUR
                state.GRIDSV[:] = state.GRDSVR[:]
                state.GRIDSW[:] = state.GRDSWR[:]
                state.GRIDTG[:] = state.GRDTGR[:]
                state.GRIDPT[:] = state.GRDPTR[:]
                state.OBULEN = state.RUROBULEN
                state.USTAR = state.RURUSTR
        elif state.URBAN and urbsrc_flag == "N":
            state.URBSTAB = False
            state.ZI = state.ZIRUR
            state.GRIDSV[:] = state.GRDSVR[:]
            state.GRIDSW[:] = state.GRDSWR[:]
            state.GRIDTG[:] = state.GRDTGR[:]
            state.GRIDPT[:] = state.GRDPTR[:]
            state.OBULEN = state.RUROBULEN
            state.USTAR = state.RURUSTR
        else:
            state.URBSTAB = False

        # Calculate the initial meteorological variables --- CALL METINI
        metini(state)

        # Calculate Buoyancy and Momentum Fluxes --- CALL FLUXES
        vseq = fluxes(state)

        # Set Wake and Building Type Switches --- CALL WAKFLG
        if state.OSPLAT[isrc_idx]:
            state.WAKE = False
        else:
            wakflg(state)

        # Define temporary values of CENTER and SURFAC based on HS
        state.CENTER = state.HS
        if state.CENTER < 0.1 * state.ZI:
            state.SURFAC = True
        else:
            state.SURFAC = False

        # Check for stack-tip downwash option and adjust if necessary
        srctyp = str(state.SRCTYP[isrc_idx]).strip()
        if srctyp == "POINTCAP":
            state.HSP = hsprim(state.US, vseq, state.HS, state.DS)
        elif srctyp == "POINTHOR":
            state.HSP = state.HS
        elif state.NOSTD:
            state.HSP = state.HS
        else:
            state.HSP = hsprim(state.US, state.VS, state.HS, state.DS)

        # Calculate Distance to Final Rise --- CALL DISTF
        distf(state)

        # Calculate the plume penetration factor --- CALL PENFCT
        penfct(state)

        if state.DEBUG:
            # WRITE(DBGUNT,6000) DHFAER, UP, TGS
            # Note: in MODEL.DBG, 6000 and 6001 are printed before 6010 (which resets
            # parser receptor/comp state after a previous source's receptor loop).
            if state.prev_active_isrc == 0:
                state.emit_debug(state.ISRC, 0, "", "PCALC", "DHFAER", state.DHFAER)
                state.emit_debug(state.ISRC, 0, "", "PCALC", "UP", state.UP)
                state.emit_debug(state.ISRC, 0, "", "PCALC", "TGS", state.TGS)
            else:
                state.emit_debug(
                    state.prev_active_isrc,
                    state.NUMREC,
                    "PAN",
                    "PCALC",
                    "DHFAER",
                    state.DHFAER,
                )
                state.emit_debug(
                    state.prev_active_isrc,
                    state.NUMREC,
                    "PAN",
                    "PCALC",
                    "UP",
                    state.UP,
                )
                state.emit_debug(
                    state.prev_active_isrc,
                    state.NUMREC,
                    "PAN",
                    "PCALC",
                    "TGS",
                    state.TGS,
                )

        if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
            # Use iterative approach to stable plume rise calculations
            kiter = 0
            while True:
                zplm = state.HSP + 0.5 * state.DHFAER
                dhfold = state.DHFAER

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

                # Use average of stack top and midpoint wind speeds
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
                # Use average of stack top and midpoint temperature gradients
                state.TGP = 0.5 * (state.TGS + tgpm)
                ptp = 0.5 * (state.PTS + ptpm)
                state.BVF = math.sqrt(state.G * state.TGP / ptp)
                if state.BVF < 1.0e-10:
                    state.BVF = 1.0e-10
                state.BVPRIM = 0.7 * state.BVF

                distf(state)

                kiter = kiter + 1

                if state.DEBUG:
                    # WRITE(DBGUNT,6001) KITER, DHFOLD, DHFAER, ZPLM, UP, TGP
                    if state.prev_active_isrc == 0:
                        state.emit_debug(state.ISRC, 0, "", "PCALC", "DHFOLD", dhfold)
                        state.emit_debug(
                            state.ISRC, 0, "", "PCALC", "DHFAER", state.DHFAER
                        )
                        state.emit_debug(state.ISRC, 0, "", "PCALC", "ZPLM", zplm)
                        state.emit_debug(state.ISRC, 0, "", "PCALC", "UP", state.UP)
                        state.emit_debug(state.ISRC, 0, "", "PCALC", "TGP", state.TGP)
                    else:
                        state.emit_debug(
                            state.prev_active_isrc,
                            state.NUMREC,
                            "PAN",
                            "DELTAH",
                            "DHPOLD",
                            dhfold,
                        )
                        state.emit_debug(
                            state.prev_active_isrc,
                            state.NUMREC,
                            "PAN",
                            "DELTAH",
                            "DHP",
                            state.DHFAER,
                        )
                        state.emit_debug(
                            state.prev_active_isrc,
                            state.NUMREC,
                            "PAN",
                            "DELTAH",
                            "ZPLM",
                            zplm,
                        )
                        state.emit_debug(
                            state.prev_active_isrc,
                            state.NUMREC,
                            "PAN",
                            "DELTAH",
                            "UP",
                            state.UP,
                        )
                        state.emit_debug(
                            state.prev_active_isrc,
                            state.NUMREC,
                            "PAN",
                            "DELTAH",
                            "TGP",
                            state.TGP,
                        )

                # Check for convergence
                if abs((dhfold - state.DHFAER) / state.DHFAER) < 0.01:
                    break

                if kiter >= 5:
                    state.DHFAER = 0.5 * (state.DHFAER + dhfold)
                    break

            # After completing iteration, reset UP and TGP to stack top values
            state.UP = state.US
            state.TGP = state.TGS
            ptp = state.PTS
            state.BVF = math.sqrt(state.G * state.TGP / ptp)
            if state.BVF < 1.0e-10:
                state.BVF = 1.0e-10
            state.BVPRIM = 0.7 * state.BVF

        state.PRM_FSTREC = True
        state.ZMIDMX = 0.5 * state.ZI

        if state.DEBUG:
            # WRITE(DBGUNT,6010) KURDAT, ZMIDMX
            state.emit_debug(state.ISRC, 0, "", "PCALC", "ZMIDMX", state.ZMIDMX)

        state.XFINAL = state.XMAX
        state.DHCRIT = state.DHFAER
        state.XMIXED = state.ZI * state.UAVG / state.SWAVG
        if state.UNSTAB and state.HS < state.ZI:
            if state.XMIXED < 1.25 * state.XFINAL:
                state.XFINAL = 0.8 * state.XMIXED
                cblprd(state, state.XFINAL)
                state.DHCRIT = state.DHP1

        # Initialize PDF parameters for use in calculating ZSUBP
        if state.UNSTAB and (state.HS < state.ZI):
            pdf(state)

        # Determine transport wind direction using midpoint between stack height and "final" plume height
        zmid = min(4000.0, (state.HS + 0.5 * state.DHFAER))

        ndxzmid = locate(state.GRIDHT, 1, state.MXGLVL, zmid)
        # Fortran NDXZMID -> idx = ndxzmid - 1, NDXZMID+1 -> idx + 1
        idx_zmid = ndxzmid - 1
        valabv = float(state.GRIDWD[idx_zmid + 1])
        vbelow = float(state.GRIDWD[idx_zmid])

        if (valabv - vbelow) < -180.0:
            valabv = valabv + 360.0
        elif (valabv - vbelow) > 180.0:
            valabv = valabv - 360.0

        if vbelow == valabv:
            state.WDIR = vbelow
        else:
            state.WDIR = gintrp(
                float(state.GRIDHT[idx_zmid]),
                vbelow,
                float(state.GRIDHT[idx_zmid + 1]),
                valabv,
                zmid,
            )

        if state.WDIR > 360.0:
            state.WDIR = state.WDIR - 360.0
        elif state.WDIR <= 0.0:
            state.WDIR = state.WDIR + 360.0

        state.WDSIN = math.sin(state.WDIR * state.DTORAD)
        state.WDCOS = math.cos(state.WDIR * state.DTORAD)

        state.AWDSIN[isrc_idx] = state.WDSIN
        state.AWDCOS[isrc_idx] = state.WDCOS

        state.AFV = state.WDIR - 180.0
        if state.AFV < 0.0:
            state.AFV = state.AFV + 360.0
        state.AAFV[isrc_idx] = state.AFV
        state.IFVSEC = f_int(state.AFV * 0.10 + 0.4999)
        if state.IFVSEC == 0:
            state.IFVSEC = 36

        if state.WAKE:
            ustack = state.US
            ndxbh = locate(state.GRIDHT, 1, state.MXGLVL, state.DSBH)
            # Fortran NDXBH -> idx_bh = ndxbh - 1, NDXBH+1 -> idx_bh + 1
            idx_bh = ndxbh - 1
            ubldg = gintrp(
                float(state.GRIDHT[idx_bh]),
                float(state.GRIDWS[idx_bh]),
                float(state.GRIDHT[idx_bh + 1]),
                float(state.GRIDWS[idx_bh + 1]),
                state.DSBH,
            )
            ldbhr = state.PRIMEDBG
            state.RURAL = True
            wake_ini(
                state,
                state.KURDAT,
                ldbhr,
                state.PRMDBUNT,
                state.RURAL,
                state.DSBH,
                state.DSBW,
                state.DSBL,
                state.XADJ,
                state.YADJ,
                ubldg,
                ustack,
            )

        if state.DEBUG:
            # WRITE(DBGUNT, 6011) DHCRIT, XFINAL, XMIXED, AFV
            state.emit_debug(state.ISRC, 0, "", "PCALC", "DHCRIT", state.DHCRIT)
            state.emit_debug(state.ISRC, 0, "", "PCALC", "XFINAL", state.XFINAL)
            state.emit_debug(state.ISRC, 0, "", "PCALC", "XMIXED", state.XMIXED)
            state.emit_debug(state.ISRC, 0, "", "PCALC", "AFV", state.AFV)
            psrdeb(state)

        # Begin Receptor LOOP
        # Fortran IREC = 1..NUMREC -> irec in range(state.NUMREC)
        for irec in range(state.NUMREC):
            state.IREC = irec + 1

            if state.EVONLY:
                xydist(state, state.IEVENT)
            else:
                xydist(state, state.IREC)

            if state.DISTR < 0.99 or state.DISTR > state.MAXDIST:
                state.HRVAL[:] = 0.0
                aerplm[:] = 0.0
                aerpan[:] = 0.0
                state.PRMVAL[:] = 0.0
                continue

            # Calculate coherent plume component using downwind distance
            l_plume = True
            state.XDIST = state.X
            aercalc(state, state.X, l_plume, aerplm)

            if state.L_EFFSIGY:
                state.AERVAL[:] = aerplm[:]
                aerpan[:] = 0.0
                fran = 0.0
            else:
                # Next calculate random "pancake" component using radial distance
                l_plume = False
                state.XDIST = state.DISTR
                aercalc(state, state.DISTR, l_plume, aerpan)

                state.debug_comp = "PAN"
                if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
                    fran = meandr(state, state.UEFF, state.SVEFF)
                elif state.UNSTAB:
                    fran = meandr(state, state.UEFFD, state.SVEFFD)
                    if state.PPF > 0.0:
                        fran3 = meandr(state, state.UEFF3, state.SVEFF3)
                        fran = state.PPF * fran3 + (1.0 - state.PPF) * fran

                state.AERVAL[:] = fran * aerpan + (1.0 - fran) * aerplm

            if state.DEBUG:
                # Fortran DO ITYP = 1, NUMTYP -> ityp in range(state.NUMTYP)
                for ityp in range(state.NUMTYP):
                    # WRITE(DBGUNT,10) AERPAN(ITYP), AERPLM(ITYP), FRAN, AERVAL(ITYP)
                    state.emit_debug(
                        state.ISRC,
                        state.IREC,
                        "PAN",
                        "PCALC",
                        "AERPAN",
                        float(aerpan[ityp]),
                    )
                    state.emit_debug(
                        state.ISRC,
                        state.IREC,
                        "PAN",
                        "PCALC",
                        "AERPLM",
                        float(aerplm[ityp]),
                    )
                    state.emit_debug(
                        state.ISRC, state.IREC, "PAN", "PCALC", "FRAN", fran
                    )
                    state.emit_debug(
                        state.ISRC,
                        state.IREC,
                        "PAN",
                        "PCALC",
                        "AERVAL",
                        float(state.AERVAL[ityp]),
                    )

            if state.WAKE and (state.STABLE or state.HS <= state.ZI):
                xbrec = state.X - state.XADJ
                ybrec = state.Y - state.YADJ
                state.XDIST = state.X
                prmcalc(state, xbrec, ybrec)
                if state.RUNERR:
                    return
                gamcalc(state, xbrec, ybrec)
                state.HRVAL[:] = (
                    state.GAMFACT * state.PRMVAL
                    + (1.0 - state.GAMFACT) * state.AERVAL
                )
                if state.PRIMEDBG:
                    # Fortran DO ITYP = 1, NUMTYP -> ityp in range(state.NUMTYP)
                    for ityp in range(state.NUMTYP):
                        state.emit_debug(
                            state.ISRC,
                            state.IREC,
                            "PRIME",
                            "PCALC",
                            "GAMFACT",
                            state.GAMFACT,
                        )
                        state.emit_debug(
                            state.ISRC,
                            state.IREC,
                            "PRIME",
                            "PCALC",
                            "AERVAL",
                            float(state.AERVAL[ityp]),
                        )
                        state.emit_debug(
                            state.ISRC,
                            state.IREC,
                            "PRIME",
                            "PCALC",
                            "PRMVAL",
                            float(state.PRMVAL[ityp]),
                        )
                        state.emit_debug(
                            state.ISRC,
                            state.IREC,
                            "PRIME",
                            "PCALC",
                            "HRVAL",
                            float(state.HRVAL[ityp]),
                        )
            else:
                state.GAMFACT = 0.0
                state.HRVAL[:] = state.AERVAL[:]
                state.PRMVAL[:] = 0.0

            # Sum HRVAL to AVEVAL and ANNVAL Arrays --- CALL SUMVAL
            if not state.EVONLY:
                # Fortran IGRP = 1..NUMGRP -> igrp in range(state.NUMGRP)
                for igrp in range(state.NUMGRP):
                    state.IGRP = igrp + 1
                    sumval(state)

            # Initialize __VAL arrays (1:NUMTYP)
            state.HRVAL[:] = 0.0
            state.AERVAL[:] = 0.0
            aerplm[:] = 0.0
            aerpan[:] = 0.0
            state.PRMVAL[:] = 0.0

        state.prev_active_isrc = state.ISRC


def aercalc(
    state: AermodState, xarg: float, l_plume: bool, aerout: xp.ndarray
) -> None:
    """SUBROUTINE AERCALC (calc1.f)."""
    aerout[:] = 0.0
    aertmp = xp.zeros(state.NUMTYP, dtype=xp.float64)

    fran = 0.0
    fran3 = 0.0

    if xarg < 1.0:
        aerout[:] = 0.0
        return

    state.debug_comp = "PLM" if l_plume else "PAN"
    comp = state.debug_comp

    # Determine Deposition Correction Factors
    if state.NPD == 0 and (state.LDGAS or state.LWGAS):
        raise RuntimeError("Gas deposition out of scope")
    else:
        state.DQCORG = 1.0
        state.WQCORG = 1.0

    # Set initial effective parameters
    state.UEFF = state.US
    state.SVEFF = state.SVS
    state.SWEFF = state.SWS
    state.TGEFF = state.TGS
    if state.UNSTAB and (state.HS < state.ZI):
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

    if state.DEBUG:
        # WRITE(DBGUNT, 6015 / 6016) UEFF, SVEFF, SWEFF
        # Parsed by dbgparse.py as IBLVAL UEFF, SVEFF, SWEFF
        state.emit_debug(state.ISRC, state.IREC, comp, "IBLVAL", "UEFF", state.UEFF)
        state.emit_debug(state.ISRC, state.IREC, comp, "IBLVAL", "SVEFF", state.SVEFF)
        state.emit_debug(state.ISRC, state.IREC, comp, "IBLVAL", "SWEFF", state.SWEFF)

    # Define plume centroid height (CENTER) for use in inhomogeneity calculations
    centroid(state, xarg)

    # Calculate the plume rise --- CALL DELTAH
    deltah(state, xarg)

    # If the atmosphere is unstable and the stack top is below the mixing height,
    # calculate the CBL PDF coefficients --- CALL PDF
    if state.UNSTAB and (state.HS < state.ZI):
        pdf(state)

    # Determine Effective Plume Height --- CALL HEFF
    heff(state, xarg)

    # Compute effective parameters using an average through plume layer
    iblval(state, xarg)

    # Call PDF & HEFF again for final CBL plume heights
    if state.UNSTAB and (state.HS < state.ZI):
        pdf(state)
        heff(state, xarg)

    # Determine Dispersion Parameters --- CALL PDIS
    pdis(state, xarg)

    # Calculate the 'y-term' contribution to dispersion, FSUBY
    if l_plume:
        if state.L_EFFSIGY:
            if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
                fran = meandr(state, state.UEFF, state.SVEFF)
            elif state.UNSTAB:
                fran = meandr(state, state.UEFFD, state.SVEFFD)
                if state.PPF > 0.0:
                    fran3 = meandr(state, state.UEFF3, state.SVEFF3)
                    fran = state.PPF * fran3 + (1.0 - state.PPF) * fran

            state.SYEFF = 1.0 / (
                (fran / (state.SRT2PI * xarg)) + (1.0 - fran) / state.SY
            )
            if abs(state.Y) > state.NUMSYEFF * state.SYEFF:
                fyout = 0.0
            else:
                fyout = fyplm(state, state.SYEFF)
        else:
            fyout = fyplm(state, state.SY)
    else:
        fyout = fypan(state)

    state.FSUBY = fyout
    state.FSUBYD = state.FSUBY
    state.FSUBYN = state.FSUBYD

    # Calculate the 'y-term' contribution to dispersion for the penetrated plume, FSUBY3
    if state.UNSTAB and (state.HS < state.ZI) and (state.PPF > 0.0):
        if l_plume:
            if state.L_EFFSIGY:
                state.SYEFF = 1.0 / (
                    (fran / (state.SRT2PI * xarg)) + (1.0 - fran) / state.SY3
                )
                if abs(state.Y) > state.NUMSYEFF * state.SYEFF:
                    fyout = 0.0
                else:
                    fyout = fyplm(state, state.SYEFF)
            else:
                fyout = fyplm(state, state.SY3)
        else:
            fyout = fypan(state)
        state.FSUBY3 = fyout
    else:
        state.FSUBY3 = 0.0

    # Check for zero "y-terms"; if zero then skip calculations
    if state.FSUBY == 0.0 and state.FSUBY3 == 0.0:
        aerout[:] = 0.0
    else:
        if state.NPD == 0:
            # Perform calculations for gases
            state.HV = 0.0
            adj = state.DQCORG * state.WQCORG

            if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
                state.HSBL = refl_ht(state, state.HE, xarg, state.SZB, 0.0)
            elif state.UNSTAB:
                state.HSBL = 0.0

            if state.UNSTAB and (state.HS < state.ZI) and (state.PPF > 0.0):
                state.HPEN = refl_ht(state, state.HE3, xarg, state.SZB3, 0.0)
            else:
                state.HPEN = 0.0

            # Determine the CRITical Dividing Streamline --- CALL CRITDS
            critds(state, state.HE)

            # Calculate the fraction of plume below HCRIT, PHEE --- CALL PFRACT
            pfract(state, state.HE)

            # Calculate FOPT = f(PHEE) --- CALL FTERM
            fterm(state)

            # Calculate AERMOD Concentration --- CALL AER_PCHI
            aer_pchi(state, xarg, adj, state.VDEPG, 0, aerout)
        else:
            # Perform calculations for particles
            # Fortran J = 1..NPD -> j in range(state.NPD)
            for j in range(state.NPD):
                state.HV = (xarg / state.US) * float(state.VGRAV[j])
                adj = (
                    float(state.PHI[j])
                    * float(state.DQCOR[j])
                    * float(state.WQCOR[j])
                )
                if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
                    state.HESETL = max(0.0, state.HE - state.HV)
                    state.HSBL = refl_ht(state, state.HESETL, xarg, state.SZB, 0.0)
                elif state.UNSTAB:
                    state.HESETL = max(
                        0.0, 0.5 * (state.HED1 + state.HED2) - state.HV
                    )
                    state.HSBL = 0.0

                if state.UNSTAB and (state.HS < state.ZI) and (state.PPF > 0.0):
                    state.HE3SETL = max(0.0, state.HE3 - state.HV)
                    state.HPEN = refl_ht(state, state.HE3SETL, xarg, state.SZB3, 0.0)
                    state.HPEN = max(state.HPEN, state.ZI)
                else:
                    state.HPEN = 0.0

                critds(state, state.HESETL)
                pfract(state, state.HESETL)
                fterm(state)
                aer_pchi(state, xarg, adj, float(state.VDEP[j]), j + 1, aertmp)
                aerout[:] = aerout + aertmp


def centroid(state: AermodState, xarg: float) -> None:
    """SUBROUTINE CENTROID (calc1.f)."""
    xtmp = max(xarg, 1.0)
    # Fortran ISRC (1-based) -> state.ISRC - 1
    srctyp = str(state.SRCTYP[state.ISRC - 1]).strip()

    if state.UNSTAB and (state.HS < state.ZI):
        if srctyp[:5] == "POINT":
            cblprd(state, xtmp)
            state.HTEFF = min(state.HSP + state.DHP1, state.ZI)
        else:
            state.HTEFF = state.HSP
            state.DHCRIT = 0.0
            state.XFINAL = 0.0

        if xtmp < state.XFINAL:
            state.CENTER = state.HTEFF
        elif xtmp >= state.XMIXED:
            state.CENTER = state.ZMIDMX
        else:
            delx = state.XMIXED - state.XFINAL
            delz = state.ZMIDMX - min(state.HSP + state.DHCRIT, state.ZI)
            frac = (xtmp - state.XFINAL) / delx
            state.CENTER = min(state.HSP + state.DHCRIT, state.ZI) + frac * delz

        if state.CENTER < 0.1 * state.ZI:
            state.SURFAC = True
        else:
            state.SURFAC = False
    elif state.UNSTAB and (state.HS >= state.ZI):
        state.SURFAC = False
        state.CENTER = state.HSP
        if state.CENTER < 0.1 * state.ZI:
            state.SURFAC = True
        else:
            state.SURFAC = False
    else:
        state.CENTER = state.HSP
        if state.CENTER < 0.1 * state.ZI:
            state.SURFAC = True
        else:
            state.SURFAC = False


def refl_ht(
    state: AermodState,
    hearg: float,
    xarg: float,
    szbarg: float,
    vsigzarg: float,
) -> float:
    """SUBROUTINE REFL_HT (calc1.f)."""
    ndxhe = locate(state.GRIDHT, 1, state.MXGLVL, hearg)

    if ndxhe >= 1:
        # Fortran NDXHE -> idx = ndxhe - 1, NDXHE+1 -> idx + 1
        idx = ndxhe - 1
        ht_lo = float(state.GRIDHT[idx])
        ht_hi = float(state.GRIDHT[idx + 1])

        svrefl = gintrp(
            ht_lo,
            float(state.GRIDSV[idx]),
            ht_hi,
            float(state.GRIDSV[idx + 1]),
            hearg,
        )
        swrefl = gintrp(
            ht_lo,
            float(state.GRIDSW[idx]),
            ht_hi,
            float(state.GRIDSW[idx + 1]),
            hearg,
        )
        urefl = gintrp(
            ht_lo,
            float(state.GRIDWS[idx]),
            ht_hi,
            float(state.GRIDWS[idx + 1]),
            hearg,
        )
        tgrefl = gintrp(
            ht_lo,
            float(state.GRIDTG[idx]),
            ht_hi,
            float(state.GRIDTG[idx + 1]),
            hearg,
        )
        ptrefl = gintrp(
            ht_lo,
            float(state.GRIDPT[idx]),
            ht_hi,
            float(state.GRIDPT[idx + 1]),
            hearg,
        )
    else:
        svrefl = float(state.GRIDSV[0])
        swrefl = float(state.GRIDSW[0])
        urefl = float(state.GRIDWS[0])
        tgrefl = float(state.GRIDTG[0])
        ptrefl = float(state.GRIDPT[0])

    swrefl = max(swrefl, state.SWMIN)
    svrefl = max(svrefl, state.SVMIN, state.SVUMIN * urefl)
    if state.L_VECTORWS:
        urefl = math.sqrt(urefl * urefl + 2.0 * svrefl * svrefl)
    urefl = max(urefl, state.WSMIN)

    if state.STABLE:
        state.SZSURF = (
            (state.RTOF2 / state.RTOFPI)
            * state.USTAR
            * (xarg / urefl)
            * (1.0 + 0.7 * xarg / state.OBULEN) ** (-1.0 * state.THIRD)
        )
    else:
        state.SZSURF = 0.0

    ttravl = xarg / urefl
    bvfrq = math.sqrt(state.G * tgrefl / ptrefl)
    if bvfrq < 1.0e-10:
        bvfrq = 1.0e-10

    ztmp = max(state.HS, hearg, 1.0e-4)
    szrefl = (
        swrefl
        * ttravl
        / math.sqrt(
            1.0
            + swrefl
            * ttravl
            * (1.0 / (0.72 * ztmp) + bvfrq / (0.54 * swrefl))
        )
    )

    if hearg >= state.ZI:
        szrf = szrefl
    else:
        sigf = min(hearg / state.ZI, 1.0)
        szrf = (1.0 - sigf) * state.SZSURF + sigf * szrefl

    szhsbl = math.sqrt(szbarg * szbarg + szrf * szrf + vsigzarg * vsigzarg)
    herefl = max(state.ZI, hearg + 2.15 * szhsbl)
    return herefl


def psrdeb(state: AermodState) -> None:
    """SUBROUTINE PSRDEB (calc1.f)."""
    isrc = state.ISRC
    # WRITE (DBGUNT, 6135) ISRC, QS, TS, VS, DS, FB, FM, HS, DHCRIT
    state.emit_debug(isrc, 0, "", "PSRDEB", "QS", state.QS)
    state.emit_debug(isrc, 0, "", "PSRDEB", "TS", state.TS)
    state.emit_debug(isrc, 0, "", "PSRDEB", "VS", state.VS)
    state.emit_debug(isrc, 0, "", "PSRDEB", "DS", state.DS)
    state.emit_debug(isrc, 0, "", "PSRDEB", "FB", state.FB)
    state.emit_debug(isrc, 0, "", "PSRDEB", "FM", state.FM)
    state.emit_debug(isrc, 0, "", "PSRDEB", "HS", state.HS)
    state.emit_debug(isrc, 0, "", "PSRDEB", "DHCRIT", state.DHCRIT)

    # WRITE (DBGUNT, 6140) HS, WDIR, US, UP, SVS, SWS, TGS
    state.emit_debug(isrc, 0, "", "PSRDEB", "HS", state.HS)
    state.emit_debug(isrc, 0, "", "PSRDEB", "WDIR", state.WDIR)
    state.emit_debug(isrc, 0, "", "PSRDEB", "US", state.US)
    state.emit_debug(isrc, 0, "", "PSRDEB", "UP", state.UP)
    state.emit_debug(isrc, 0, "", "PSRDEB", "SVS", state.SVS)
    state.emit_debug(isrc, 0, "", "PSRDEB", "SWS", state.SWS)
    state.emit_debug(isrc, 0, "", "PSRDEB", "TGS", state.TGS)


def setsrc(state: AermodState) -> None:
    """SUBROUTINE SETSRC (calc1.f)."""
    state.XINIT = 0.0
    state.YINIT = 0.0
    state.SYINIT = 0.0
    state.SZINIT = 0.0
    state.ANGLE = 0.0
    state.PALPHA = 0.0
    state.PDEFF = 0.0
    state.PITLEN = 0.0
    state.PITWID = 0.0

    # Fortran ISRC (1-based) -> idx = state.ISRC - 1
    idx = state.ISRC - 1
    srctyp = str(state.SRCTYP[idx]).strip()

    if srctyp[:5] == "POINT":
        state.XS = float(state.AXS[idx])
        state.YS = float(state.AYS[idx])
        state.ZS = float(state.AZS[idx])
        state.QS = float(state.AQS[idx])
        state.HS = float(state.AHS[idx])

        state.DS = float(state.ADS[idx])
        state.VS = float(state.AVS[idx])
        state.TS = float(state.ATS[idx])

        if srctyp == "POINTCAP":
            state.DSFACT = float(state.ADSFACT[idx])
        else:
            state.DSFACT = 1.0

    state.NPD = int(state.INPD[idx])
    if state.NPD > 0:
        # Fortran J = 1..NPD -> j in range(state.NPD)
        state.PDIAM = state.APDIAM[: state.NPD, idx].copy()
        state.PHI = state.APHI[: state.NPD, idx].copy()
        state.PDENS = state.APDENS[: state.NPD, idx].copy()
        state.VGRAV = state.AVGRAV[: state.NPD, idx].copy()
        state.TSTOP = state.ATSTOP[: state.NPD, idx].copy()

    if state.HS < 0.1 * state.ZI:
        state.SURFAC = True
    else:
        state.SURFAC = False


def fluxes(state: AermodState) -> float:
    """SUBROUTINE FLUXES (calc1.f)."""
    # Check for Negative Stack Temperature, Used to Indicate Constant TS-TA
    if state.TS < 0.0:
        state.TS = state.TA + abs(state.TS)

    if state.TS < state.TA:
        state.TS = state.TA
    state.FB = (
        (0.25 / state.TS)
        * (state.VS * state.DS * state.DS)
        * state.G
        * (state.TS - state.TA)
    )
    state.FM = (
        (0.25 / state.TS)
        * (state.VS * state.DS * state.DS)
        * state.VS
        * state.TA
    )

    # Fortran ISRC (1-based) -> state.ISRC - 1
    srctyp = str(state.SRCTYP[state.ISRC - 1]).strip()
    if srctyp == "POINTCAP":
        vseq = 0.001
        dseq = state.DS * math.sqrt(state.VS / vseq)
        tseq = state.TS
        state.FM = (0.25 / tseq) * (vseq * dseq * dseq) * vseq * state.TA
    elif srctyp == "POINTHOR":
        vseq = 0.001
        dseq = state.DS * math.sqrt(state.VS / vseq)
        tseq = state.TS
        state.FM = (0.25 / tseq) * (vseq * dseq * dseq) * vseq * state.TA
    else:
        vseq = state.VS

    if state.FB < 1.0e-10:
        state.FB = 1.0e-10
    if state.FM < 1.0e-10:
        state.FM = 1.0e-10

    return vseq


def heff(state: AermodState, xarg: float) -> None:
    """SUBROUTINE HEFF (calc1.f)."""
    state.DHP3PLAT = 0.0
    # Fortran ISRC (1-based) -> isrc_idx = state.ISRC - 1
    isrc_idx = state.ISRC - 1

    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        state.HE = state.HSP + state.DHP
        state.HE = max(0.0, state.HE)

        state.HED1 = 0.0
        state.HED2 = 0.0
        state.HEN1 = 0.0
        state.HEN2 = 0.0
        state.HE3 = 0.0
    elif state.UNSTAB:
        state.HE = 0.0

        state.HED1 = state.HSP + state.DHP1 + (state.ASUB1 * state.WSTAR * xarg / state.UEFFD)
        state.HED2 = state.HSP + state.DHP1 + (state.ASUB2 * state.WSTAR * xarg / state.UEFFD)

        state.HEN1 = (
            state.HSP
            + state.DHP1
            - state.DHP2
            + (state.ASUB1 * state.WSTAR * xarg / state.UEFFN)
        )
        state.HEN2 = (
            state.HSP
            + state.DHP1
            - state.DHP2
            + (state.ASUB2 * state.WSTAR * xarg / state.UEFFN)
        )

        if state.PPF > 0.0:
            if state.PPF == 1.0:
                state.DHP3 = state.HEDHH * (state.ZI - state.HSP)
            else:
                state.DHP3 = (
                    0.75 * (state.ZI - state.HSP) * state.HEDHH
                    + 0.5 * (state.ZI - state.HSP)
                )

            if state.OSPLAT[isrc_idx]:
                state.HE3 = state.HSP + state.DHP3 - state.DHP3PLAT
            else:
                state.HE3 = state.HSP + state.DHP3
        else:
            state.DHP3 = 0.0
            state.HE3 = 0.0


def pdis(state: AermodState, xarg: float) -> None:
    """SUBROUTINE PDIS (calc1.f)."""
    # Calculate Sigma-z from formulae --- CALL SIGZ
    sigz(state, xarg)
    # Calculate Sigma-y from formulae --- CALL SIGY
    sigy(state, xarg)

    # Set all virtual source terms to 0 for non-downwashing sources
    state.VSIGY = 0.0
    state.VSYN = 0.0
    state.VSIGZ = 0.0
    state.VSZD1 = 0.0
    state.VSZD2 = 0.0
    state.VSZN1 = 0.0
    state.VSZN2 = 0.0
    state.VSZ3 = 0.0
    state.VSY3 = 0.0

    # Calculate the buoyancy-induced dispersion parameters
    if state.NOBID:
        if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
            state.SYB = 0.0
            state.SZB = 0.0
        elif state.UNSTAB:
            state.SYB = 0.0
            state.SZBD = 0.0
            state.SZBN = 0.0
            state.SYB3 = 0.0
            state.SZB3 = 0.0
    else:
        bid(state)

    # Initialize platform downwash sigmas
    state.PLATSZ = 0.0
    state.PLATSY = 0.0
    state.PLATSZD1 = 0.0
    state.PLATSYD1 = 0.0
    state.PLATSZD2 = 0.0
    state.PLATSYD2 = 0.0
    state.PLATSZN1 = 0.0
    state.PLATSYN1 = 0.0
    state.PLATSZN2 = 0.0
    state.PLATSYN2 = 0.0
    state.PLATSZP = 0.0
    state.PLATSYP = 0.0

    # Calculate the root-mean-square sigma_Y and sigma_Z --- CALL RMSSIG
    rmssig(state)


def vdis(state: AermodState, xarg: float) -> None:
    """SUBROUTINE VDIS (calc1.f)."""
    sigy(state, xarg)
    sigz(state, xarg)

    state.VSIGY = state.SYINIT
    state.VSYN = state.SYINIT
    state.VSIGZ = state.SZINIT
    state.VSZD1 = state.SZINIT
    state.VSZD2 = state.SZINIT
    state.VSZN1 = state.SZINIT
    state.VSZN2 = state.SZINIT
    state.VSZ3 = 0.0
    state.VSY3 = 0.0

    # Fortran ISRC -> state.ISRC - 1
    if str(state.AFTSRC[state.ISRC - 1]).strip() == "Y":
        bid(state)
    else:
        state.SYB = 0.0
        state.SZB = 0.0
        state.SZBD = 0.0
        state.SZBN = 0.0
        state.SYB3 = 0.0
        state.SZB3 = 0.0

    rmssig(state)


def adisz(state: AermodState, xarg: float) -> None:
    """SUBROUTINE ADISZ (calc1.f)."""
    sigz(state, xarg)

    state.VSIGZ = state.SZINIT
    state.VSZD1 = state.SZINIT
    state.VSZD2 = state.SZINIT
    state.VSZN1 = state.SZINIT
    state.VSZN2 = state.SZINIT
    state.VSZ3 = 0.0

    # Fortran ISRC -> state.ISRC - 1
    if str(state.AFTSRC[state.ISRC - 1]).strip() == "Y":
        bid(state)
    else:
        state.SZB = 0.0
        state.SZBD = 0.0
        state.SZBN = 0.0
        state.SZB3 = 0.0

    rmssig(state)


def aer_pchi(
    state: AermodState,
    xarg: float,
    adj: float,
    vdinp: float,
    jin: int,
    aerout: xp.ndarray,
) -> None:
    """SUBROUTINE AER_PCHI (calc1.f)."""
    # Calculate the contribution due to horizontal plume, CWRAP
    if state.FOPT == 0.0:
        state.CWRAP = 0.0
    else:
        state.CWRAP = cplume(state, state.ZRT)

    # Calculate the contribution due to terrain-following plume, CLIFT
    if state.ZRT == state.ZFLAG:
        state.CLIFT = state.CWRAP
    elif state.FOPT == 1.0:
        state.CLIFT = 0.0
    else:
        state.CLIFT = cplume(state, state.ZFLAG)

    # Calculate the exponential decay term, D --- CALL DECAY
    decay(state, xarg)

    state.ITYP = 0
    if state.CONC:
        state.ITYP = 1
        # Fortran ITYP = 1 -> index 0
        aerout[0] = (
            adj
            * float(state.EMIFAC[0])
            * (state.FOPT * state.CWRAP + (1.0 - state.FOPT) * state.CLIFT)
            * state.D
        )

        if state.DEBUG:
            # WRITE(DBGUNT,10) ITYP, ADJ, FOPT, CWRAP, CLIFT, D, AEROUT(ITYP)
            comp = state.debug_comp
            isrc = state.ISRC
            irec = state.IREC
            state.emit_debug(isrc, irec, comp, "AER_PCHI", "ADJ", adj)
            state.emit_debug(isrc, irec, comp, "AER_PCHI", "FOPT", state.FOPT)
            state.emit_debug(isrc, irec, comp, "AER_PCHI", "CWRAP", state.CWRAP)
            state.emit_debug(isrc, irec, comp, "AER_PCHI", "CLIFT", state.CLIFT)
            state.emit_debug(isrc, irec, comp, "AER_PCHI", "D", state.D)
            state.emit_debug(
                isrc, irec, comp, "AER_PCHI", "AEROUT", float(aerout[0])
            )

    if state.METEORDBG:
        metdeb(state)

    if state.DEBUG:
        debout(state)


def debout(state: AermodState) -> None:
    """SUBROUTINE DEBOUT (calc1.f)."""
    emifac1 = float(state.EMIFAC[0])
    chid = 0.0
    chin = 0.0
    chi3 = 0.0

    # Calculate contributions from each "plume"
    if state.STABLE or (state.UNSTAB and state.HS >= state.ZI):
        # Fortran HRVAL(1) -> state.HRVAL[0]
        chid = float(state.HRVAL[0])
    elif state.UNSTAB:
        chid = (
            (state.QTK * emifac1 * (1.0 - state.PPF) / state.UEFFD)
            * (state.FSUBYD * state.FSUBZD)
        )
        chin = (
            (state.QTK * emifac1 * (1.0 - state.PPF) / state.UEFFN)
            * (state.FSUBYN * state.FSUBZN)
        )
        if state.PPF > 0.0 and state.UEFF3 > 0.0:
            chi3 = (
                (state.QTK * emifac1 * state.PPF / state.UEFF3)
                * (state.FSUBY3 * state.FSUBZ3)
            )
        else:
            chi3 = 0.0

    isrc = state.ISRC
    irec = state.IREC
    comp = state.debug_comp

    # WRITE ( DBGUNT , 320 ) IREC, XR, YR, ZELEV, ZHILL, ZFLAG,
    # X, Y, ZELEV-ZS, HCRIT, PHEE, FOPT,
    # D, CWRAP*EMIFAC(1), CLIFT*EMIFAC(1),
    # AERVAL(1), PRMVAL(1)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "XR", state.XR)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "YR", state.YR)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "ZELEV", state.ZELEV)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "ZHILL", state.ZHILL)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "ZFLAG", state.ZFLAG)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "X", state.X)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "Y", state.Y)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "ZELEV-ZS", state.ZELEV - state.ZS)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "HCRIT", state.HCRIT)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "PHEE", state.PHEE)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "FOPT", state.FOPT)
    state.emit_debug(isrc, irec, comp, "DEBOUT", "D", state.D)
    state.emit_debug(
        isrc, irec, comp, "DEBOUT", "CWRAP*EMIFAC", state.CWRAP * emifac1
    )
    state.emit_debug(
        isrc, irec, comp, "DEBOUT", "CLIFT*EMIFAC", state.CLIFT * emifac1
    )
    state.emit_debug(isrc, irec, comp, "DEBOUT", "AERVAL", float(state.AERVAL[0]))
    state.emit_debug(isrc, irec, comp, "DEBOUT", "PRMVAL", float(state.PRMVAL[0]))

    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        # WRITE ( DBGUNT, 400 ) PPF,QTK,HE,SYAMB,VSIGY,SYB,SY,
        # FSUBY,SZAMB,VSIGZ,SZB,SZSURF,SZ,FSUBZ,CHID
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.PPF", state.PPF)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.QTK", state.QTK)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.HE", state.HE)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.SYAMB", state.SYAMB)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.VSIGY", state.VSIGY)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.SYB", state.SYB)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.SY", state.SY)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.FSUBY", state.FSUBY)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.SZAMB", state.SZAMB)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.VSIGZ", state.VSIGZ)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.SZB", state.SZB)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.SZSURF", state.SZSURF)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.SZ", state.SZ)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.FSUBZ", state.FSUBZ)
        state.emit_debug(isrc, irec, comp, "DEBOUT", "GAUSSIAN.CHID", chid)
    elif state.UNSTAB:
        qtk_dir = (1.0 - state.PPF) * state.QTK
        if qtk_dir > 0.0:
            # WRITE ( DBGUNT, 410 ) PPF,(1.0D0-PPF)*QTK,HED1,SYAMB,
            # VSIGY,SYB,SY,SZAD1,VSZD1,SZBD,SZSURF,SZD1
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT1.PPF", state.PPF)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT1.QTK*(1-PPF)", qtk_dir
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT1.HED1", state.HED1)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT1.SYAMB", state.SYAMB
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT1.VSIGY", state.VSIGY
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT1.SYB", state.SYB)
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT1.SY", state.SY)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT1.SZAD1", state.SZAD1
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT1.VSZD1", state.VSZD1
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT1.SZBD", state.SZBD)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT1.SZSURF", state.SZSURF
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT1.SZD1", state.SZD1)

            # WRITE ( DBGUNT, 420 ) (1.0D0-PPF)*QTK,HED2,SYAMB,VSIGY,
            # SYB,SY,FSUBYD,SZAD2,VSZD2,SZBD,SZSURF,SZD2,FSUBZD,CHID
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT2.QTK*(1-PPF)", qtk_dir
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT2.HED2", state.HED2)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT2.SYAMB", state.SYAMB
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT2.VSIGY", state.VSIGY
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT2.SYB", state.SYB)
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT2.SY", state.SY)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT2.FSUBYD", state.FSUBYD
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT2.SZAD2", state.SZAD2
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT2.VSZD2", state.VSZD2
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT2.SZBD", state.SZBD)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT2.SZSURF", state.SZSURF
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT2.SZD2", state.SZD2)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "DIRECT2.FSUBZD", state.FSUBZD
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "DIRECT2.CHID", chid)

            # WRITE ( DBGUNT, 430 ) PPF,(1.0D0-PPF)*QTK,HEN1,SYAMB,
            # VSIGY,SYB,SY,SZAN1,VSZN1,SZBN,SZSURF,SZN1
            state.emit_debug(isrc, irec, comp, "DEBOUT", "INDIRECT1.PPF", state.PPF)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.QTK*(1-PPF)", qtk_dir
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.HEN1", state.HEN1
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.SYAMB", state.SYAMB
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.VSIGY", state.VSIGY
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "INDIRECT1.SYB", state.SYB)
            state.emit_debug(isrc, irec, comp, "DEBOUT", "INDIRECT1.SY", state.SY)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.SZAN1", state.SZAN1
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.VSZN1", state.VSZN1
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.SZBN", state.SZBN
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.SZSURF", state.SZSURF
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT1.SZN1", state.SZN1
            )

            # WRITE ( DBGUNT, 440 ) (1.0D0-PPF)*QTK,HEN2,SYAMB,
            # VSIGY,SYB,SY,FSUBYN,SZAN2,VSZN2,SZBN,SZSURF,SZN2,FSUBZN,CHIN
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.QTK*(1-PPF)", qtk_dir
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.HEN2", state.HEN2
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.SYAMB", state.SYAMB
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.VSIGY", state.VSIGY
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "INDIRECT2.SYB", state.SYB)
            state.emit_debug(isrc, irec, comp, "DEBOUT", "INDIRECT2.SY", state.SY)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.FSUBYN", state.FSUBYN
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.SZAN2", state.SZAN2
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.VSZN2", state.VSZN2
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.SZBN", state.SZBN
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.SZSURF", state.SZSURF
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.SZN2", state.SZN2
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "INDIRECT2.FSUBZN", state.FSUBZN
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "INDIRECT2.CHIN", chin)

        qtk_pen = state.PPF * state.QTK
        if qtk_pen > 0.0:
            # WRITE ( DBGUNT, 450 ) PPF, PPF*QTK, HE3,SYA3,VSY3,
            # SYB3,SY3,FSUBY3,SZA3,VSZ3,SZB3,SZ3,FSUBZ3,CHI3
            state.emit_debug(isrc, irec, comp, "DEBOUT", "PENETRATE.PPF", state.PPF)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.PPF*QTK", qtk_pen
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "PENETRATE.HE3", state.HE3)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.SYA3", state.SYA3
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.VSY3", state.VSY3
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.SYB3", state.SYB3
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "PENETRATE.SY3", state.SY3)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.FSUBY3", state.FSUBY3
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.SZA3", state.SZA3
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.VSZ3", state.VSZ3
            )
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.SZB3", state.SZB3
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "PENETRATE.SZ3", state.SZ3)
            state.emit_debug(
                isrc, irec, comp, "DEBOUT", "PENETRATE.FSUBZ3", state.FSUBZ3
            )
            state.emit_debug(isrc, irec, comp, "DEBOUT", "PENETRATE.CHI3", chi3)


def penfct(state: AermodState) -> None:
    """SUBROUTINE PENFCT (calc1.f)."""
    if state.STABLE:
        state.PPF = 0.0
    elif state.UNSTAB and (state.HS >= state.ZI):
        state.PPF = 1.0
    else:
        bvzi2 = (state.G / state.PTATZI) * state.VPTGZI
        # Fortran ISRC -> state.ISRC - 1
        if str(state.AFTSRC[state.ISRC - 1]).strip() == "Y":
            state.PSUBS = state.FB / (
                bvzi2
                * (state.ZI - state.HSP)
                * (state.ZI - state.HSP)
                * (state.ZI - state.HSP)
            )
        else:
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


def cplume(state: AermodState, zarg: float) -> float:
    """SUBROUTINE CPLUME (calc1.f)."""
    state.ZR = zarg
    cout = 0.0

    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        if state.ZR <= state.HSBL:
            vrtsbl(state, state.SZ, max(0.0, state.HE - state.HV), state.HSBL)
        else:
            vrtsbn(state, state.SZ, max(0.0, state.HE - state.HV))

        cout = (state.QTK / state.UEFF) * (state.FSUBY * state.FSUBZ)

    elif state.UNSTAB:
        if state.PPF < 1.0:
            if state.ZR <= state.ZI:
                vrtcbl(
                    state,
                    state.HED1 - state.HV,
                    state.HED2 - state.HV,
                    state.SZD1,
                    state.SZD2,
                    1.0,
                )
                state.FSUBZD = state.FSUBZ
            else:
                state.FSUBZD = 0.0

            if state.ZR <= state.ZI:
                vrtcbl(
                    state,
                    state.HEN1 - state.HV,
                    state.HEN2 - state.HV,
                    state.SZN1,
                    state.SZN2,
                    -1.0,
                )
                state.FSUBZN = state.FSUBZ
            else:
                state.FSUBZN = 0.0
        else:
            state.FSUBZD = 0.0
            state.FSUBZN = 0.0

        if state.PPF > 0.0:
            if state.ZR <= state.HPEN:
                vrtsbl(state, state.SZ3, max(0.0, state.HE3 - state.HV), state.HPEN)
            else:
                vrtsbn(state, state.SZ3, max(0.0, state.HE3 - state.HV))
            state.FSUBZ3 = state.FSUBZ

            if state.PPF < 1.0:
                cout = (
                    (state.QTK * (1.0 - state.PPF) / state.UEFFD)
                    * (state.FSUBYD * state.FSUBZD)
                    + (state.QTK * (1.0 - state.PPF) / state.UEFFN)
                    * (state.FSUBYN * state.FSUBZN)
                    + (state.QTK * state.PPF / state.UEFF3)
                    * (state.FSUBY3 * state.FSUBZ3)
                )
            else:
                cout = (state.QTK * state.PPF / state.UEFF3) * (
                    state.FSUBY3 * state.FSUBZ3
                )
        else:
            state.FSUBZ3 = 0.0
            state.HPEN = 0.0
            cout = (state.QTK / state.UEFFD) * (state.FSUBYD * state.FSUBZD) + (
                state.QTK / state.UEFFN
            ) * (state.FSUBYN * state.FSUBZN)

    return cout


def ltopg(state: AermodState) -> int:
    """SUBROUTINE LTOPG (calc1.f)."""

    def xl(yy: float, xm: float, b: float) -> float:
        return xm / (math.log(yy) - b)

    el = state.OBULEN
    zr0 = state.SFCZ0

    z0 = zr0
    if z0 > 0.5:
        z0 = 0.5
    if z0 < 0.01:
        z0 = 0.01

    if el < 0.0:
        xel = -el
        if xel <= xl(z0, -70.0, 4.35):
            lstab = 1
        elif xel <= xl(z0, -85.2, 0.502):
            lstab = 2
        elif xel <= xl(z0, -245.0, 0.050):
            lstab = 3
        else:
            lstab = 4
    else:
        if el >= xl(z0, -327.0, 0.627):
            lstab = 4
        elif el >= xl(z0, -70.0, 0.295):
            lstab = 5
        else:
            lstab = 6

    return lstab


from .prmcalc import gamcalc, prmcalc  # noqa: E402
