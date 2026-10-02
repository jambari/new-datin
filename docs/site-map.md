# Site Map — Datin App (Stasiun Geofisika Kelas I Jayapura)

Peta situs aplikasi Django `datin_project`, dengan penjelasan mendetail untuk dua halaman
utama area kerja internal: **Dashboard** (`/dashboard/`) dan **Logbook** (`/logbook/`).

- Root URLconf: `datin_project/urls.py`
- Template shell: `theme/templates/base.html`
- Navigasi internal: `theme/templates/partials/_sidebar.html` + `theme/templates/partials/_topbar.html`

> Semua rute di bawah ini diverifikasi langsung dari `django.urls.reverse()` / `get_resolver()`,
> bukan dari asumsi dokumen.

---

## 1. Peta Situs Tingkat Atas

```
/                                      → Landing publik (theme.views.landing)
│
├── 🌐 AREA PUBLIK (tanpa login)
│   ├── /gempa/                       Daftar gempa
│   ├── /gempa/<public_id>/           Detail gempa
│   ├── /gempa-merusak/               Katalog gempa merusak
│   ├── /gempa-merusak/<pk>/          Detail gempa merusak
│   ├── /skala-mmi/                   Referensi skala MMI
│   ├── /shakemap/                    Daftar shakemap
│   ├── /shakemap/<pk>/               Detail shakemap
│   ├── /shakemap/<pk>/spectrum/      Spektrum respons
│   ├── /spectra-acceleration/        Daftar spektra akselerasi
│   ├── /petir/                       Informasi petir
│   ├── /magnetbumi/                  Informasi magnetbumi + indeks K & A (anchor #indeks-k-a)
│   ├── /kegiatan/                    Kegiatan / our work
│   ├── /tentang/ · /glosarium/       Halaman statis
│   ├── /poster/                      Poster Datin
│   ├── /buletin/ · /buletin/<pk>/    Buletin
│   ├── /siaran-pers/ · /siaran-pers/<pk>/
│   ├── /ttm/                         Terbit–Terbenam Matahari (publik)
│   ├── /layanan/…                    Portal layanan (tentang, tarif, alur, jasa, magang, gts, daftar)
│   ├── /buku-tamu/ · /buku-tamu/create/ · /buku-tamu/search/
│   └── /pengaduan/ · /pengaduan/success/
│
├── 🔐 AUTENTIKASI
│   ├── /accounts/login/              theme.views.custom_login  (name: login)
│   ├── /accounts/otp-verify/         theme.views.otp_verify    (2FA / TOTP)
│   ├── /accounts/logout/             django.contrib.auth
│   └── /accounts/password_*          django.contrib.auth (reset/change)
│
├── 🏠 AREA KERJA INTERNAL (login + IP allowlist untuk logbook)
│   ├── /dashboard/          ★  Dashboard utama            (name: dashboard)
│   ├── /logbook/            ★  Logbook operasional        (name: logbook:logbook_list)
│   ├── /logbook/edit/<id>/     Edit log                   (name: logbook:edit_log)
│   ├── /logbook/print/<id>/    Cetak log                  (name: logbook:print_log_detail)
│   ├── /account/               Profil akun                (name: account_profile)
│   ├── /repository/…           Gempa, shakemap, integrasi, buletin, siaran pers, upload
│   ├── /magnet/…               Geomagnet: absolut, DIM, prekursor, ketersediaan, status instrumen
│   ├── /magnet/fmi-indices/    Indeks K & A magnetbumi (citra harian hasil scraping)
│   ├── /lightning/…            Petir: query, upload, grid, ketersediaan
│   ├── /wrsng/…                WRSNG: status log, laporan ketersediaan
│   ├── /qc/…                   QC Reviewer (event, run, station review, export CSV/PDF)
│   ├── /jadwal/…               Jadwal dinas, pegawai, lapbul
│   ├── /maintenance/…          Maintenance: alat, tiket
│   ├── /perjadin/…             Perjalanan dinas
│   ├── /monitoring_pm → /peralatan/, /peminjaman/, /suku-cadang/…
│   ├── /arsip/ · /arsip/<pk>/  Arsip foto
│   ├── /data/hujan/…           Data hujan, laporan bulanan, export Excel
│   ├── /events/ · /report/     Almanak: event & laporan terbit–terbenam
│   ├── /layanan/dashboard/…    CRUD layanan publik
│   ├── /buku-tamu/dashboard/…  CRUD buku tamu
│   ├── /pengaduan/list/        Daftar pengaduan
│   ├── /station-map/           Peta stasiun
│   └── /yolo-progress/         Dashboard privat training YOLO (+ /yolo-progress/download/<key>)
│
├── ⚙️ ADMIN & API
│   ├── /admin/                 Django admin dengan OTP (OTPAdminSite)
│   ├── /api/…                  repository.api_urls (availability, station search, push events, spectrum, mseed, dll.)
│   └── /magnet/api/instrument/status/   JSON status instrumen (dipakai dashboard)
│
└── 🔎 SEO / BOT
    ├── /robots.txt             explicit Allow publik, Disallow internal
    └── /sitemap.xml            django.contrib.sitemaps (StaticViewSitemap, ShakemapSitemap, GempaMerusakSitemap)
```

