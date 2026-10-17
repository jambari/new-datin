"""Grafik laporan (matplotlib, Agg) sebagai data URI PNG agar laporan bisa dicetak utuh."""
import base64
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({
    "font.family": ["Liberation Sans", "DejaVu Sans"],
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#e5e7eb",
    "grid.linewidth": 0.6,
    "axes.axisbelow": True,
    "axes.edgecolor": "#9ca3af",
    "axes.titleweight": "bold",
    "axes.titlesize": 10,
    "mathtext.default": "regular",
})

NAVY = "#1f3864"
RED = "#dc2626"
GREEN = "#16a34a"
AMBER = "#d97706"
GRAY = "#9ca3af"


def to_data_uri(fig, dpi=160):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def new_figure(width=7.4, height=2.9, **kwargs):
    return plt.subplots(figsize=(width, height), **kwargs)


def thousands(ax, axis="y"):
    fmt = matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}".replace(",", "."))
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)
