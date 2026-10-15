"""Build SPECFEM3D Cartesian input files for one earthquake (regional, 1D crust).

Runs on the SPECFEM host (172.21.63.51, Python 3.8). Uses the socal1D
meshfem3D example shipped with SPECFEM as template and only overrides the
keys we need, so it follows whatever SPECFEM version is installed.

Model: flat-topped block, 1D layered crust/upper mantle (AK135 crust),
point-source moment tensor from strike/dip/rake + Mw (Aki & Richards),
half duration from the GCMT empirical scaling.
"""
import math
import os
import re

TEMPLATE_DIR = os.path.expanduser(
    "~/specfem3d/EXAMPLES/applications/meshfem3D_examples/socal1D/DATA")

# Layers from bottom to top: (top depth km, element layers, rho, vp, vs, Qmu).
# Bottom of the block is DEPTH_KM. AK135 crust (two layers) over mantle.
DEPTH_KM = 80.0
LAYERS = [
    (35.0, 8, 3320, 8040, 4480, 600.0),   # mantle 35-80 km
    (20.0, 5, 2920, 6500, 3850, 400.0),   # lower crust 20-35 km
    (0.0, 7, 2720, 5800, 3460, 250.0),    # upper crust 0-20 km
]
NZ_DOUBLING = 7          # one mesh doubling inside the mantle layer


def moment_tensor(strike, dip, rake, m0):
    """Harvard convention (r, t, p) moment tensor components from fault angles."""
    s, d, r = (math.radians(x) for x in (strike, dip, rake))
    mxx = -m0 * (math.sin(d) * math.cos(r) * math.sin(2 * s)
                 + math.sin(2 * d) * math.sin(r) * math.sin(s) ** 2)
    myy = m0 * (math.sin(d) * math.cos(r) * math.sin(2 * s)
                - math.sin(2 * d) * math.sin(r) * math.cos(s) ** 2)
    mzz = m0 * math.sin(2 * d) * math.sin(r)
    mxy = m0 * (math.sin(d) * math.cos(r) * math.cos(2 * s)
                + 0.5 * math.sin(2 * d) * math.sin(r) * math.sin(2 * s))
    mxz = -m0 * (math.cos(d) * math.cos(r) * math.cos(s)
                 + math.cos(2 * d) * math.sin(r) * math.sin(s))
    myz = -m0 * (math.cos(d) * math.cos(r) * math.sin(s)
                 - math.cos(2 * d) * math.sin(r) * math.cos(s))
    return {"Mrr": mzz, "Mtt": mxx, "Mpp": myy, "Mrt": mxz, "Mrp": -myz, "Mtp": -mxy}


