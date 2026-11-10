# Peta Isoseismal otomatis

Halaman publik: `/peta-isoseismal/` (daftar) dan `/peta-isoseismal/<slug>/` (detail, mis.
`peta-isoseismal-gempabumi-kab-jayapura-22-mei-2026`). Admin: *Peta Isoseismal* di `/admin/`.

## Alur data

```
.50 ShakeMap v3 (data_MMI/<WIB>_…/output/)          .189 new-datin
  grid.xml, stationlist.xml ──datin_push.py (2e)──▶ media/shakemaps/<WIB>/
                                                     ingest_pushed_event <WIB>
                                                       └─ isoseismal.services.store_shakemap
                                                            grid.xml → .npz (dihapus), stasiun, titik teramati
                                                       └─ generate_isoseismal_task.delay(<WIB>)
  fetch_bmkg_felt (tiap jam) ─▶ FeltEarthquake.dirasakan ┐
  katalog gempa (terasa=True) ─▶ Gempa.terdampak        ├─ isoseismal.felt.collect_felt
  stationlist insttype="Observed" (composite)           ┘
                                                     scan_isoseismal_task (menit 10 tiap jam, 7 hari terakhir)
                                                       gambar ulang bila laporan dirasakan baru/berubah
```

* Peta hanya digambar untuk gempa **dirasakan** (ada titik teramati ShakeMap, teks BMKG
  "Dirasakan", atau katalog stasiun `terasa=True` dengan skala MMI di `terdampak`/`narasi`).
* Peta langsung tampil publik; staf bisa *Sembunyikan* atau *Gambar ulang* lewat aksi admin.

## Komponen

| Berkas | Isi |
|---|---|
| `isoseismal/shakemap_io.py` | baca `grid.xml` (kolom MMI → .npz float16) dan `stationlist.xml` (stasiun vs titik `Observed`) |
| `isoseismal/felt.py` | pengurai teks dirasakan ("III Jayapura, II-III Sentani" / "Dirasakan di … III MMI"), gazetir kabupaten & distrik Papua dari `repository/static/repository/js/batas_*_indo.geojson`, alias kota (`ALIASES`) |
| `isoseismal/layout.py` | gambar PNG (matplotlib + tile OSM `reporting.osm`), warna & tabel skala Worden dkk. (2011) seperti template QGIS `BMKG_MMI_Template` |
| `isoseismal/services.py` | `store_shakemap`, `wilayah_mmi` (MMI grid maks. per kabupaten), `generate` |
| `isoseismal/tasks.py` | `generate_isoseismal_task`, `scan_isoseismal_task` |

Tempat yang tidak dikenali tetap tercantum di tabel halaman detail ("lokasi tidak dikenali");
tambahkan ke `ALIASES` di `felt.py` bila sering muncul.

## Pemasangan

1. .189: deploy kode, `python manage.py migrate isoseismal`, `collectstatic`, restart gunicorn,
   celery worker, dan celery beat (jadwal `scan-isoseismal`).
2. .50: `event_dashboard/datin_push.py` langkah **2e** mengirim `grid.xml` + `stationlist.xml`;
   restart `celery-worker.service` setelah mengganti berkas.
3. Kejadian lama: tekan PUSH lagi di dashboard .50 untuk kejadian itu (idempoten).