Catatan `robots.txt` (`theme/templates/robots.txt`): `/dashboard/`, `/logbook/`, `/admin/`, `/qc/`,
`/wrsng/`, `/jadwal/`, `/maintenance/`, `/perjadin/`, `/accounts/`, `/api/` semuanya `Disallow`.

---

## 2. Peta Navigasi Sidebar (Area Kerja Internal)

Sumber tunggal navigasi: `theme/templates/partials/_sidebar.html`.
Semua item memakai `{% url %}` kecuali satu link eksternal Google Drive.

| # | Menu (label UI) | Rute tujuan | URL | Route name |
|---|---|---|---|---|
| 1 | **Dashboard** | `theme.views.dashboard` | `/dashboard/` | `dashboard` |
| 2 | **Akun Saya** | `theme.views.account_profile` | `/account/` | `account_profile` |
| 3 | **Operasional** ▾ | | | |
| 3.1 | Logbook | `logbook.views.index` | `/logbook/` | `logbook:logbook_list` |
| 3.2 | Jadwal Dinas *(butuh login)* | `jadwal` | `/jadwal/` | `jadwal_dinas` |
| 3.3 | Data Pegawai *(butuh login)* | `jadwal` | `/jadwal/pegawai/` | `pegawai_list` |
| 3.4 | Arsip Foto | `arsip` | `/arsip/` | `arsip:album_list` |
| 3.5 | Laporan Operasional ↗ | Google Drive (eksternal) | — | — |
| 3.6 | Lapbul | `jadwal` | `/jadwal/lapbul/` | `lapbul_list` |
| 3.7 | Monitoring Inventaris ▾ | | | |
| 3.7.1 | Peralatan Teknis ▾ | Peralatan / Peminjaman / Unduh Data | `/peralatan/`, `/peminjaman/`, `/peminjaman/unduh-data/` | `monitoring_pm:*` |
| 3.7.2 | Suku Cadang ▾ | Peralatan / Manajemen / Unduh Data | `/suku-cadang/peralatan/`, `/suku-cadang/manajemen/`, `/suku-cadang/unduh-data/` | `monitoring_pm:*` |
| 3.8 | **Publikasi** | Buletin → `/repository/bulletin/`, Siaran Pers → `/repository/siaran-pers/` | | `bulletin_list`, `siaranpress_list` |
| 3.9 | **Layanan Publik** | Pelayanan → `/layanan/dashboard/`, Buku Tamu → `/buku-tamu/dashboard/`, Pengaduan → `/pengaduan/list/` | | `layanan_dashboard_list`, `guests_dashboard_list`, `pengaduan_list` |
| 4 | **Direktorat Gempa Tsunami** ▾ | | | |
| 4.1 | Gempa Bumi | Repository → `/repository/`, Katalog Gempa Merusak → `/repository/gempa-merusak/` | | `gempa_list`, `gempa_merusak_list` |
| 4.2 | Seismik | Channel → `/repository/data-availability/`, Ketersediaan Data → `/repository/seismo-availability-query/` | | `data_availability_list`, `seismo_availability_query` |
| 4.3 | WRSNG | Status Log → `/wrsng/status/list/` | | `wrsng:status_list` |
| 4.4 | QC Reviewer | Seismic QC → `/qc/` | | `qc_review:event_list` |
| 4.5 | Integrasi | `/repository/integrasi/` | | `event_browser_list` |
| 5 | **Direktorat SGT** ▾ | | | |
| 5.1 | Magnetik | Absolut MinGeo → `/magnet/records/mingeo/`, Absolut Bartington → `/magnet/records/bartington/`, Arsip Absolut → `/magnet/observation/legacy/`, Kalkulator DIM → `/magnet/dim-calculator/`, Validasi Prekursor → `/magnet/precursor/`, Ketersediaan Data → `/magnet/availability-query/`, **Indeks K & A** → `/magnet/fmi-indices/` | | `observation_list_mingeo`, `observation_list_bartington`, `observation_legacy_list`, `dim_calculator`, `precursor_list`, `magnet_availability_query`, `fmi_indices_list` |
| 5.2 | Petir | Query Sambaran → `/lightning/query/`, Ketersediaan Data → `/lightning/availability/`, Hitung Sambaran → `/lightning/upload/`, Peta Kerapatan Petir → `/lightning/grid/`, Terbit Terbenam → `/events/` | | `lightning:*`, `event_list` |
| 5.3 | Akselerograf | Channel → `/repository/accelero-availability-list/`, Ketersediaan Data → `/repository/accelero-availability-query/` | | `accelero_availability_list`, `accelero_availability_query` |
| 5.4 | Shakemap | Shakemap List → `/repository/shakemap/` | | `shakemap-list` |
| 5.5 | Monitor Instrumen | Status Log → `/magnet/instrument/status/log/` | | `instrument_status_list` |
| 6 | **Lapbul dan Infografis** ▾ | | | |
| 6.1 | Lapbul Gempa → `/repository/event-browser/`, Shakemap → `/repository/shakemap/report/`, Almanak → `/report/`, Hujan → `/data/hujan/query/` | | `event_browser`, `shakemap_report_query`, `sunmoon_report`, `query_laporan_hujan` |
| 6.2 | Petir | Query Sambaran → `/lightning/query/`, Peta Kerapatan → `/lightning/grid/` | | `lightning:*` |
| 6.3 | Ketersediaan Data | Seismik → `/repository/seismo-availability-query/`, Akselerograf → `/repository/accelero-availability-query/`, WRSNG → `/wrsng/status/report/` | | `*_availability_query` |
| 7 | **Kualitas Udara** ▾ | | | |
| 7.1 | Hujan | Data Hujan → `/data/hujan/`, Laporan Bulanan → `/data/hujan/query/` | | `daftar_hujan`, `query_laporan_hujan` |

