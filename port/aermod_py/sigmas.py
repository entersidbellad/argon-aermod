"""SUBROUTINE SIGY, SIGZ, BID, SZSFCL, RMSSIG (sigmas.f)."""

from __future__ import annotations

import math

from .state import AermodState
from .iblval import locate
from .metext import gintrp


def sigy(state: AermodState, xarg: float) -> None:
    """SUBROUTINE SIGY (sigmas.f)."""
    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        svovru = max(state.SVUMIN, state.SVEFF / state.UEFF)
        tyeff = (state.ZIMECH / (156.0 * state.SVEFF)) * (
            max(state.HE, 0.46) / 0.46
        )
        state.SYAMB = (svovru * xarg) / (
            1.0 + xarg / (2.0 * state.UEFF * tyeff)
        ) ** 0.3

    elif state.UNSTAB:
        svovru = max(state.SVUMIN, state.SVEFFD / state.UEFFD)
        xnodim = svovru * xarg / state.ZI
        denomi = max(state.HS, 0.46)
        betalph = max(78.0 * (0.46 / denomi), 0.7)
        state.SYAMB = (svovru * xarg) / (1.0 + betalph * xnodim) ** 0.3

        state.SYAN = state.SYAMB

        if state.PPF > 0.0:
            svovru = max(state.SVUMIN, state.SVEFF3 / state.UEFF3)
            tyeff3 = (state.ZIMECH / (156.0 * state.SVEFF3)) * (
                max(state.HE3, 0.46) / 0.46
            )
            state.SYA3 = (svovru * xarg) / (
                1.0 + xarg / (2.0 * state.UEFF3 * tyeff3)
            ) ** 0.3
        else:
            state.SYA3 = 0.0


def sigz(state: AermodState, xarg: float) -> None:
    """SUBROUTINE SIGZ (sigmas.f)."""
    if state.STABLE or (state.UNSTAB and state.HS >= state.ZI):
        ttravl = xarg / state.UEFF

        ndxzhe = locate(state.GRIDHT, 1, state.MXGLVL, state.HE)
        # Fortran NDXZHE -> idx = ndxzhe - 1, NDXZHE+1 -> idx + 1
        idx = ndxzhe - 1
        ptp = gintrp(
            float(state.GRIDHT[idx]),
            float(state.GRIDPT[idx]),
            float(state.GRIDHT[idx + 1]),
            float(state.GRIDPT[idx + 1]),
            state.HE,
        )

        if state.TGEFF > 0.0:
            bvfrq = math.sqrt(state.G * state.TGEFF / ptp)
        else:
            bvfrq = 1.0e-10

        if bvfrq < 1.0e-10:
            bvfrq = 1.0e-10

        ztmp = max(state.HS, state.HE, 1.0e-4)

        if state.URBSTAB:
            state.SZAMB = (
                state.SWEFF
                * ttravl
                / math.sqrt(
                    1.0 + state.SWEFF * ttravl * (1.0 / (0.72 * ztmp))
                )
            )
        else:
            state.SZAMB = (
                state.SWEFF
                * ttravl
                / math.sqrt(
                    1.0
                    + state.SWEFF
                    * ttravl
                    * (1.0 / (0.72 * ztmp) + bvfrq / (0.54 * state.SWEFF))
                )
            )

        if state.HE < state.ZI:
            szsfcl(state, xarg)
            sigf = min(state.HE / state.ZI, 1.0)
            state.SZAS = (1.0 - sigf) * state.SZSURF + sigf * state.SZAMB
        else:
            state.SZAS = state.SZAMB

    elif state.UNSTAB:
        if state.PPF < 1.0:
            if not state.SURFAC:
                alphab = 1.0
            else:
                alphab = 0.6 + 0.4 * (state.CENTER / (0.1 * state.ZI))

            state.SZAD1 = alphab * state.BSUB1 * state.WSTAR * xarg / state.UEFFD
            state.SZAD2 = alphab * state.BSUB2 * state.WSTAR * xarg / state.UEFFD

            szsfcl(state, xarg)

            state.SZAD1 = math.sqrt(
                state.SZAD1 * state.SZAD1 + state.SZSURF * state.SZSURF
            )
            state.SZAD2 = math.sqrt(
                state.SZAD2 * state.SZAD2 + state.SZSURF * state.SZSURF
            )
        else:
            state.SZAD1 = 1.0
            state.SZAD2 = 1.0

        state.SZAN1 = state.SZAD1
        state.SZAN2 = state.SZAD2

        if state.PPF > 0.0:
            ttravl = xarg / state.UEFF3
            state.SZA3 = (
                state.SWEFF3
                * ttravl
                / math.sqrt(
                    1.0 + state.SWEFF3 * ttravl * (1.0 / (0.72 * state.HE3))
                )
            )
        else:
            state.SZA3 = 0.0


