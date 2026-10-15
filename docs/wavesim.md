# Simulasi Penjalaran Gelombang (SPECFEM3D) — Gempa Merusak

Staff can run a numerical wave-propagation simulation for a damaging
earthquake in the Gempa Merusak catalogue. The result is shown on the public
page `/gempa-merusak/<pk>/` and on the staff page `/repository/gempa-merusak/<pk>/`.

## Flow

```
staff page ──POST /repository/gempa-merusak/<pk>/simulasi/──► WaveSimulation (queued)
                                                                   │
172.21.63.51 cron */5 ── wavesim_worker.py ──POST /api/wavesim/claim/ ┘  (bearer WAVESIM_WORKER_TOKEN)
   specfem_inputs.py   → DATA/ (Mesh_Par_file, interfaces, Par_file, CMTSOLUTION, STATIONS)
   xmeshfem3D → xgenerate_databases → xspecfem3D (GPU)
   postprocess.py      → web/frames/fNNN.png, web/pgv.png, result.json
   POST /api/wavesim/<id>/result/  (tar.gz + result JSON)  → MEDIA_ROOT/wavesim/<id>/
```

.51 can reach `stageof-jayapura.bmkg.go.id`, but .189 cannot reach .51, so
the worker pulls jobs (same pattern as the scproc jobs).

## Model and assumptions

- Point source at the catalogue hypocentre. Moment tensor from strike/dip/rake
  (Aki & Richards) and M0 = 10^(1.5 Mw + 9.1) N·m. Half duration from the
  GCMT scaling 1.05e-8 · M0[dyn·cm]^(1/3) (≈3.9 s for M6.4).
- Block 300 × 300 km around the epicentre, 80 km deep, flat surface (no
  topography, no ocean). 1D model: AK135 crust (0–20 km Vp 5.8 / Vs 3.46,
  20–35 km Vp 6.5 / Vs 3.85) over mantle (Vp 8.04 / Vs 4.48). No attenuation.
- Mesh: 96 × 96 elements at the surface (~3.1 km), one doubling in the
  mantle, ~150 000 elements. DT 0.02 s, 140 s simulated. SPECFEM reports a
  shortest resolved period of ~2.35 s (~0.4 Hz), and the M6.4 source has a
  3.9 s half duration, so only long-period motion is modelled: velocities and
  PGV are far below the real shaking (Sarmi test: PGV 2.6 cm/s at the
  epicentre, 3–9 mm/s at stations 20–100 km away).
- Runtime on the RTX A2000 (Sarmi test, 2026-10-15): mesher 3 s, database
  generation 6.5 min (serial CPU), solver 5 min (GPU, 1.7 GB), rendering
  ~1 min; about 16 MB of PNG per run.
- Events need latitude, longitude, depth, magnitude and strike/dip/rake;
  the button explains what is missing otherwise.

The pictures show how waves spread from that source in a simple model. They
are not recorded data and not an official shaking map.

## Outputs

- `frames/fNNN.png`: vertical surface velocity every 1 s on a 360×360
  lon/lat grid (asinh-compressed colour scale, transparent where quiet),
  played as a Leaflet image overlay.
- `pgv.png`: peak ground velocity (log scale 0.1 mm/s – 1 m/s).
- `result.json` (stored in `WaveSimulation.result`): bounds, frame times,
  colour scales, synthetic velocity seismograms (Z/N/E) at the active
  stations inside the block, timings.

## Operations

- Install/update the worker on .51:
  `scp -r scripts/wavesim sysop@172.21.63.51:/tmp/wavesim_src`
  `ssh sysop@172.21.63.51 'bash /tmp/wavesim_src/install_on_specfem.sh [TOKEN]'`
  (TOKEN only on first install; it must equal `WAVESIM_WORKER_TOKEN` in
  `.env.production` on .189).
- Worker log: `~/wavesim/worker.log` on .51. Run directories:
  `~/wavesim/runs/sim_<id>/` (last 5 kept; databases deleted after upload).
- A run that stays "running" for more than 6 h is marked failed at the next
  claim. Failed runs show the log tail on the staff page and can be re-run.
- Admin: Django admin → Simulasi Gelombang.
