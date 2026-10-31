#!/usr/bin/env python3
"""Daily spectra and images per seismic station, next to station_qc.py on scproc.

For each station with data that UTC day: PPSD per channel compared with Peterson's NLNM/NHNM,
a 24 h overview, a noise HVSR curve, and the response metadata from the local fdsnws. Results
and PNGs go to new-datin /qc/api/station-media/. Kept apart from station_qc.py so a slow or
failed run here never holds up the daily metrics and the morning report.

PPSD and HVSR follow the accelerograph worker on .51 (station_health.py), adapted to velocity
sensors. Waveforms stay on this host; only numbers and images are sent.

    station_media.py --day yesterday --post
    station_media.py --day 2026-10-30 --stations ARMI,JAY --out /tmp/media   # no upload
"""
import argparse
import datetime as dt
import glob
import io
import json
import logging
import os
import re
import shutil
import sys
import time
import traceback
from multiprocessing import Pool

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
from obspy import Stream, UTCDateTime, read, read_inventory  # noqa: E402
from obspy.signal import PPSD  # noqa: E402
from obspy.signal.spectral_estimation import get_nhnm, get_nlnm  # noqa: E402
from obspy.signal.trigger import classic_sta_lta  # noqa: E402

log = logging.getLogger("station_media")

ARCHIVE = "/home/sysop/seiscomp/var/lib/archive"
FDSN = "http://localhost:8081/fdsnws/station/1/query"
OUT_ROOT = "/home/sysop/station_qc/media_out"
SEISMIC_CHANNEL = re.compile(r"^[SBHEC]H[ZNE123]$")
FULL_SCALE = 2 ** 23            # 24-bit digitizers
PSD_BAND_S = (0.1, 5.0)         # compared with the noise models; band of the short-period sensors
HV_WIN_S = 60.0
HV_FMIN_PEAK = 0.5
HV_FREQS = np.logspace(np.log10(0.2), np.log10(25.0), 160)
HV_MAX_WINDOWS = 300
OVERVIEW_HP_HZ = 0.5
DPI = 72


def stations_with_data(archive, day):
    """{(net, sta): {(loc, cha): path}} of seismic day files for `day`."""
    out = {}
    doy = day.timetuple().tm_yday
    for f in glob.glob(f"{archive}/{day.year}/*/*/*.D/*.D.{day.year}.{doy:03d}"):
        net, sta, loc, cha = os.path.basename(f).split(".")[:4]
        if SEISMIC_CHANNEL.match(cha) and os.path.getsize(f):
            out.setdefault((net, sta), {})[(loc, cha)] = f
    return out


def inventory(net, sta):
    """All epochs with responses; no time window (see the note in the .51 worker)."""
    r = requests.get(FDSN, params=dict(network=net, station=sta, channel="?H?", level="response"), timeout=60)
    if r.status_code != 200 or not r.content:
        return None
    return read_inventory(io.BytesIO(r.content))


def channel_meta(inv, tr):
    """Sensitivity, sensor and coordinates for the channel epoch in use."""
    meta = {}
    if inv is None:
        return meta
    picked = inv.select(network=tr.stats.network, station=tr.stats.station, location=tr.stats.location,
                        channel=tr.stats.channel, time=tr.stats.starttime)
    for n in picked:
        for s in n:
            for c in s.channels:
                meta["sensor"] = (c.sensor.description or c.sensor.model or c.sensor.type or "") if c.sensor else ""
                if c.response and c.response.instrument_sensitivity:
                    meta["sensitivity"] = float(c.response.instrument_sensitivity.value)
                return meta
    return meta


