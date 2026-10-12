"""Plain-language diagnoses for daily station waveform metrics.

Input is what the scproc station-QC job sends for one station-day (one
metrics dict per channel) plus that station's recent history; output is a
list of findings, each with a severity, an Indonesian and an English
message and the numbers it is based on.

Rules are deliberately simple and explainable. Where digitizers differ
(e.g. some never set the GPS "clock locked" flag), a rule compares the
channel with its own recent baseline instead of a fixed threshold, so a
station is only flagged when it behaves differently from its normal self.

Metric keys (all optional, missing = not measured):
    availability_pct, n_gaps, n_overlaps, max_gap_s,
    timing_quality_mean, timing_quality_min, clock_locked_pct,
    noise_rms, mean_counts, max_abs_counts,
    flatline_pct, n_spikes, n_clip_runs, future_dates (list of "YYYY-MM-DD")
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median

SEVERITY_ORDER = {"green": 0, "unknown": 0, "yellow": 1, "red": 2}

# Thresholds (tuned conservatively; adjust after a few weeks of data).
AVAIL_RED_PCT = 80.0
AVAIL_YELLOW_PCT = 98.0
FLATLINE_RED_PCT = 5.0
COMPONENT_RATIO_DB = 20.0     # one component 10x quieter/louder than the others
GAIN_CHANGE_DB = 20.0         # vs the channel's own baseline
TIMING_RED = 50.0
TIMING_YELLOW = 80.0
CLOCK_BASELINE_MIN_PCT = 80.0
CLOCK_TODAY_MAX_PCT = 20.0
SPIKES_MIN = 100
SPIKES_FACTOR = 10
BASELINE_MIN_DAYS = 5

# Short Indonesian labels for compact places (Telegram caption).
CODE_LABELS_ID = {
    "NO_DATA": "Tidak ada data",
    "DATA_GAPS": "Data terputus",
    "FLATLINE": "Sinyal datar",
    "FUTURE_TIMESTAMP": "Pergeseran waktu",
    "TIMING_QUALITY": "Timing GPS buruk",
    "CLOCK_UNLOCKED": "GPS tidak terkunci",
    "COMPONENT_DEAD": "Komponen rusak",
    "COMPONENT_NOISY": "Komponen noisy",
    "AMPLITUDE_CHANGE": "Perubahan amplitudo",
    "SPIKES": "Banyak spike",
    "CLIPPING": "Clipping",
}

COMPONENT_NAMES = {
    "Z": ("vertikal", "vertical"),
    "N": ("horizontal utara-selatan", "north-south horizontal"),
    "1": ("horizontal 1", "horizontal 1"),
    "E": ("horizontal timur-barat", "east-west horizontal"),
    "2": ("horizontal 2", "horizontal 2"),
}


@dataclass
class Finding:
    code: str
    severity: str
    message_id: str
    message_en: str
    location: str = ""
    channel: str = ""          # "" = whole station
    evidence: dict = field(default_factory=dict)


def fmt_duration(seconds, lang: str = "id") -> str:
    """34s · 2m 53s · 1j 12m 32s (EN: 1h 12m 32s)."""
    total = int(round(float(seconds or 0)))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}{'j' if lang == 'id' else 'h'} {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _fmt_day(iso: str) -> str:
    y, mo, d = iso.split("-")
    return f"{d}-{mo}-{y}"


def _db(ratio: float) -> float:
    return 20.0 * math.log10(ratio)


def _comp_name(channel: str) -> tuple[str, str]:
    return COMPONENT_NAMES.get(channel[-1:], (channel, channel))


def _baseline(history: list[dict], key: str) -> float | None:
    vals = [h[key] for h in history if h.get(key) is not None]
    if len(vals) < BASELINE_MIN_DAYS:
        return None
    return median(vals)


def evaluate(channels: list[dict], history: dict | None = None) -> list[Finding]:
    """Diagnose one station-day.

    channels: [{"location": "", "channel": "SHZ", "metrics": {...}}, ...]
    history:  {(location, channel): [metrics dict of earlier days, ...]}
    """
    history = history or {}
    findings: list[Finding] = []

    for ch in channels:
        loc, cha, m = ch.get("location", ""), ch["channel"], ch.get("metrics") or {}
        hist = history.get((loc, cha), [])
        name_id, name_en = _comp_name(cha)
        add = lambda code, sev, mid, men, ev: findings.append(
            Finding(code, sev, mid, men, loc, cha, ev))

        avail = m.get("availability_pct")
        if avail is not None and avail <= 0:
            # last_data_day / days_without_data are added on .189 at ingest.
            last, n_days = m.get("last_data_day"), m.get("days_without_data")
            if last and n_days and n_days > 1:
                since_id = f"sejak {_fmt_day(last)} ({n_days} hari tanpa data)"
                since_en = f"since {_fmt_day(last)} ({n_days} days without data)"
            else:
                since_id, since_en = "sepanjang hari", "for the whole day"
            add("NO_DATA", "red",
                f"Tidak ada data pada kanal {cha} ({name_id}) {since_id}. "
                f"Sensor/digitizer mati atau komunikasi terputus.",
                f"No data on channel {cha} ({name_en}) {since_en}. "
                f"Sensor/digitizer down or telemetry lost.",
                {"availability_pct": avail, "last_data_day": last, "days_without_data": n_days})
            continue   # nothing else can be judged without data
        if avail is not None and avail < AVAIL_YELLOW_PCT:
            sev = "red" if avail < AVAIL_RED_PCT else "yellow"
            add("DATA_GAPS", sev,
                f"Data terputus pada {cha}: hanya {avail:.1f}% tersedia "
                f"({m.get('n_gaps', 0)} gap, terpanjang {fmt_duration(m.get('max_gap_s'), 'id')}). "
                f"Periksa komunikasi/daya stasiun.",
                f"Data gaps on {cha}: only {avail:.1f}% available "
                f"({m.get('n_gaps', 0)} gaps, longest {fmt_duration(m.get('max_gap_s'), 'en')}). "
                f"Check station telemetry/power.",
                {k: m.get(k) for k in ("availability_pct", "n_gaps", "max_gap_s")})

        flat = m.get("flatline_pct")
        if flat is not None and flat > FLATLINE_RED_PCT:
            add("FLATLINE", "red",
                f"Sinyal {cha} ({name_id}) datar (flatline) pada {flat:.1f}% data — "
                f"sensor atau digitizer kemungkinan rusak.",
                f"{cha} ({name_en}) signal is flat on {flat:.1f}% of the data — "
                f"possible sensor or digitizer fault.",
                {"flatline_pct": flat})

        future = m.get("future_dates") or []
        if future:
            dates = ", ".join(sorted(set(future)))
            add("FUTURE_TIMESTAMP", "red",
                f"Pergeseran waktu: data {cha} tercatat dengan tanggal {dates}. "
                f"Jam digitizer/GPS bermasalah — waktu tiba fase dari stasiun ini tidak dapat dipercaya.",
                f"Time shift: {cha} data was stamped {dates}. Digitizer/GPS clock fault — "
                f"phase arrival times from this station cannot be trusted.",
                {"future_dates": sorted(set(future))})

        # Always flagged: a GPS that is bad every day is still bad. When the
        # baseline is low too, the message says the problem is ongoing.
        tq = m.get("timing_quality_mean")
        tq_base = _baseline(hist, "timing_quality_mean")
        if tq is not None and tq < TIMING_YELLOW:
            sev = "red" if tq < TIMING_RED else "yellow"
            chronic = tq_base is not None and tq_base < TIMING_YELLOW
            if chronic:
                note_id = f" Masalah ini berlangsung terus (rata-rata {len(hist)} hari terakhir {tq_base:.0f}%)."
                note_en = f" This is ongoing (last {len(hist)} days averaged {tq_base:.0f}%)."
            elif tq_base is not None:
                note_id, note_en = f" Biasanya {tq_base:.0f}%.", f" Normally {tq_base:.0f}%."
            else:
                note_id = note_en = ""
            add("TIMING_QUALITY", sev,
                f"Kualitas waktu (timing quality) {cha} rendah: rata-rata {tq:.0f}%. "
                f"Kemungkinan GPS bermasalah — risiko pergeseran waktu.{note_id}",
                f"Low timing quality on {cha}: mean {tq:.0f}%. "
                f"Possible GPS problem — risk of time shift.{note_en}",
                {"timing_quality_mean": tq, "timing_quality_min": m.get("timing_quality_min"),
                 "baseline": tq_base, "chronic": chronic})

        locked = m.get("clock_locked_pct")
        locked_base = _baseline(hist, "clock_locked_pct")
        if (locked is not None and locked_base is not None
                and locked_base >= CLOCK_BASELINE_MIN_PCT and locked < CLOCK_TODAY_MAX_PCT):
            add("CLOCK_UNLOCKED", "red",
                f"GPS tidak terkunci pada {cha}: hanya {locked:.0f}% record terkunci "
                f"(biasanya {locked_base:.0f}%). Waktu data dapat bergeser.",
                f"GPS not locked on {cha}: only {locked:.0f}% of records locked "
                f"(normally {locked_base:.0f}%). Data timing may drift.",
                {"clock_locked_pct": locked, "baseline": locked_base})

        rms = m.get("noise_rms")
        rms_base = _baseline(hist, "noise_rms")
        if rms and rms_base and rms > 0 and rms_base > 0:
            change = _db(rms / rms_base)
            if abs(change) >= GAIN_CHANGE_DB:
                arah_id, arah_en = ("naik", "rose") if change > 0 else ("turun", "dropped")
                add("AMPLITUDE_CHANGE", "yellow",
                    f"Level noise {cha} ({name_id}) {arah_id} {abs(change):.0f} dB dibanding "
                    f"normalnya — kemungkinan perubahan gain/respons, gangguan sensor, atau noise lokal baru.",
                    f"{cha} ({name_en}) noise level {arah_en} by {abs(change):.0f} dB versus its "
                    f"normal level — possible gain/response change, sensor problem or new local noise.",
                    {"noise_rms": rms, "baseline": rms_base, "change_db": round(change, 1)})

        # Spike counts depend a lot on the sensor and site (and earthquakes add
        # some), so only a jump against the channel's own normal rate counts.
        # A one-day burst is usually an earthquake, so it must persist: today
        # and the previous day both above the threshold.
        spikes = m.get("n_spikes")
        spikes_base = _baseline(hist[:-1], "n_spikes")
        spikes_prev = hist[-1].get("n_spikes") if hist else None
        threshold = max(SPIKES_MIN, SPIKES_FACTOR * spikes_base) if spikes_base is not None else None
        if (threshold is not None and spikes is not None and spikes_prev is not None
                and spikes > threshold and spikes_prev > threshold):
            add("SPIKES", "yellow",
                f"Spike/glitch pada {cha} tinggi dua hari berturut-turut: {spikes} hari ini, "
                f"{spikes_prev} kemarin (biasanya ~{spikes_base:.0f}). Periksa digitizer, kabel atau grounding.",
                f"Spikes/glitches on {cha} elevated two days in a row: {spikes} today, "
                f"{spikes_prev} yesterday (normally ~{spikes_base:.0f}). Check digitizer, cabling or grounding.",
                {"n_spikes": spikes, "previous_day": spikes_prev, "baseline": spikes_base})

        clips = m.get("n_clip_runs")
        if clips and not (flat is not None and flat > FLATLINE_RED_PCT):   # a flatline is not clipping
            add("CLIPPING", "yellow",
                f"Clipping/saturasi digitizer pada {cha} ({clips} kali). Wajar saat gempa kuat "
                f"di dekat stasiun; bila tanpa gempa, periksa gain atau sensor.",
                f"Digitizer clipping/saturation on {cha} ({clips} times). Expected during a strong "
                f"nearby earthquake; otherwise check gain or sensor.",
                {"n_clip_runs": clips, "max_abs_counts": m.get("max_abs_counts")})

    findings.extend(_component_balance(channels))
    return findings


def _component_balance(channels: list[dict]) -> list[Finding]:
    """Compare Z/N/E of the same sensor: one component far quieter or louder
    than the other two points at a broken or mis-wired component."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for ch in channels:
        m = ch.get("metrics") or {}
        if (m.get("availability_pct") or 0) < 50 or not m.get("noise_rms"):
            continue
        groups.setdefault((ch.get("location", ""), ch["channel"][:2]), []).append(ch)

    out = []
    for (loc, _band), chans in groups.items():
        if len(chans) != 3:
            continue
        ref = median(c["metrics"]["noise_rms"] for c in chans)
        if ref <= 0:
            continue
        for c in chans:
            cha = c["channel"]
            ratio_db = _db(c["metrics"]["noise_rms"] / ref)
            name_id, name_en = _comp_name(cha)
            others = ", ".join(o["channel"] for o in chans if o is not c)
            ev = {"noise_rms": {o["channel"]: o["metrics"]["noise_rms"] for o in chans},
                  "ratio_db": round(ratio_db, 1)}
            if ratio_db <= -COMPONENT_RATIO_DB:
                out.append(Finding(
                    "COMPONENT_DEAD", "red",
                    f"Komponen {name_id} ({cha}) kemungkinan rusak/mati: noise "
                    f"{abs(ratio_db):.0f} dB di bawah komponen lain ({others}).",
                    f"{name_en.capitalize()} component ({cha}) likely broken/dead: noise "
                    f"{abs(ratio_db):.0f} dB below the other components ({others}).",
                    loc, cha, ev))
            elif ratio_db >= COMPONENT_RATIO_DB:
                out.append(Finding(
                    "COMPONENT_NOISY", "yellow",
                    f"Komponen {name_id} ({cha}) jauh lebih noisy: {ratio_db:.0f} dB di atas "
                    f"komponen lain ({others}) — periksa sensor, kabel atau pemasangan.",
                    f"{name_en.capitalize()} component ({cha}) is much noisier: {ratio_db:.0f} dB "
                    f"above the other components ({others}) — check sensor, cable or installation.",
                    loc, cha, ev))
    return out


def worst(severities) -> str:
    sev = "green"
    for s in severities:
        if SEVERITY_ORDER.get(s, 0) > SEVERITY_ORDER[sev]:
            sev = s
    return sev
