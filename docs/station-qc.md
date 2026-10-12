# Station waveform health (Kesehatan Stasiun)

Daily per-channel QC of every seismic station in the SeisComP archive, with
plain-language findings in Indonesian and English. Page: `/qc/stations/`
(sidebar → QC Reviewer → Kesehatan Stasiun); station detail
`/qc/stations/<NET>.<STA>/`.

## Flow

```
scproc (192.168.1.5)                                 .189 new-datin (qc_review)
cron 10:40 WIT (01:40 UTC)                           POST /qc/api/station-daily/  (DRF token)
~/station_qc/station_qc.py --day yesterday --post ─▶ StationDailyQC  (metrics per channel-day)
  reads SDS ~/seiscomp/var/lib/archive                station_rules.evaluate(today, last 14 days)
  ObsPy 1.5 from /opt/seiscomp_qc/.venv           ─▶ StationDiagnosis (ID + EN message, evidence)
  env: /etc/seiscomp-qc/watcher.env                   status = worst severity per channel
```

The per-event EQTransformer QC (`seiscomp-qc-watcher.service` → `/qc/api/qc-events/`)
is unchanged.

## Metrics (per channel, per UTC day)

| key | meaning |
|---|---|
| `availability_pct`, `n_gaps`, `n_overlaps`, `max_gap_s` | data completeness (day edges count as gaps) |
| `timing_quality_mean/min` | MiniSEED blockette 1001 timing quality (digitizer GPS) |
| `clock_locked_pct` | % of records with the "clock locked" flag |
| `noise_rms` | median RMS of 10-min windows after 1 Hz high-pass (counts) |
| `mean_counts`, `max_abs_counts` | DC offset, peak |
| `flatline_pct` | % of samples in runs of ≥10 s of identical values |
| `n_spikes` | isolated one-sample up-and-back jumps (>100 × MAD of the first difference) |
| `n_clip_runs` | flat tops: ≥3 identical samples at the day's extreme, \|value\| ≥ 2²¹ |
| `future_dates` | files written that day into a future year directory (clock jump, e.g. 2036-02-07) |

## Rules (`qc_review/station_rules.py`)

| code | severity | trigger |
|---|---|---|
| `NO_DATA` | red | availability 0 %; message says "no data since <last day with data> (N days)". Channels with data in the last 60 days are expected every day: when the daily batch is complete, .189 adds missing channels itself, so a dead station never silently disappears |
| `DATA_GAPS` | red < 80 %, yellow < 98 % | availability |
| `FLATLINE` | red | flatline > 5 % |
| `FUTURE_TIMESTAMP` | red | any future-dated file → "time shift / clock fault" |
| `TIMING_QUALITY` | red < 50, yellow < 80 | mean timing quality — always flagged; when the 14-day baseline is also low the message says the problem is ongoing |
| `CLOCK_UNLOCKED` | red | locked < 20 % while the baseline is ≥ 80 % (digitizers that never set the bit are ignored) |
| `COMPONENT_DEAD` | red | one of Z/N/E ≥ 20 dB below the median of the three ("vertical component broken") |
| `COMPONENT_NOISY` | yellow | one component ≥ 20 dB above the median |
| `AMPLITUDE_CHANGE` | yellow | noise RMS ≥ 20 dB away from the channel's 14-day median (gain/response change) |
| `SPIKES` | yellow | today and the previous day both > max(100, 10 × the channel's 14-day median) |
| `CLIPPING` | yellow | any flat-top run, unless the channel is flatlined (may be a strong nearby earthquake) |

Baseline rules need ≥ 5 earlier days; they stay silent until then. Thresholds are
module constants — tune after a few weeks of data.

## Operations

- Install / update on scproc: see `scripts/station_qc/install_on_scproc.sh`.
- Dry run without posting: `station_qc.py --day yesterday --out /tmp/qc.json`.
- Backfill: `--day yesterday --backfill 60 --post` (≈ 75 s per day for ~190 channels).
- Re-posting a day replaces that station-day's rows and findings.
- After changing the rules: `manage.py reevaluate_station_qc [--since D]` re-runs them over stored metrics (oldest first).
- Durations in messages: `34s`, `2m 53s`, `1j 12m 32s` (EN `1h 12m 32s`).
- Log: `~/logs/station_qc.log` on scproc.

## Daily PDF report (Telegram)

Celery beat `send-station-qc-report-daily` at 02:30 UTC (11:30 WIT) runs
`manage.py send_station_qc_report` for yesterday (UTC): a PDF (summary, all red/yellow
findings in ID + EN, 7-day station grid) is sent with `sendDocument` to
`STATION_QC_TELEGRAM_CHAT_ID`, or `TELEGRAM_CHAT_ID` when that is empty. If scproc has not
delivered the day, a warning message is sent instead.

- Preview: `manage.py send_station_qc_report --day 2026-10-11 --out /tmp/r.pdf`
- Resend: `manage.py send_station_qc_report --day 2026-10-11`

## Planned (Phase 2/3)

PPSD noise spectra vs NLNM/NHNM and station baseline; P-residual timing bias from
`StationResult.delta_p`; mass-position (VM*) tilt; per-station health badge on the
event QC page; polarity/orientation; Telegram alert on new red findings.