def psd_vs_models(ppsd):
    per, med = ppsd.get_percentile(percentile=50)
    _, p10 = ppsd.get_percentile(percentile=10)
    _, p90 = ppsd.get_percentile(percentile=90)
    lp, ln = get_nlnm()
    hp, hn = get_nhnm()
    nl = np.interp(np.log10(per), np.log10(lp), ln)
    nh = np.interp(np.log10(per), np.log10(hp), hn)
    band = (per >= PSD_BAND_S[0]) & (per <= PSD_BAND_S[1])
    return {
        "psd_hours": len(ppsd.times_processed),
        "psd_median_db_1s": round(float(np.interp(0.0, np.log10(per), med)), 1),
        "psd_above_nhnm_pct": round(float(np.mean(med[band] > nh[band]) * 100), 1),
        "psd_below_nlnm_pct": round(float(np.mean(med[band] < nl[band]) * 100), 1),
        "psd_spread_db": round(float(np.median(p90[band] - p10[band])), 1),
    }


def channel_media(path, inv, day, outdir, sid):
    """Numbers and PPSD image for one channel; also returns the traces and sensitivity."""
    t0 = UTCDateTime(day.isoformat())
    st = read(path)
    st.merge(method=1)
    st = st.split()
    st.trim(t0, t0 + 86400)
    traces = [tr for tr in st if tr.stats.npts > 1]
    m, images = {}, {}
    if not traces:
        return m, images, [], None
    meta = channel_meta(inv, traces[0])
    sens = meta.get("sensitivity")
    if meta.get("sensor"):
        m["sensor"] = meta["sensor"][:80]
    if sens:
        m["sensitivity"] = sens
    allx = np.concatenate([tr.data.astype(np.float64) for tr in traces])
    m["dc_pct_full_scale"] = round(float(abs(allx.mean()) / FULL_SCALE * 100), 2)
    if sens:
        m["rms_um_s"] = float("%.4g" % (allx.std() / abs(sens) * 1e6))   # some metadata has a negative gain
    if inv is None or not sens:
        m["ppsd_error"] = "no instrument response"
        return m, images, traces, sens
    try:
        sr = traces[0].stats.sampling_rate
        ppsd = PPSD(traces[0].stats, metadata=inv, ppsd_length=3600.0, overlap=0.5, db_bins=(-200, -20, 1.0),
                    period_limits=(max(0.02, 2.5 / sr), 50.0))
        ppsd.add(Stream(traces))
        if len(ppsd.times_processed):
            m.update(psd_vs_models(ppsd))
            fig = ppsd.plot(show=False, show_noise_models=True, show_mode=False, show_mean=False,
                            show_percentiles=True, percentiles=[10, 50, 90])
            fig.set_size_inches(7.5, 5.0)
            fig.suptitle(f"{sid}  {day}  PPSD ({len(ppsd.times_processed)} h)", fontsize=10)
            name = f"{sid}_ppsd.png"
            fig.savefig(os.path.join(outdir, name), dpi=DPI)
            plt.close(fig)
            images["ppsd"] = name
        else:
            m["ppsd_error"] = "no full hour of data"
    except Exception as exc:
        m["ppsd_error"] = repr(exc)[:200]
    return m, images, traces, sens


def overview(by_cha, sens_by_cha, day, outdir, sid):
    t0 = UTCDateTime(day.isoformat())
    chans = sorted(by_cha)
    fig, axes = plt.subplots(len(chans), 1, figsize=(10, 1.6 * len(chans) + 0.6), sharex=True, squeeze=False)
    for ax, cha in zip(axes[:, 0], chans):
        for tr in by_cha[cha]:
            n = int(60 * tr.stats.sampling_rate)
            hp = tr.copy()
            hp.data = hp.data.astype(float)
            hp.detrend("demean")
            hp.filter("highpass", freq=OVERVIEW_HP_HZ, corners=2, zerophase=True)
            sens = sens_by_cha.get(cha)
            x = hp.data / abs(sens) * 1e6 if sens else hp.data
            k = len(x) // n
            if k == 0:
                continue
            blk = x[:k * n].reshape(k, n)
            th = (tr.stats.starttime - t0) / 3600.0 + np.arange(k) / 60.0
            ax.fill_between(th, blk.min(axis=1), blk.max(axis=1), color="k", lw=0, step="mid")
        ax.set_ylabel(cha + (" µm/s" if sens_by_cha.get(cha) else " counts"), fontsize=8)
        ax.set_xlim(0, 24)
        ax.grid(alpha=0.3)
        ax.tick_params(labelsize=7)
    axes[-1, 0].set_xticks(range(0, 25, 2))
    axes[-1, 0].set_xlabel(f"hours UTC, {day}   (1-min min/max, high-pass {OVERVIEW_HP_HZ} Hz)", fontsize=8)
    fig.suptitle(f"{sid}  24 h overview", fontsize=10)
    fig.tight_layout()
    name = f"{sid}_overview.png"
    fig.savefig(os.path.join(outdir, name), dpi=DPI)
    plt.close(fig)
    return name


