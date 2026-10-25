"""PRIME numerical plume rise and wake debugging routines (prime.f, prise.f)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as xp

from .prime_base import (
    cavity_ht,
    lump,
    marching,
    numgrad,
    position,
    rate,
    sigypr,
    sigzpr,
    unlump,
    wake_dim,
    wake_drdx,
    wake_xsig,
    zmet,
    zstream,
)
from .prime_state import MXNTR, MXNW
from .prime_wake import wake_dfsn, wake_dfsn2, wake_fqc, wake_u
from .state import f_idiv, f_int

if TYPE_CHECKING:
    from .state import AermodState


def numrise(
    state: AermodState,
    ldbhr: bool,
    h: float,
    reff: float,
    texit: float,
    wexit: float,
    ntr: int,
    capped: bool,
    horiz: bool,
    capfact: float,
    xtr: xp.ndarray,
    ytr: xp.ndarray,
    ztr: xp.ndarray,
    rtr: xp.ndarray,
    dbgunt: int = 0,
) -> tuple[bool, int, int]:
    """SUBROUTINE NUMRISE (prime.f). Mutates xtr(ntr), ytr(ntr), ztr(ntr), rtr(ntr) in place; returns (linwake, numwake, ierr)."""
    p = state.prime
    xt = xp.zeros(MXNW, dtype=xp.float64)
    yt = xp.zeros(MXNW, dtype=xp.float64)
    zt = xp.zeros(MXNW, dtype=xp.float64)
    rt = xp.zeros(MXNW, dtype=xp.float64)
    rhs = xp.zeros(7, dtype=xp.float64)
    rhstemp = xp.zeros(7, dtype=xp.float64)
    f = xp.zeros(7, dtype=xp.float64)
    ftemp = xp.zeros(7, dtype=xp.float64)

    ldb = bool(ldbhr)
    ldbu = False
    ierr = 0
    nn = 0
    numwake = 0
    linwake = False
    p.x = 0.0
    p.y = 0.0
    p.z = max(h, p.zmin)
    p.s = 0.0
    p.r = reff
    p.u = 0.000002
    p.w = wexit
    p.tp = texit
    drdxa = 0.0
    ipositn = 4
    ds0 = p.ds
    zcumul = 0.0
    r15src = p.xbadj + (p.xlb + 15.0 * p.rb)
    ua0, ra, ta, dudz0, dpdz = zmet(state, p.z)
    xb = p.x - p.xbadj
    yb = p.y - p.ybadj
    zb = max(p.z, p.zmin)
    ipositn = position(state, xb, yb, zb)
    ufac = 1.0
    dufac = 0.0
    if ipositn < 4:
        ufac, dufac = wake_u(state, False, xb, yb, zb, dbgunt)
    ua = ufac * ua0
    dudz = ufac * dudz0 + dufac * ua0
    deltat = max(p.tp - ta, 0.0)
    fdum = p.w * p.r * p.r / p.tp
    fb = p.gravi * fdum * deltat
    fm = p.w * fdum * ta
    if capped:
        p.r = capfact * reff
        p.u = wexit / (capfact**2)
        p.w = 0.001
        fm = p.w * p.w * p.r * p.r * ta / p.tp
    elif horiz:
        p.u = wexit
        p.w = 0.001
        fm = p.w * p.w * p.r * p.r * ta / p.tp

    uam = max(ua, 1.0)
    wbyu = max(1.0, p.w / uam)
    xmaxm = 8.0 * p.r * wbyu * (1.0 + 3.0 / wbyu) ** 2
    if fb <= 0.0:
        xmax = xmaxm
    elif fb < 55.0:
        xmaxb = 49.0 * fb**0.625
        xmax = max(xmaxm, xmaxb)
    else:
        xmax = 119.0 * fb**0.4

    if fb <= 0.0:
        znf = 6.0 * p.r * p.w / uam
    elif fb < 55.0:
        znf = 21.425 * (fb**0.75) / uam
    else:
        znf = 38.71 * (fb**0.60) / uam

    znf0 = max(0.1, znf)
    dmin = 0.5 * znf0
    if p.ds > dmin:
        p.ds = dmin
        if ldb:
            p.emit_debug(state, "NUMRISE", "ZNF", znf)
            p.emit_debug(state, "NUMRISE", "DS0", ds0)
            p.emit_debug(state, "NUMRISE", "DS", p.ds)

    p.usc = math.sqrt(p.u * p.u + p.w * p.w)
    p.phi = math.atan(p.w / p.u)
    np_step = p.nstep
    xnp = float(np_step)
    nnp = 1
    p.den = ra * ta / texit
    lump(state, ua, ta, f)

    xbi = 0.0
    szi = 0.0
    syi = 0.0

    # Label 999: step loop
    while True:
        if nnp < 150:
            ldbnn = ldb
        else:
            ldbnn = False
        xb = p.x - p.xbadj
        yb = p.y - p.ybadj
        zb = max(p.z + zcumul, p.zmin)
        dxds = 0.0
        dzds = 0.0
        dzdx = 0.0
        dzstrm = 0.0
        ipositn = position(state, xb, yb, zb)
        if ipositn > 2 and p.x <= r15src:
            dzdx = zstream(state, p.hb, p.wb, p.xlb, p.rb, p.xlr, p.hr, xb, yb, zb)
            dxds = p.u / p.usc
            dzds = dzdx * dxds
            dzstrm = dzds * p.ds
        dyds = 0.0
        p.v = 0.0
        drdxa = rate(state, ua, dudz, ra, dpdz, ta, drdxa, rhs)
        marching(state, f, ftemp, rhs, p.ds)
        unlump(state, ua, ta, ra, ftemp)
        zb = max(p.z + zcumul + dzstrm, p.zmin)
        ua0, ra, ta, dudz0, dpdz = zmet(state, zb)
        ipositn = position(state, xb, yb, zb)
        ufac = 1.0
        dufac = 0.0
        if ipositn < 4:
            ufac, dufac = wake_u(state, ldbu, xb, yb, zb, dbgunt)
        ua = ufac * ua0
        dudz = ufac * dudz0 + dufac * ua0
        drdxa = rate(state, ua, dudz, ra, dpdz, ta, drdxa, rhstemp)
        # Fortran I=1..7 -> i in range(7)
        for i in range(7):
            rhs[i] = 0.5 * (rhstemp[i] - rhs[i])
        marching(state, ftemp, f, rhs, p.ds)
        unlump(state, ua, ta, ra, f)
        zcumul = zcumul + dzstrm
        zc = max(p.z + zcumul, p.zmin)
        xb = p.x - p.xbadj
        yb = p.y - p.ybadj
        zb = zc
        ipositn = position(state, xb, yb, zb)
        if p.x < 0.0:
            p.x = 0.0
            p.s = p.s + p.ds
            nnp = nnp - 1
            # goto 96
        else:
            if ldbnn:
                deltaz = zc - h
                p.emit_debug(state, "NUMRISE", "X", p.x)
                p.emit_debug(state, "NUMRISE", "Y", p.y)
                p.emit_debug(state, "NUMRISE", "ZC", zc)
                p.emit_debug(state, "NUMRISE", "R", p.r)
                p.emit_debug(state, "NUMRISE", "U", p.u)
                p.emit_debug(state, "NUMRISE", "V", p.v)
                p.emit_debug(state, "NUMRISE", "W", p.w)
                p.emit_debug(state, "NUMRISE", "USC", p.usc)
                p.emit_debug(state, "NUMRISE", "PHI", p.phi)
                p.emit_debug(state, "NUMRISE", "DEN", p.den)
                p.emit_debug(state, "NUMRISE", "TP", p.tp)
                p.emit_debug(state, "NUMRISE", "UA", ua)
                p.emit_debug(state, "NUMRISE", "RA", ra)
                p.emit_debug(state, "NUMRISE", "TA", ta)
                p.emit_debug(state, "NUMRISE", "DUDZ", dudz)
                p.emit_debug(state, "NUMRISE", "DPDZ", dpdz)
                p.emit_debug(state, "NUMRISE", "DZDS", dzds)
                p.emit_debug(state, "NUMRISE", "DYDS", dyds)
                p.emit_debug(state, "NUMRISE", "IPOSITN", ipositn)
                p.emit_debug(state, "NUMRISE", "DELTAZ", deltaz)

            if p.phi <= 0.349065850398866 and ipositn < 4:
                if not linwake:
                    linwake = True
                    xbi = xb
                    base = max(h, p.zmin)
                    rise = max(0.0, p.z - base)
                    bidsq = (rise / 3.5) ** 2
                    if p.x <= 0.0:
                        szi = math.sqrt(bidsq)
                        syi = szi
                    else:
                        szi = sigzpr(state, p.x, p.z)
                        szi = math.sqrt(szi**2 + bidsq)
                        syi = sigypr(state, p.x, p.z)
                        syi = math.sqrt(syi**2 + bidsq)
                    if ldbhr:
                        p.emit_debug(state, "NUMRISE", "X", p.x)
                        p.emit_debug(state, "NUMRISE", "Y", p.y)
                        p.emit_debug(state, "NUMRISE", "Z", p.z)
                        p.emit_debug(state, "NUMRISE", "Z+ZCUM", zc)
                        p.emit_debug(state, "NUMRISE", "DS", p.ds)
                        p.emit_debug(state, "NUMRISE", "U", p.u)
                        p.emit_debug(state, "NUMRISE", "W", p.w)
                        p.emit_debug(state, "NUMRISE", "XB", xb)
                        p.emit_debug(state, "NUMRISE", "PHI", p.phi)
                        p.emit_debug(state, "NUMRISE", "SZI", szi)
                        p.emit_debug(state, "NUMRISE", "SYI", syi)
                    wake_dfsn(state, ldb, xbi, szi, syi, p.z, dbgunt)
                    numwake = p.nwak
                drdxa = wake_drdx(state, p.x)

            p.s = p.s + p.ds
            if float(f_idiv(nnp, np_step)) == float(nnp) / xnp:
                nn = f_idiv(nnp, np_step)
                if nn > MXNW:
                    ierr = 1
                    return linwake, numwake, ierr
                # Fortran NN=1..MXNW -> nn - 1
                xt[nn - 1] = p.x
                yt[nn - 1] = p.y
                zt[nn - 1] = zc
                rt[nn - 1] = p.r
                if p.x >= xmax:
                    zfin = zc
                    yfin = p.y
                    xfin = p.x
                    rfin = p.r
                    break

        # Label 96
        ua0, ra, ta, dudz0, dpdz = zmet(state, zb)
        ufac = 1.0
        dufac = 0.0
        if ipositn < 4:
            ufac, dufac = wake_u(state, False, xb, yb, zb, dbgunt)
        ua = ufac * ua0
        dudz = ufac * dudz0 + dufac * ua0
        nnp = nnp + 1
        if p.w < 0.0:
            zfin = zc
            yfin = p.y
            xfin = p.x
            rfin = p.r
            break
        if p.ds < ds0:
            p.ds = min(ds0, 2.0 * p.ds)
        if p.s < p.slast:
            continue
        zfin = zc
        yfin = p.y
        xfin = p.x
        rfin = p.r
        break

    # Label 97
    xfin0 = xfin
    x15r = r15src - xfin0
    if x15r > 0.0:
        dsfin = float(p.nstep) * p.ds
        dx15r = x15r / float(MXNW - nn)
        dx15r = max(dsfin, dx15r)
        n15r = min(f_int(x15r / dx15r), MXNW - nn)
        nbeg = nn + 1
        nend = nn + n15r
        # Fortran IN=NBEG..NEND (1-based) -> in_ in range(nbeg, nend + 1)
        for in_ in range(nbeg, nend + 1):
            xbb = float(xt[in_ - 2]) - p.xbadj
            xbe = xbb + dx15r
            yb = float(yt[in_ - 2]) - p.ybadj
            zb = float(zt[in_ - 2])
            dzdx = 0.0
            ipos = position(state, xbb, yb, zb)
            if ipos > 2:
                dzdxb = zstream(state, p.hb, p.wb, p.xlb, p.rb, p.xlr, p.hr, xbb, yb, zb)
                dzdxe = zstream(state, p.hb, p.wb, p.xlb, p.rb, p.xlr, p.hr, xbe, yb, zb)
                dzdx = 0.5 * (dzdxb + dzdxe)
            xt[in_ - 1] = float(xt[in_ - 2]) + dx15r
            yt[in_ - 1] = yfin
            zt[in_ - 1] = max(p.zmin, float(zt[in_ - 2]) + dzdx * dx15r)
            rt[in_ - 1] = rfin
            zcumul = zcumul + dzdx * dx15r
            if not linwake:
                if ipos < 4:
                    linwake = True
                    p.x = float(xt[in_ - 1])
                    p.z = float(zt[in_ - 1]) - zcumul
                    xbi = p.x - p.xbadj
                    base = max(h, p.zmin)
                    rise = max(0.0, p.z - base)
                    bidsq = (rise / 3.5) ** 2
                    szi = sigzpr(state, p.x, p.z)
                    szi = math.sqrt(szi**2 + bidsq)
                    syi = sigypr(state, p.x, p.z)
                    syi = math.sqrt(syi**2 + bidsq)
                    if ldbhr:
                        p.emit_debug(state, "NUMRISE", "X", p.x)
                        p.emit_debug(state, "NUMRISE", "Y", yfin)
                        p.emit_debug(state, "NUMRISE", "Z", p.z)
                        p.emit_debug(state, "NUMRISE", "Z+ZCUM", float(zt[in_ - 1]))
                        p.emit_debug(state, "NUMRISE", "XB", xbi)
                        p.emit_debug(state, "NUMRISE", "PHI", p.phi)
                        p.emit_debug(state, "NUMRISE", "SZI", szi)
                        p.emit_debug(state, "NUMRISE", "SYI", syi)
                    wake_dfsn(state, ldb, xbi, szi, syi, p.z, dbgunt)
                    numwake = p.nwak
                drdxa = wake_drdx(state, p.x)
        nn = nend
        xfin = float(xt[nn - 1])
        zfin = float(zt[nn - 1])

    if nn > ntr:
        # Fortran NTR -> ntr - 1
        xtr[ntr - 1] = xfin
        ytr[ntr - 1] = yfin
        ztr[ntr - 1] = zfin
        rtr[ntr - 1] = rfin
        if nn <= 2 * ntr:
            deln = float(nn) / float(ntr)
            # Fortran IN=1..NTR-1 -> in_ in range(1, ntr)
            for in_ in range(1, ntr):
                jn = f_int(float(in_) * deln)
                xtr[in_ - 1] = xt[jn - 1]
                ytr[in_ - 1] = yt[jn - 1]
                ztr[in_ - 1] = zt[jn - 1]
                rtr[in_ - 1] = rt[jn - 1]
        else:
            deln = 2.0 * float(nn - ntr) / float(ntr * (ntr - 1))
            rn = 0.0
            # Fortran IN=1..NTR-1 -> in_ in range(1, ntr)
            for in_ in range(1, ntr):
                rn = rn + 1.0 + float(in_ - 1) * deln
                jn = f_int(rn)
                xtr[in_ - 1] = xt[jn - 1]
                ytr[in_ - 1] = yt[jn - 1]
                ztr[in_ - 1] = zt[jn - 1]
                rtr[in_ - 1] = rt[jn - 1]
    else:
        # Fortran IN=1..NN -> in_ in range(1, nn + 1)
        for in_ in range(1, nn + 1):
            xtr[in_ - 1] = xt[in_ - 1]
            ytr[in_ - 1] = yt[in_ - 1]
            ztr[in_ - 1] = zt[in_ - 1]
            rtr[in_ - 1] = rt[in_ - 1]
        # Fortran IT=NN+1..NTR -> it in range(nn + 1, ntr + 1)
        for it in range(nn + 1, ntr + 1):
            xtr[it - 1] = xfin
            ytr[it - 1] = yfin
            ztr[it - 1] = zfin
            rtr[it - 1] = rfin

    p.ds = ds0
    if linwake:
        if xbi < (p.xlb + p.xlr):
            wake_fqc(state, ldb, xbi, xtr, ztr, MXNTR, dbgunt)
        else:
            p.fqcav = 0.0
    else:
        p.fqcav = 0.0

    if ldbhr:
        delzfin = zfin - h
        p.emit_debug(state, "NUMRISE", "TEXIT", texit)
        p.emit_debug(state, "NUMRISE", "FB", fb)
        p.emit_debug(state, "NUMRISE", "FM", fm)
        p.emit_debug(state, "NUMRISE", "XMAX", xmax)
        p.emit_debug(state, "NUMRISE", "XFIN0", xfin0)
        p.emit_debug(state, "NUMRISE", "X15R", x15r)
        p.emit_debug(state, "NUMRISE", "XFIN", xfin)
        p.emit_debug(state, "NUMRISE", "YFIN", yfin)
        p.emit_debug(state, "NUMRISE", "ZFIN", zfin)
        p.emit_debug(state, "NUMRISE", "DELZFIN", delzfin)
        p.emit_debug(state, "NUMRISE", "RFIN", rfin)
        p.emit_debug(state, "NUMRISE", "ZCUMUL", zcumul)
        p.emit_debug(state, "NUMRISE", "FQCAV", p.fqcav)

    if ldb:
        # Fortran I=1..NTR -> i in range(ntr)
        for i in range(ntr):
            p.emit_debug(state, "NUMRISE", "XTR", float(xtr[i]))
            p.emit_debug(state, "NUMRISE", "YTR", float(ytr[i]))
            p.emit_debug(state, "NUMRISE", "ZTR", float(ztr[i]))
            p.emit_debug(state, "NUMRISE", "RTR", float(rtr[i]))

    if state.L_AWMA_UTURB or state.L_AWMA_UTURBHX:
        p.xtr_sav[:ntr] = xtr[:ntr]
        p.ztr_sav[:ntr] = ztr[:ntr]

    if linwake:
        p.dfsn2call = True
        wake_dfsn2(state, ldb, xbi, szi, syi, xtr, ztr, ntr, dbgunt)

    if ldb:
        # Fortran I=1..NTR -> i in range(ntr)
        for i in range(ntr):
            p.emit_debug(state, "NUMRISE", "XTR", float(xtr[i]))
            p.emit_debug(state, "NUMRISE", "YTR", float(ytr[i]))
            p.emit_debug(state, "NUMRISE", "ZTR", float(ztr[i]))
            p.emit_debug(state, "NUMRISE", "RTR", float(rtr[i]))

    return linwake, numwake, ierr


def wake_dbg(
    state: AermodState,
    io: int,
    ntr: int,
    xtr: xp.ndarray,
    ytr: xp.ndarray,
    ztr: xp.ndarray,
    rtr: xp.ndarray,
    nobid: bool,
    hstack: float,
) -> None:
    """SUBROUTINE WAKE_DBG (prime.f)."""
    p = state.prime
    rt2bypi = 0.797884560802866
    ldb = False
    dbduw = 0.0

    # Fortran XCAV(1), YTR(1), SZCAV(1), SYCAV(1) -> index 0
    if float(p.xcav[0]) < 0.0:
        dbx = float(p.xcav[0])
        dby = float(ytr[0])
        dbz = 0.0
        dbsz = 0.0
        dbsy = 0.0
        dbhw = 0.0
        dbhc = 0.0
        dbrsz = 0.0
        dbuw = 1.0
        ipositn = 4
        rise = 0.0
        xb = dbx - p.xbadj
        yb = dby - p.ybadj
        zb = dbz
        dbxb = xb
        dbsz = 0.0
        dbsy = 0.0
        dbszc = float(p.szcav[0])
        dbsyc = float(p.sycav[0])
        dbdrdx = 0.0
        if xb >= 0.0:
            dbhw, dbww = wake_dim(state, xb, p.hb, p.wb, p.rb)
            dbhc, dbwc = cavity_ht(state, p.hb, p.wb, p.xlb, p.rb, p.xlc, p.xlr, p.hr, xb)
            ipositn = position(state, xb, yb, zb)
            dbuw = 1.0
            if ipositn < 4:
                dbuw, dbduw = wake_u(state, ldb, xb, yb, zb, io)
            else:
                dbduw = 0.0
        p.emit_debug(state, "WAKE_DBG", "DBXB", dbxb)
        p.emit_debug(state, "WAKE_DBG", "DBX", dbx)
        p.emit_debug(state, "WAKE_DBG", "DBZ", dbz)
        p.emit_debug(state, "WAKE_DBG", "DBHW", dbhw)
        p.emit_debug(state, "WAKE_DBG", "DBHC", dbhc)
        p.emit_debug(state, "WAKE_DBG", "DBSZ", dbsz)
        p.emit_debug(state, "WAKE_DBG", "DBSY", dbsy)
        p.emit_debug(state, "WAKE_DBG", "DBUW", dbuw)
        p.emit_debug(state, "WAKE_DBG", "DBDUW", dbduw)
        p.emit_debug(state, "WAKE_DBG", "DBRSZ", dbrsz)
        p.emit_debug(state, "WAKE_DBG", "DBDRDX", dbdrdx)
        p.emit_debug(state, "WAKE_DBG", "IPOSITN", ipositn)
        p.emit_debug(state, "WAKE_DBG", "DBSZC", dbszc)

    dbx = 0.0
    dby = float(ytr[0])
    dbz = hstack
    dbsz = 0.0
    dbsy = 0.0
    dbhw = 0.0
    dbhc = 0.0
    dbrsz = 0.0
    dbuw = 1.0
    ipositn = 4
    rise = dbz - hstack
    xb = dbx - p.xbadj
    yb = dby - p.ybadj
    zb = dbz
    dbxb = xb
    xzero = 0.001
    dbsz, dbsy, dbszc, dbsyc = wake_xsig(state, xzero, hstack, rise, nobid)
    dbdrdx = wake_drdx(state, dbx)
    if xb >= 0.0:
        dbhw, dbww = wake_dim(state, xb, p.hb, p.wb, p.rb)
        dbhc, dbwc = cavity_ht(state, p.hb, p.wb, p.xlb, p.rb, p.xlc, p.xlr, p.hr, xb)
        ipositn = position(state, xb, yb, zb)
        dbuw = 1.0
        if ipositn < 4:
            dbuw, dbduw = wake_u(state, ldb, xb, yb, zb, io)
        else:
            dbduw = 0.0
    else:
        dbduw = 0.0
    p.emit_debug(state, "WAKE_DBG", "DBXB", dbxb)
    p.emit_debug(state, "WAKE_DBG", "DBX", dbx)
    p.emit_debug(state, "WAKE_DBG", "DBZ", dbz)
    p.emit_debug(state, "WAKE_DBG", "DBHW", dbhw)
    p.emit_debug(state, "WAKE_DBG", "DBHC", dbhc)
    p.emit_debug(state, "WAKE_DBG", "DBSZ", dbsz)
    p.emit_debug(state, "WAKE_DBG", "DBSY", dbsy)
    p.emit_debug(state, "WAKE_DBG", "DBUW", dbuw)
    p.emit_debug(state, "WAKE_DBG", "DBDUW", dbduw)
    p.emit_debug(state, "WAKE_DBG", "DBRSZ", dbrsz)
    p.emit_debug(state, "WAKE_DBG", "DBDRDX", dbdrdx)
    p.emit_debug(state, "WAKE_DBG", "IPOSITN", ipositn)
    p.emit_debug(state, "WAKE_DBG", "DBSZC", dbszc)

    # Fortran IT=1..NTR -> it in range(ntr)
    for it in range(ntr):
        dbx = float(xtr[it])
        dby = float(ytr[it])
        dbz = float(ztr[it])
        dbrsz = float(rtr[it]) * rt2bypi
        dbhw = 0.0
        dbhc = 0.0
        dbuw = 1.0
        ipositn = 4
        rise = dbz - hstack
        xb = dbx - p.xbadj
        yb = dby - p.ybadj
        zb = dbz
        dbxb = xb
        dbsz, dbsy, dbszc, dbsyc = wake_xsig(state, dbx, hstack, rise, nobid)
        dbdrdx = wake_drdx(state, dbx)
        if xb >= 0.0:
            dbhw, dbww = wake_dim(state, xb, p.hb, p.wb, p.rb)
            dbhc, dbwc = cavity_ht(state, p.hb, p.wb, p.xlb, p.rb, p.xlc, p.xlr, p.hr, xb)
            ipositn = position(state, xb, yb, zb)
            dbuw = 1.0
            if ipositn < 4:
                dbuw, dbduw = wake_u(state, ldb, xb, yb, zb, io)
            else:
                dbduw = 0.0
        else:
            dbduw = 0.0
        p.emit_debug(state, "WAKE_DBG", "DBXB", dbxb)
        p.emit_debug(state, "WAKE_DBG", "DBX", dbx)
        p.emit_debug(state, "WAKE_DBG", "DBZ", dbz)
        p.emit_debug(state, "WAKE_DBG", "DBHW", dbhw)
        p.emit_debug(state, "WAKE_DBG", "DBHC", dbhc)
        p.emit_debug(state, "WAKE_DBG", "DBSZ", dbsz)
        p.emit_debug(state, "WAKE_DBG", "DBSY", dbsy)
        p.emit_debug(state, "WAKE_DBG", "DBUW", dbuw)
        p.emit_debug(state, "WAKE_DBG", "DBDUW", dbduw)
        p.emit_debug(state, "WAKE_DBG", "DBRSZ", dbrsz)
        p.emit_debug(state, "WAKE_DBG", "DBDRDX", dbdrdx)
        p.emit_debug(state, "WAKE_DBG", "IPOSITN", ipositn)
        p.emit_debug(state, "WAKE_DBG", "DBSZC", dbszc)


def prmdelh(state: AermodState, xarg: float, l_inwake: bool = False) -> bool:
    """SUBROUTINE PRMDELH (prise.f). Returns l_inwake."""
    p = state.prime
    p.prmdelh_capped = False
    p.prmdelh_horiz = False
    if state.WAKE:
        if state.PRM_FSTREC:
            state.PRM_FSTREC = False
            l_inwake = False
            p.dfsn2call = False
            p.prmdelh_hseff = state.HS
            p.prmdelh_reff = 0.5 * state.DS
            # Fortran ISRC=1..NUMSRC -> state.ISRC - 1
            srctyp_isrc = state.SRCTYP[state.ISRC - 1]
            if srctyp_isrc == "POINTCAP":
                p.prmdelh_capped = True
            else:
                p.prmdelh_capped = False
            if srctyp_isrc == "POINTHOR":
                p.prmdelh_horiz = True
            else:
                p.prmdelh_horiz = False
            dsfact = (
                state.DSFACT
                if hasattr(state, "DSFACT")
                else float(state.ADSFACT[state.ISRC - 1])
            )
            l_inwake, numwake, ierr = numrise(
                state,
                state.PRIMEDBG,
                p.prmdelh_hseff,
                p.prmdelh_reff,
                state.TS,
                state.VS,
                MXNTR,
                p.prmdelh_capped,
                p.prmdelh_horiz,
                dsfact,
                p.prmdelh_xtr,
                p.prmdelh_ytr,
                p.prmdelh_ztr,
                p.prmdelh_rtr,
                state.PRMDBUNT,
            )
            if ierr == 1:
                state.RUNERR = True
                raise RuntimeError(
                    f"PRMDELH: NUMRISE error 499 for source {state.SRCID[state.ISRC - 1]}"
                )
            if numwake <= 1:
                l_inwake = False
            # Fortran ZTR(MXNTR) -> index MXNTR - 1
            state.DHF = float(p.prmdelh_ztr[MXNTR - 1]) - p.prmdelh_hseff
            if state.PRIMEDBG:
                wake_dbg(
                    state,
                    state.PRMDBUNT,
                    MXNTR,
                    p.prmdelh_xtr,
                    p.prmdelh_ytr,
                    p.prmdelh_ztr,
                    p.prmdelh_rtr,
                    state.NOBID,
                    p.prmdelh_hseff,
                )
            p.prmdelh_l_inwake_save = l_inwake
        else:
            l_inwake = p.prmdelh_l_inwake_save

        # Fortran XTR(MXNTR), ZTR(MXNTR) -> index MXNTR - 1
        if xarg < float(p.prmdelh_xtr[MXNTR - 1]):
            zeff = numgrad(state, xarg, p.prmdelh_xtr, p.prmdelh_ztr, MXNTR)
            state.ZEFF = zeff
            state.DHP = zeff - p.prmdelh_hseff
        else:
            state.DHP = float(p.prmdelh_ztr[MXNTR - 1]) - p.prmdelh_hseff

    return l_inwake