**Aturan visibilitas sidebar**

- Link **Logbook**, **Arsip Foto**, **Lapbul**, seluruh blok Direktorat, Lapbul & Infografis,
  dan Kualitas Udara **selalu tampil**, termasuk untuk pengunjung yang belum login.
  (Proteksi sebenarnya ada di view, bukan di menu.)
- Hanya **Jadwal Dinas** dan **Data Pegawai** yang dibungkus `{% if request.user.is_authenticated %}`.
- Belum ada penanda "menu aktif" (active state) berbasis `request.path`.

---

## 3. ★ Dashboard — `/dashboard/`

### 3.1 Identitas halaman

| Aspek | Nilai |
|---|---|
| URL | `/dashboard/` |
| Route name | `dashboard` |
| View | `theme.views.dashboard` (baris 12–168) |
| Template | `theme/templates/dashboard.html` (523 baris) |
| Dekorator | `@never_cache`, `@login_required` |
| Redirect setelah login | `LOGIN_REDIRECT_URL = '/dashboard/'` (`datin_project/settings.py`) |
| Cache server | Key `dash_ctx_{user_id}_{YYYY-MM-DD}`, TTL **120 detik** (per-user) |
| Layout | Full-screen flex: `_sidebar.html` + `_topbar.html` + `<main>` scrollable |

### 3.2 Struktur layout (dari atas ke bawah)

```
base.html
└─ div.flex.h-screen
   ├─ partials/_sidebar.html            ← navigasi gelap (lihat §2)
   └─ div.flex-1
      ├─ partials/_topbar.html          ← #sidebar-toggle, toggle tema, "Welcome, {user}", Logout (POST)
      └─ main
         │
         ├─ 1. Top Action Bar
         │     ├─ <h1>Dashboard</h1>
         │     ├─ [Buat Logbook]  → /logbook/            (CTA ungu #4f46e5)
         │     └─ badge pengingat harian ({{ reminders }})
         │
         ├─ 2. Stat Cards (grid auto-fit minmax(200px,1fr))
         │     ├─ Kartu ulang tahun  (jika birthday_pegawai) — else kartu "Triger SHAKEMAP 3.5"
         │     │     └─ eksternal http://172.21.63.50:8000
         │     ├─ Kartu Sirine Jayapura   → https://sirine.id:8088/login/ (berisi kredensial)
         │     ├─ Kartu Tsunami GPU-COMCOT → http://172.21.63.51:8000
         │     ├─ Kartu Buletin (deadline tgl 15) + ikon ✅/❌ ({{ bulletin_ada }})
         │     ├─ Kartu Lap. Observasi ({{ lapbul_bulan_ini.lapbul_obs }}, PIC, ✅/❌)
         │     └─ Kartu Lap. Data & Info ({{ lapbul_bulan_ini.lapbul_datin }}, PIC, ✅/❌)
         │
         ├─ 3. Row 2 (grid 2fr 1fr)
         │     ├─ Kolom kiri
         │     │   ├─ "Status Instrumen"        ← DIKOMENTARI (menunggu pentest CSIRT)
         │     │   └─ QC Terkini ({{ latest_qc_rows }}, maks 5)
         │     │        └─ tiap baris → /qc/event/<public_id>/  (qc_review:event_detail)
         │     │           bar warna hijau/kuning/merah + badge jumlah stasiun bermasalah
         │     └─ Kolom kanan (satu kartu)
         │         ├─ Jadwal Shift Berikutnya ({{ next_shift_by_pola }}, {{ next_shift_date }})
         │         ├─ <hr>
         │         └─ Logbook Terkini ({{ recent_logbook }}, maks 5)
         │              └─ "Lihat semua →" → /logbook/
         │
         ├─ 4. Row 3 — Status WRSNG ({{ wrsng_statuses }})
         │     └─ "Log lengkap →" → /wrsng/status/list/
         │
         └─ 5. Row 4 — Akses Cepat
               ├─ loop {{ quick_links }}   ← variabel TIDAK ADA di context (lihat §6)
               └─ hardcoded: Repository Gempa, Gempa Merusak ({{ gempa_merusak_total }}),
                  Shakemap, WRSNG Status, Logbook, Almanak, Data Hujan, Upload Laporan Gempa
```

