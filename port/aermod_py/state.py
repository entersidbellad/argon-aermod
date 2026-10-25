"""MODULE MAIN1, RLINE_DATA, BUOYANT_LINE (modules.f) state and Fortran intrinsics."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as xp
import glue


def f_nint(x: float) -> int:
    """Fortran NINT / IDNINT: round half away from zero."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def f_int(x: float) -> int:
    """Fortran INT / IDINT: truncate toward zero."""
    return int(math.trunc(x))


def f_idiv(a: int, b: int) -> int:
    """Fortran integer division: truncate toward zero."""
    return int(math.trunc(a / b))


def f_mod_int(a: int, b: int) -> int:
    """Fortran integer MOD(A, B): sign of A."""
    return a - f_idiv(a, b) * b


def f_mod_real(a: float, b: float) -> float:
    """Fortran real MOD(A, B): math.fmod."""
    return math.fmod(a, b)


def f_sign(a: float, b: float) -> float:
    """Fortran DSIGN(A, B): magnitude of A with sign of B."""
    return math.copysign(abs(a), b)


# modules.f DATA GRIDHT (87 levels)
GRIDHT_DATA = (
    0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 14.0, 20.0,
    30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0,
    100.0, 120.0, 140.0, 160.0, 180.0, 200.0, 250.0,
    300.0, 350.0, 400.0, 450.0, 500.0, 550.0, 600.0,
    650.0, 700.0, 750.0, 800.0, 850.0, 900.0, 950.0,
    1000.0, 1050.0, 1100.0, 1150.0, 1200.0, 1250.0,
    1300.0, 1350.0, 1400.0, 1450.0, 1500.0, 1550.0,
    1600.0, 1650.0, 1700.0, 1750.0, 1800.0, 1850.0,
    1900.0, 1950.0, 2000.0, 2100.0, 2200.0, 2300.0,
    2400.0, 2500.0, 2600.0, 2700.0, 2800.0, 2900.0,
    3000.0, 3100.0, 3200.0, 3300.0, 3400.0, 3500.0,
    3600.0, 3700.0, 3800.0, 3900.0, 4000.0, 4100.0,
    4200.0, 4300.0, 4400.0, 4500.0, 4600.0, 4700.0,
    4800.0, 4900.0, 5000.0,
)


