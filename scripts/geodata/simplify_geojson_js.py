"""Ramping-kan file data peta `var Nama = [GeoJSON ...];` untuk Leaflet.

Membulatkan koordinat, membuang ketinggian (z), dan menyederhanakan garis dengan
Douglas–Peucker (toleransi dalam derajat). Nama variabel & struktur tetap sama.

    python scripts/geodata/simplify_geojson_js.py IN.js OUT.js --tolerance 0.0005 --precision 5

Dipakai untuk repository/static/repository/js/batas_provinsi_papua.js (--keep-props WADMPR)
dan garis_pantai_papua.js (--keep-props ""), yang semula 39 MB dan 29 MB.
"""
import argparse
import json
import re


def _perp(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / (dx * dx + dy * dy) ** 0.5


def rdp(points, tol):
    """Douglas–Peucker iteratif (aman untuk garis sangat panjang)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        dmax, idx = 0.0, None
        a, b = points[i], points[j]
        for k in range(i + 1, j):
            d = _perp(points[k], a, b)
            if d > dmax:
                dmax, idx = d, k
        if idx is not None and dmax > tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(points, keep) if k]


def simplify_line(coords, tol, prec, ring=False):
    pts = [(c[0], c[1]) for c in coords]
    out = rdp(pts, tol)
    if ring and len(out) < 4:          # cincin poligon minimal 4 titik
        out = pts[:: max(1, len(pts) // 4)][:3] + [pts[0]] if len(pts) >= 4 else pts
    out = [[round(x, prec), round(y, prec)] for x, y in out]
    dedup = [out[0]] + [p for prev, p in zip(out, out[1:]) if p != prev]
    return dedup


def simplify_geometry(g, tol, prec):
    t, c = g["type"], g["coordinates"]
    if t == "LineString":
        g["coordinates"] = simplify_line(c, tol, prec)
    elif t == "MultiLineString":
        g["coordinates"] = [simplify_line(l, tol, prec) for l in c]
    elif t == "Polygon":
        g["coordinates"] = [simplify_line(r, tol, prec, ring=True) for r in c]
    elif t == "MultiPolygon":
        g["coordinates"] = [[simplify_line(r, tol, prec, ring=True) for r in poly] for poly in c]
    return g


def count_points(obj):
    if isinstance(obj, list) and obj and isinstance(obj[0], (int, float)):
        return 1
    if isinstance(obj, list):
        return sum(count_points(x) for x in obj)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--tolerance", type=float, default=0.0005)
    ap.add_argument("--precision", type=int, default=5)
    ap.add_argument("--keep-props", default=None,
                    help="Atribut yang dipertahankan, dipisah koma; '' = buang semua; default = simpan semua")
    args = ap.parse_args()
    keep = None if args.keep_props is None else [k for k in args.keep_props.split(",") if k]
    text = open(args.src, encoding="utf-8").read()
    m = re.match(r"\s*var\s+(\w+)\s*=\s*", text)
    name = m.group(1)
    data = json.loads(text[m.end():].strip().rstrip(";"))
    before = sum(count_points(f["geometry"]["coordinates"]) for fc in data for f in fc["features"] if f.get("geometry"))
    for fc in data:
        for f in fc["features"]:
            if f.get("geometry"):
                simplify_geometry(f["geometry"], args.tolerance, args.precision)
            if keep is not None:
                f["properties"] = {k: v for k, v in (f.get("properties") or {}).items() if k in keep}
    after = sum(count_points(f["geometry"]["coordinates"]) for fc in data for f in fc["features"] if f.get("geometry"))
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with open(args.dst, "w", encoding="utf-8") as f:
        f.write(f"var {name} = {body};\n")
    print(f"{name}: titik {before:,} -> {after:,}; {len(text)/1e6:.1f} MB -> {len(body)/1e6:.2f} MB")


if __name__ == "__main__":
    main()