### 3.3 Modal & perilaku client-side

| Elemen | Trigger | Perilaku |
|---|---|---|
| `#birthday-modal` | otomatis saat DOMContentLoaded jika `birthday_pegawai` tidak kosong | Animasi `birthdayBounce`/`birthdayPulse`; tutup via tombol atau klik backdrop |
| `#instr-alert-modal` + `#instr-alert-audio` (`static/alert.mp3`) | polling `GET /magnet/api/instrument/status/` tiap 30 detik | **DINONAKTIFKAN** — baris `checkInstruments()` dan `setInterval(...)` dikomentari (baris 518–520). Kartu status instrumen juga dikomentari. |
| Snooze alert | tombol "Dismiss (10 menit)" | Set `localStorage.instr_silenced_until = Date.now() + 10*60*1000` |
| `#sidebar-toggle` | klik hamburger di topbar | Toggle class `hidden` pada `#sidebar` |
| Toggle tema | tombol `.thm-btn` | `toggleTheme()` di `base.html`, simpan `localStorage.landingTheme` |

Label mapping instrumen yang masih ada di JS: `lemi → LEMI-018`, `proton → Proton`,
`nexstorm → Nexstorm`, dengan status `ok`, `not_responding`, `not_running`, `monitor_offline`, `unknown`.

### 3.4 Sumber data (context dashboard)

| Context key | Sumber model / query | Keterangan |
|---|---|---|
| `gempa_7d`, `gempa_30d`, `gempa_total` | `repository.EventBrowser` | hitung per jendela waktu |
| `latest_gempa` | `EventBrowser` terbaru | `order_by('-origin_time')` |
| `felt_30d`, `recent_felt` | `repository.FeltEarthquake` | 30 hari + 5 terbaru |
| `gempa_merusak_total` | `repository.GempaMemusak.count()` | dipakai di chip Akses Cepat |
| `sun_rise_wit`, `sun_set_wit`, `sun_date` | `almanac.SunMoonEvent` (+`zoneinfo Asia/Jayapura`) | untuk **besok**, kota Jayapura |
| `birthday_pegawai` | `jadwal.Pegawai` (regex NIP `^\d{4}MMDD`) | hitung umur dari prefix tahun NIP |
| `lapbul_bulan_ini` | `jadwal.Lapbul` (bulan & tahun WIT berjalan) | kartu Lap. Observasi & Data & Info |
| `buletin_deadline`, `bulletin_ada` | `repository.Bulletin` | deadline tgl 15 bulan berjalan untuk buletin bulan lalu |
| `wrsng_statuses`, `wrsng_online`, `wrsng_total` | — | **hardcoded kosong** (dihapus demi performa) |
| `recent_logbook` | `logbook.Logbook` | 5 terbaru `order_by('-tanggal','-waktu_dibuat')` |
| `reminders` | `jadwal.JadwalHVSampler` + hari dalam minggu WIT | Senin: sampel hujan & prekursor; Rabu/Jumat: pengamatan absolut; Jumat: infografis; Kamis: prekursor |
| `next_shift_date`, `next_shift_by_pola` | `jadwal.JadwalHarian` (+`select_related`) | cari jadwal besok, jika kosong lompat ke lusa; dikelompokkan per `pola` |
| `latest_qc_rows` | `qc_review.Event` (+`prefetch_related('runs__station_results')`) | 5 terbaru + `qc_summary` |
| `quick_links` | — | **tidak pernah diisi** (loop kosong) |

Waktu acuan aplikasi: **Asia/Jayapura (WIT, UTC+9)** — baik untuk reminder maupun tanggal logbook.

---

## 4. ★ Logbook — `/logbook/`

### 4.1 Rute

| URL | Route name | View | Template | Proteksi |
|---|---|---|---|---|
| `/logbook/` | `logbook:logbook_list` | `logbook.views.index` | `logbook/templates/logbook/index.html` | **IP allowlist** (bukan login) |
| `/logbook/edit/<int:log_id>/` | `logbook:edit_log` | `logbook.views.edit_log` | `logbook/templates/logbook/edit_log.html` | ❌ tidak ada |
| `/logbook/print/<int:log_id>/` | `logbook:print_log_detail` | `logbook.views.print_log_detail` | `logbook/templates/logbook/print_detail.html` | ❌ tidak ada |

### 4.2 Kontrol akses (IP allowlist)

`logbook/views.py`:

```python
ALLOWED_IPS = ['36.91.166.189', '36.91.166.186', '127.0.0.1', '192.168.1.7', '192.168.1.5']
```

- IP diambil dari `HTTP_X_FORWARDED_FOR` (elemen pertama) atau `REMOTE_ADDR`.
- Jika tidak terdaftar → `messages.error(...)` dan render `index.html` dengan `is_authorized=False`
  (tanpa redirect). Template menampilkan kartu "🚫 Akses Ditolak" + IP pengguna.
