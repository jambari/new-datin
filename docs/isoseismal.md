# Peta Isoseismal otomatis

Halaman publik: `/peta-isoseismal/` (daftar) dan `/peta-isoseismal/<slug>/` (detail, mis.
`peta-isoseismal-gempabumi-kab-jayapura-22-mei-2026`). Admin: *Peta Isoseismal* di `/admin/`.

## Alur data

Hanya gempa **dirasakan** yang dibuatkan peta; .189 yang menentukan, .50 tidak mengirim apa pun.

```
.189 new-datin                                              .50 ShakeMap v3
  fetch_bmkg_felt (tiap jam, menit 0) → FeltEarthquake
  katalog gempa terasa=True           → Gempa
        │
  scan_isoseismal_task (tiap jam, menit 10; 7 hari terakhir)
    1. felt_events(): daftar gempa dirasakan (BMKG + katalog, kejadian sama digabung)
    2. ssh host50 find data_MMI/*/output/grid.xml ────────▶  daftar run + waktu ubah grid.xml
    3. cocokkan per gempa: waktu ±90 s, posisi ≤ 1° (dari nama folder run), ambil run terbaru
    4. rsync grid.xml + stationlist.xml ◀──────────────────  hanya bila run baru/berubah
    5. store_shakemap(): grid → .npz, stasiun, titik teramati
    6. generate(): laporan dirasakan → gambar PNG (ulang bila data/laporan berubah)
```

* `ssh host50` adalah terowongan SSH balik dari .50 ke .189 (lihat `~/.ssh/config` di .189).
  Host dan folder bisa diganti lewat `ISOSEISMAL_SHAKEMAP_HOST` / `ISOSEISMAL_SHAKEMAP_DIR` di env.
* Run yang dipakai tercatat di `shakemap_dir` + `shakemap_mtime`; run sama tidak diunduh ulang,
  run baru (koreksi magnitudo, run *composite*) membuat peta digambar ulang.
* Laporan dirasakan: titik `insttype="Observed"` di stationlist ShakeMap, teks BMKG "Dirasakan",
  dan katalog (`terdampak`/`narasi` yang memuat skala MMI). Baris katalog lama ber-origin
  "HH:MM:SS WIT" dan lintang "2.74° LS" ikut dikenali.
* Peta langsung tampil publik; staf bisa *Sembunyikan* atau *Gambar ulang* lewat aksi admin.

## Komponen

| Berkas | Isi |
|---|---|
| `isoseismal/remote.py` | daftar run ShakeMap di .50, pencocokan dengan gempa, unduh rsync |
| `isoseismal/shakemap_io.py` | baca `grid.xml` (kolom MMI → .npz float16) dan `stationlist.xml` (stasiun vs titik `Observed`) |
| `isoseismal/felt.py` | daftar gempa dirasakan, pengurai teks dirasakan ("III Jayapura, II-III Sentani" / "Dirasakan di … III MMI"), gazetir kabupaten & distrik Papua dari `repository/static/repository/js/batas_*_indo.geojson`, alias kota (`ALIASES`) |
| `isoseismal/layout.py` | gambar PNG (matplotlib + tile OSM `reporting.osm`), warna & tabel skala Worden dkk. (2011) seperti template QGIS `BMKG_MMI_Template`; lapisan MMI dipotong ke daratan |
| `isoseismal/services.py` | `sync_felt`, `store_shakemap`, `wilayah_mmi` (MMI grid maks. per kabupaten), `generate` |
| `isoseismal/tasks.py` | `scan_isoseismal_task` |

Tempat yang tidak dikenali tetap tercantum di tabel halaman detail ("lokasi tidak dikenali");
tambahkan ke `ALIASES` di `felt.py` bila sering muncul.

## Isi ulang kejadian lama

```
python manage.py sync_isoseismal --since 2026-01-01
python manage.py sync_isoseismal --since 2026-05-01 --until 2026-05-31
```
