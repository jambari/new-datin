"""Authoritative station rosters shared across apps.

Many stations are colocated (run both a seismometer and an accelerograph at
the same site), so the single Station.station_type enum can't fully describe
them. Code-level filtering against these explicit lists is the source of
truth for "which stations belong to which sensor view".
"""

ACCELEROGRAPH_STATIONS = [
    'ARKPI', 'ARPI', 'BMPI', 'BTSPI', 'DYPI', 'EDMPI', 'ELMPI', 'FKMPM',
    'GENI', 'JBPI', 'JGPI', 'JMPI', 'KIMPI', 'LJPI', 'MIBPI', 'MMPI',
    'MTJPI', 'MTMPI', 'OBMPI', 'SATPI', 'SKPM', 'SMPI', 'SOMPI', 'TMPI',
    'TRPI', 'WAMI',
]

SEISMIC_STATIONS = [
    'ARPI', 'ARKPI', 'BTSPI', 'DYPI', 'EDMPI', 'ELMPI', 'FKMPM', 'GENI', 'JAY',
    'KIMPI', 'LJPI', 'MIBPI', 'MMPI', 'MTJPI', 'MTMPI', 'OBMPI', 'SATPI', 'SJPM',
    'SKPM', 'SMPI', 'SOMPI', 'SUSPI', 'TRPI', 'UWNPI', 'WAMI', 'WANPI', 'YBYPI',
]
