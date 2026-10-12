# Ground-Motion Initiative — Roadmap (Papua strong-motion)

Started 2026-10-13. Inspired by Brendon Bradley's ground-motion simulation work
(https://www.brendonbradley.com/research/ground-motion-simulation): validate first,
then simulate.

## Systems involved

| Host | Role | Key paths |
|---|---|---|
| `sysop@172.21.63.50` (jaygenerator, internal network only) | SeisComP3 + USGS ShakeMap v3.5 pipeline, wrapped by Django `shakemap_manager` (Py3.6, Django 3.2, ObsPy 1.1) | `~/jaygenerator/shakemap_manager/` (app, `db.sqlite3`), `~/shakemap/config/grind.conf`, `~/shakemap/vs30_data/stavel.csv`, `~/seiscomp3/shakemaps_waveform_spectra/{spectra,waveforms}/` |
| `.189` new-datin (`ssh datin-189`, `/var/www/html`) | Receives psa5/mseed via `/api/shakemap/psa5/` + `/api/shakemap/waveform/` | `repository.models`: `EventResponseSpectrum`, `EventStationWaveform`, `StationDesignSpectrum`, `ShakemapEvent` |

The dev box (192.168.88.x) only reaches 172.21.63.50 when the internal network/VPN is up.

## Baseline facts (2026-10-13)

- Archive: **302 events** 2024–2026 (M2:34, M3:113, M4:116, **M5:35, M6:3**),
  **12,502 `.psa5`** (+ `.drs5`), **12,536 mseed** (2 GB), **49 IA strong-motion stations**.
- Spectra dir names encode the event: `<UTC yyyymmddHHMMSS>_<M×10>_<lat×1000>_<lon×1000>_<...>`
  → metadata recoverable for every record (on `.189` only 41/374 spectra events link to `ShakemapEvent`).
- `.psa5`: 3 header lines (Sa at 0.3/1/3 s) then 103 rows `T  Sa[g]`, T = 0–5 s.
- `grind.conf` GMPEs: BA08 (M<5.3), Zhao06 crustal/intraslab/interface (M≥5.3 by depth),
  AkkarBommer07 (shallow M<5.3); bias correction on; `smVs30default : 686`.
- **Operational site correction** = ShakeMap's slope-proxy Vs30 (Wald & Allen 2007,
  `topo2grd regime=active`, 30″ DEM): `grind -qtm -gmpesc` runs with `qtm_file` commented out
  (`#qtm_file : vs30_data/vs30_bmkgpusat2.grd` — that grid is not on disk). Confirmed in
  `info.xml`: `sitecorr_source = from topography`. The 686 m/s default only fills NaN cells.
  Each run's Vs30 is in `download/grid.xml` column `SVEL`.
- `stavel.csv` (172 rows, mostly Java) is **only used in scenario mode** (forward-station list),
  not for real events. It covers 4 of 49 recording stations; **JMPI, JBPI and JGPI have the
  latitude sign flipped** (+2.5x instead of −2.5x).

## Roadmap

| # | Step | Output | Status |
|---|---|---|---|
| 0 | Backup of jaygenerator config/app state | `~/backups/gm-initiative-<ts>.tar.gz` on jaygenerator + copy on dev box | see log |
| 1 | **Site characterization**: compare ShakeMap slope-Vs30 with earthquake H/V (Zhao et al. 2006 classes) per station; fix `stavel.csv` signs | `docs/ground-motion/step1/`, `scripts/ground_motion/` | done (keep slope map; field checks JMPI/SJPM/SKPM/SRPI + instrument checks SATPI/WWPI outstanding) |
| 2 | Ground-motion flatfile in new-datin: event × station × component with M, depth, regime, Rhyp/Rrup, Vs30, PGA, PGV, PSA(T), Arias, D5-95 | new model + management command | todo |
| 3 | GMPE residual analysis: BA08/Zhao06/AB07 (current) vs Zhao16, BCHydro, NGA-West2; between-/within-event + station terms δS2S | report + recommended `grind.conf` | todo |
| 4 | Operational feedback: chosen GMPEs + station terms into ShakeMap; "observed vs GMM vs SNI design" panel per event on new-datin | config change + UI | todo |
| 5 | Simulation: stochastic finite-fault calibrated on M5–6 events → scenario ShakeMaps (New Guinea Trench, Sorong, Yapen, Mamberamo); hybrid broadband = collaboration target (UC/QuakeCoRE, UcGmSim) | scenario products | todo |

