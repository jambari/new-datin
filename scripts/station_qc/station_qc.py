#!/usr/bin/env python3
"""Daily station waveform QC for the SeisComP SDS archive (runs on scproc).

For every seismic channel and UTC day it measures availability, gaps,
timing quality, GPS lock, noise level, flatlines, spikes, clipping and
future-dated files (clock faults such as data written into 2036), then
POSTs one JSON batch to new-datin /qc/api/station-daily/, where the
plain-language diagnoses are evaluated (qc_review/station_rules.py).

Usage (with /opt/seiscomp_qc/.venv/bin/python):
    station_qc.py --day yesterday --post              # daily cron
    station_qc.py --day 2026-10-12 --backfill 60 --post
    station_qc.py --day yesterday --out /tmp/qc.json  # dry run, no POST

Environment (from /etc/seiscomp-qc/watcher.env):
    QC_API_URL           .../qc/api/qc-events/ (the station-daily URL is derived)
    QC_API_TOKEN         DRF token
    REQUESTS_CA_BUNDLE   CA bundle trusting the .189 certificate
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

log = logging.getLogger("station_qc")

ARCHIVE = "/home/sysop/seiscomp/var/lib/archive"
SEISMIC_CHANNEL = re.compile(r"^[SBHEC][HNL][ZNE123]$")
CHANNEL_LOOKBACK_DAYS = 7       # channels seen in this window are "expected"
LAST_ACTIVE_DAYS = 30           # of a silent station, channels within this of its last data are listed
BINDING = re.compile(r"^global:(\d\d)?([A-Z]{2})\s*$", re.M)
NOISE_WINDOW_S = 600
NOISE_HIGHPASS_HZ = 1.0
FLATLINE_MIN_S = 10.0
SPIKE_K = 100.0
CLIP_MIN_COUNTS = 2 ** 21        # ignore flat tops far below any full scale


# ---------------------------------------------------------------------------
# archive helpers
# ---------------------------------------------------------------------------

def sds_path(archive: str, net: str, sta: str, loc: str, cha: str, day: dt.date) -> str:
    doy = day.timetuple().tm_yday
    return f"{archive}/{day.year}/{net}/{sta}/{cha}.D/{net}.{sta}.{loc}.{cha}.D.{day.year}.{doy:03d}"


def expected_channels(archive: str, day: dt.date) -> dict[tuple[str, str], set[tuple[str, str]]]:
    """{(net, sta): {(loc, cha), ...}} for channels with data on `day` or
    in the CHANNEL_LOOKBACK_DAYS before it."""
    out: dict = {}
    for back in range(CHANNEL_LOOKBACK_DAYS + 1):
        d = day - dt.timedelta(days=back)
        doy = d.timetuple().tm_yday
        for f in glob.glob(f"{archive}/{d.year}/*/*/*.D/*.D.{d.year}.{doy:03d}"):
            net, sta, loc, cha = os.path.basename(f).split(".")[:4]
            if SEISMIC_CHANNEL.match(cha):
                out.setdefault((net, sta), set()).add((loc, cha))
    return out


def _file_day(path: str) -> dt.date | None:
    """Date of an SDS day file from the end of its name (...D.2026.303)."""
    try:
        year, doy = path.rsplit(".", 2)[-2:]
        return dt.date(int(year), 1, 1) + dt.timedelta(days=int(doy) - 1)
    except ValueError:
        return None


def silent_stations(archive: str, key_dir: str, day: dt.date, expected: dict) -> dict:
    """Every other station SeisComP is bound to, or that the archive has ever held.

    The daily scan only sees channels with recent data, so a station silent for longer would
    vanish from the report. {(net, sta): [(loc, cha, metrics), ...]} with 0 % availability.
    Stations with live channels are left out, so a retired channel never turns a healthy one red.
    """
    bindings = {}
    for f in glob.glob(f"{key_dir}/station_*_*"):
        net, sta = os.path.basename(f).split("_")[1:3]
        with open(f) as fh:
            m = BINDING.search(fh.read())
        bindings[(net, sta)] = (m.group(1) or "", m.group(2)) if m else ("", "SH")

    # Clock faults write into future year directories, so only look up to `day`.
    files: dict = {}
    for f in glob.glob(f"{archive}/[0-9][0-9][0-9][0-9]/*/*/*.D/*.D.*"):
        parts = os.path.basename(f).split(".")
        d = _file_day(f)
        if len(parts) < 4 or d is None or d > day or not SEISMIC_CHANNEL.match(parts[3]):
            continue
        key = ((parts[0], parts[1]), (parts[2], parts[3]))
        if d > files.get(key, dt.date.min):
            files[key] = d

    by_station: dict = {}
    for sta_key, chan in files:
        by_station.setdefault(sta_key, {})[chan] = files[(sta_key, chan)]

    out = {}
    for sta_key in sorted(set(bindings) | set(by_station)):
        if sta_key in expected:
            continue
        chans = by_station.get(sta_key)
        if chans:
            newest = max(chans.values())
            out[sta_key] = [
                (loc, cha, {"availability_pct": 0.0, "not_in_archive": True,
                            "last_data_day": last.isoformat(), "days_without_data": (day - last).days})
                for (loc, cha), last in sorted(chans.items())
                if (newest - last).days <= LAST_ACTIVE_DAYS]
        else:
            loc, band = bindings[sta_key]
            out[sta_key] = [(loc, f"{band}{c}", {"availability_pct": 0.0, "not_in_archive": True,
                                                 "never_archived": True}) for c in "ZNE"]
    return out


def future_dated_files(archive: str, day: dt.date) -> dict[tuple[str, str, str, str], list[str]]:
    """Files filed under a year later than `day` that were written on `day`
    (or the day after, to cover late flushes) — the signature of a digitizer
    clock jumping forward, e.g. data stamped 2036-02-07."""
    found: dict = {}
    lo = dt.datetime.combine(day, dt.time(), tzinfo=dt.timezone.utc).timestamp()
    hi = lo + 2 * 86400
    for ydir in glob.glob(f"{archive}/[0-9][0-9][0-9][0-9]"):
        year = int(os.path.basename(ydir))
        if year <= day.year:
            continue
        for f in glob.glob(f"{ydir}/*/*/*.D/*"):
            if not (lo <= os.path.getmtime(f) < hi):
                continue
            parts = os.path.basename(f).split(".")
            net, sta, loc, cha, _, y, doy = parts[:7]
            stamped = dt.date(int(y), 1, 1) + dt.timedelta(days=int(doy) - 1)
            found.setdefault((net, sta, loc, cha), []).append(stamped.isoformat())
    return found


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _runs_of_equal(x: np.ndarray, min_len: int) -> int:
    """Total samples inside runs of >= min_len identical consecutive values."""
    if len(x) < min_len:
        return 0
    change = np.flatnonzero(np.diff(x) != 0)
    edges = np.concatenate(([0], change + 1, [len(x)]))
    lengths = np.diff(edges)
    return int(lengths[lengths >= min_len].sum())


def _count_spikes(x: np.ndarray) -> int:
    """Isolated one-sample glitches: a jump up and straight back down (or the
    reverse), far larger than the typical sample-to-sample change."""
    if len(x) < 3:
        return 0
    d = np.diff(x.astype(np.float64))
    mad = np.median(np.abs(d - np.median(d)))
    if mad <= 0:
        return 0
    big = np.abs(d) > SPIKE_K * mad
    cand = big[:-1] & big[1:] & (np.sign(d[:-1]) != np.sign(d[1:]))
    return int(cand.sum())


def _clip_runs(x: np.ndarray) -> int:
    """Flat-topped saturation: >= 3 identical consecutive samples sitting at
    the day's extreme value, with that value large enough to be near a
    digitizer's full scale. Works for any bit depth, unlike a fixed level."""
    if len(x) < 3:
        return 0
    runs = 0
    for extreme in {int(x.max()), int(x.min())}:
        if abs(extreme) < CLIP_MIN_COUNTS:
            continue
        hit = (x == extreme).astype(np.int8)
        starts = np.flatnonzero(np.diff(np.concatenate(([0], hit))) == 1)
        ends = np.flatnonzero(np.diff(np.concatenate((hit, [0]))) == -1)
        runs += int(((ends - starts + 1) >= 3).sum())
    return runs


