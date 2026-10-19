"""Bangun tile XYZ basemap relief bergaya GMT untuk Leaflet (sekali jalan, bukan per permintaan).

Gaya sama dengan peta seismisitas GMT (scripts/gmt/seismicity_map.py): GMT Earth Relief, palet
dem2 0–5000 m, iluminasi dari barat laut hanya di darat, laut berwarna datar.

Dua piramida dalam satu folder:
  * dunia    z0–5  dari earth_relief_05m (agar tampilan jauh tidak kosong)
  * regional z6–10 dari earth_relief_15s untuk Papua dan sekitarnya

Hanya memakai CLI GMT 6 dan GDAL (gdal2tiles.py), tidak perlu PyGMT:
    python3 build_relief_tiles.py /var/www/html/media/tiles/gmt_relief
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SEA_RGB = "169/211/234"                       # #a9d3ea, sama dengan peta GMT
REGION = "122/152/-13/6"                      # Papua dan sekitarnya
WORLD = "-180/180/-85/85"                     # batas Web Mercator


def gmt(*args, cwd):
    subprocess.run(["gmt", *args], check=True, cwd=cwd)


def render(region, resolution, out_tif, tmp):
    """Grid relief → GeoTIFF RGB bergaya GMT (koordinat geografis)."""
    name = Path(out_tif).stem
    relief, grad, shade, cpt = (f"{name}_relief.nc", f"{name}_grad.nc", f"{name}_shade.nc", f"{name}.cpt")
    gmt("grdcut", f"@earth_relief_{resolution}_p", f"-R{region}", f"-G{relief}", cwd=tmp)
    gmt("grdgradient", relief, "-A315", "-Nt0.7", f"-G{grad}", cwd=tmp)
    gmt("grdmath", grad, relief, "0", "GT", "MUL", "=", shade, cwd=tmp)        # laut datar: tanpa bayangan
    with open(Path(tmp) / cpt, "w") as f:
        subprocess.run(["gmt", "makecpt", "-Cdem2", "-T0/5000", "-M", f"--COLOR_BACKGROUND={SEA_RGB}",
                        f"--COLOR_NAN={SEA_RGB}"], check=True, cwd=tmp, stdout=f)
    # -JX wajib untuk -A; hasilnya GeoTIFF beresolusi grid dengan koordinat geografis.
    gmt("grdimage", relief, f"-C{cpt}", f"-I{shade}", "-JX10c", f"-A{out_tif}", f"--COLOR_BACKGROUND={SEA_RGB}",
        f"--COLOR_NAN={SEA_RGB}", cwd=tmp)


def tiles(src, out, zoom, procs=4):
    # numpy 2.x di ~/.local tidak cocok dengan binding GDAL sistem (dibangun untuk numpy 1.x).
    env = {**os.environ, "PYTHONNOUSERSITE": "1"}
    subprocess.run(["gdal2tiles.py", "--xyz", "-z", zoom, "-w", "none", "-r", "bilinear", "-s", "EPSG:4326",
                    f"--processes={procs}", "--tiledriver=WEBP", "--webp-quality=85", "-q",
                    str(src), str(out)], check=True, env=env)


def main(out):
    out = Path(out)
    tmp = Path(tempfile.mkdtemp(prefix="gmt_tiles_"))
    try:
        for region, res, zoom, name in ((WORLD, "05m", "0-5", "world"), (REGION, "15s", "6-10", "papua")):
            tif = tmp / f"{name}.tif"
            render(region, res, tif, tmp)
            tiles(tif, out, zoom)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{sum(1 for _ in out.rglob('*.webp'))} tile di {out}")


if __name__ == "__main__":
    main(sys.argv[1])