- Jika terdaftar → seluruh form, filter tanggal, dan tabel ditampilkan.
- **Tidak ada `@login_required`** di ketiga view logbook. `edit_log` dan `print_log_detail`
  tidak memeriksa IP sama sekali.

### 4.3 Struktur halaman `/logbook/`

```
base.html
└─ div.flex.h-screen
   ├─ div#sidebar → partials/_sidebar.html      ← dibungkus div tambahan (beda dari dashboard)
   └─ div.flex-1
      ├─ partials/_topbar.html
      └─ main
         └─ div.compact-container (max-width 1000px)

            ├─ [jika is_authorized == False]
            │     └─ Kartu "🚫 Akses Ditolak" + perintah pakai Wi-Fi kantor
            │
            └─ [jika is_authorized == True]
                  ├─ Kartu "🔔 PENGINGAT TUGAS HARI INI"   ({{ notif_rutin }})
                  │     Senin: Sampel Air Hujan 09:00 WIT
                  │     Rabu & Jumat: Pengamatan Absolut 09:00 WIT
                  │     Jumat: Pembuatan Infografis
                  │     Senin & Kamis: Penyusunan Laporan Prekursor 09:00 WIT
                  │
                  ├─ Kartu "Input Log Baru"  (form POST ke /logbook/)
                  │     ├─ Shift Kerja + Status Absen  (grid 2 kolom)
                  │     ├─ Petugas Sebelumnya (handover)   ← tampil bila status_absen = "Masuk"
                  │     ├─ Petugas Selanjutnya (handover)  ← tampil bila status_absen = "Pulang"
                  │     ├─ Kotak HV Sampler (kondisional, {{ show_hv_fields }})
                  │     │     Counter · Flow Rate · Berat (gr) · Jam Pasang · Jam Angkat
                  │     ├─ Status peralatan (grid 2–3 kolom, loop sisa field form)
                  │     │     Seiscomp Seismik · Seiscomp Accelero · ESDX · Petir · LEMI · Proton · Sirine
                  │     ├─ Catatan Tambahan (textarea)
                  │     └─ [Simpan Logbook]  (hijau, #34C759)
                  │
                  └─ Kartu tabel (p-0):
                        ├─ Toolbar: input start_date → end_date + [Cari]  + label "WIT (UTC+9)"
                        ├─ Tabel: Tanggal | Waktu | Shift | Petugas & Info | Aksi
                        │     tbody#log-table-body  ← {% include "logbook/_log_table_partial.html" %}
                        └─ Pagination (Prev/Next) di dalam partial, memakai fetchLogs(page)
```

### 4.4 Field form (`logbook/forms.py` → `LogbookForm`)

| Field | Widget | Catatan |
|---|---|---|
| `shift` | Select | Pagi, Siang, Malam, Pagi Siang, Malam Tengah Malam, Pagi Siang Malam |
| `status_absen` | Select (`id_status_absen`) | `Masuk` / `Pulang` — mengendalikan toggle handover |
| `petugas_sebelum` | CheckboxSelectMultiple | queryset: user di grup **`operasional`**, urut `first_name` |
| `petugas_selanjutnya` | CheckboxSelectMultiple | idem |
| `hv_counter_hour`, `hv_flow_rate` | NumberInput step 0.01 | HV Sampler |
| `hv_berat_kertas` | NumberInput step 0.0001 | satuan gram |
| `hv_jam_pasang`, `hv_jam_angkat` | TimeInput | |
| `seiscomp_seismik`, `seiscomp_accelero`, `esdx`, `petir`, `lemi`, `proton`, `sirine` | Select | ON / OFF, default OFF |
| `catatan` | Textarea rows=3 | |

Tidak ada di form (di-set otomatis oleh view): `petugas` (= `request.user` bila login),
`tanggal` (= tanggal hari ini WIT), `waktu_dibuat` (`auto_now_add`).

Label checkbox petugas memakai `"{first_name} {last_name}".title()` atau `username.title()`
bila `first_name` kosong.

### 4.5 Alur POST simpan log

```
POST /logbook/
  → LogbookForm(request.POST)
  → form.is_valid()
  → log_entry = form.save(commit=False)
  → log_entry.petugas  = request.user (jika authenticated)
  → log_entry.tanggal  = today_jayapura (WIT)
  → log_entry.save(); form.save_m2m()
  → send_telegram_log(log_entry)          # logbook/utils.py, error hanya di-print
  → messages.success("Log berhasil disimpan.")
  → redirect('logbook:logbook_list')
```

### 4.6 Tabel & pagination (AJAX)

- Query: `Logbook.objects.all().order_by('-waktu_dibuat')`, difilter
  `tanggal__range=[start_date, end_date]` (default: hari ini WIT untuk kedua batas).
- `Paginator(logs_list, 10)` → 10 baris per halaman.
- **Kontrak AJAX**: `GET /logbook/?start_date=…&end_date=…&page=N` dengan header
  `x-requested-with: XMLHttpRequest` → response hanya `_log_table_partial.html`
  (view baris 88–89). Tanpa header tersebut → halaman penuh.