def ko_matrix(freqs, centers, b=40.0):
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log10(freqs[None, :] / centers[:, None]) * b
        w = (np.sin(r) / r) ** 4
    w[~np.isfinite(w)] = 1.0
    w[np.abs(r) > np.pi * 2] = 0.0
    return w / w.sum(axis=1, keepdims=True)


def hvsr(by_cha, outdir, sid):
    """Noise H/V from quiet 60 s windows common to E, N, Z (SESAME 2004 checks), as on .51."""
    need = {cha[-1]: cha for cha in by_cha}
    if not all(k in need for k in "ENZ"):
        return None, None
    st = Stream([tr.copy() for k in "ENZ" for tr in by_cha[need[k]]])
    st.merge(method=1, fill_value=None)
    srs = {t.stats.sampling_rate for t in st}
    if len(srs) != 1:
        return None, None
    sr = srs.pop()
    t_start = max(t.stats.starttime for t in st)
    t_end = min(t.stats.endtime for t in st)
    n = int(HV_WIN_S * sr)
    comps = {k: st.select(channel="*" + k)[0].slice(t_start, t_end).data for k in "ENZ"}
    nwin = min(len(v) for v in comps.values()) // n
    if nwin < 10:
        return None, None
    blocks = {}
    for k, v in comps.items():
        v = v[:nwin * n]
        mask = np.ma.getmaskarray(v).reshape(nwin, n).any(axis=1)
        blocks[k] = (np.ma.filled(v, 0).astype(float).reshape(nwin, n), mask)
    bad = blocks["E"][1] | blocks["N"][1] | blocks["Z"][1]
    z = blocks["Z"][0]
    rms = np.sqrt(np.mean((z - z.mean(axis=1, keepdims=True)) ** 2, axis=1))
    med = np.median(rms[~bad]) if (~bad).any() else 0
    bad |= rms > 2.0 * med
    flat_z = np.ma.filled(comps["Z"][:nwin * n], 0).astype(float)
    cft = classic_sta_lta(flat_z - flat_z.mean(), int(1 * sr), int(30 * sr)).reshape(nwin, n)
    bad |= cft.max(axis=1) > 2.5
    good = np.flatnonzero(~bad)
    if len(good) < 10:
        return {"n_windows": int(len(good)), "error": "too few quiet windows"}, None
    if len(good) > HV_MAX_WINDOWS:
        good = good[np.linspace(0, len(good) - 1, HV_MAX_WINDOWS).astype(int)]
    taper = np.ones(n)
    tw = int(0.05 * n)
    taper[:tw] = 0.5 * (1 - np.cos(np.pi * np.arange(tw) / tw))
    taper[-tw:] = taper[:tw][::-1]
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    sel = (freqs >= 0.1) & (freqs <= min(30.0, sr / 2.5))
    grid = HV_FREQS[HV_FREQS <= min(25.0, sr / 2.5)]
    W = ko_matrix(freqs[sel], grid)
    spec = {}
    for k in "ENZ":
        x = blocks[k][0][good]
        x = (x - x.mean(axis=1, keepdims=True)) * taper
        spec[k] = np.abs(np.fft.rfft(x, axis=1))[:, sel] @ W.T
    H = np.sqrt((spec["E"] ** 2 + spec["N"] ** 2) / 2.0)
    hv = H / np.maximum(spec["Z"], 1e-30)
    lhv = np.log(hv)
    mean = np.exp(lhv.mean(axis=0))
    sd = lhv.std(axis=0)
    fsel = (grid >= HV_FMIN_PEAK) & (grid <= 20.0)
    i0 = np.flatnonzero(fsel)[np.argmax(mean[fsel])]
    f0, a0 = float(grid[i0]), float(mean[i0])
    pk = grid[np.argmax(np.where(fsel[None, :], hv, -np.inf), axis=1)]
    sigma_f = float(np.std(pk))
    nw = len(good)
    lo_band = (grid >= 0.5 * f0) & (grid <= 2 * f0)
    sig_a = np.exp(sd)
    rel = [f0 > 10.0 / HV_WIN_S, f0 * HV_WIN_S * nw > 200,
           bool(np.all(sig_a[lo_band] < (2.0 if f0 > 0.5 else 3.0)))]
    fm = (grid >= f0 / 4) & (grid < f0)
    fp = (grid > f0) & (grid <= 4 * f0)
    eps = 0.25 if f0 < 0.2 else 0.2 if f0 < 0.5 else 0.15 if f0 < 1 else 0.10 if f0 < 2 else 0.05
    theta = 3.0 if f0 < 0.2 else 2.5 if f0 < 0.5 else 2.0 if f0 < 1 else 1.78 if f0 < 2 else 1.58
    clar = [bool(fm.any() and (mean[fm] < a0 / 2).any()), bool(fp.any() and (mean[fp] < a0 / 2).any()),
            a0 > 2.0, sigma_f < eps * f0, float(sig_a[i0]) < theta]
    res = {"f0_hz": round(f0, 3), "a0": round(a0, 2), "sigma_f_hz": round(sigma_f, 3),
           "n_windows": int(nw), "sesame_reliable": bool(all(rel)),
           "sesame_clarity_passed": int(sum(clar)), "sesame_clarity_of": 5}
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for row in hv[np.linspace(0, nw - 1, min(nw, 80)).astype(int)]:
        ax.loglog(grid, row, color="0.75", lw=0.4)
    ax.loglog(grid, mean, "k-", lw=2, label="geometric mean")
    ax.loglog(grid, mean * np.exp(sd), "k--", lw=1, label="±1 σ")
    ax.loglog(grid, mean / np.exp(sd), "k--", lw=1)
    ax.axvline(f0, color="tab:red", lw=1)
    ax.axhline(1, color="0.5", lw=0.6)
    ax.set_xlim(grid[0], grid[-1])
    ax.set_ylim(0.1, max(10, a0 * 2))
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("H/V")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title(f"{sid}  noise HVSR  f0={f0:.2f} Hz  A0={a0:.1f}  ({nw} × {HV_WIN_S:.0f} s; SESAME "
                 f'{"reliable" if all(rel) else "not reliable"}, clarity {sum(clar)}/5)', fontsize=9)
    fig.tight_layout()
    name = f"{sid}_hvsr.png"
    fig.savefig(os.path.join(outdir, name), dpi=DPI)
    plt.close(fig)
    return res, name


