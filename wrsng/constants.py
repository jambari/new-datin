WRS_CODE_MAP = {
    "STAGEOF JAYAPURA":    ["stageof_JAY"],
    "RRI JAYAPURA":        ["rri_kojay"],
    "MAKO LANTAMAL X":     ["kodaeral_x"],
    "BPBD KOTA JAYAPURA":  ["bpbd_kojay"],
    "BBMKG V JAYAPURA":    ["bbmkgv"],
    "BPBD PROVINSI PAPUA": ["BPBD_PROV"],
    "BASARNAS PAPUA":      ["basarnas_jay"],
    "BPBD KAB. JAYAPURA":  ["bpbd_kabjay"],
    "BPBD BIAK NUMFOR":    ["BPBD_BIAK"],
    "BPBD WAROPEN":        [],
    "BASARNAS MERAUKE":    ["BASARNAS_MERAUKE"],
    "BPBD KAB. MIMIKA":    ["bpbd-mimika"],
}

CODE_TO_STATION = {
    code: name
    for name, codes in WRS_CODE_MAP.items()
    for code in codes
}