def utm_zone(lon, lat):
    zone = int((lon + 180.0) // 6.0) + 1
    return -zone if lat < 0 else zone


def _set_keys(text, values):
    for key, val in values.items():
        pat = re.compile(r"^(%s\s*=\s*)[^#\n]*" % re.escape(key), re.M)
        if not pat.search(text):
            raise KeyError("key %s not found in template" % key)
        text = pat.sub(lambda m: m.group(1) + str(val) + " ", text, count=1)
    return text


def domain(event, half_width_km):
    lat, lon = event["latitude"], event["longitude"]
    dlat = half_width_km / 111.19
    dlon = half_width_km / (111.19 * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def write_inputs(run_dir, event, stations, params):
    """event: dict(latitude, longitude, depth_km, magnitude, strike, dip, rake,
    origin 'YYYY-MM-DDTHH:MM:SS', name). params: half_width_km, nex, dt, duration_s,
    frame_every_s. Returns the dict of derived values (domain, nstep, hdur, ...)."""
    data = os.path.join(run_dir, "DATA")
    mesh_dir = os.path.join(data, "meshfem3D_files")
    os.makedirs(mesh_dir, exist_ok=True)

    lat_min, lat_max, lon_min, lon_max = domain(event, params["half_width_km"])
    zone = utm_zone(event["longitude"], event["latitude"])
    nex = params["nex"]
    nz_total = sum(l[1] for l in LAYERS)
    dt = params["dt"]
    nstep = int(round(params["duration_s"] / dt))
    frame_every = max(1, int(round(params["frame_every_s"] / dt)))

    # --- Mesh_Par_file ------------------------------------------------------
    with open(os.path.join(TEMPLATE_DIR, "meshfem3D_files", "Mesh_Par_file")) as f:
        mesh = f.read()
    mesh = _set_keys(mesh, {
        "LATITUDE_MIN": "%.5fd0" % lat_min, "LATITUDE_MAX": "%.5fd0" % lat_max,
        "LONGITUDE_MIN": "%.5fd0" % lon_min, "LONGITUDE_MAX": "%.5fd0" % lon_max,
        "DEPTH_BLOCK_KM": "%.1fd0" % DEPTH_KM,
        "UTM_PROJECTION_ZONE": zone, "SUPPRESS_UTM_PROJECTION": ".false.",
        "INTERFACES_FILE": "interfaces.dat",
        "NEX_XI": nex, "NEX_ETA": nex, "NPROC_XI": 1, "NPROC_ETA": 1,
        "USE_REGULAR_MESH": ".false.", "NDOUBLINGS": 1, "NZ_DOUBLING_1": NZ_DOUBLING,
        "CREATE_ABAQUS_FILES": ".false.", "CREATE_DX_FILES": ".false.",
        "CREATE_VTK_FILES": ".false.",
        "LOCAL_PATH": "./OUTPUT_FILES/DATABASES_MPI",
    })
    mesh = re.sub(r"^NZ_DOUBLING_2\s*=.*\n", "", mesh, flags=re.M)
    head = mesh[:mesh.index("NMATERIALS")]
    mats, regions = [], []
    iz = 1
    for i, (_top, n, rho, vp, vs, qmu) in enumerate(LAYERS, start=1):
        mats.append("%d  %d  %d  %d  9999.  %.1f  0  2" % (i, rho, vp, vs, qmu))
        regions.append("1  %d  1  %d  %d  %d  %d" % (nex, nex, iz, iz + n - 1, i))
        iz += n
    mesh = (head + "NMATERIALS                      = %d\n" % len(mats)
            + "\n".join(mats) + "\n\nNREGIONS                        = %d\n" % len(regions)
            + "\n".join(regions) + "\n")
    with open(os.path.join(mesh_dir, "Mesh_Par_file"), "w") as f:
        f.write(mesh)

    # --- interfaces: flat surfaces at the layer tops (metres, up positive) --
    lines = ["%d" % len(LAYERS)]
    grid = ".false. 2 2 %.3fd0 %.3fd0 10.d0 10.d0" % (lon_min - 2.0, lat_min - 2.0)
    for i, layer in enumerate(LAYERS, start=1):
        name = "interface%d.dat" % i
        with open(os.path.join(mesh_dir, name), "w") as f:
            f.write(("%d\n" % int(-layer[0] * 1000)) * 4)
        lines += [grid, name]
    lines += ["%d" % l[1] for l in LAYERS]
    with open(os.path.join(mesh_dir, "interfaces.dat"), "w") as f:
        f.write("\n".join(lines) + "\n")

    # --- Par_file -------------------------------------------------------------
    with open(os.path.join(TEMPLATE_DIR, "Par_file")) as f:
        par = f.read()
    par = _set_keys(par, {
        "SIMULATION_TYPE": 1, "NOISE_TOMOGRAPHY": 0, "SAVE_FORWARD": ".false.",
        "UTM_PROJECTION_ZONE": zone, "SUPPRESS_UTM_PROJECTION": ".false.",
        "NPROC": 1, "NSTEP": nstep, "DT": dt, "NGNOD": 8, "MODEL": "default",
        "APPROXIMATE_OCEAN_LOAD": ".false.", "TOPOGRAPHY": ".false.",
        "ATTENUATION": ".false.", "ANISOTROPY": ".false.", "GRAVITY": ".false.",
        "PML_CONDITIONS": ".false.", "STACEY_ABSORBING_CONDITIONS": ".true.",
        "STACEY_INSTEAD_OF_FREE_SURFACE": ".false.",
        "CREATE_SHAKEMAP": ".true.", "MOVIE_SURFACE": ".true.", "MOVIE_TYPE": 1,
        "MOVIE_VOLUME": ".false.", "SAVE_DISPLACEMENT": ".false.",
        "USE_HIGHRES_FOR_MOVIES": ".false.", "NTSTEP_BETWEEN_FRAMES": frame_every,
        "HDUR_MOVIE": "0.0", "SAVE_MESH_FILES": ".false.",
        "LOCAL_PATH": "./OUTPUT_FILES/DATABASES_MPI",
        "NTSTEP_BETWEEN_OUTPUT_INFO": 500, "USE_SOURCES_RECEIVERS_Z": ".false.",
        "USE_FORCE_POINT_SOURCE": ".false.", "USE_RICKER_TIME_FUNCTION": ".false.",
        "NTSTEP_BETWEEN_OUTPUT_SEISMOS": nstep,
        "SAVE_SEISMOGRAMS_DISPLACEMENT": ".false.", "SAVE_SEISMOGRAMS_VELOCITY": ".true.",
        "SAVE_SEISMOGRAMS_ACCELERATION": ".false.", "USE_BINARY_FOR_SEISMOGRAMS": ".false.",
        "GPU_MODE": ".true.",
    })
    with open(os.path.join(data, "Par_file"), "w") as f:
        f.write(par)

    # --- CMTSOLUTION ----------------------------------------------------------
    m0_nm = 10 ** (1.5 * event["magnitude"] + 9.1)
    m0_dyncm = m0_nm * 1e7
    hdur = 1.05e-8 * m0_dyncm ** (1.0 / 3.0)
    mt = moment_tensor(event["strike"], event["dip"], event["rake"], m0_dyncm)
    o = event["origin"]  # 'YYYY-MM-DDTHH:MM:SS'
    pde = "PDE %s %s %s %s %s %s %.4f %.4f %.1f %.1f %.1f %s" % (
        o[0:4], o[5:7], o[8:10], o[11:13], o[14:16], o[17:19],
        event["latitude"], event["longitude"], event["depth_km"],
        event["magnitude"], event["magnitude"], event.get("name", "event").replace(" ", "_"))
    cmt = [pde,
           "event name:     %s" % event.get("name", "event").replace(" ", "_")[:20],
           "time shift:       0.0000",
           "half duration:    %.4f" % hdur,
           "latitude:       %.4f" % event["latitude"],
           "longitude:      %.4f" % event["longitude"],
           "depth:          %.4f" % event["depth_km"]]
    cmt += ["%s:  %+.6e" % (k, mt[k]) for k in ("Mrr", "Mtt", "Mpp", "Mrt", "Mrp", "Mtp")]
    with open(os.path.join(data, "CMTSOLUTION"), "w") as f:
        f.write("\n".join(cmt) + "\n")

    # --- STATIONS (only those inside the block, away from the edges) ---------
    inside = []
    margin = 0.05 * (lat_max - lat_min)
    for s in stations:
        if (lat_min + margin < s["latitude"] < lat_max - margin
                and lon_min + margin < s["longitude"] < lon_max - margin):
            inside.append(s)
    with open(os.path.join(data, "STATIONS"), "w") as f:
        for s in inside:
            f.write("%s %s %.4f %.4f 0.0 0.0\n" % (s["code"], s["network"],
                                                  s["latitude"], s["longitude"]))

    return {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max,
            "utm_zone": zone, "nstep": nstep, "dt": dt, "frame_every": frame_every,
            "hdur": hdur, "m0_nm": m0_nm, "nz": nz_total, "stations": inside}
