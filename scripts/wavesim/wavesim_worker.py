#!/usr/bin/env python3
"""SPECFEM3D wave-simulation worker for new-datin (runs on 172.21.63.51).

Cron, every 5 minutes (flock keeps it to one run at a time):
  */5 * * * * flock -n /tmp/wavesim.lock python3 ~/wavesim/wavesim_worker.py >> ~/wavesim/worker.log 2>&1

Config in ~/wavesim/worker.env:
  WAVESIM_API=https://stageof-jayapura.bmkg.go.id/api/wavesim/
  WAVESIM_TOKEN=<WAVESIM_WORKER_TOKEN of new-datin>

One cycle: claim the oldest queued simulation, write SPECFEM inputs, run
mesher/databases/solver (GPU), render web assets, upload them, clean up the
large database files. Failures are reported back with the log tail.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import traceback

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import postprocess  # noqa: E402
import specfem_inputs  # noqa: E402

RUNS = os.path.join(HERE, "runs")
KEEP_RUNS = 5          # keep the last few run directories (without databases)


def load_env(path=os.path.join(HERE, "worker.env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


class Api:
    def __init__(self, base, token):
        self.base = base.rstrip("/") + "/"
        self.s = requests.Session()
        self.s.headers.update({"Authorization": "Bearer " + token,
                               "User-Agent": "datin-wavesim-worker/1.0"})

    def post(self, path, timeout=60, **kw):
        r = self.s.post(self.base + path, timeout=timeout, **kw)
        r.raise_for_status()
        return r.json()


def log(msg):
    print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def tail(path, n=60):
    try:
        with open(path, errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


def min_period(run_dir):
    """Shortest period the mesh resolves, as reported by the solver."""
    m = re.search(r"Minimum period resolved\s*=\s*([0-9.Ee+-]+)",
                  tail(os.path.join(run_dir, "OUTPUT_FILES", "output_solver.txt"), 100000))
    return round(float(m.group(1)), 2) if m else None


def run_stage(api, job_id, run_dir, name, cmd):
    api.post("%d/progress/" % job_id, data={"stage": name})
    log("job %d: %s" % (job_id, name))
    t0 = time.time()
    subprocess.run(cmd, cwd=run_dir, check=True,
                   stdout=open(os.path.join(run_dir, "OUTPUT_FILES", "log_%s.txt" % name), "w"),
                   stderr=subprocess.STDOUT)
    return time.time() - t0


def run_job(api, job):
    job_id = job["id"]
    run_dir = os.path.join(RUNS, "sim_%d" % job_id)
    shutil.rmtree(run_dir, ignore_errors=True)
    derived = specfem_inputs.write_inputs(run_dir, job["event"], job["stations"], job["params"])

    specfem = os.path.expanduser("~/specfem3d")
    os.makedirs(os.path.join(run_dir, "bin"))
    os.makedirs(os.path.join(run_dir, "OUTPUT_FILES", "DATABASES_MPI"))
    for x in ("xmeshfem3D", "xgenerate_databases", "xspecfem3D"):
        os.symlink(os.path.join(specfem, "bin", x), os.path.join(run_dir, "bin", x))

    timings = {}
    timings["mesher"] = run_stage(api, job_id, run_dir, "mesher", ["mpirun", "-np", "1", "./bin/xmeshfem3D"])
    timings["databases"] = run_stage(api, job_id, run_dir, "databases",
                                     ["mpirun", "-np", "1", "./bin/xgenerate_databases"])
    timings["solver"] = run_stage(api, job_id, run_dir, "solver", ["mpirun", "-np", "1", "./bin/xspecfem3D"])

    api.post("%d/progress/" % job_id, data={"stage": "render"})
    log("job %d: render" % job_id)
    out, result = postprocess.postprocess(run_dir, derived, job["event"])
    result["timings_s"] = {k: round(v, 1) for k, v in timings.items()}
    result["mesh"] = {"nex": job["params"]["nex"], "nz": derived["nz"],
                      "half_width_km": job["params"]["half_width_km"],
                      "min_period_s": min_period(run_dir)}

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(os.path.join(out, "pgv.png"), arcname="pgv.png")
        for name in sorted(os.listdir(os.path.join(out, "frames"))):
            tar.add(os.path.join(out, "frames", name), arcname="frames/" + name)
    buf.seek(0)
    api.post("%d/progress/" % job_id, data={"stage": "upload"})
    api.post("%d/result/" % job_id, timeout=300,
             files={"archive": ("assets.tar.gz", buf, "application/gzip")},
             data={"result": json.dumps(result),
                   "log": tail(os.path.join(run_dir, "OUTPUT_FILES", "output_solver.txt"), 40)})
    log("job %d: done (%s)" % (job_id, result["timings_s"]))
    shutil.rmtree(os.path.join(run_dir, "OUTPUT_FILES", "DATABASES_MPI"), ignore_errors=True)


def prune_runs():
    dirs = sorted((d for d in os.listdir(RUNS) if d.startswith("sim_")),
                  key=lambda d: int(d.split("_")[1]))
    for d in dirs[:-KEEP_RUNS]:
        shutil.rmtree(os.path.join(RUNS, d), ignore_errors=True)


def main():
    env = load_env()
    api = Api(env["WAVESIM_API"], env["WAVESIM_TOKEN"])
    os.makedirs(RUNS, exist_ok=True)
    job = api.post("claim/").get("job")
    if not job:
        return
    log("job %d claimed: %s M%s" % (job["id"], job["event"]["name"], job["event"]["magnitude"]))
    try:
        run_job(api, job)
    except Exception:
        run_dir = os.path.join(RUNS, "sim_%d" % job["id"])
        msg = traceback.format_exc()
        for name in ("solver", "databases", "mesher"):
            t = tail(os.path.join(run_dir, "OUTPUT_FILES", "log_%s.txt" % name), 30)
            if t:
                msg += "\n--- log_%s.txt ---\n%s" % (name, t)
                break
        log("job %d failed:\n%s" % (job["id"], msg))
        try:
            api.post("%d/fail/" % job["id"], data={"log": msg[-15000:]})
        except requests.RequestException as exc:
            log("could not report failure: %s" % exc)
    finally:
        prune_runs()


if __name__ == "__main__":
    main()