def process_station(args):
    net, sta, files, day, out_root = args
    outdir = os.path.join(out_root, day.isoformat(), f"{net}.{sta}")
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        os.remove(os.path.join(outdir, f))
    payload = {"day": day.isoformat(), "network": net, "station": sta, "channels": [],
               "images": {}, "hvsr": None}
    try:
        inv = inventory(net, sta)
        stations = [s for n in (inv or []) for s in n]
        if stations:
            s = max(stations, key=lambda x: x.start_date)
            payload.update(latitude=s.latitude, longitude=s.longitude, elevation=s.elevation,
                           site=(s.site.name or "")[:120])
        by_loc = {}
        for (loc, cha), path in sorted(files.items()):
            sid = f"{net}.{sta}.{loc}.{cha}"
            m, images, traces, sens = channel_media(path, inv, day, outdir, sid)
            payload["channels"].append({"location": loc, "channel": cha, "metrics": m, "images": images})
            if traces:
                by_loc.setdefault(loc, {})[cha] = (traces, sens)
        if by_loc:
            # one location is enough for the station images: the one with most components
            loc = max(sorted(by_loc), key=lambda k: len(by_loc[k]))
            by_cha = {c: v[0] for c, v in by_loc[loc].items()}
            sid = f"{net}.{sta}"
            payload["images"]["overview"] = overview(by_cha, {c: v[1] for c, v in by_loc[loc].items()},
                                                     day, outdir, sid)
            try:
                res, img = hvsr(by_cha, outdir, sid)
                payload["hvsr"] = res
                if img:
                    payload["images"]["hvsr"] = img
            except Exception as exc:
                payload["hvsr"] = {"error": repr(exc)[:200]}
    except Exception as exc:
        payload["error"] = repr(exc)[:300]
        log.error("%s.%s %s: %s", net, sta, day, traceback.format_exc())
    with open(os.path.join(outdir, "payload.json"), "w") as fh:
        json.dump(payload, fh, default=str)
    return outdir


