"""PRIME wake turbulence, velocity deficit, dispersion, and cavity subroutines (prime.f)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as xp

from .iblval import anyavg, locate
from .prime_base import (
    cavity_ht,
    frgauss,
    numgrad,
    position,
    sigypr,
    sigzpr,
    wake_cav0,
    wake_dim,
    wake_xa,
    wake_xsig,
)
from .prime_state import MXNTR, MXNW, P2MXNTR
from .state import f_int, f_nint

if TYPE_CHECKING:
    from .state import AermodState


def wake_u_turb(
    state: AermodState,
    scope: str,
    xinp: float,
    znew: float,
    ambiz: float,
    ambiy: float,
) -> tuple[float, float, float]:
    """SUBROUTINE WAKE_U_TURB (prime.f). Returns (du_ua, tiz, tiy)."""
    p = state.prime
    du_ua = 0.0
    tiz = 0.0
    tiy = 0.0

    vufac = 0.0
    svfac = 0.0
    swfac = 0.0
    au = 0.0
    asv = 0.0
    asw = 0.0
    nu = 0.0
    nsv = 0.0
    nsw = 0.0
    bu = 0.0
    bsv = 0.0
    bsw = 0.0
    ru = 0.0
    rsv = 0.0
    rsw = 0.0
    lrudfac = 0.0
    lrsvfac = 0.0
    lrswfac = 0.0
    hwminu = 0.0
    hwminsv = 0.0
    hwminsw = 0.0
    hlminu = 0.0
    hlminsv = 0.0
    hlminsw = 0.0
    hwmaxu = 0.0
    hwmaxsv = 0.0
    hwmaxsw = 0.0
    hlmaxu = 0.0
    hlmaxsv = 0.0
    hlmaxsw = 0.0

    if state.L_RECT_BLDG:
        vufac = 0.294
        svfac = 0.320
        swfac = 0.290
        au = 0.500
        asv = 0.700
        asw = 0.650
        nu = 0.000
        nsv = 0.356
        nsw = 0.336
        bu = 3.494
        ru = 1.667
        lrudfac = 1.135
        lrsvfac = 1.349
        lrswfac = 1.794
        hwminu = 0.449
        hwminsv = 0.200
        hwminsw = 0.375
        hlminu = 0.753
        hlminsv = 0.321
        hlminsw = 0.308
        hwmaxu = 3.00
        hwmaxsv = 3.00
        hwmaxsw = 3.00
        hlmaxu = 3.00
        hlmaxsv = 3.00
        hlmaxsw = 3.00
    elif state.L_STRMLN_BLDG:
        vufac = 0.294
        svfac = 0.225
        swfac = 0.225
        au = 0.400
        asv = 0.550
        asw = 0.450
        nu = 0.631
        nsv = 0.477
        nsw = 0.570
        bu = 2.113
        ru = 1.796
        lrudfac = 0.563
        lrsvfac = 0.971
        lrswfac = 0.640
        hwminu = 0.449
        hwminsv = 0.375
        hwminsw = 0.375
        hlminu = 0.753
        hlminsv = 0.308
        hlminsw = 0.308
        hwmaxu = 3.00
        hwmaxsv = 3.00
        hwmaxsw = 3.00
        hlmaxu = 3.00
        hlmaxsv = 3.00
        hlmaxsw = 3.00

    if state.L_RECT_BLDG:
        absv = 0.018571
        bbsv = -1.10574
        cbsv = 18.30949
        absw = 0.045142
        bbsw = -2.1585
        cbsw = 29.33697
        arsv = -0.00124
        brsv = 0.033975
        crsv = 1.431187
        arsw = 0.000155
        brsw = -0.00626
        crsw = 1.562781
        iy0 = p.sv30 / p.u30 * 100.0
        if iy0 > 29.2:
            iy0 = 29.2
        if iy0 < 5.0:
            iy0 = 5.0
        iz0 = p.sw30 / p.u30 * 100.0
        if iz0 > 18.6:
            iz0 = 18.6
        if iz0 < 2.0:
            iz0 = 2.0
        bsv = absv * iy0 ** 2 + bbsv * iy0 + cbsv
        bsw = absw * iz0 ** 2 + bbsw * iz0 + cbsw
        rsv = arsv * iy0 ** 2 + brsv * iy0 + crsv
        rsw = arsw * iz0 ** 2 + brsw * iz0 + crsw
    elif state.L_STRMLN_BLDG:
        absv = 0.008223
        bbsv = -0.42265
        cbsv = 9.330299
        absw = 0.092864
        bbsw = -3.68931
        cbsw = 39.21321
        arsv = 0.000861
        brsv = 0.004194
        crsv = 1.385942
        arsw = 0.004627
        brsw = -0.15270
        crsw = 2.939305
        iy0 = p.sv30 / p.u30 * 100.0
        iz0 = p.sw30 / p.u30 * 100.0
        bsv = absv * iy0 ** 2 + bbsv * iy0 + cbsv
        bsw = absw * iz0 ** 2 + bbsw * iz0 + cbsw
        rsv = arsv * iy0 ** 2 + brsv * iy0 + crsv
        rsw = arsw * iz0 ** 2 + brsw * iz0 + crsw

    z = p.wake_u_turb_z
    zvel_sav = p.wake_u_turb_zvel_sav
    if scope == "vel":
        z = znew
        zvel_sav = znew
        p.wake_u_turb_z = z
        p.wake_u_turb_zvel_sav = zvel_sav
    elif scope == "turb":
        z = min(zvel_sav, p.zeff_prm2)
        if state.L_AWMA_UTurbHX and p.dfsn2call:
            # Fortran xtr_sav(p2mxntr), ztr_sav(p2mxntr) -> index P2MXNTR - 1
            if xinp < p.xtr_sav[P2MXNTR - 1]:
                zplm = numgrad(state, xinp, p.xtr_sav, p.ztr_sav, P2MXNTR)
                z = zplm
            else:
                zplm = float(p.ztr_sav[P2MXNTR - 1])
                z = zplm
        p.wake_u_turb_z = z
    else:
        raise RuntimeError(
            'Improper u/turb scope in wake_u_turb - must be "vel" or "turb" (lower case)'
        )

    xml = max(0.0, xinp - p.xlb)
    eps = xml + p.hb
    hwlimu = p.hb / p.wb
    if hwlimu < hwminu:
        hwlimu = hwminu
    if hwlimu > hwmaxu:
        hwlimu = hwmaxu
    hllimu = p.hb / p.xlb
    if hllimu < hlminu:
        hllimu = hlminu
    if hllimu > hlmaxu:
        hllimu = hlmaxu
    a1 = 1.0 / hwlimu
    a2 = (1.0 / hllimu ** 0.3) * (1.0 + 0.24 / hwlimu)
    xlrud = 1.8 * a1 / a2
    xiud_hb = max((lrudfac * xlrud + 1), eps / p.hb)
    a1 = xiud_hb * hwlimu ** (2.0 / 3.0)
    a2 = hllimu ** (-nu)
    udmax = bu * (a1 * a2) ** (-ru)
    zudmax_hb = au * (p.hr / p.hb) ** 1.5
    if z / p.hb >= zudmax_hb:
        a1 = (zudmax_hb - z / p.hb) ** 2
        a2 = (vufac ** 2) * xiud_hb
        du_ua = udmax * math.exp(-a1 / a2)
    else:
        du_ua = udmax
    if scope == "vel":
        return du_ua, tiz, tiy

    hwlimsw = p.hb / p.wb
    if hwlimsw < hwminsw:
        hwlimsw = hwminsw
    if hwlimsw > hwmaxsw:
        hwlimsw = hwmaxsw
    hllimsw = p.hb / p.xlb
    if hllimsw < hlminsw:
        hllimsw = hlminsw
    if hllimsw > hlmaxsw:
        hllimsw = hlmaxsw
    hwlimsv = p.hb / p.wb
    if hwlimsv < hwminsv:
        hwlimsv = hwminsv
    if hwlimsv > hwmaxsv:
        hwlimsv = hwmaxsv
    hllimsv = p.hb / p.xlb
    if hllimsv < hlminsw:
        hllimsv = hlminsw
    if hllimsv > hlmaxsw:
        hllimsv = hlmaxsw
    a1 = 1.0 / hwlimsw
    a2 = (1.0 / hllimsw ** 0.3) * (1.0 + 0.24 / hwlimsw)
    xlrsw = 1.8 * a1 / a2
    a1 = 1.0 / hwlimsv
    a2 = (1.0 / hllimsv ** 0.3) * (1.0 + 0.24 / hwlimsv)
    xlrsv = 1.8 * a1 / a2
    xisw_hb = max((lrswfac * xlrsw + 1), eps / p.hb)
    xisv_hb = max((lrsvfac * xlrsv + 1), eps / p.hb)
    a1 = xisw_hb * hwlimsw ** (2.0 / 3.0)
    a2 = hllimsw ** (-nsw)
    swmaxx = bsw * (a1 * a2) ** (-rsw)
    a1 = xisv_hb * hwlimsv ** (2.0 / 3.0)
    a2 = hllimsv ** (-nsv)
    svmaxx = bsv * (a1 * a2) ** (-rsv)
    zsw_hb = asw * (p.hr / p.hb) ** 1.5
    zsv_hb = asv * (p.hr / p.hb) ** 1.5
    a1 = (zsw_hb - z / p.hb) ** 2
    a2 = (swfac ** 2) * xisw_hb
    if z / p.hb >= zsw_hb:
        sw = swmaxx * math.exp(-a1 / a2)
    else:
        sw = swmaxx
    a1 = (zsv_hb - z / p.hb) ** 2
    a2 = (svfac ** 2) * xisv_hb
    if z / p.hb >= zsv_hb:
        sv = svmaxx * math.exp(-a1 / a2)
    else:
        sv = svmaxx
    du_ua = min(du_ua, 0.9)
    a1 = (1.0 + sw) / (1.0 - du_ua)
    tiz = ambiz * min(18.0, a1)
    tiz = min(0.9, tiz)
    a1 = (1.0 + sv) / (1.0 - du_ua)
    tiy = ambiy * min(6.0, a1)
    tiy = min(0.9, tiy)
    return du_ua, tiz, tiy


def wake_turb(
    state: AermodState,
    xinp: float,
    l: float,
    rinp: float,
) -> tuple[float, float]:
    """SUBROUTINE WAKE_TURB (prime.f). Returns (tiz, tiy)."""
    one = 1.0
    zero = 0.0
    p = state.prime
    ambiz = state.SWEFF / state.UEFF
    ambiy = state.SVEFF / state.UEFF
    fariz = min(p.wiz0, ambiz)
    fariy = min(p.wiy0, ambiy)
    if state.L_AWMA_UTurbHX and p.dfsn2call:
        # Fortran xtr_sav(p2mxntr), ztr_sav(p2mxntr) -> index P2MXNTR - 1
        if xinp < p.xtr_sav[P2MXNTR - 1]:
            p.zeff_prm2 = numgrad(state, xinp, p.xtr_sav, p.ztr_sav, P2MXNTR)
        else:
            p.zeff_prm2 = float(p.ztr_sav[P2MXNTR - 1])
        zhi = p.zeff_prm2 + 5.0
        zlo = p.zeff_prm2 - 5.0
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
        ambiz = state.SWEFF / state.UEFF
        ambiy = state.SVEFF / state.UEFF
    if state.L_AWMA_UTurb or state.L_AWMA_UTurbHX:
        zdum = -1.0
        _dum, tiz, tiy = wake_u_turb(state, "turb", xinp, zdum, ambiz, ambiy)
    else:
        xml = max(zero, xinp - l)
        xfac = one / (((xml + rinp) / rinp) ** p.xdecay - p.dua_ua)
        tiz = fariz * (one + ((p.wfz * p.wiz0 / fariz - one) + p.dua_ua) * xfac)
        tiy = fariy * (one + ((p.wfy * p.wiy0 / fariy - one) + p.dua_ua) * xfac)
    if xinp < l:
        xfrac = xinp / l
        tiz = ambiz + xfrac * (tiz - ambiz)
        tiy = ambiy + xfrac * (tiy - ambiy)
    if state.L_AWMA_UTurbHX:
        state.UEFF = p.ueff_save
        state.SWEFF = p.sweff_save
        state.SVEFF = p.sveff_save
    return tiz, tiy


def wake_u(
    state: AermodState,
    ldb: bool,
    x: float,
    y: float,
    z: float,
    dbgunt: int = 0,
) -> tuple[float, float]:
    """SUBROUTINE WAKE_U (prime.f). Returns (ubyua, dufac)."""
    zero = 0.0
    one = 1.0
    two = 2.0
    fmin = 0.01
    p = state.prime
    zcav, _ycav = cavity_ht(state, p.hb, p.wb, p.xlb, p.rb, p.xlc, p.xlr, p.hr, x)
    hwake, wwake = wake_dim(state, x, p.hb, p.wb, p.rb)
    yabs = abs(y)
    ubyua = one
    dufac = zero
    if z >= hwake or yabs >= wwake:
        return ubyua, dufac
    if state.L_AWMA_UTurb or state.L_AWMA_UTurbHX:
        dum = 0.0
        du_ua, _dum1, _dum2 = wake_u_turb(state, "vel", x, z, dum, dum)
        ymin = max(0.5 * p.wb, wwake - p.rb / 3.0)
        ydiff = wwake - ymin
        if yabs > ymin and ydiff > zero:
            du_ua = du_ua * (one - (yabs - ymin) / ydiff)
    else:
        ymin = max(0.5 * p.wb, wwake - p.rb / 3.0)
        du_ua = p.dua_ua
        ydiff = wwake - ymin
        if yabs > ymin and ydiff > zero:
            du_ua = p.dua_ua * (one - (yabs - ymin) / ydiff)
        xml = max(zero, x - p.xlb)
        du_ua = du_ua * ((xml + p.rb) / p.rb) ** (-p.xdecay)
    if x < p.xlb:
        xfrac = x / p.xlb
        du_ua = xfrac * du_ua
    ucbyua = max(zero, (one - two * hwake * du_ua / (hwake + zcav)))
    dufac = zero
    if z > zcav:
        dufac = (one - ucbyua) / (hwake - zcav)
    zz = min(z, hwake)
    ubyua = max(fmin, (ucbyua + dufac * (zz - zcav)))
    return ubyua, dufac


def wake_sig(
    state: AermodState,
    x: float,
    xd: float,
    xold: float,
    turbz: float,
    turby: float,
    szold: float,
    syold: float,
    h: float,
    w: float,
    r: float,
    zk: float,
    yk: float,
) -> tuple[float, float, float, float, float]:
    """SUBROUTINE WAKE_SIG (prime.f). Returns (zk, yk, sz, sy, dsz)."""
    two = 2.0
    htwake, hwwake = wake_dim(state, x, h, w, r)
    fwwake = two * hwwake
    delx = x - xold
    xstepi = 1.0 / delx
    if x < xd:
        dsz = turbz
        sz = szold + delx * turbz
        sy = syold + delx * turby
    elif xold > xd:
        dsz2 = zk * turbz * htwake
        dsy2 = yk * turby * fwwake
        sz = math.sqrt(szold ** 2 + delx * dsz2)
        sy = math.sqrt(syold ** 2 + delx * dsy2)
        dsz = (sz - szold) * xstepi
    else:
        delx = xd - xold
        sigzd = szold + delx * turbz
        sigyd = syold + delx * turby
        zk = two * sigzd / htwake
        yk = two * sigyd / fwwake
        delx = x - xd
        dsz2 = zk * turbz * htwake
        dsy2 = yk * turby * fwwake
        sz = math.sqrt(sigzd ** 2 + delx * dsz2)
        sy = math.sqrt(sigyd ** 2 + delx * dsy2)
        dsz = (sz - szold) * xstepi
    return zk, yk, sz, sy, dsz


def wake_dfsn(
    state: AermodState,
    ldbhr: bool,
    xi: float,
    szi: float,
    syi: float,
    z: float,
    dbgunt: int = 0,
) -> None:
    """SUBROUTINE WAKE_DFSN (prime.f)."""
    zero = 0.0
    half = 0.5
    one = 1.0
    rtpiby2 = 1.25331413731550
    p = state.prime

    dist = xp.zeros(MXNW, dtype=xp.float64)
    asigz = xp.zeros(MXNW, dtype=xp.float64)
    asigy = xp.zeros(MXNW, dtype=xp.float64)
    dsz = xp.zeros(MXNW, dtype=xp.float64)
    csigz = xp.zeros(MXNW, dtype=xp.float64)
    csigy = xp.zeros(MXNW, dtype=xp.float64)

    xaz, xay = wake_xa(state, p.xlb, p.rb)
    xamx = max(xaz, xay)
    xamn = min(xaz, xay)
    p.vsigy = 0.0
    p.vsigz = 0.0
    p.vsigyc = 0.0
    p.vsigzc = 0.0
    zkdum = 0.0
    ykdum = 0.0
    zk = 0.0
    yk = 0.0
    zkc = 0.0
    ykc = 0.0
    xcave = p.xlb + p.xlr
    distc = p.xlb + p.xbadj
    xbc = max(xi, p.xlb)
    xbc = min(xbc, xcave)
    xdc = xbc + p.xlr
    szcav0, sycav0 = wake_cav0(state, syi)
    if xi < p.xlb:
        lrevcav = True
    else:
        lrevcav = False
    p.ncav = 1
    # Fortran 1-based index 1 -> 0
    p.xcav[0] = xbc + p.xbadj
    p.szcav[0] = szcav0
    p.sycav[0] = sycav0
    if xi >= xcave:
        lcav = False
        lrevcav = False
    else:
        lcav = True
    p.nwak = 1
    # Fortran 1-based index 1 -> 0
    p.xwak[0] = xi + p.xbadj
    p.szwak[0] = szi
    p.sywak[0] = syi
    p.drwak[0] = zero
    if xi >= xamx:
        lwak = False
        if ldbhr:
            p.emit_debug(state, "WAKE_DFSN", "NWAK", p.nwak, irec=0)
            p.emit_debug(state, "WAKE_DFSN", "XAZ+XBADJ", xaz + p.xbadj, irec=0)
            p.emit_debug(state, "WAKE_DFSN", "XAY+XBADJ", xay + p.xbadj, irec=0)
            p.emit_debug(state, "WAKE_DFSN", "XBADJ", p.xbadj, irec=0)
            p.emit_debug(state, "WAKE_DFSN", "YBADJ", p.ybadj, irec=0)
            p.emit_debug(state, "WAKE_DFSN", "XI", xi, irec=0)
    else:
        lwak = True
    if not lwak and not lcav:
        return
    xd = xi + p.xlr
    dx = 2.0
    xlow = xi
    xhi = xamx
    if lcav:
        xlow = min(xi, xbc)
        xhi = max(xamx, xcave)
    xrange = xhi - xlow + dx
    np = f_nint(xrange / dx) + 1
    np = min(np, MXNW - 1)
    dx = xrange / (float(np) - one)
    dxi = one / dx
    nws = 0
    ncs = 0
    npw = 0
    npc = 0
    # Fortran 1-based index 1 -> 0
    dist[0] = xlow + p.xbadj
    if lwak:
        asigz[0] = szi
        asigy[0] = syi
        dsz[0] = zero
    if lcav:
        csigz[0] = szcav0
        csigy[0] = sycav0
    x = xlow
    # Fortran do n = 2, np -> 0-based index n - 1
    for n in range(2, np + 1):
        xold = x
        x = x + dx
        dist[n - 1] = dist[n - 2] + dx
        if lrevcav and xold >= p.xlb:
            szcav0, sycav0r = wake_cav0(state, float(asigy[n - 2]))
            if sycav0r > sycav0:
                sycav0 = sycav0r
                p.sycav[0] = sycav0
                # Fortran do ir = 1, n - 1 -> 0-based index ir - 1
                for ir in range(1, n):
                    csigy[ir - 1] = max(float(csigy[ir - 1]), sycav0)
            lrevcav = False
        if lwak and (xi >= x):
            asigz[n - 1] = asigz[n - 2]
            asigy[n - 1] = asigy[n - 2]
            dsz[n - 1] = dsz[n - 2]
            nws = n
        if lcav and (xbc >= x):
            csigz[n - 1] = szcav0
            csigy[n - 1] = sycav0
            ncs = n
        if xold > xamx:
            if lwak and (xi < x):
                p.vsigz = max(p.vsigz, szi)
                p.vsigy = max(p.vsigy, syi)
                asigz[n - 1] = sigzpr(state, float(dist[n - 1]), z)
                asigy[n - 1] = sigypr(state, float(dist[n - 1]), z)
                asigz[n - 1] = math.sqrt(float(asigz[n - 1]) ** 2 + p.vsigz ** 2)
                asigy[n - 1] = math.sqrt(float(asigy[n - 1]) ** 2 + p.vsigy ** 2)
                dsz[n - 1] = (float(asigz[n - 1]) - float(asigz[n - 2])) * dxi
            if lcav and (xbc < x):
                p.vsigzc = max(p.vsigzc, szcav0)
                p.vsigyc = max(p.vsigyc, sycav0)
                csigz[n - 1] = sigzpr(state, float(dist[n - 1]), 0.0)
                csigy[n - 1] = sigypr(state, float(dist[n - 1]), 0.0)
                csigz[n - 1] = math.sqrt(float(csigz[n - 1]) ** 2 + p.vsigzc ** 2)
                csigy[n - 1] = math.sqrt(float(csigy[n - 1]) ** 2 + p.vsigyc ** 2)
        else:
            if x < xamn:
                xmid = half * (x + xold)
                wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                if lwak and (xi <= x):
                    zk, yk, asigz[n - 1], asigy[n - 1], dsz[n - 1] = wake_sig(
                        state,
                        x,
                        xd,
                        xold,
                        wakiz,
                        wakiy,
                        float(asigz[n - 2]),
                        float(asigy[n - 2]),
                        p.hb,
                        p.wb,
                        p.rb,
                        zk,
                        yk,
                    )
                if lcav and (xbc <= x):
                    zkc, ykc, csigz[n - 1], csigy[n - 1], _dzrate = wake_sig(
                        state,
                        x,
                        xdc,
                        xold,
                        wakiz,
                        wakiy,
                        float(csigz[n - 2]),
                        float(csigy[n - 2]),
                        p.hb,
                        p.wb,
                        p.rb,
                        zkc,
                        ykc,
                    )
                    csigz[n - 1] = max(float(csigz[n - 1]), szcav0)
            else:
                if xold >= xaz:
                    if lwak and (xi <= x):
                        asigz[n - 1] = sigzpr(state, float(dist[n - 1]), z)
                        p.vsigz = max(p.vsigz, szi)
                        asigz[n - 1] = math.sqrt(
                            float(asigz[n - 1]) ** 2 + p.vsigz ** 2
                        )
                        dsz[n - 1] = (float(asigz[n - 1]) - float(asigz[n - 2])) * dxi
                    if lcav and (xbc <= x):
                        csigz[n - 1] = sigzpr(state, float(dist[n - 1]), 0.0)
                        csigz[n - 1] = math.sqrt(
                            float(csigz[n - 1]) ** 2 + p.vsigzc ** 2
                        )
                        csigz[n - 1] = max(float(csigz[n - 1]), szcav0)
                elif x >= xaz:
                    xnew = xaz
                    xmid = half * (xnew + xold)
                    wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                    if lwak and (xi <= xnew):
                        zk, ykdum, sigzxa, _sydum, _dzrate = wake_sig(
                            state,
                            xnew,
                            xd,
                            xold,
                            wakiz,
                            wakiy,
                            float(asigz[n - 2]),
                            float(asigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zk,
                            ykdum,
                        )
                        sz = sigzpr(state, xaz + p.xbadj, z)
                        if sigzxa > sz:
                            p.vsigz = math.sqrt(sigzxa ** 2 - sz ** 2)
                        else:
                            p.vsigz = 0.0
                        asigz[n - 1] = sigzpr(state, float(dist[n - 1]), z)
                        asigz[n - 1] = math.sqrt(
                            float(asigz[n - 1]) ** 2 + p.vsigz ** 2
                        )
                        dsz[n - 1] = (float(asigz[n - 1]) - float(asigz[n - 2])) * dxi
                    if lcav and (xbc <= xnew):
                        zkc, ykdum, sigzxa, _sydum, _dzrate = wake_sig(
                            state,
                            xnew,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkc,
                            ykdum,
                        )
                        sz = sigzpr(state, xaz + p.xbadj, 0.0)
                        if sigzxa > sz:
                            p.vsigzc = math.sqrt(sigzxa ** 2 - sz ** 2)
                        else:
                            p.vsigzc = 0.0
                        p.vsigzc = max(p.vsigzc, szcav0)
                        csigz[n - 1] = sigzpr(state, float(dist[n - 1]), 0.0)
                        csigz[n - 1] = math.sqrt(
                            float(csigz[n - 1]) ** 2 + p.vsigzc ** 2
                        )
                else:
                    xmid = half * (x + xold)
                    wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                    if lwak and (xi <= x):
                        zk, ykdum, asigz[n - 1], _sydum, dsz[n - 1] = wake_sig(
                            state,
                            x,
                            xd,
                            xold,
                            wakiz,
                            wakiy,
                            float(asigz[n - 2]),
                            float(asigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zk,
                            ykdum,
                        )
                    if lcav and (xbc <= x):
                        zkc, ykdum, csigz[n - 1], _sydum, _dzrate = wake_sig(
                            state,
                            x,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkc,
                            ykdum,
                        )
                        csigz[n - 1] = max(float(csigz[n - 1]), szcav0)

                if xold >= xay:
                    if lwak and (xi <= x):
                        asigy[n - 1] = sigypr(state, float(dist[n - 1]), z)
                        p.vsigy = max(p.vsigy, syi)
                        asigy[n - 1] = math.sqrt(
                            float(asigy[n - 1]) ** 2 + p.vsigy ** 2
                        )
                    if lcav and (xbc <= x):
                        csigy[n - 1] = sigypr(state, float(dist[n - 1]), 0.0)
                        p.vsigyc = max(p.vsigyc, sycav0)
                        csigy[n - 1] = math.sqrt(
                            float(csigy[n - 1]) ** 2 + p.vsigyc ** 2
                        )
                elif x >= xay:
                    xnew = xay
                    xmid = half * (xnew + xold)
                    wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                    if lwak and (xi <= xnew):
                        zkdum, yk, _szdum, sigyxa, _dzrate = wake_sig(
                            state,
                            xnew,
                            xd,
                            xold,
                            wakiz,
                            wakiy,
                            float(asigz[n - 2]),
                            float(asigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkdum,
                            yk,
                        )
                        sy = sigypr(state, xay + p.xbadj, z)
                        if sigyxa > sy:
                            p.vsigy = math.sqrt(sigyxa ** 2 - sy ** 2)
                        else:
                            p.vsigy = 0.0
                        asigy[n - 1] = sigypr(state, float(dist[n - 1]), z)
                        asigy[n - 1] = math.sqrt(
                            float(asigy[n - 1]) ** 2 + p.vsigy ** 2
                        )
                    if lcav and (xbc <= xnew):
                        zkdum, ykc, _szdum, sigyxa, _dzrate = wake_sig(
                            state,
                            xnew,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkdum,
                            ykc,
                        )
                        sy = sigypr(state, xay + p.xbadj, 0.0)
                        if sigyxa > sy:
                            p.vsigyc = math.sqrt(sigyxa ** 2 - sy ** 2)
                        else:
                            p.vsigyc = 0.0
                        csigy[n - 1] = sigypr(state, float(dist[n - 1]), 0.0)
                        csigy[n - 1] = math.sqrt(
                            float(csigy[n - 1]) ** 2 + p.vsigyc ** 2
                        )
                else:
                    xmid = half * (x + xold)
                    wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                    if lwak and (xi <= x):
                        zkdum, yk, _szdum, asigy[n - 1], _dzrate = wake_sig(
                            state,
                            x,
                            xd,
                            xold,
                            wakiz,
                            wakiy,
                            float(asigz[n - 2]),
                            float(asigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkdum,
                            yk,
                        )
                    if lcav and (xbc <= x):
                        zkdum, ykc, _szdum, csigy[n - 1], _dzrate = wake_sig(
                            state,
                            x,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkdum,
                            ykc,
                        )

    if lwak:
        npw = np - nws
        # Fortran 1-based index 1 -> 0
        p.xwak[0] = xi + p.xbadj
        p.szwak[0] = szi
        p.sywak[0] = syi
        p.drwak[0] = zero
        if npw >= MXNTR:
            p.nwak = MXNTR
            # Fortran nwak, np -> indices p.nwak - 1, np - 1
            p.xwak[p.nwak - 1] = dist[np - 1]
            p.szwak[p.nwak - 1] = asigz[np - 1]
            p.sywak[p.nwak - 1] = asigy[np - 1]
            p.drwak[p.nwak - 1] = rtpiby2 * dsz[np - 1]
            if npw <= 2 * MXNTR:
                deln = float(npw) / float(p.nwak)
                # Fortran do in = 2, nwak - 1 -> 0-based index in_ - 1
                for in_ in range(2, p.nwak):
                    jn = f_int(float(in_) * deln) + nws
                    p.xwak[in_ - 1] = dist[jn - 1]
                    p.szwak[in_ - 1] = asigz[jn - 1]
                    p.sywak[in_ - 1] = asigy[jn - 1]
                    p.drwak[in_ - 1] = rtpiby2 * dsz[jn - 1]
            else:
                deln = 2.0 * float(npw - MXNTR) / float(MXNTR * (MXNTR - 1))
                rn = one
                # Fortran do in = 2, nwak - 1 -> 0-based index in_ - 1
                for in_ in range(2, p.nwak):
                    rn = rn + one + float(in_ - 1) * deln
                    jn = f_int(rn) + nws
                    p.xwak[in_ - 1] = dist[jn - 1]
                    p.szwak[in_ - 1] = asigz[jn - 1]
                    p.sywak[in_ - 1] = asigy[jn - 1]
                    p.drwak[in_ - 1] = rtpiby2 * dsz[jn - 1]
        else:
            p.nwak = npw
            # Fortran do in = 2, npw -> 0-based index in_ - 1
            for in_ in range(2, npw + 1):
                inp = in_ + nws
                p.xwak[in_ - 1] = dist[inp - 1]
                p.szwak[in_ - 1] = asigz[inp - 1]
                p.sywak[in_ - 1] = asigy[inp - 1]
                p.drwak[in_ - 1] = rtpiby2 * dsz[inp - 1]

    if lcav:
        npc = np - ncs
        # Fortran 1-based index 1 -> 0
        p.xcav[0] = xbc + p.xbadj
        p.szcav[0] = szcav0
        p.sycav[0] = sycav0
        if npc >= MXNTR:
            p.ncav = MXNTR
            # Fortran ncav, np -> indices p.ncav - 1, np - 1
            p.xcav[p.ncav - 1] = dist[np - 1]
            p.szcav[p.ncav - 1] = csigz[np - 1]
            p.sycav[p.ncav - 1] = csigy[np - 1]
            if npc <= 2 * MXNTR:
                deln = float(npc) / float(p.ncav)
                # Fortran do in = 2, ncav - 1 -> 0-based index in_ - 1
                for in_ in range(2, p.ncav):
                    jn = f_int(float(in_) * deln) + ncs
                    p.xcav[in_ - 1] = dist[jn - 1]
                    p.szcav[in_ - 1] = csigz[jn - 1]
                    p.sycav[in_ - 1] = csigy[jn - 1]
            else:
                deln = 2.0 * float(npc - MXNTR) / float(MXNTR * (MXNTR - 1))
                rn = one
                # Fortran do in = 2, ncav - 1 -> 0-based index in_ - 1
                for in_ in range(2, p.ncav):
                    rn = rn + one + float(in_ - 1) * deln
                    jn = f_int(rn) + ncs
                    p.xcav[in_ - 1] = dist[jn - 1]
                    p.szcav[in_ - 1] = csigz[jn - 1]
                    p.sycav[in_ - 1] = csigy[jn - 1]
        else:
            p.ncav = npc
            # Fortran do in = 2, npc -> 0-based index in_ - 1
            for in_ in range(2, npc + 1):
                inp = in_ + ncs
                p.xcav[in_ - 1] = dist[inp - 1]
                p.szcav[in_ - 1] = csigz[inp - 1]
                p.sycav[in_ - 1] = csigy[inp - 1]

    if ldbhr:
        p.emit_debug(state, "WAKE_DFSN", "NWAK", p.nwak, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "XAZ+XBADJ", xaz + p.xbadj, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "XAY+XBADJ", xay + p.xbadj, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "XBADJ", p.xbadj, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "YBADJ", p.ybadj, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "XI", xi, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "XBC", xbc, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "DISTC", distc, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "XDC", xdc, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "LWAK", 1.0 if lwak else 0.0, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "NWS", nws, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "NPW", npw, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "LCAV", 1.0 if lcav else 0.0, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "NCS", ncs, irec=0)
        p.emit_debug(state, "WAKE_DFSN", "NPC", npc, irec=0)
        # Fortran do i = 1, nwak -> 0-based index i - 1
        for i in range(1, p.nwak + 1):
            p.emit_debug(state, "WAKE_DFSN", "XWAK", float(p.xwak[i - 1]), irec=0)
            p.emit_debug(state, "WAKE_DFSN", "SZWAK", float(p.szwak[i - 1]), irec=0)
            p.emit_debug(state, "WAKE_DFSN", "SYWAK", float(p.sywak[i - 1]), irec=0)
            p.emit_debug(state, "WAKE_DFSN", "DRWAK", float(p.drwak[i - 1]), irec=0)
        # Fortran do i = 1, ncav -> 0-based index i - 1
        for i in range(1, p.ncav + 1):
            p.emit_debug(state, "WAKE_DFSN", "XCAV", float(p.xcav[i - 1]), irec=0)
            p.emit_debug(state, "WAKE_DFSN", "SZCAV", float(p.szcav[i - 1]), irec=0)
            p.emit_debug(state, "WAKE_DFSN", "SYCAV", float(p.sycav[i - 1]), irec=0)


def wake_dfsn2(
    state: AermodState,
    ldbhr: bool,
    xi: float,
    szi: float,
    syi: float,
    xtr: xp.ndarray,
    ztr: xp.ndarray,
    ntr: int,
    dbgunt: int = 0,
) -> None:
    """SUBROUTINE WAKE_DFSN2 (prime.f)."""
    zero = 0.0
    half = 0.5
    one = 1.0
    rtpiby2 = 1.25331413731550
    p = state.prime

    dist = xp.zeros(MXNW, dtype=xp.float64)
    asigz = xp.zeros(MXNW, dtype=xp.float64)
    asigy = xp.zeros(MXNW, dtype=xp.float64)
    dsz = xp.zeros(MXNW, dtype=xp.float64)
    csigz = xp.zeros(MXNW, dtype=xp.float64)
    csigy = xp.zeros(MXNW, dtype=xp.float64)

    xaz, xay = wake_xa(state, p.xlb, p.rb)
    xamx = max(xaz, xay)
    xamn = min(xaz, xay)
    zxay = numgrad(state, xay + p.xbadj, xtr, ztr, ntr)
    zxaz = numgrad(state, xaz + p.xbadj, xtr, ztr, ntr)
    p.vsigy = 0.0
    p.vsigz = 0.0
    p.vsigyc = 0.0
    p.vsigzc = 0.0
    zkdum = 0.0
    ykdum = 0.0
    zk = 0.0
    yk = 0.0
    zkc = 0.0
    ykc = 0.0
    xcave = p.xlb + p.xlr
    xbc = max(xi, p.xlb)
    xbc = min(xbc, xcave)
    xdc = xbc + p.xlr
    szcav0, sycav0 = wake_cav0(state, syi)
    if xi < p.xlb:
        lrevcav = True
    else:
        lrevcav = False
    p.ncav = 1
    # Fortran 1-based index 1 -> 0
    p.xcav[0] = xbc + p.xbadj
    p.szcav[0] = szcav0
    p.sycav[0] = sycav0
    if xi >= xcave:
        lcav = False
        lrevcav = False
    else:
        lcav = True
    p.nwak = 1
    # Fortran 1-based index 1 -> 0
    p.xwak[0] = xi + p.xbadj
    p.szwak[0] = szi
    p.sywak[0] = syi
    p.drwak[0] = zero
    if xi >= xamx:
        lwak = False
        if ldbhr:
            p.emit_debug(state, "WAKE_DFSN2", "NWAK", p.nwak, irec=0)
            p.emit_debug(state, "WAKE_DFSN2", "XAZ+XBADJ", xaz + p.xbadj, irec=0)
            p.emit_debug(state, "WAKE_DFSN2", "XAY+XBADJ", xay + p.xbadj, irec=0)
            p.emit_debug(state, "WAKE_DFSN2", "XBADJ", p.xbadj, irec=0)
            p.emit_debug(state, "WAKE_DFSN2", "YBADJ", p.ybadj, irec=0)
            p.emit_debug(state, "WAKE_DFSN2", "XI", xi, irec=0)
    else:
        lwak = True
    if not lwak and not lcav:
        return
    xd = xi + p.xlr
    dx = 2.0
    xlow = xi
    xhi = xamx
    if lcav:
        xlow = min(xi, xbc)
        xhi = max(xamx, xcave)
    xrange = xhi - xlow + dx
    np = f_nint(xrange / dx) + 1
    np = min(np, MXNW - 1)
    dx = xrange / (float(np) - one)
    dxi = one / dx
    nws = 0
    ncs = 0
    # Fortran 1-based index 1 -> 0
    dist[0] = xlow + p.xbadj
    if lwak:
        asigz[0] = szi
        asigy[0] = syi
        dsz[0] = zero
    if lcav:
        csigz[0] = szcav0
        csigy[0] = sycav0
    x = xlow
    # Fortran do n = 2, np -> 0-based index n - 1
    for n in range(2, np + 1):
        xold = x
        x = x + dx
        dist[n - 1] = dist[n - 2] + dx
        if lrevcav and xold >= p.xlb:
            szcav0, sycav0r = wake_cav0(state, float(asigy[n - 2]))
            if sycav0r > sycav0:
                sycav0 = sycav0r
                p.sycav[0] = sycav0
                # Fortran do ir = 1, n - 1 -> 0-based index ir - 1
                for ir in range(1, n):
                    csigy[ir - 1] = max(float(csigy[ir - 1]), sycav0)
            lrevcav = False
        if lwak and (xi >= x):
            asigz[n - 1] = asigz[n - 2]
            asigy[n - 1] = asigy[n - 2]
            dsz[n - 1] = dsz[n - 2]
            nws = n
        if lcav and (xbc >= x):
            csigz[n - 1] = szcav0
            csigy[n - 1] = sycav0
            ncs = n
        if xold > xamx:
            if lwak and (xi < x):
                p.vsigz = max(p.vsigz, szi)
                p.vsigy = max(p.vsigy, syi)
                zdist = numgrad(state, float(dist[n - 1]), xtr, ztr, ntr)
                asigz[n - 1] = sigzpr(state, float(dist[n - 1]), zdist)
                asigy[n - 1] = sigypr(state, float(dist[n - 1]), zdist)
                asigz[n - 1] = math.sqrt(float(asigz[n - 1]) ** 2 + p.vsigz ** 2)
                asigy[n - 1] = math.sqrt(float(asigy[n - 1]) ** 2 + p.vsigy ** 2)
                dsz[n - 1] = (float(asigz[n - 1]) - float(asigz[n - 2])) * dxi
            if lcav and (xbc < x):
                p.vsigzc = max(p.vsigzc, szcav0)
                p.vsigyc = max(p.vsigyc, sycav0)
                csigz[n - 1] = sigzpr(state, float(dist[n - 1]), 0.0)
                csigy[n - 1] = sigypr(state, float(dist[n - 1]), 0.0)
                csigz[n - 1] = math.sqrt(float(csigz[n - 1]) ** 2 + p.vsigzc ** 2)
                csigy[n - 1] = math.sqrt(float(csigy[n - 1]) ** 2 + p.vsigyc ** 2)
        else:
            if x < xamn:
                xmid = half * (x + xold)
                wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                if lwak and (xi <= x):
                    zk, yk, asigz[n - 1], asigy[n - 1], dsz[n - 1] = wake_sig(
                        state,
                        x,
                        xd,
                        xold,
                        wakiz,
                        wakiy,
                        float(asigz[n - 2]),
                        float(asigy[n - 2]),
                        p.hb,
                        p.wb,
                        p.rb,
                        zk,
                        yk,
                    )
                if state.L_ORD_Cav:
                    if lcav and (xbc <= x) and (x >= xcave):
                        zkc, ykc, csigz[n - 1], csigy[n - 1], _dzrate = wake_sig(
                            state,
                            x,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkc,
                            ykc,
                        )
                        csigz[n - 1] = max(float(csigz[n - 1]), szcav0)
                    elif lcav and (xbc <= x) and (x < xcave):
                        zkc, ykc, csigz[n - 1], csigy[n - 1], _dzrate = wake_sig(
                            state,
                            x,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkc,
                            ykc,
                        )
                        # Fortran csigz(1), csigy(1) -> index 0
                        csigz[n - 1] = 1.00 * csigz[0]
                        csigy[n - 1] = 1.00 * csigy[0]
                else:
                    if lcav and (xbc <= x):
                        zkc, ykc, csigz[n - 1], csigy[n - 1], _dzrate = wake_sig(
                            state,
                            x,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkc,
                            ykc,
                        )
                        csigz[n - 1] = max(float(csigz[n - 1]), szcav0)
            else:
                if xold >= xaz:
                    if lwak and (xi <= x):
                        zdist = numgrad(state, float(dist[n - 1]), xtr, ztr, ntr)
                        asigz[n - 1] = sigzpr(state, float(dist[n - 1]), zdist)
                        p.vsigz = max(p.vsigz, szi)
                        asigz[n - 1] = math.sqrt(
                            float(asigz[n - 1]) ** 2 + p.vsigz ** 2
                        )
                        dsz[n - 1] = (float(asigz[n - 1]) - float(asigz[n - 2])) * dxi
                    if lcav and (xbc <= x):
                        p.vsigzc = max(p.vsigzc, szcav0)
                        csigz[n - 1] = sigzpr(state, float(dist[n - 1]), 0.0)
                        csigz[n - 1] = math.sqrt(
                            float(csigz[n - 1]) ** 2 + p.vsigzc ** 2
                        )
                elif x >= xaz:
                    xnew = xaz
                    xmid = half * (xnew + xold)
                    wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                    if lwak and (xi <= xnew):
                        zk, ykdum, sigzxa, _sydum, _dzrate = wake_sig(
                            state,
                            xnew,
                            xd,
                            xold,
                            wakiz,
                            wakiy,
                            float(asigz[n - 2]),
                            float(asigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zk,
                            ykdum,
                        )
                        sz = sigzpr(state, xaz + p.xbadj, zxaz)
                        if sigzxa > sz:
                            p.vsigz = math.sqrt(sigzxa ** 2 - sz ** 2)
                        else:
                            p.vsigz = 0.0
                        zdist = numgrad(state, float(dist[n - 1]), xtr, ztr, ntr)
                        asigz[n - 1] = sigzpr(state, float(dist[n - 1]), zdist)
                        asigz[n - 1] = math.sqrt(
                            float(asigz[n - 1]) ** 2 + p.vsigz ** 2
                        )
                        dsz[n - 1] = (float(asigz[n - 1]) - float(asigz[n - 2])) * dxi
                    if lcav and (xbc <= xnew):
                        zkc, ykdum, sigzxa, _sydum, _dzrate = wake_sig(
                            state,
                            xnew,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkc,
                            ykdum,
                        )
                        sz = sigzpr(state, xaz + p.xbadj, 0.0)
                        if sigzxa > sz:
                            p.vsigzc = math.sqrt(sigzxa ** 2 - sz ** 2)
                        else:
                            p.vsigzc = 0.0
                        p.vsigzc = max(p.vsigzc, szcav0)
                        csigz[n - 1] = sigzpr(state, float(dist[n - 1]), 0.0)
                        csigz[n - 1] = math.sqrt(
                            float(csigz[n - 1]) ** 2 + p.vsigzc ** 2
                        )
                else:
                    xmid = half * (x + xold)
                    wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                    if lwak and (xi <= x):
                        zk, ykdum, asigz[n - 1], _sydum, dsz[n - 1] = wake_sig(
                            state,
                            x,
                            xd,
                            xold,
                            wakiz,
                            wakiy,
                            float(asigz[n - 2]),
                            float(asigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zk,
                            ykdum,
                        )
                    if lcav and (xbc <= x):
                        zkc, ykdum, csigz[n - 1], _sydum, _dzrate = wake_sig(
                            state,
                            x,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkc,
                            ykdum,
                        )
                        csigz[n - 1] = max(float(csigz[n - 1]), szcav0)

                if xold >= xay:
                    if lwak and (xi <= x):
                        zdist = numgrad(state, float(dist[n - 1]), xtr, ztr, ntr)
                        asigy[n - 1] = sigypr(state, float(dist[n - 1]), zdist)
                        p.vsigy = max(p.vsigy, syi)
                        asigy[n - 1] = math.sqrt(
                            float(asigy[n - 1]) ** 2 + p.vsigy ** 2
                        )
                    if state.L_ORD_Cav:
                        if lcav and (x >= xcave) and (xbc <= x):
                            csigy[n - 1] = sigypr(state, float(dist[n - 1]), 0.0)
                            p.vsigyc = max(p.vsigyc, sycav0)
                            csigy[n - 1] = math.sqrt(
                                float(csigy[n - 1]) ** 2 + p.vsigyc ** 2
                            )
                        elif lcav and (x < xcave) and (xbc <= x):
                            csigy[n - 1] = sigypr(state, float(dist[n - 1]), 0.0)
                            p.vsigyc = max(p.vsigyc, sycav0)
                            # Fortran csigy(1) -> index 0
                            csigy[n - 1] = 1.00 * csigy[0]
                    else:
                        if lcav and (xbc <= x):
                            csigy[n - 1] = sigypr(state, float(dist[n - 1]), 0.0)
                            p.vsigyc = max(p.vsigyc, sycav0)
                            csigy[n - 1] = math.sqrt(
                                float(csigy[n - 1]) ** 2 + p.vsigyc ** 2
                            )
                elif x >= xay:
                    xnew = xay
                    xmid = half * (xnew + xold)
                    wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                    if lwak and (xi <= xnew):
                        zkdum, yk, _szdum, sigyxa, _dzrate = wake_sig(
                            state,
                            xnew,
                            xd,
                            xold,
                            wakiz,
                            wakiy,
                            float(asigz[n - 2]),
                            float(asigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkdum,
                            yk,
                        )
                        sy = sigypr(state, xay + p.xbadj, zxay)
                        if sigyxa > sy:
                            p.vsigy = math.sqrt(sigyxa ** 2 - sy ** 2)
                        else:
                            p.vsigy = 0.0
                        zdist = numgrad(state, float(dist[n - 1]), xtr, ztr, ntr)
                        asigy[n - 1] = sigypr(state, float(dist[n - 1]), zdist)
                        asigy[n - 1] = math.sqrt(
                            float(asigy[n - 1]) ** 2 + p.vsigy ** 2
                        )
                    if lcav and (xbc <= xnew):
                        zkdum, ykc, _szdum, sigyxa, _dzrate = wake_sig(
                            state,
                            xnew,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkdum,
                            ykc,
                        )
                        sy = sigypr(state, xay + p.xbadj, 0.0)
                        if sigyxa > sy:
                            p.vsigyc = math.sqrt(sigyxa ** 2 - sy ** 2)
                        else:
                            p.vsigyc = 0.0
                        csigy[n - 1] = sigypr(state, float(dist[n - 1]), 0.0)
                        csigy[n - 1] = math.sqrt(
                            float(csigy[n - 1]) ** 2 + p.vsigyc ** 2
                        )
                else:
                    xmid = half * (x + xold)
                    wakiz, wakiy = wake_turb(state, xmid, p.xlb, p.rb)
                    if lwak and (xi <= x):
                        zkdum, yk, _szdum, asigy[n - 1], _dzrate = wake_sig(
                            state,
                            x,
                            xd,
                            xold,
                            wakiz,
                            wakiy,
                            float(asigz[n - 2]),
                            float(asigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkdum,
                            yk,
                        )
                    if lcav and (xbc <= x):
                        zkdum, ykc, _szdum, csigy[n - 1], _dzrate = wake_sig(
                            state,
                            x,
                            xdc,
                            xold,
                            wakiz,
                            wakiy,
                            float(csigz[n - 2]),
                            float(csigy[n - 2]),
                            p.hb,
                            p.wb,
                            p.rb,
                            zkdum,
                            ykc,
                        )

    if lwak:
        npw = np - nws
        # Fortran 1-based index 1 -> 0
        p.xwak[0] = xi + p.xbadj
        p.szwak[0] = szi
        p.sywak[0] = syi
        p.drwak[0] = zero
        if npw >= MXNTR:
            p.nwak = MXNTR
            # Fortran nwak, np -> indices p.nwak - 1, np - 1
            p.xwak[p.nwak - 1] = dist[np - 1]
            p.szwak[p.nwak - 1] = asigz[np - 1]
            p.sywak[p.nwak - 1] = asigy[np - 1]
            p.drwak[p.nwak - 1] = rtpiby2 * dsz[np - 1]
            if npw <= 2 * MXNTR:
                deln = float(npw) / float(p.nwak)
                # Fortran do in = 2, nwak - 1 -> 0-based index in_ - 1
                for in_ in range(2, p.nwak):
                    jn = f_int(float(in_) * deln) + nws
                    p.xwak[in_ - 1] = dist[jn - 1]
                    p.szwak[in_ - 1] = asigz[jn - 1]
                    p.sywak[in_ - 1] = asigy[jn - 1]
                    p.drwak[in_ - 1] = rtpiby2 * dsz[jn - 1]
            else:
                deln = 2.0 * float(npw - MXNTR) / float(MXNTR * (MXNTR - 1))
                rn = one
                # Fortran do in = 2, nwak - 1 -> 0-based index in_ - 1
                for in_ in range(2, p.nwak):
                    rn = rn + one + float(in_ - 1) * deln
                    jn = f_int(rn) + nws
                    p.xwak[in_ - 1] = dist[jn - 1]
                    p.szwak[in_ - 1] = asigz[jn - 1]
                    p.sywak[in_ - 1] = asigy[jn - 1]
                    p.drwak[in_ - 1] = rtpiby2 * dsz[jn - 1]
        else:
            p.nwak = npw
            # Fortran do in = 2, npw -> 0-based index in_ - 1
            for in_ in range(2, npw + 1):
                inp = in_ + nws
                p.xwak[in_ - 1] = dist[inp - 1]
                p.szwak[in_ - 1] = asigz[inp - 1]
                p.sywak[in_ - 1] = asigy[inp - 1]
                p.drwak[in_ - 1] = rtpiby2 * dsz[inp - 1]

    if lcav:
        npc = np - ncs
        # Fortran 1-based index 1 -> 0
        p.xcav[0] = xbc + p.xbadj
        p.szcav[0] = szcav0
        p.sycav[0] = sycav0
        if npc >= MXNTR:
            p.ncav = MXNTR
            # Fortran ncav, np -> indices p.ncav - 1, np - 1
            p.xcav[p.ncav - 1] = dist[np - 1]
            p.szcav[p.ncav - 1] = csigz[np - 1]
            p.sycav[p.ncav - 1] = csigy[np - 1]
            if npc <= 2 * MXNTR:
                deln = float(npc) / float(p.ncav)
                # Fortran do in = 2, ncav - 1 -> 0-based index in_ - 1
                for in_ in range(2, p.ncav):
                    jn = f_int(float(in_) * deln) + ncs
                    p.xcav[in_ - 1] = dist[jn - 1]
                    p.szcav[in_ - 1] = csigz[jn - 1]
                    p.sycav[in_ - 1] = csigy[jn - 1]
            else:
                deln = 2.0 * float(npc - MXNTR) / float(MXNTR * (MXNTR - 1))
                rn = one
                # Fortran do in = 2, ncav - 1 -> 0-based index in_ - 1
                for in_ in range(2, p.ncav):
                    rn = rn + one + float(in_ - 1) * deln
                    jn = f_int(rn) + ncs
                    p.xcav[in_ - 1] = dist[jn - 1]
                    p.szcav[in_ - 1] = csigz[jn - 1]
                    p.sycav[in_ - 1] = csigy[jn - 1]
        else:
            p.ncav = npc
            # Fortran do in = 2, npc -> 0-based index in_ - 1
            for in_ in range(2, npc + 1):
                inp = in_ + ncs
                p.xcav[in_ - 1] = dist[inp - 1]
                p.szcav[in_ - 1] = csigz[inp - 1]
                p.sycav[in_ - 1] = csigy[inp - 1]

    if ldbhr:
        p.emit_debug(state, "WAKE_DFSN2", "VSIGY", p.vsigy, irec=0)
        p.emit_debug(state, "WAKE_DFSN2", "VSIGZ", p.vsigz, irec=0)
        p.emit_debug(state, "WAKE_DFSN2", "VSIGYC", p.vsigyc, irec=0)
        p.emit_debug(state, "WAKE_DFSN2", "VSIGZC", p.vsigzc, irec=0)


def wake_fqc(
    state: AermodState,
    ldb: bool,
    xbi: float,
    xtr: xp.ndarray,
    ztr: xp.ndarray,
    ntr: int,
    dbgunt: int = 0,
) -> None:
    """SUBROUTINE WAKE_FQC (prime.f)."""
    p = state.prime
    p.fqcav = 0.0
    xmax = 0.0
    fzmax = 0.0
    xbstart = max(xbi, p.xlb)
    xbend = p.xlb + p.xlr
    xrange = 0.99 * (xbend - xbstart)
    yba = abs(p.ybadj)
    xend = xbend + p.xbadj
    nstep = max(5, f_int(1.0 + xrange / 10.0))
    xstep = xrange / float(nstep)
    zplm = numgrad(state, xend, xtr, ztr, ntr)
    sz, sy, _szc, _syc = wake_xsig(state, xend, p.hb, 0.0, True)
    fractz0 = frgauss(state, zplm, sz, p.hb, -p.hb)
    # Fortran do is = 0, nstep
    for is_ in range(0, nstep + 1):
        xb = xbstart + float(is_) * xstep
        x = xb + p.xbadj
        zplm = numgrad(state, x, xtr, ztr, ntr)
        zcav, ycav = cavity_ht(
            state, p.hb, p.wb, p.xlb, p.rb, p.xlc, p.xlr, p.hr, xb
        )
        sz, sy, _szc, _syc = wake_xsig(state, x, zplm, 0.0, True)
        fractz = frgauss(state, zplm, sz, zcav, -zcav)
        fracty = frgauss(state, yba, sy, ycav, -ycav)
        fz = min(fractz, fractz0)
        fract = fz * fracty
        if fract > p.fqcav:
            p.fqcav = fract
            xmax = x
            fzmax = fz
    xb85 = p.xlb + 0.85 * p.xlr
    if xbstart > xb85:
        fq85 = max(0.0, 1.0 - (xbstart - xb85) / (xbend - xb85))
        p.fqcav = min(p.fqcav, fq85)
    if ldb:
        p.emit_debug(state, "WAKE_FQC", "XBI", xbi, irec=0)
        p.emit_debug(state, "WAKE_FQC", "XBSTART", xbstart, irec=0)
        p.emit_debug(state, "WAKE_FQC", "XBEND", xbend, irec=0)
        p.emit_debug(state, "WAKE_FQC", "XSTEP", xstep, irec=0)
        p.emit_debug(state, "WAKE_FQC", "NSTEP", nstep, irec=0)
        p.emit_debug(state, "WAKE_FQC", "FRACTZ0", fractz0, irec=0)
        p.emit_debug(state, "WAKE_FQC", "XB85", xb85, irec=0)
        p.emit_debug(state, "WAKE_FQC", "XMAX", xmax, irec=0)
        p.emit_debug(state, "WAKE_FQC", "FQCAV", p.fqcav, irec=0)
        p.emit_debug(state, "WAKE_FQC", "FZMAX", fzmax, irec=0)


def cav_src(
    state: AermodState,
    xr: float,
    yr: float,
    zr: float,
    qc: xp.ndarray,
    hc: xp.ndarray,
    yrc: xp.ndarray,
    zrc: xp.ndarray,
    szc: xp.ndarray,
    syc: xp.ndarray,
) -> tuple[float, int, int]:
    """SUBROUTINE CAV_SRC (prime.f). Mutates qc(3), hc(3), yrc(3), zrc(3), szc(3), syc(3) in place; returns (fqcav0, n1, n2)."""
    rt2pi = 2.50662827463100
    p = state.prime
    # Fortran szcav(1), sycav(1) -> index 0
    szcav0 = float(p.szcav[0])
    sycav0 = float(p.sycav[0])
    fqcav0 = p.fqcav
    # Fortran hc(2), hc(3) -> indices 1, 2
    hc[1] = 0.0
    hc[2] = 0.0
    mode = 0
    n1 = 1
    n2 = 1
    if p.fqcav <= 0.0:
        n1 = 1
        n2 = 1
        # Fortran do i = 2, 3 -> index i - 1
        for i in range(2, 4):
            qc[i - 1] = 0.0
            yrc[i - 1] = yr
            zrc[i - 1] = zr
            szc[i - 1] = szcav0
            syc[i - 1] = sycav0
    else:
        xrb = xr - p.xbadj
        yrb = yr - p.ybadj
        zrb = zr
        ipositn = position(state, xrb, yrb, zrb)
        x115b = p.xlb + 1.15 * p.xlr
        x85b = p.xlb + 0.85 * p.xlr
        # Fortran qc(2), qc(3) -> indices 1, 2
        if xrb >= x115b:
            qc[1] = 1.0
            qc[2] = 0.0
            mode = 1
        elif xrb > x85b:
            qc[1] = (xrb - x85b) / (x115b - x85b)
            qc[2] = 1.0 - float(qc[1])
            mode = 3
        elif xrb > p.xlb:
            qc[1] = 0.0
            qc[2] = 1.0
            mode = 2
        else:
            qc[1] = 0.0
            qc[2] = max(0.0, xrb / p.xlb)
            mode = 2
        if ipositn == 4:
            mode = 0
            n1 = 1
            n2 = 1
            # Fortran do i = 2, 3 -> index i - 1
            for i in range(2, 4):
                qc[i - 1] = 0.0
                yrc[i - 1] = yr
                zrc[i - 1] = zr
                szc[i - 1] = szcav0
                syc[i - 1] = sycav0
        else:
            wtop = sycav0 * rt2pi
            ybmax = 0.5 * (p.wb - wtop)
            # Fortran yrc(2), yrc(3) -> indices 1, 2
            if ybmax <= 0.0:
                yrc[1] = yrb
            else:
                ysb = -p.ybadj
                if ysb < 0.0:
                    yrc[1] = yrb - max(ysb, -ybmax)
                else:
                    yrc[1] = yrb - min(ysb, ybmax)
            yrc[2] = yrc[1]
            if ipositn <= 2:
                if mode == 3:
                    n1 = 2
                    n2 = 3
                elif mode == 2:
                    n1 = 3
                    n2 = 3
                elif mode == 1:
                    n1 = 2
                    n2 = 2
                # Fortran do i = n1, n2 -> index i - 1
                for i in range(n1, n2 + 1):
                    zrc[i - 1] = 0.0
                    szc[i - 1] = szcav0
                    syc[i - 1] = sycav0
                if (mode == 1 or mode == 3) and xr > 0.0:
                    # Fortran hc(2), szc(2), syc(2) -> index 1
                    _dumz, _dumy, szc[1], syc[1] = wake_xsig(
                        state, xr, float(hc[1]), 0.0, True
                    )
            else:
                n1 = 1
                n2 = 3
                # Fortran zrc(2), zrc(3) -> indices 1, 2
                if xrb >= (p.xlb + p.xlr):
                    zrc[1] = zr
                else:
                    zcav, _wcav = cavity_ht(
                        state, p.hb, p.wb, p.xlb, p.rb, p.xlc, p.xlr, p.hr, xrb
                    )
                    zrc[1] = max(0.0, zr - zcav)
                zrc[2] = zrc[1]
                if mode == 2:
                    qc[1] = 0.0
                    szc[1] = szcav0
                    syc[1] = sycav0
                    szc[2] = szcav0
                    syc[2] = sycav0
                    n2 = 3
                elif mode == 1:
                    _dumz, _dumy, szc[1], syc[1] = wake_xsig(
                        state, xr, float(hc[1]), 0.0, True
                    )
                    n2 = 2
                else:
                    szc[1] = szcav0
                    syc[1] = sycav0
                    szc[2] = szcav0
                    syc[2] = sycav0
                    if xr >= 0.0:
                        _dumz, _dumy, szc[1], syc[1] = wake_xsig(
                            state, xr, float(hc[1]), 0.0, True
                        )
    if n1 == 1 and (xr <= 0.0 or p.fqcav == 1.0):
        n1 = 2
    return fqcav0, n1, n2