- `_log_table_partial.html` merender kolom **Tanggal** (`d-m-Y`), **Waktu**
  (`timezone:"Asia/Jayapura"` → `H:i`), **Shift**, **Petugas & Info**
  (nama petugas + `Ganti:`/`Diganti:` daftar M2M), **Aksi** (tombol `Edit` → `edit_log`,
  `Print` → `print_log_detail` dengan `target="_blank"`).
- Empty state: satu baris `colspan=5` "Tidak ada data ditemukan."
- Pagination di dalam tbody: tombol Prev/Next memanggil `window.fetchLogs(page)`,
  yang melakukan `fetch()` dan mengganti `innerHTML` dari `#log-table-body`
  (opacity diturunkan saat loading).
- Catatan: tombol Prev/Next berada **di dalam** `#log-table-body`, sehingga akan
  ikut ter-replace pada render berikutnya — perilaku ini memang diinginkan.

### 4.7 Logika HV Sampler

- Saat render `/logbook/`: cari `JadwalHVSampler` untuk **tanggal hari ini**.
  Bila ada → `show_hv_fields=True`, `hv_today` diisi, dan `hv_label` = `PASANG`
  (bila `tipe` mengandung "Pasang") atau `ANGKAT`. (Template memakai
  `{% if hv_today %}PASANG{% else %}ANGKAT{% endif %}`.)
- Saat render `/logbook/edit/<id>/`: `show_hv_fields` = ada `JadwalHVSampler`
  pada rentang `[log_entry.tanggal - 1 hari, log_entry.tanggal]`.

### 4.8 Notifikasi Telegram

`logbook/utils.py::send_telegram_log(log_entry, is_update=False)`

- Kirim via `curl` ke `https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage`
  dengan `parse_mode=HTML`.
- Token/chat diambil dari settings; bila kosong → fungsi langsung `return`.
- Isi pesan: header (`LAPORAN LOGBOOK HARIAN` atau `UPDATE LOGBOOK`), tanggal + jam WIT,
  petugas, shift, status handover (Masuk/Pulang), blok DATA HV SAMPLER (opsional),
  tujuh status peralatan dengan emoji ✅/🔴, dan catatan.
- Konfigurasi `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` ada di `datin_project/settings.py`.
- Kegagalan Telegram tidak pernah memblokir penyimpanan (dibungkus `try/except`).

### 4.9 Halaman Edit — `/logbook/edit/<id>/`

- Shell sama (sidebar + topbar), kartu aksen kuning `#ffc107`, tombol "Kembali" dan
  "Simpan Perubahan".
- Form = `LogbookForm(request.POST or None, instance=log_entry)`.
- Saat sukses: `send_telegram_log(saved_log, is_update=True)` → redirect `/logbook/`.
- `show_hv_fields` dihitung dari rentang tanggal log (lihat §4.7).
- Grid checkbox petugas dipaksa 180–200px per item agar rapi di layar lebar.

### 4.10 Halaman Cetak — `/logbook/print/<id>/`

- Template **standalone**: tidak `{% extends "base.html" %}`, jadi **tanpa sidebar, topbar,
  dan tanpa CSS aplikasi** — hanya `serif` + CSS internal.
- `<body onload="window.print()">` → dialog print terbuka otomatis.
- Isi: kop "LAPORAN LOGBOOK HARIAN / BMKG Stasiun Geofisika Kelas I Jayapura",
  tabel meta (tanggal, waktu input WIT, shift, petugas, status absen, handover),
  blok DATA HV SAMPLER (kondisional), blok STATUS PERALATAN (7 item), CATATAN TAMBAHAN,
  lalu dua kolom tanda tangan (Koordinator/Kepala dan Petugas Jaga).
- `@media print { .no-print { display:none } }`.

### 4.11 Model `Logbook` (`logbook/models.py`)

| Field | Tipe | Keterangan |
|---|---|---|
| `petugas` | FK → `auth.User` | `null=True`, `related_name='logs_as_petugas'` |
| `tanggal` | DateField | default `timezone.now` |
| `waktu_dibuat` | DateTimeField | `auto_now_add` |
| `status_absen` | CharField(20) | `Masuk` / `Pulang`, default `Masuk` |
| `petugas_sebelum` | M2M → User | `logs_as_previous` |
| `petugas_selanjutnya` | M2M → User | `logs_as_next` |
| `shift` | CharField(50) | 6 pilihan (lihat §4.4) |
| `seiscomp_seismik`, `seiscomp_accelero`, `esdx`, `petir`, `lemi`, `proton`, `sirine` | CharField(3) | ON / OFF, default OFF |
| `hv_counter_hour`, `hv_flow_rate` | Decimal(10,2) | nullable |
| `hv_berat_kertas` | Decimal(10,4) | nullable |
| `hv_jam_pasang`, `hv_jam_angkat` | TimeField | nullable |
| `catatan` | TextField | nullable |

`Meta.ordering = ['-tanggal', '-waktu_dibuat']`; `verbose_name = "Logbook Harian"`.

---

## 5. Titik Sambung Dashboard ↔ Logbook