def upload(outdir, url, token):
    with open(os.path.join(outdir, "payload.json")) as fh:
        payload = fh.read()
    names = sorted(f for f in os.listdir(outdir) if f.endswith(".png"))
    handles = [open(os.path.join(outdir, f), "rb") for f in names]
    try:
        for attempt in range(3):
            for fh in handles:
                fh.seek(0)
            try:
                r = requests.post(url, data={"payload": payload},
                                  files=[("files", (n, fh, "image/png")) for n, fh in zip(names, handles)],
                                  headers={"Authorization": f"Token {token}", "User-Agent": "station-media/1"},
                                  timeout=120)
                if r.status_code == 200:
                    return True
                log.warning("upload %s: HTTP %s %s", outdir, r.status_code, r.text[:200])
                if r.status_code < 500:
                    return False
            except requests.RequestException as exc:
                log.warning("upload %s: %s", outdir, exc)
            time.sleep(10 * (attempt + 1))
    finally:
        for fh in handles:
            fh.close()
    return False


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--day", default="yesterday", help="YYYY-MM-DD or 'yesterday' (UTC)")
    p.add_argument("--archive", default=ARCHIVE)
    p.add_argument("--stations", help="comma-separated station codes (default: all)")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--post", action="store_true", help="POST to new-datin")
    p.add_argument("--out", default=OUT_ROOT, help="folder for results; day folders are replaced")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    day = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
           if args.day == "yesterday" else dt.date.fromisoformat(args.day))
    only = set(args.stations.split(",")) if args.stations else None
    found = stations_with_data(args.archive, day)
    jobs = [(n, s, f, day, args.out) for (n, s), f in sorted(found.items()) if not only or s in only]
    t = time.time()
    with Pool(args.workers) as pool:
        dirs = pool.map(process_station, jobs, chunksize=1)
    log.info("%s: %d stations in %.0f s", day, len(dirs), time.time() - t)
    if not args.post:
        return 0
    base = re.sub(r"/qc/api/.*$", "", os.environ["QC_API_URL"])
    token = os.environ["QC_API_TOKEN"]
    ok = 0
    for d in dirs:
        if upload(d, f"{base}/qc/api/station-media/", token):
            ok += 1
            shutil.rmtree(d, ignore_errors=True)   # .189 keeps the images; failed days stay here
    log.info("%s: uploaded %d of %d stations", day, ok, len(dirs))
    return 0 if ok == len(dirs) else 1


if __name__ == "__main__":
    sys.exit(main())