@dataclass
class AermodState:
    """Explicit state holding MODULE MAIN1, BUOYANT_LINE, RLINE_DATA variables."""

    project: glue.Project
    met: glue.Met

    # Met file cursor (0-based surface record index)
    sfc_cursor: int = 0
    pfl_cursor: int = 0

    # Output accumulators for glue.Result
    dates_out: list[int] = field(default_factory=list)
    conc_out: list[xp.ndarray] = field(default_factory=list)
    hr_conc: Optional[xp.ndarray] = None
    debug_rows: list[tuple] = field(default_factory=list)
    debug_comp: str = ""
    prev_active_isrc: int = 0

    # Parameters from MAIN1
    NWSCAT: int = 6
    NKST: int = 6
    NHR: int = 24
    NPAIR: int = 100
    NHIANN: int = 10
    NMXPM: int = 10
    MXPLVL: int = 50
    MXGLVL: int = 87
    NYEARS: int = 5

    G: float = 9.80616
    VONKAR: float = 0.4
    GOVRCP: float = 0.00977
    DCTODK: float = 273.16
    BETA1: float = 0.6
    BETA2: float = 0.4
    AT1PT2: float = 1.2
    UMINGR: float = 0.01
    GSIGV: float = 0.073864
    EFOLDH: float = 0.44
    SVUMIN: float = 0.05
    XVAL: float = 0.0
    SPTGMN: float = 0.002
    BSUBC: float = 0.5
    ALPHAR: float = 1.4
    LAMDAY: float = 2.3
    ASUBE: float = 0.1
    REFPOP: float = 2.0e6
    DELTRUR: float = 12.0
    RGAS: float = 8.3145
    AWMA_BETA_ENTRAINCOEFF: float = 0.35
    ALPHAM: float = 0.10
    PAA: float = 1.013e5
    RAA: float = 287.058
    HFUEL: float = 4.3e7
    CPA: float = 1003.0
    NENG: float = 2.0
    NUMSYEFF: float = 4.0
    ALPHA: float = 0.029

    # Mathematical constants (setup.f VARINI)
    PI: float = 0.0
    TWOPI: float = 0.0
    RTOFPI: float = 0.0
    SRT2PI: float = 0.0
    RTOF2: float = 0.0
    RTPIBY2: float = 0.0
    RT2BYPI: float = 0.0
    DTORAD: float = 0.0
    RTODEG: float = 0.0
    THIRD: float = 1.0 / 3.0
    TWOTHIRDS: float = 2.0 / 3.0

    # Tuning/limit variables
    SZCOEF: float = 2.15
    SVMIN: float = 0.2
    WSMIN: float = 0.2828
    FRANMAX: float = 1.0
    FRANMIN: float = 0.0
    SWMIN: float = 0.02
    BIGT: float = 24.0
    MAXDIST: float = 1.0e20
    EXPLIM: float = -50.0

    # File units
    IOUNIT: int = 8
    MFUNIT: int = 19
    MPUNIT: int = 21
    DBGUNT: int = 24
    DBMUNT: int = 25
    PRMDBUNT: int = 27
    ISUMUNT: int = 28
    AWMADWDBUNT: int = 34
    PLATFMDBUNT: int = 36
    URBUNT: int = 37
    URBUNT1: int = 38
    URBUNT2: int = 40

    # Error / status variables
    PATH: str = ""
    DUMMY: str = ""
    FATAL: bool = False
    RUNERR: bool = False
    PFLERR: bool = False
    EOF: bool = False
    L_SkipMessages: bool = False
    ILINE: int = 0
    IBLINE: int = 0
    IOLINE: int = 0
    INOXLINE: int = 0
    IHR_NDX: int = 0
    IYR_NDX: int = 0
    NumHeaders: int = 0
    C_METVER: str = "      "

    ICSTAT: xp.ndarray = field(default_factory=lambda: xp.zeros(50, dtype=xp.int64))
    ISSTAT: xp.ndarray = field(default_factory=lambda: xp.zeros(50, dtype=xp.int64))
    IRSTAT: xp.ndarray = field(default_factory=lambda: xp.zeros(50, dtype=xp.int64))
    IMSTAT: xp.ndarray = field(default_factory=lambda: xp.zeros(50, dtype=xp.int64))
    IOSTAT: xp.ndarray = field(default_factory=lambda: xp.zeros(50, dtype=xp.int64))
    IESTAT: xp.ndarray = field(default_factory=lambda: xp.zeros(50, dtype=xp.int64))

    # Control pathway flags
    DFAULT: bool = False
    CONC: bool = True
    DEPOS: bool = False
    DDEP: bool = False
    WDEP: bool = False
    RURAL: bool = True
    URBAN: bool = False
    NOSTD: bool = False
    NOBID: bool = False
    CLMPRO: bool = True
    MSGPRO: bool = True
    PERIOD: bool = False
    ANNUAL: bool = False
    MONTH: bool = False
    FLAT: bool = True
    ELEV: bool = False
    FLATSRCS: bool = False
    FLGPOL: bool = False
    RSTSAV: bool = False
    RSTINP: bool = False
    DAYTAB: bool = False
    MXFILE: bool = False
    PPFILE: bool = True
    MULTYR: bool = False
    TXFILE: bool = False
    SEASONHR: bool = False
    L_MAXDCONT: bool = False
    EVONLY: bool = False
    PM25AVE: bool = False
    NO2AVE: bool = False
    SO2AVE: bool = False
    NOCHKD: bool = False
    DEBUG: bool = False
    METEORDBG: bool = False
    PRIMEDBG: bool = False
    AWMADWDBG: bool = False
    PLATFMDBG: bool = False
    URBDBUG: bool = False
    L_WARNCHKD: bool = False
    SCIM: bool = False
    SCIMHR: bool = False
    SCIMOUT: bool = False
    FASTAREA: bool = False
    SCREEN: bool = False
    URBSTAB: bool = False
    PRM_FSTREC: bool = False
    PVMRM: bool = False
    PSDCREDIT: bool = False
    OLM: bool = False
    L_UrbanTransition: bool = True
    L_STRMLN_BLDG: bool = False
    L_RECT_BLDG: bool = False
    L_AWMA_Ueff: bool = False
    L_AWMA_UTurb: bool = False
    L_AWMA_ENTRAIN: bool = False
    L_AWMA_UTurbHX: bool = False
    L_ORD_Ueff: bool = False
    L_ORD_Turb: bool = False
    L_ORD_Cav: bool = False
    ARM2: bool = False
    GRSM: bool = False
    RUNTTRM: bool = False
    RUNTTRM2: bool = False
    HBPLUME: bool = False
    HBPDBG: bool = False
    L_EFFSIGY: bool = False
    L_VECTORWS: bool = False
    L_AdjUstar: bool = False
    L_BULKRN: bool = False
    L_UserFRANmax: bool = False
    L_UserFRANmin: bool = False
    L_PBal: bool = False
    L_TurbData: bool = False
    L_Got_SigA: bool = False
    L_Got_SigW: bool = False
    L_OldMetVer: bool = False
    L_NAD_ADJ_Flags: bool = False
    L_LeapYear: bool = False
    L_DayOfWeekOpts: bool = False
    RESET_SA: bool = False
    RESET_SW: bool = False

    # SAVEd locals in PFLCNV
    N_Got_SigA: int = 0
    N_Got_SigW: int = 0
    N_Turb_Warn: int = 0
    L_Turb_Warn: bool = False

    # Chemistry / background flags and values
    POLLUT: str = ""
    O3CONC: float = 0.0
    O3BACK: xp.ndarray = field(default_factory=lambda: xp.full(6, -999.0, dtype=xp.float64))
    O3SECT: xp.ndarray = field(default_factory=lambda: xp.zeros(6, dtype=xp.float64))
    O3MISS: bool = False
    L_O3Sector: bool = False
    L_O3Hourly: bool = False
    L_O3VAL: xp.ndarray = field(default_factory=lambda: xp.zeros(6, dtype=bool))
    L_O3VALUES: xp.ndarray = field(default_factory=lambda: xp.zeros(6, dtype=bool))
    NUMO3Sects: int = 1
    IO3SECT: int = 0

    NOXBGCONC: float = 0.0
    NOXBACK: xp.ndarray = field(default_factory=lambda: xp.full(6, -999.0, dtype=xp.float64))
    NOXSECT: xp.ndarray = field(default_factory=lambda: xp.zeros(6, dtype=xp.float64))
    L_NOXSector: bool = False
    L_NOxHourly: bool = False
    L_NOXVALUE: xp.ndarray = field(default_factory=lambda: xp.zeros(6, dtype=bool))
    L_NOX_VALS: xp.ndarray = field(default_factory=lambda: xp.zeros(6, dtype=bool))
    NumNOxSects: int = 1
    INOXSECT: int = 0

    L_BACKGRND: bool = False
    L_BGHourly: bool = False
    L_BGSector: bool = False
    L_BGValues: xp.ndarray = field(default_factory=lambda: xp.zeros(6, dtype=bool))
    BGCONC: float = 0.0
    BGSECT: xp.ndarray = field(default_factory=lambda: xp.zeros(6, dtype=xp.float64))
    NUMBGSects: int = 1
    IBGSECT: int = 0

    # Array dimensions & counts
    NSRC: int = 0
    NUMSRC: int = 0
    NUMREC: int = 0
    NUMGRP: int = 1
    NUMAVE: int = 1
    NUMTYP: int = 1
    NSEC: int = 0
    NURB: int = 0
    NUMURB: int = 0
    IEVENT: int = 0
    IPAIR: int = 0
    FULLHRQ: int = 0
    HOURLY: bool = False
    SUMMFILE: bool = False

    # Source arrays
    SRCID: Optional[xp.ndarray] = None
    SRCTYP: Optional[xp.ndarray] = None
    AXS: Optional[xp.ndarray] = None
    AYS: Optional[xp.ndarray] = None
    AZS: Optional[xp.ndarray] = None
    AQS: Optional[xp.ndarray] = None
    AHS: Optional[xp.ndarray] = None
    ATS: Optional[xp.ndarray] = None
    AVS: Optional[xp.ndarray] = None
    ADS: Optional[xp.ndarray] = None
    ADSFACT: Optional[xp.ndarray] = None
    ASYINI: Optional[xp.ndarray] = None
    ASZINI: Optional[xp.ndarray] = None
    L_FLATSRC: Optional[xp.ndarray] = None
    L_HRLYSIG: Optional[xp.ndarray] = None
    NDXSTK: Optional[xp.ndarray] = None
    QFLAG: Optional[xp.ndarray] = None
    QFACT: Optional[xp.ndarray] = None
    ADSBH: Optional[xp.ndarray] = None
    ADSBW: Optional[xp.ndarray] = None
    ADSBL: Optional[xp.ndarray] = None
    ADSXADJ: Optional[xp.ndarray] = None
    ADSYADJ: Optional[xp.ndarray] = None
    IGROUP: Optional[xp.ndarray] = None
    AFTSRC: Optional[xp.ndarray] = None
    URBSRC: Optional[xp.ndarray] = None
    EVAL: Optional[xp.ndarray] = None
    OSPLAT: Optional[xp.ndarray] = None
    INPD: Optional[xp.ndarray] = None
    HOUREMISARRAY: Optional[xp.ndarray] = None
    AAFR: Optional[xp.ndarray] = None
    ABA: Optional[xp.ndarray] = None
    ABH: Optional[xp.ndarray] = None
    ABL: Optional[xp.ndarray] = None
    ABW: Optional[xp.ndarray] = None
    ABYPR: Optional[xp.ndarray] = None
    AFP: Optional[xp.ndarray] = None
    AMFUEL: Optional[xp.ndarray] = None
    ARPWR: Optional[xp.ndarray] = None
    ASRCANGLE: Optional[xp.ndarray] = None
    ATHRUST: Optional[xp.ndarray] = None
    AVAA: Optional[xp.ndarray] = None
    HENRY: Optional[xp.ndarray] = None
    PLATHB: Optional[xp.ndarray] = None
    PLATWB: Optional[xp.ndarray] = None
    EMIFAC: Optional[xp.ndarray] = None
    APDIAM: Optional[xp.ndarray] = None
    APHI: Optional[xp.ndarray] = None
    APDENS: Optional[xp.ndarray] = None
    AVGRAV: Optional[xp.ndarray] = None
    ATSTOP: Optional[xp.ndarray] = None
    AXINIT: Optional[xp.ndarray] = None
    AYINIT: Optional[xp.ndarray] = None
    AANGLE: Optional[xp.ndarray] = None
    AXVERT: Optional[xp.ndarray] = None
    AYVERT: Optional[xp.ndarray] = None
    AXCNTR: Optional[xp.ndarray] = None
    AYCNTR: Optional[xp.ndarray] = None
    NVERTS: Optional[xp.ndarray] = None
    AALPHA: Optional[xp.ndarray] = None
    APDEFF: Optional[xp.ndarray] = None
    IURBGRP: Optional[xp.ndarray] = None
    URBPOP: Optional[xp.ndarray] = None
    URBZ0: Optional[xp.ndarray] = None
    VDEP: Optional[xp.ndarray] = None
    WASHOUT: Optional[xp.ndarray] = None

    # Receptor arrays
    AXR: Optional[xp.ndarray] = None
    AYR: Optional[xp.ndarray] = None
    AZELEV: Optional[xp.ndarray] = None
    AZHILL: Optional[xp.ndarray] = None
    AZFLAG: Optional[xp.ndarray] = None

    # Averaging / output arrays
    KAVE: Optional[xp.ndarray] = None
    IDYTAB: Optional[xp.ndarray] = None
    ITOXFL: Optional[xp.ndarray] = None
    ITXUNT: Optional[xp.ndarray] = None
    ISEAHR: Optional[xp.ndarray] = None

    # Deposition / decay scalars
    LDPART: bool = False
    LWPART: bool = False
    LDGAS: bool = False
    LWGAS: bool = False
    LUSERVD: bool = False
    USERVD: float = 0.0
    VDEPG: float = 0.0
    ZRDEP: float = 0.0
    ZSUBP: float = 0.0
    FRACSAT: float = 0.0
    DENOM: float = 0.0
    DECOEF: float = 0.0
    Wold: float = 0.0
    Wnew: float = 0.0
    f2: float = 0.0
    EsTa: float = 0.0

    # Meteorology pathway variables
    METINP: str = ""
    PROINP: str = ""
    METFRM: str = "FREE"
    PROFRM: str = "FREE"
    SFNAME: str = ""
    UANAME: str = ""
    IDSURF: int = 0
    IDUAIR: int = 0
    ISYEAR: int = 0
    IUYEAR: int = 0
    ISDATE: int = 0
    IEDATE: int = 2147123124
    ISJDAY: int = 0
    IEJDAY: int = 0
    ISYR: int = 0
    ISMN: int = 0
    ISDY: int = 0
    ISHR: int = 0
    NDAYS: int = 0
    INCRST: int = 1
    ISTRT_CENT: int = 19
    ISTRT_WIND: int = 50
    NREGSTART: int = 0
    NREGINT: int = 0
    IFIRSTHR: int = 0
    NSKIPTOT: int = 0
    IMETMSG: int = 0
    ROTANG: float = 0.0
    ZBASE: float = 0.0
    TURBOPTS: xp.ndarray = field(default_factory=lambda: xp.zeros(9, dtype=bool))
    IPROC: xp.ndarray = field(default_factory=lambda: xp.ones(366, dtype=xp.int64))
    IPROCL: xp.ndarray = field(default_factory=lambda: xp.ones(366, dtype=xp.int64))
    UCAT: xp.ndarray = field(
        default_factory=lambda: xp.array([1.54, 3.09, 5.14, 8.23, 10.8], dtype=xp.float64)
    )

    # Hourly met variables
    CLMHR: bool = False
    MSGHR: bool = False
    UNSTAB: bool = False
    NEUTRL: bool = False
    STABLE: bool = False
    ENDMON: bool = False
    METHDR: bool = False
    IHOUR: int = 0
    IYEAR: int = 0
    IMONTH: int = 0
    IDAY: int = 0
    KURDAT: int = 0
    JDAY: int = 0
    ISEAS: int = 0
    KHOUR: int = 0
    KYEAR: int = 0
    KMONTH: int = 0
    KDAY: int = 0
    KURPFL: int = 0
    NTOTHRS: int = 0
    IPHOUR: int = 0
    IPYEAR: int = 0
    IPDATE: int = 0
    IPCODE: int = 0
    NCLOUD: int = 0
    KST: int = 4
    IYR: int = 0
    IDAY_OF_WEEK: int = 1
    IDAY_OF_WEEK7: int = 1
    NPLVLS: int = 0
    NTGLVL: int = 0
    JDAY_PREV: int = 0
    FULLDATE: int = 0
    NUMYRS: int = 0
    NREMAIN: int = 0
    NDX4ZI: int = 0
    IENDHOUR: int = 0
    IENDDY: int = 0
    IENDMN: int = 0

    SFCHF: float = 0.0
    USTAR: float = 0.0
    WSTAR: float = 0.0
    VPTGZI: float = 0.0
    ZICONV: float = 0.0
    ZIMECH: float = 0.0
    OBULEN: float = 0.0
    SFCZ0: float = 0.0
    BOWEN: float = 0.0
    ALBEDO: float = 0.0
    UREF: float = 0.0
    WDREF: float = 0.0
    UREFHT: float = 0.0
    TA: float = 0.0
    TREFHT: float = 0.0
    ZI: float = 0.0
    AFV: float = 0.0
    BVF: float = 0.0
    BVPRIM: float = 0.0
    ZIRUR: float = 0.0
    PRATE: float = 0.0
    PREC1: float = 0.0
    PREC2: float = 0.0
    TOTAL_PRECIP: float = 0.0
    RURUSTR: float = 0.0
    RUROBULEN: float = 0.0
    RH: float = 0.0
    SFCP: float = 0.0
    QSW: float = 0.0
    ZICONVN: float = -999.0
    ZIMECHN: float = -999.0
    TG4PFL: float = 0.0
    TG4XTR: float = 0.0
    THSTAR: float = 0.0
    SVAVG: float = 0.0
    SWAVG: float = 0.0
    UAVG: float = 0.0
    SVATZI: float = 0.0
    SWATZI: float = 0.0
    UATZI: float = 0.0
    PTATZI: float = 0.0
    SWRMAX: float = 0.0

    IFLAG: xp.ndarray = field(default_factory=lambda: xp.zeros(50, dtype=xp.int64))
    PFLHT: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))
    PFLWD: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))
    PFLWS: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))
    PFLTA: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))
    PFLSA: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))
    PFLSW: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))
    PFLSV: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))
    PFLTG: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))
    PFLTGZ: xp.ndarray = field(default_factory=lambda: xp.full(50, -99.0, dtype=xp.float64))

    GRIDHT: xp.ndarray = field(
        default_factory=lambda: xp.array(GRIDHT_DATA, dtype=xp.float64)
    )
    GRIDWD: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRIDWS: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRIDSW: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRIDSV: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRIDTG: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRIDPT: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRIDRHO: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRIDEPS: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    RL_GRIDWS: xp.ndarray = field(default_factory=lambda: xp.zeros((87, 3), dtype=xp.float64))

    GRDSWR: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRDSVR: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRDTGR: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRDPTR: xp.ndarray = field(default_factory=lambda: xp.full(87, -99.0, dtype=xp.float64))
    GRDSWU: Optional[xp.ndarray] = None
    GRDSVU: Optional[xp.ndarray] = None
    GRDTGU: Optional[xp.ndarray] = None
    GRDPTU: Optional[xp.ndarray] = None
    ZIURB: Optional[xp.ndarray] = None
    URBWSTR: Optional[xp.ndarray] = None
    URBUSTR: Optional[xp.ndarray] = None
    URBOBULEN: Optional[xp.ndarray] = None
    L_MorningTrans: Optional[xp.ndarray] = None

    # Calculation variables
    CALCS: bool = False
    WAKE: bool = False
    SURFAC: bool = False
    IREC: int = 0
    ISRC: int = 0
    IGRP: int = 0
    IAVE: int = 0
    ITYP: int = 0
    NPD: int = 0
    IFVSEC: int = 0
    IUCAT: int = 0
    IURB: int = 0
    CMETH: int = 0
    IVERT: int = 0
    NVERT: int = 0

    XS: float = 0.0
    YS: float = 0.0
    ZS: float = 0.0
    QS: float = 0.0
    HS: float = 0.0
    DS: float = 0.0
    VS: float = 0.0
    TS: float = 0.0
    SYINIT: float = 0.0
    SZINIT: float = 0.0
    XINIT: float = 0.0
    YINIT: float = 0.0
    ANGLE: float = 0.0
    XCNTR: float = 0.0
    YCNTR: float = 0.0
    DSFACT: float = 1.0
    DSBH: float = 0.0
    DSBW: float = 0.0
    DSBL: float = 0.0
    XADJ: float = 0.0
    YADJ: float = 0.0
    B_SUBS: float = 0.0
    B_SUBL: float = 0.0
    RSCALE: float = 0.0
    D: float = 1.0
    WDSIN: float = 0.0
    WDCOS: float = 0.0
    MFUEL: float = 0.0
    THRUST: float = 0.0
    VAA: float = 0.0
    AFR: float = 0.0
    BYPR: float = 0.0
    SRCANGLE: float = 0.0
    RPWR: float = 0.0
    PLUME_SPREAD: float = 0.0
    PALPHA: float = 0.0
    PDEFF: float = 0.0
    PITLEN: float = 0.0
    PITWID: float = 0.0
    EMIHGT: float = 0.0
    BL: float = 0.0
    BW: float = 0.0
    BH: float = 0.0
    BA: float = 0.0

    # Platform downwash variables
    AC: float = 0.0
    BC: float = 0.0
    PLATSY: float = 0.0
    PLATSZ: float = 0.0
    PLATSYD1: float = 0.0
    PLATSZD1: float = 0.0
    PLATSYD2: float = 0.0
    PLATSZD2: float = 0.0
    PLATSYN1: float = 0.0
    PLATSZN1: float = 0.0
    PLATSYN2: float = 0.0
    PLATSZN2: float = 0.0
    PLATSYP: float = 0.0
    PLATSZP: float = 0.0
    DHP3PLAT: float = 0.0

    # Plume & dispersion scalars
    WQCORG: float = 1.0
    DQCORG: float = 1.0
    XR: float = 0.0
    YR: float = 0.0
    X: float = 0.0
    Y: float = 0.0
    ZELEV: float = 0.0
    ZFLAG: float = 0.0
    ZR: float = 0.0
    ZEFF: float = 0.0
    DISTR: float = 0.0
    ZHILL: float = 0.0
    HCRIT: float = 0.0
    ZRT: float = 0.0
    XDIST: float = 0.0
    HE: float = 0.0
    HSP: float = 0.0
    HEDHH: float = 0.0
    HED1: float = 0.0
    HED2: float = 0.0
    HEN1: float = 0.0
    HEN2: float = 0.0
    HE3: float = 0.0
    HPEN: float = 0.0
    HSBL: float = 0.0
    FM: float = 0.0
    FB: float = 0.0
    DHF: float = 0.0
    DHFAER: float = 0.0
    DHP: float = 0.0
    DHP1: float = 0.0
    DHP2: float = 0.0
    DHP3: float = 0.0
    XMAX: float = 0.0
    DHCRIT: float = 0.0
    HTEFF: float = 0.0
    CENTER: float = 0.0
    HESETL: float = 0.0
    HE3SETL: float = 0.0
    HV: float = 0.0
    US: float = 0.0
    SVS: float = 0.0
    SWS: float = 0.0
    TGS: float = 0.0
    PTS: float = 0.0
    UP: float = 0.0
    WDIR: float = 0.0
    QTK: float = 0.0
    PPF: float = 0.0
    PSUBS: float = 0.0
    SY: float = 0.0
    SYB: float = 0.0
    SYN: float = 0.0
    SY3: float = 0.0
    SZ: float = 0.0
    SYAMB: float = 0.0
    SZAMB: float = 0.0
    SZAS: float = 0.0
    SZAD1: float = 0.0
    SZAD2: float = 0.0
    SZAN1: float = 0.0
    SZAN2: float = 0.0
    SYAN: float = 0.0
    SZA3: float = 0.0
    SZB: float = 0.0
    SZBD: float = 0.0
    SZBN: float = 0.0
    SZ3: float = 0.0
    SZD1: float = 0.0
    SZD2: float = 0.0
    SZN1: float = 0.0
    SZN2: float = 0.0
    SZSURF: float = 0.0
    SYA3: float = 0.0
    SYB3: float = 0.0
    SZB3: float = 0.0
    VSY3: float = 0.0
    VSIGY: float = 0.0
    VSIGZ: float = 0.0
    VSYN: float = 0.0
    VSZD1: float = 0.0
    VSZD2: float = 0.0
    VSZN1: float = 0.0
    VSZN2: float = 0.0
    VSZ3: float = 0.0
    TGP: float = 0.0
    SVP: float = 0.0
    SWP: float = 0.0
    PPFN: float = 1.0
    ZIN: float = 0.0
    ZIAVG: float = 0.0
    HHTOP: float = 0.0
    HTOPDIF: float = 0.0
    HHBOT: float = 0.0
    PPWID: float = 0.0
    SZ3DBG: float = 0.0

    FSUBY: float = 0.0
    FSUBYD: float = 0.0
    FSUBYN: float = 0.0
    FSUBY3: float = 0.0
    FSUBZ: float = 0.0
    FSUBZD: float = 0.0
    FSUBZN: float = 0.0
    FSUBZ3: float = 0.0
    PHEE: float = 0.0
    FOPT: float = 0.0
    CWRAP: float = 0.0
    CLIFT: float = 0.0
    UEFF: float = 0.0
    SVEFF: float = 0.0
    SWEFF: float = 0.0
    TGEFF: float = 0.0
    UEFFD: float = 0.0
    SVEFFD: float = 0.0
    SWEFFD: float = 0.0
    UEFFN: float = 0.0
    SVEFFN: float = 0.0
    SWEFFN: float = 0.0
    UEFF3: float = 0.0
    SVEFF3: float = 0.0
    SWEFF3: float = 0.0
    TGEFF3: float = 0.0
    EPSEFF: float = 0.0
    EPSEFFD: float = 0.0
    EPSEFF3: float = 0.0
    XMIXED: float = 0.0
    XFINAL: float = 0.0
    ZMIDMX: float = 0.0
    SYEFF: float = 0.0

    SKEW: float = 0.0
    R: float = 0.0
    ALPHPD: float = 0.0
    BETAPD: float = 0.0
    ASUB1: float = 0.0
    ASUB2: float = 0.0
    BSUB1: float = 0.0
    BSUB2: float = 0.0
    LAMDA1: float = 0.0
    LAMDA2: float = 0.0
    GAMFACT: float = 0.0
    CHI_TTRAVPLM: float = 0.0
    CHI_TTRAVPAN: float = 0.0
    CHI_TTRAVAER: float = 0.0
    CHI_TTRAVPRM: float = 0.0
    UCHM: float = 0.0
    PRMVAL_Src1: float = 0.0

    # Working / result arrays
    PDIAM: Optional[xp.ndarray] = None
    PHI: Optional[xp.ndarray] = None
    PDENS: Optional[xp.ndarray] = None
    VGRAV: Optional[xp.ndarray] = None
    TSTOP: Optional[xp.ndarray] = None
    WQCOR: Optional[xp.ndarray] = None
    DQCOR: Optional[xp.ndarray] = None
    XVERT: Optional[xp.ndarray] = None
    YVERT: Optional[xp.ndarray] = None
    AWDSIN: Optional[xp.ndarray] = None
    AWDCOS: Optional[xp.ndarray] = None
    AAFV: Optional[xp.ndarray] = None
    HRVAL: Optional[xp.ndarray] = None
    AERVAL: Optional[xp.ndarray] = None
    PRMVAL: Optional[xp.ndarray] = None
    AVEVAL: Optional[xp.ndarray] = None
    ANNVAL: Optional[xp.ndarray] = None
    SHVALS: Optional[xp.ndarray] = None
    NUMHRS: Optional[xp.ndarray] = None
    NUMCLM: Optional[xp.ndarray] = None
    NUMMSG: Optional[xp.ndarray] = None
    NSEAHR: xp.ndarray = field(default_factory=lambda: xp.zeros((4, 24), dtype=xp.int64))
    NSEACM: xp.ndarray = field(default_factory=lambda: xp.zeros((4, 24), dtype=xp.int64))
    IANHRS: int = 0
    IANCLM: int = 0
    IANMSG: int = 0

    # BUOYANT_LINE / RLINE_DATA module variables
    L_BLSOURCE: bool = False
    NUMBLGRPS: int = 0
    BLTA: float = 0.0
    BL_UREF: float = 0.0
    RLPROCESSED: bool = False
    I_ALPHA: int = 0

    @classmethod
    def from_setup(
        cls,
        project: glue.Project,
        met: glue.Met,
        setup: dict,
        *,
        debug: bool = False,
    ) -> AermodState:
        """Create AermodState from glue.Project, glue.Met, and setup dict."""
        st = cls(project=project, met=met)

        # Populate case-insensitive mapping from setup keys to dataclass fields
        field_map = {k.upper(): k for k in cls.__dataclass_fields__}
        for k, v in setup.items():
            ku = k.upper()
            if ku in field_map:
                attr = field_map[ku]
                if isinstance(v, xp.ndarray):
                    setattr(st, attr, v.copy())
                else:
                    setattr(st, attr, v)

        # Derived constants from VARINI (setup.f)
        st.RTODEG = 180.0 / st.PI
        st.THIRD = 1.0 / 3.0
        st.TWOTHIRDS = 2.0 / 3.0

        # Project-level variables
        st.FLAT = bool(project.FLAT)
        st.FLATSRCS = bool(project.ELEV)
        st.FLGPOL = bool(project.FLGPOL)
        st.ISDATE = int(project.ISDATE)

        # Extract ISYEAR from ME SURFDATA card if available
        me_cards = project.cards.get("ME", [])
        for toks in me_cards:
            if toks and toks[0].upper() == "SURFDATA" and len(toks) >= 3:
                yy = f_nint(float(toks[2]))
                if yy <= 99:
                    yy = (1900 if yy >= 50 else 2000) + yy
                st.ISYEAR = yy
                break

        # Allocate runtime arrays
        nsrc = st.NUMSRC
        nrec = st.NUMREC
        ngrp = st.NUMGRP
        nave = st.NUMAVE
        ntyp = st.NUMTYP

        st.HRVAL = xp.zeros(ntyp, dtype=xp.float64)
        st.AERVAL = xp.zeros(ntyp, dtype=xp.float64)
        st.PRMVAL = xp.zeros(ntyp, dtype=xp.float64)
        st.AVEVAL = xp.zeros((nrec, ngrp, nave, ntyp), dtype=xp.float64)
        st.ANNVAL = xp.zeros((nrec, ngrp, ntyp), dtype=xp.float64)
        if st.SEASONHR or xp.any(st.ISEAHR == 1):
            st.SHVALS = xp.zeros((nrec, ngrp, 4, 24, ntyp), dtype=xp.float64)
        st.NUMHRS = xp.zeros(nave, dtype=xp.int64)
        st.NUMCLM = xp.zeros(nave, dtype=xp.int64)
        st.NUMMSG = xp.zeros(nave, dtype=xp.int64)
        st.AWDSIN = xp.zeros(nsrc, dtype=xp.float64)
        st.AWDCOS = xp.zeros(nsrc, dtype=xp.float64)
        st.AAFV = xp.zeros(nsrc, dtype=xp.float64)
        st.hr_conc = xp.zeros(nrec, dtype=xp.float64)

        if st.NURB > 0:
            st.GRDSWU = xp.full((st.MXGLVL, st.NURB), -99.0, dtype=xp.float64)
            st.GRDSVU = xp.full((st.MXGLVL, st.NURB), -99.0, dtype=xp.float64)
            st.GRDTGU = xp.full((st.MXGLVL, st.NURB), -99.0, dtype=xp.float64)
            st.GRDPTU = xp.full((st.MXGLVL, st.NURB), -99.0, dtype=xp.float64)
            st.ZIURB = xp.zeros(st.NURB, dtype=xp.float64)
            st.URBWSTR = xp.zeros(st.NURB, dtype=xp.float64)
            st.URBUSTR = xp.zeros(st.NURB, dtype=xp.float64)
            st.URBOBULEN = xp.zeros(st.NURB, dtype=xp.float64)
            st.L_MorningTrans = xp.zeros(st.NURB, dtype=bool)

        if debug:
            st.DEBUG = True
            st.METEORDBG = True
            if st.NSEC > 0:
                st.PRIMEDBG = True

        return st

    def emit_debug(
        self,
        isrc: int,
        irec: int,
        comp: str,
        sub: str,
        var: str,
        value: float | int,
    ) -> None:
        """Append one debug row (KURDAT, ISRC, IREC, comp, sub, var, value)."""
        self.debug_rows.append(
            (int(self.KURDAT), int(isrc), int(irec), comp, sub, var, float(value))
        )
