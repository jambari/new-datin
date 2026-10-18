WRS_CODE_MAP = {
    "STAGEOF JAYAPURA":    ["stageof_JAY"],
    "RRI JAYAPURA":        ["rri_kojay"],
    "MAKO LANTAMAL X":     ["kodaeral_x"],
    "BPBD KOTA JAYAPURA":  ["bpbd_kojay"],
    "BBMKG V JAYAPURA":    ["bbmkgv"],
    "BPBD PROVINSI PAPUA": ["BPBD_PROV"],
    "BASARNAS PAPUA":      ["basarnas_jay"],
    "BPBD KAB. JAYAPURA":  ["bpbd_kabjay"],
    "BPBD BIAK NUMFOR":    ["BPBD_BIAK", "bpbd_biak", "bpbd biak"],
    "BASARNAS MERAUKE":    ["BASARNAS_MERAUKE"],
    "BPBD KAB. MIMIKA":    ["bpbd-mimika"],
    # Belum ada log status dari perangkat; isi kode alat bila sudah diketahui.
    "BPBD KAB. WAROPEN":   [],
    "BPBD KAB. SUPIORI":   [],
}

# Stasiun pada laporan bulanan availability (/wrsng/status/report/), sesuai urutan tampil.
# BPBD KAB. MIMIKA tidak dilaporkan, tetapi tetap di WRS_CODE_MAP agar log statusnya
# masih bernama di halaman Status Log.
WRS_REPORT_STATIONS = [
    name for name in WRS_CODE_MAP if name != "BPBD KAB. MIMIKA"
]

CODE_TO_STATION = {
    code: name
    for name, codes in WRS_CODE_MAP.items()
    for code in codes
}