| Dari | Pemicu | Ke |
|---|---|---|
| Dashboard → Top Action Bar | tombol **Buat Logbook** | `/logbook/` (`logbook:logbook_list`) |
| Dashboard → Logbook Terkini | pranala **Lihat semua →** | `/logbook/` |
| Dashboard → Akses Cepat | chip **Logbook** | `/logbook/` |
| Sidebar (semua halaman) | menu **Operasional → Logbook** | `/logbook/` |
| Logbook → tabel | tombol **Edit** | `/logbook/edit/<id>/` |
| Logbook → tabel | tombol **Print** (tab baru) | `/logbook/print/<id>/` |
| Logbook → edit | **Kembali** / sukses simpan | `/logbook/` |
| Logbook → cetak | (standalone, tanpa navigasi) | — |
| Dashboard kartu reminder | badge harian | informasi saja (tidak menaut) |
| Dashboard | **Jadwal Shift Berikutnya** | data `jadwal.JadwalHarian` (tanpa pranala ke `/jadwal/`) |
| Dashboard | **QC Terkini** | `/qc/event/<public_id>/` |
| Dashboard | **Status WRSNG** | `/wrsng/status/list/` |

Logbook menyumbang 3 titik masuk di Dashboard: CTA header, panel "Logbook Terkini",
dan chip "Akses Cepat". Dashboard menyumbang 0 titik keluar dari halaman Logbook
(halaman Logbook tidak punya breadcrumb/tautan balik ke Dashboard selain menu sidebar).

---

## 6. Temuan & Catatan (status saat dokumen ini dibuat)

1. **`quick_links` tidak pernah didefinisikan.** `dashboard.html` baris 299 melakukan
   `{% for label, url in quick_links %}`, namun `theme/views.py` tidak mengisi key ini dan tidak
   ada context processor yang menyediakannya (`theme/context_processors.py` hanya inject SEO).
   Akibatnya loop selalu kosong; chip yang benar-benar tampil hanyalah 9 tautan hardcoded.
2. **`wrsng_statuses` selalu `[]`.** Baris 80–82 `theme/views.py` men-disable query WRSNG
   "for performance", sehingga kartu Status WRSNG hanya menampilkan heading + tautan
   "Log lengkap"; `wrsng_online` / `wrsng_total` selalu 0.
3. **Monitor Instrumen dimatikan.** Blok kartu Status Instrumen di `dashboard.html`
   (baris 116–158) dan polling `checkInstruments()` (baris 518–520) dikomentari,
   menunggu hasil pentest CSIRT. Modal + audio alert masih ada di DOM.
4. **`edit_log` dan `print_log_detail` tanpa proteksi.** Tidak ada `login_required`,
   tidak ada cek `ALLOWED_IPS`, dan tidak ada pemeriksaan kepemilikan. Siapa pun yang
   mengetahui `log_id` dapat mengubah (edit) atau mencetak log.
5. **Allowlist logbook berbasis IP.** Karena diambil dari `X-Forwarded-For` (elemen pertama),
   akurasi bergantung pada konfigurasi reverse proxy. IP mobile/rumah akan ditolak
   meski pengguna sudah login — memang sesuai desain ("gunakan Wi-Fi kantor").
6. **`print_detail.html` tidak memakai `base.html`.** Tidak ada sidebar/topbar di halaman cetak,
   dan styling berbeda total dari halaman lain.
7. **Perbedaan pembungkus sidebar.** `index.html` logbook membungkus include sidebar dengan
   `<div id="sidebar">`, sementara `dashboard.html` dan `edit_log.html` mengandalkan
   `<aside id="sidebar">` di dalam partial. Toggle `#sidebar-toggle` menargetkan id yang sama,
   tetapi CSS tinggi penuh (`min-height:100vh`) hanya didefinisikan di `index.html`.
8. **Cache dashboard 120 detik per user.** Perubahan data (mis. logbook baru) tidak selalu
   langsung tampak di panel "Logbook Terkini" sampai cache kedaluwarsa atau di-bypass.
9. **Tidak ada indikator menu aktif** di sidebar, dan **tidak ada breadcrumb** untuk halaman
   internal; `theme/middleware.py` hanya memetakan prefix path ke label ActivityLog,
   tidak ke UI navigasi.
10. **Logbook hanya muncul sekali di sidebar** (di bawah Operasional), padahal ada
    duplikasi tautan di blok lain (mis. Query Sambaran dan Ketersediaan Seismik muncul
    di beberapa dropdown).

---

## 7. Peta Berkas Sumber

| Bagian | Berkas |
|---|---|
| Root URLconf | `datin_project/urls.py` |
| Dashboard view + context | `theme/views.py` (baris 12–168) |
| Dashboard template | `theme/templates/dashboard.html` |
| Sidebar & topbar | `theme/templates/partials/_sidebar.html`, `theme/templates/partials/_topbar.html` |
| Shell layout & tema | `theme/templates/base.html` |
| Sitemap XML (SEO) | `theme/sitemaps.py`, `theme/templates/robots.txt` |
| Label ActivityLog | `theme/middleware.py` |
| Logbook routes | `logbook/urls.py` |
| Logbook views | `logbook/views.py` |
| Logbook form | `logbook/forms.py` |
| Logbook model | `logbook/models.py` |
| Notifikasi Telegram | `logbook/utils.py` |
| Logbook templates | `logbook/templates/logbook/index.html`, `edit_log.html`, `print_detail.html`, `_log_table_partial.html` |
| Backup DB (perintah) | `logbook/management/commands/backup_db.py` |