Side items: ShakeMap 3.5 → 4 migration (Python, OpenQuake GMPE library); Python 3.6/ObsPy 1.1
are EOL; `mysql -uroot` without password in the pipeline; PSA5 API token committed in
`scripts/shakemap/*_send.sh` — rotate and move to env.

## Log

- 2026-10-13: Roadmap written.
- 2026-10-13 **Step 0 done.** Backup on jaygenerator `~/backups/gm-initiative-20261013_004431.tar.gz`
  (shakemap/config, vs30_data, lib/sitecorr, seiscomp3/etc, shakemap_manager code) and
  `~/backups/db.sqlite3.20261013_004431.gz` (copied under a write lock; integrity ok, 22,550 events).
  Copies on dev box: `/home/sysop/backups/jaygenerator/`.
- 2026-10-13 **Step 1 analysis done.**
  - `scripts/ground_motion/svel_at_stations.py` (runs on jaygenerator, Py3.6): nearest-node `SVEL`
    from 282 `grid.xml` → `svel.json`.
  - `scripts/ground_motion/hv_site_class.py` (dev box): per record H = √(Sa_E·Sa_N), H/V = H/Sa_Z;
    station geometric mean; T_G = argmax over 0.05–2 s; Zhao06 class SC I <0.2 s, II 0.2–0.4,
    III 0.4–0.6, IV ≥0.6. "loose" run: PGA ≥ 0.2 gal, ≤300 km (2,078 records, 34 stations ≥5 recs);
    "strict" run: M ≥ 4, PGA ≥ 1 gal, ≤200 km (608 records). Outputs in `docs/ground-motion/step1/`.
  - Result: H/V agrees with ShakeMap's slope-Vs30 class at only ~6 of 34 stations. Stable under
    both filters (same T_G, *higher* peak when strict → real resonance, not noise):
    - **Soft-soil SC IV (T_G 0.8–1.8 s, peak 2.6–5) where ShakeMap assumes stiffer ground:**
      JMPI (Jayapura, 0.86 s, SM 330), SJPM (1.1 s, SM **800**), SKPM, SRPI, YBYPI, WAMI, MTJPI,
      MTMPI, MAPI, ERPN, LJPI.
    - Consistent SC II: AMPM, BTSPI, IWPI, JBPI, JGPI, MIPI, TMPI, WANPI.
    - Class shifts between filters (moderate confidence): ARKPI, BMPI, SUSPI, SWPM.
    - **Instrument QC flags:** SATPI (H/V ≈ 0 → vertical ≫ horizontal; check channel gain/orientation),
      WWPI (flat ~1).
    - Too few records (<5): 36 of 70 stations (incl. JAY, NBPI, SWI — not in this accelerograph archive).
  - Implication: slope-proxy Vs30 likely **under-predicts** shaking at basin/alluvial sites
    (incl. Jayapura city). H/V is a proxy — confirm with field microtremor/MASW, and quantify
    actual amplification with station terms in Step 3.
- 2026-10-13 **`stavel.csv` fixed** on jaygenerator (user-approved): JMPI → −2.5757,140.519;
  JBPI → −2.57; JGPI → −2.51445,140.703762. Same 173 lines, only those 3 rows changed.
  Original kept as `~/shakemap/vs30_data/stavel.csv.bak.20261013` (also in the Step 0 tarball).
  Scenario-mode only; operational ShakeMaps are unaffected.
- **Pending (needs user):**
  1. ~~stavel.csv sign fix~~ done.
  2. ~~Decide the operational Vs30 grid~~ **Decided 2026-10-13: option (b)** — keep ShakeMap's
     slope-proxy Vs30 map unchanged; derive per-station corrections (station terms δS2S) in Step 3
     and apply them in Step 4. BMKG HQ's `vs30_bmkgpusat2.grd` is not being pursued for now.
     No operational change until Step 3 quantifies the amplification.
  3. Field verification priority: JMPI, SJPM, SKPM, SRPI; instrument check: SATPI, WWPI.
- 2026-10-13: **Paused after Step 1** at the user's request. Next session starts at Step 2
  (flatfile in new-datin) only when the user asks.