def channel_metrics(path: str, day: dt.date) -> dict:
    from obspy import UTCDateTime, read
    from obspy.io.mseed.util import get_flags

    if not os.path.exists(path):
        return {"availability_pct": 0.0}

    t0 = UTCDateTime(day.isoformat())
    t1 = t0 + 86400
    st = read(path)
    st.trim(t0, t1, nearest_sample=False)
    if not st:
        return {"availability_pct": 0.0}
    sr = float(st[0].stats.sampling_rate)

    gaps = [g for g in st.get_gaps() if g[6] > 0]
    overlaps = [g for g in st.get_gaps() if g[6] < 0]
    st.sort(["starttime"])
    edge_gaps = [st[0].stats.starttime - t0, t1 - st[-1].stats.endtime - 1.0 / sr]
    max_gap = max([g[6] for g in gaps] + [e for e in edge_gaps if e > 1.0 / sr] + [0.0])

    st.merge(method=1, fill_value=None)
    data = st[0].data
    if np.ma.isMaskedArray(data):       # gaps become masked samples
        raw_parts = [data.data[s] for s in np.ma.clump_unmasked(data)]
    else:
        raw_parts = [np.asarray(data)]
    valid = sum(len(p) for p in raw_parts)
    expected = sr * 86400
    m = {
        "availability_pct": round(min(100.0, 100.0 * valid / expected), 2),
        "n_gaps": len(gaps) + sum(1 for e in edge_gaps if e > 1.0 / sr),
        "n_overlaps": len(overlaps),
        "max_gap_s": round(float(max_gap), 1),
    }

    raw = np.concatenate(raw_parts) if raw_parts else np.array([])
    if raw.size:
        m["mean_counts"] = round(float(raw.mean()), 1)
        m["max_abs_counts"] = int(np.abs(raw).max())
        m["flatline_pct"] = round(100.0 * sum(
            _runs_of_equal(p, int(FLATLINE_MIN_S * sr)) for p in raw_parts) / raw.size, 2)
        m["n_spikes"] = sum(_count_spikes(p) for p in raw_parts)
        m["n_clip_runs"] = sum(_clip_runs(p) for p in raw_parts)

    # Noise level: median RMS of 10-minute windows after a 1 Hz high-pass,
    # so earthquakes and gaps barely move it.
    rms = []
    nwin = int(NOISE_WINDOW_S * sr)
    for tr_seg in st.split():
        if tr_seg.stats.npts < nwin or sr <= 2 * NOISE_HIGHPASS_HZ:
            continue
        seg = tr_seg.copy()
        seg.data = seg.data.astype(np.float64)
        seg.detrend("demean")
        seg.filter("highpass", freq=NOISE_HIGHPASS_HZ, corners=2)
        x = seg.data[: (len(seg.data) // nwin) * nwin].reshape(-1, nwin)
        rms.extend(np.sqrt((x ** 2).mean(axis=1)).tolist())
    if rms:
        m["noise_rms"] = round(float(np.median(rms)), 3)

    try:
        fl = get_flags(path, starttime=t0, endtime=t1, timing_quality=True)
        tq = fl.get("timing_quality") or {}
        if tq:
            m["timing_quality_mean"] = round(float(tq["mean"]), 1)
            m["timing_quality_min"] = round(float(tq["min"]), 1)
        n_rec = fl.get("record_count")
        locked = (fl.get("io_and_clock_flags_counts") or {}).get("clock_locked")
        if n_rec and locked is not None:
            m["clock_locked_pct"] = round(100.0 * locked / n_rec, 1)
    except Exception as exc:     # flags are a bonus; never fail the channel
        log.debug("flags failed for %s: %s", path, exc)
    return m


def _work(args):
    archive, net, sta, loc, cha, day = args
    path = sds_path(archive, net, sta, loc, cha, day)
    try:
        return net, sta, loc, cha, channel_metrics(path, day)
    except Exception as exc:
        log.warning("metrics failed for %s: %s", path, exc)
        return net, sta, loc, cha, {"error": str(exc)[:200]}


def build_day(archive: str, day: dt.date, workers: int, only: set[str] | None) -> dict:
    expected = expected_channels(archive, day)
    future = future_dated_files(archive, day)
    jobs = [(archive, net, sta, loc, cha, day)
            for (net, sta), chans in expected.items() if not only or sta in only
            for (loc, cha) in sorted(chans)]
    stations: dict = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for net, sta, loc, cha, m in pool.map(_work, jobs, chunksize=4):
            if (net, sta, loc, cha) in future:
                m["future_dates"] = sorted(set(future[(net, sta, loc, cha)]))
            stations.setdefault((net, sta), []).append(
                {"location": loc, "channel": cha, "metrics": m})
    if not only:
        key_dir = os.path.normpath(os.path.join(archive, "..", "..", "..", "etc", "key"))
        for sta_key, chans in silent_stations(archive, key_dir, day, expected).items():
            stations.setdefault(sta_key, []).extend(
                {"location": loc, "channel": cha, "metrics": m} for loc, cha, m in chans)
    # complete: the whole archive was scanned, so .189 may treat channels that
    # are missing from this batch as silent (not just not-yet-processed).
    return {"day": day.isoformat(), "complete": not only,
            "stations": [{"network": n, "station": s, "channels": c}
                         for (n, s), c in sorted(stations.items())]}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def post(batch: dict, url: str, token: str, ca: str | None) -> None:
    import requests
    for attempt in range(3):
        try:
            r = requests.post(url, json=batch, timeout=120, verify=ca or True,
                              headers={"Authorization": f"Token {token}"})
            r.raise_for_status()
            log.info("posted %s: %s", batch["day"], r.json())
            return
        except Exception as exc:
            log.warning("post %s failed (attempt %d): %s", batch["day"], attempt + 1, exc)
            time.sleep(10 * (attempt + 1))
    raise SystemExit(f"giving up posting {batch['day']}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--day", default="yesterday", help="YYYY-MM-DD or 'yesterday' (UTC)")
    p.add_argument("--backfill", type=int, default=1, help="number of days ending at --day")
    p.add_argument("--archive", default=ARCHIVE)
    p.add_argument("--stations", help="comma-separated station codes (default: all)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--post", action="store_true", help="POST to new-datin")
    p.add_argument("--out", help="write JSON batches here instead of / as well as posting")
    p.add_argument("--api-url", default=os.environ.get("STATION_QC_API_URL") or
                   os.environ.get("QC_API_URL", "").replace("qc-events/", "station-daily/"))
    p.add_argument("--log-level", default="INFO")
    a = p.parse_args(argv)
    logging.basicConfig(level=a.log_level, format="%(asctime)s %(levelname)s %(message)s")

    last = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
            if a.day == "yesterday" else dt.date.fromisoformat(a.day))
    days = [last - dt.timedelta(days=i) for i in range(a.backfill - 1, -1, -1)]
    only = set(a.stations.split(",")) if a.stations else None
    token = os.environ.get("QC_API_TOKEN", "")
    if a.post and (not a.api_url.endswith("station-daily/") or not token):
        p.error("--post needs QC_API_URL/--api-url ending in station-daily/ and QC_API_TOKEN")

    batches = []
    for day in days:
        t = time.time()
        batch = build_day(a.archive, day, a.workers, only)
        n = sum(len(s["channels"]) for s in batch["stations"])
        log.info("%s: %d stations, %d channels in %.0f s", day, len(batch["stations"]), n, time.time() - t)
        if a.post:
            post(batch, a.api_url, token, os.environ.get("REQUESTS_CA_BUNDLE"))
        batches.append(batch)
    if a.out:
        Path(a.out).write_text(json.dumps(batches if len(batches) > 1 else batches[0], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