---

## 8. Job Terjadwal: Indeks K & A Magnetbumi

Halaman galeri: **`/magnet/fmi-indices/`** (`magnet:views.fmi_indices_list`, template
`magnet/templates/magnet/fmi_indices_list.html`, menu sidebar **Direktorat SGT → Magnetik → Indeks K & A**).

**Alur job harian**

```
Celery beat  fetch-fmi-indices-daily  (crontab: 07:00 UTC = 16:00 WIT)
    └─ magnet.tasks.fetch_fmi_indices_task()
         └─ manage.py fetch_fmi_indices
              ├─ GET https://dataweb.bmkg.go.id/geofisika/magnet/FMI-K-Indices-JYP.png?ssl=1
              ├─ GET https://dataweb.bmkg.go.id/geofisika/magnet/FMI-A-Indices-JYP.png?ssl=1
              ├─ INSERT/UPDATE magnet.FmiIndicesImage  (1 baris per jenis per tanggal WIT)
              └─ curl sendPhoto → grup Telegram (TELEGRAM_CHAT_ID)
```

| Aspek | Nilai |
|---|---|
| Model | `magnet.FmiIndicesImage` (migrasi `magnet/0009_fmiindicesimage.py`) |
| Kunci unik | `(jenis, tanggal)` — job diulang pada hari yang sama akan **update**, bukan duplikat |
| Field | `jenis` (K/A), `tanggal` (WIT), `image`, `source_url`, `etag`, `sha256`, `size_bytes`, `fetched_at`, `updated_at`, `telegram_sent_at` |
| Penyimpanan berkas | `MEDIA_ROOT/magnet/fmi_indices/YYYY/MM/FMI-<J>-Indices-JYP-YYYYMMDD.png` (nama deterministik, overwrite) |
| Deteksi perubahan | `sha256` + `ETag`; bila citra identik dan sudah terkirim, Telegram dilewati (kecuali `--force`) |
| Pengiriman Telegram | dua pesan `sendPhoto` terpisah (caption: jenis, tanggal WIT, jam pengambilan) |
| Tanggal acuan | zona **Asia/Jayapura**, bukan UTC — job 07:00 UTC menyimpan tanggal WIT hari yang sama |
| Kegagalan | error HTTP/bukan-PNG → `CommandError` (task autoretry 3×, jeda 5 menit); kegagalan Telegram **tidak** membatalkan penyimpanan |
| Trigger manual | tombol **Ambil Sekarang** di halaman (dispatch `.delay()`, non-blocking) atau perintah di bawah |

**Perintah manual**

```bash
python manage.py fetch_fmi_indices                     # hari ini WIT, K & A, kirim Telegram
python manage.py fetch_fmi_indices --date 2026-10-01   # isi data historis
python manage.py fetch_fmi_indices --jenis K           # hanya K (atau A)
python manage.py fetch_fmi_indices --no-telegram       # simpan saja
python manage.py fetch_fmi_indices --force             # kirim ulang walau citra sama
```

**Catatan operasional**

- Menambah entri `CELERY_BEAT_SCHEDULE` di `settings.py` **wajib diikuti restart
  `datin-celery-beat`**; task baru juga butuh restart `datin-celery` agar terdaftar.
- `scripts/deploy.sh` sudah me-restart ketiganya, jadi cukup jalankan deploy seperti biasa.
- Berkas citra dilayani dari `MEDIA_URL` (`/media/`), sama seperti shakemap dan aset lain.

**Tampilan publik**

| Tempat | Isi |
|---|---|
| `/magnetbumi/` (section `id="indeks-k-a"`, `theme.views.public_magnetbumi`) | Pasangan citra **K** dan **A** terbaru (tanggal terbaru yang tersedia), masing-masing dengan tanggal WIT, jam pengambilan (dikonversi ke Asia/Jayapura), ukuran berkas, dan tautan ukuran penuh. Bila belum ada data → state kosong. |
| Navbar landing (`theme/templates/landing.html`) | Item **Magnetbumi** kini berupa dropdown: **Absolut Magnetik** → `/magnetbumi/`, **K dan A Indeks** → `/magnetbumi/#indeks-k-a`. Memakai CSS/JS `.nav-dropdown` yang sudah ada (hover + klik di mobile). |
| Section anchor | `.fmi-section` memakai `scroll-margin-top: 80px` agar tidak tertutup header tetap. |

> Halaman galeri internal `/magnet/fmi-indices/` tetap menyediakan riwayat lengkap +
> filter; halaman publik sengaja hanya menampilkan pasangan terbaru.