def bid(state: AermodState) -> None:
    """SUBROUTINE BID (sigmas.f)."""
    # Fortran ISRC -> state.ISRC - 1
    aftsrc_flag = str(state.AFTSRC[state.ISRC - 1]).strip()

    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        if aftsrc_flag == "Y":
            state.SZB = state.PLUME_SPREAD / 5.93
            state.SYB = state.PLUME_SPREAD / 2.28
            state.SZBD = 0.0
            state.SZBN = 0.0
            state.SYB3 = 0.0
            state.SZB3 = 0.0
        else:
            state.SZB = state.BETA2 * state.DHP / state.RTOF2
            state.SYB = state.SZB
            state.SZBD = 0.0
            state.SZBN = 0.0
            state.SYB3 = 0.0
            state.SZB3 = 0.0
    elif state.UNSTAB:
        if aftsrc_flag == "Y":
            state.SZBD = state.PLUME_SPREAD / 5.93
            state.SZBN = state.SZBD
        else:
            state.SZBD = state.BETA2 * state.DHP1 / state.RTOF2
            state.SZBN = state.SZBD

        if state.PPF > 0.0:
            state.SZB3 = state.BETA2 * state.PPF * state.DHP3 / state.RTOF2
        else:
            state.SZB3 = 0.0

        if aftsrc_flag == "Y":
            state.SYB = 2.6 * state.SZBD
            state.SYB3 = state.SZB3
        else:
            state.SYB = state.SZBD
            state.SYB3 = state.SZB3


def szsfcl(state: AermodState, xarg: float) -> None:
    """SUBROUTINE SZSFCL (sigmas.f)."""
    if state.UNSTAB and state.SURFAC:
        state.SZSURF = (
            state.BSUBC
            * (1.0 - 10.0 * (state.CENTER / state.ZI))
            * (state.USTAR / state.UEFFD)
            * (state.USTAR / state.UEFFD)
            * (xarg * xarg / abs(state.OBULEN))
        )
    elif state.STABLE:
        state.SZSURF = (
            (state.RTOF2 / state.RTOFPI)
            * state.USTAR
            * (xarg / state.UEFF)
            * (1.0 + 0.7 * xarg / state.OBULEN) ** (-1.0 * state.THIRD)
        )
    else:
        state.SZSURF = 0.0


def rmssig(state: AermodState) -> None:
    """SUBROUTINE RMSSIG (sigmas.f)."""
    if state.STABLE or (state.UNSTAB and (state.HS >= state.ZI)):
        state.SY = math.sqrt(
            state.SYB * state.SYB
            + state.SYAMB * state.SYAMB
            + state.VSIGY * state.VSIGY
            + state.PLATSY * state.PLATSY
        )
        state.SZ = math.sqrt(
            state.SZB * state.SZB
            + state.SZAS * state.SZAS
            + state.VSIGZ * state.VSIGZ
            + state.PLATSZ * state.PLATSZ
        )

        state.SYN = 0.0
        state.SZD1 = 0.0
        state.SZD2 = 0.0
        state.SZN1 = 0.0
        state.SZN2 = 0.0
        state.SY3 = 0.0
        state.SZ3 = 0.0

    elif state.UNSTAB:
        max_platsyd = max(state.PLATSYD1, state.PLATSYD2)
        max_platsyn = max(state.PLATSYN1, state.PLATSYN2)
        state.SY = math.sqrt(
            state.SYB * state.SYB
            + state.SYAMB * state.SYAMB
            + state.VSIGY * state.VSIGY
            + max_platsyd * max_platsyd
        )
        state.SYN = math.sqrt(
            state.SYB * state.SYB
            + state.SYAN * state.SYAN
            + state.VSYN * state.VSYN
            + max_platsyn * max_platsyn
        )
        state.SZD1 = math.sqrt(
            state.SZBD * state.SZBD
            + state.SZAD1 * state.SZAD1
            + state.VSZD1 * state.VSZD1
            + state.PLATSZD1 * state.PLATSZD1
        )
        state.SZD2 = math.sqrt(
            state.SZBD * state.SZBD
            + state.SZAD2 * state.SZAD2
            + state.VSZD2 * state.VSZD2
            + state.PLATSZD2 * state.PLATSZD2
        )
        state.SZN1 = math.sqrt(
            state.SZBN * state.SZBN
            + state.SZAN1 * state.SZAN1
            + state.VSZN1 * state.VSZN1
            + state.PLATSZN1 * state.PLATSZN1
        )
        state.SZN2 = math.sqrt(
            state.SZBN * state.SZBN
            + state.SZAN2 * state.SZAN2
            + state.VSZN2 * state.VSZN2
            + state.PLATSZN2 * state.PLATSZN2
        )

        if state.PPF > 0.0:
            state.SY3 = math.sqrt(
                state.SYB3 * state.SYB3
                + state.SYA3 * state.SYA3
                + state.PLATSYP * state.PLATSYP
            )
            state.SZ3 = math.sqrt(
                state.SZB3 * state.SZB3
                + state.SZA3 * state.SZA3
                + state.PLATSZP * state.PLATSZP
            )
        else:
            state.SY3 = 0.0
            state.SZ3 = 0.0
