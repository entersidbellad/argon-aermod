"""PRIME building downwash module state (modules.f: PRIME_PARAMS, PRIME_NUMPARM,
PRIME_DFSN, PRIME_WAKEDAT, PRIME_AMBIENT, PRIME_PLU, PRM2_WAKEDAT).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import TYPE_CHECKING

import numpy as xp

if TYPE_CHECKING:
    from .state import AermodState

# MODULE PRIME_PARAMS
IO5: int = 7
IO6: int = 8

# MODULE PRIME_NUMPARM
MXNW: int = 5000
MXENT: int = 10
MXENTP1: int = MXENT + 1

# MODULE PRIME_WAKEDAT
MXNTR: int = 50

# MODULE PRIME_AMBIENT
MXNZ: int = 100
MXNZP1: int = MXNZ + 1

# MODULE PRM2_WAKEDAT
P2MXNTR: int = 50


@dataclass
class PrimeState:
    """Explicit state holding PRIME module variables and SAVEd locals.

    Note: SAVEd local variables of PRIME units are stored here with fields
    named ``<unit>_<var>``; later chunks add fields using the same naming rule.
    """

    # MODULE PRIME_NUMPARM
    nstep: int = 0
    nent: int = 0
    gravi: float = 0.0
    rgas: float = 0.0
    zmin: float = 0.0
    ds: float = 0.0
    slast: float = 0.0
    rp: float = 0.0
    alphap: xp.ndarray = field(default_factory=lambda: xp.zeros(MXENT, dtype=xp.float64))
    betap: xp.ndarray = field(default_factory=lambda: xp.zeros(MXENT, dtype=xp.float64))
    xcat: xp.ndarray = field(default_factory=lambda: xp.zeros(MXENTP1, dtype=xp.float64))

    # MODULE PRIME_DFSN
    afac: float = 0.0
    xbyrmax: float = 0.0
    wiz0: float = 0.0
    wiy0: float = 0.0
    wfz: float = 0.0
    wfy: float = 0.0
    dua_ua: float = 0.0
    xdecay: float = 0.0
    xdecayi: float = 0.0

    # MODULE PRIME_WAKEDAT
    lrurl: bool = False
    nwak: int = 0
    ncav: int = 0
    hb: float = 0.0
    wb: float = 0.0
    xlb: float = 0.0
    rb: float = 0.0
    hr: float = 0.0
    xlr: float = 0.0
    xlc: float = 0.0
    xbadj: float = 0.0
    ybadj: float = 0.0
    ub: float = 0.0
    urh: float = 0.0
    xwak: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    szwak: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    sywak: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    drwak: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    xcav: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    szcav: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    sycav: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    fqcav: float = 0.0
    vsigy: float = 0.0
    vsigz: float = 0.0
    vsigyc: float = 0.0
    vsigzc: float = 0.0
    zint: float = 0.0
    third: float = 0.0

    # MODULE PRIME_AMBIENT
    nza: int = 0
    uamb: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNZ, dtype=xp.float64))
    ramb: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNZ, dtype=xp.float64))
    dedz: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNZP1, dtype=xp.float64))
    tamb: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNZ, dtype=xp.float64))
    zfacea: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNZP1, dtype=xp.float64))
    zgpta: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNZ, dtype=xp.float64))
    tamb0: float = 0.0
    ramb0: float = 0.0
    adia: float = 0.0
    ptgrad0: float = 0.0

    # MODULE PRIME_PLU
    s: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    r: float = 0.0
    u: float = 0.0
    v: float = 0.0
    w: float = 0.0
    usc: float = 0.0
    phi: float = 0.0
    den: float = 0.0
    tp: float = 0.0

    # MODULE PRM2_WAKEDAT
    zeff_prm2: float = 0.0
    u30: float = 0.0
    sv30: float = 0.0
    sw30: float = 0.0
    xtr_sav: xp.ndarray = field(default_factory=lambda: xp.zeros(P2MXNTR, dtype=xp.float64))
    ztr_sav: xp.ndarray = field(default_factory=lambda: xp.zeros(P2MXNTR, dtype=xp.float64))
    ueff_save: float = 0.0
    sweff_save: float = 0.0
    sveff_save: float = 0.0
    dfsn2call: bool = False

    # DATA-initialized / SAVEd locals for prime_base units (<unit>_<var>)
    fnerf_a: xp.ndarray = field(
        default_factory=lambda: xp.array(
            [
                0.0000430638,
                0.0002765672,
                0.0001520143,
                0.0092705272,
                0.0422820123,
                0.0705230784,
            ],
            dtype=xp.float64,
        )
    )
    fnerf_xcut: float = 3.919206
    fnerfc_a: xp.ndarray = field(
        default_factory=lambda: xp.array(
            [
                0.0000430638,
                0.0002765672,
                0.0001520143,
                0.0092705272,
                0.0422820123,
                0.0705230784,
            ],
            dtype=xp.float64,
        )
    )
    fnerfc_xcutl: float = -3.919206
    fnerfc_xcuth: float = 13.306
    fnerfc_rtpii: float = 0.564189583547756
    rate_alpha0: float = 0.11
    rate_beta0: float = 0.6

    # SAVEd locals for prime_wake units (<unit>_<var>)
    wake_u_turb_z: float = 0.0
    wake_u_turb_zvel_sav: float = 0.0

    # SAVEd locals for prime_rise units (<unit>_<var>)
    prmdelh_hseff: float = 0.0
    prmdelh_reff: float = 0.0
    prmdelh_xtr: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    prmdelh_ytr: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    prmdelh_ztr: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    prmdelh_rtr: xp.ndarray = field(default_factory=lambda: xp.zeros(MXNTR, dtype=xp.float64))
    prmdelh_l_inwake_save: bool = False
    prmdelh_capped: bool = False
    prmdelh_horiz: bool = False

    def emit_debug(
        self,
        state: AermodState,
        sub: str,
        var: str,
        value: float,
        irec: int = 0,
    ) -> None:
        """Emit one PRIME debug row via state.emit_debug."""
        fn = state.emit_debug
        params = inspect.signature(fn).parameters
        mapping = {
            "kurdat": int(state.KURDAT),
            "isrc": int(state.ISRC),
            "irec": int(irec),
            "comp": "PRIME",
            "sub": sub,
            "var": var,
            "name": var,
            "value": float(value),
            "val": float(value),
        }
        kwargs = {k: mapping[k] for k in params if k in mapping}
        if "irec" not in params and hasattr(state, "IREC"):
            old_irec = state.IREC
            state.IREC = int(irec)
            try:
                fn(**kwargs)
            finally:
                state.IREC = old_irec
        else:
            fn(**kwargs)
