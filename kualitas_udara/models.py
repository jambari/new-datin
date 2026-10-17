from django.db import models

# Ambang batas SPM (Suspended Particulate Matter / TSP) berdasarkan
# PP No. 41 Tahun 1999 tentang Pengendalian Pencemaran Udara:
# partikulat (SPM/TSP) 24 jam = 230 µg/m³.
SPM_THRESHOLD = 230.0
SPM_THRESHOLD_LABEL = "PP No. 41/1999 (TSP/SPM 24 jam, > 230 µg/m³)"

# Ambang batas parameter Kimia Air Hujan (KAH).
# Untuk parameter yang tidak memiliki baku mutu nasional, dipakai
# referensi umum BMKG/WMO. Nilai dapat disesuaikan dengan mudah.
# op '<' berarti "melebihi ambang" bila nilai LEBIH KECIL dari limit
# (misal pH: hujan asam bila pH < 5.6).
KAH_THRESHOLDS = {
    "PH": {"limit": 5.6, "op": "<", "unit": "", "label": "BMKG (hujan asam pH < 5.6)"},
    "DH": {"limit": 100.0, "op": ">", "unit": "µS/cm", "label": "Referensi umum DHL"},
    "CA": {"limit": 15.0, "op": ">", "unit": "mg/L", "label": "Referensi umum"},
    "MG": {"limit": 10.0, "op": ">", "unit": "mg/L", "label": "Referensi umum"},
    "NA": {"limit": 20.0, "op": ">", "unit": "mg/L", "label": "Referensi umum"},
    "K": {"limit": 10.0, "op": ">", "unit": "mg/L", "label": "Referensi umum"},
    "NH4": {"limit": 1.5, "op": ">", "unit": "mg/L", "label": "Referensi umum"},
    "CL": {"limit": 20.0, "op": ">", "unit": "mg/L", "label": "Referensi umum"},
    "SO4": {"limit": 10.0, "op": ">", "unit": "mg/L", "label": "Referensi deposisi asam"},
    "NO3": {"limit": 5.0, "op": ">", "unit": "mg/L", "label": "Referensi deposisi asam"},
    # KT, AC, AL, CH, OX: tidak memiliki ambang baku -> remark "Tidak diatur".
}

KAH_FIELD_LABELS = {
    "PH": "pH",
    "DH": "DHL",
    "CA": "Ca",
    "MG": "Mg",
    "NA": "Na",
    "K": "K",
    "NH4": "NH₄",
    "CL": "Cl",
    "SO4": "SO₄",
    "NO3": "NO₃",
    "KT": "KT",
    "AC": "AC",
    "AL": "AL",
    "CH": "CH",
    "OX": "OX",
}

KAH_FIELDS = list(KAH_FIELD_LABELS.keys())


def evaluate_threshold(value, spec):
    """Kembalikan status ambang untuk satu nilai pengukuran."""
    if value is None or spec is None:
        return "na"
    op = spec["op"]
    limit = spec["limit"]
    if op == "<":
        return "exceed" if value < limit else "normal"
    return "exceed" if value > limit else "normal"


class KAHSeriesData(models.Model):
    """Data Kimia Air Hujan (KAH) mingguan per stasiun."""

    stasiun = models.CharField(max_length=100, db_index=True)
    bulan = models.CharField(max_length=7, db_index=True, verbose_name="Bulan (YYYY-MM)")
    minggu = models.CharField(max_length=2, verbose_name="Minggu")
    ph = models.FloatField(null=True, blank=True, db_column="PH", verbose_name="pH")
    dh = models.FloatField(null=True, blank=True, db_column="DH", verbose_name="DHL (µS/cm)")
    ca = models.FloatField(null=True, blank=True, db_column="CA", verbose_name="Ca (mg/L)")
    mg = models.FloatField(null=True, blank=True, db_column="MG", verbose_name="Mg (mg/L)")
    na = models.FloatField(null=True, blank=True, db_column="NA", verbose_name="Na (mg/L)")
    k = models.FloatField(null=True, blank=True, db_column="K", verbose_name="K (mg/L)")
    nh4 = models.FloatField(null=True, blank=True, db_column="NH4", verbose_name="NH₄ (mg/L)")
    cl = models.FloatField(null=True, blank=True, db_column="CL", verbose_name="Cl (mg/L)")
    so4 = models.FloatField(null=True, blank=True, db_column="SO4", verbose_name="SO₄ (mg/L)")
    no3 = models.FloatField(null=True, blank=True, db_column="NO3", verbose_name="NO₃ (mg/L)")
    kt = models.FloatField(null=True, blank=True, db_column="KT", verbose_name="KT")
    ac = models.FloatField(null=True, blank=True, db_column="AC", verbose_name="AC")
    al = models.FloatField(null=True, blank=True, db_column="AL", verbose_name="AL")
    ch = models.FloatField(null=True, blank=True, db_column="CH", verbose_name="CH")
    ox = models.FloatField(null=True, blank=True, db_column="OX", verbose_name="OX")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kualitas_udara_kah"
        verbose_name = "KAH (Kimia Air Hujan)"
        verbose_name_plural = "KAH (Kimia Air Hujan)"
        ordering = ["-bulan", "-minggu"]
        constraints = [
            models.UniqueConstraint(
                fields=["stasiun", "bulan", "minggu"],
                name="uniq_kah_stasiun_bulan_minggu",
            ),
        ]

    def __str__(self):
        return f"KAH {self.stasiun} {self.bulan} minggu {self.minggu}"

    def get_remark(self, field_name):
        """Kembalikan dict status remark untuk satu kolom.

        status: 'exceed' -> melebihi ambang batas polusi udara,
                'normal' -> masih di bawah ambang,
                'na'     -> tidak ada ambang/nilai kosong.
        """
        spec = KAH_THRESHOLDS.get(field_name)
        value = getattr(self, field_name.lower(), None)
        status = evaluate_threshold(value, spec)
        if status == "exceed":
            op = spec["op"]
            text = f"Melebihi ambang ({op} {spec['limit']:g} {spec['unit']})".strip()
        elif status == "normal":
            text = "Normal"
        elif value is None:
            text = "Tidak ada data"
        else:
            text = "Tidak diatur"
        return {"status": status, "text": text, "label": spec["label"] if spec else ""}

    def get_exceeded_fields(self):
        """Daftar field yang melebihi ambang batas (untuk kolom Ringkasan Remark)."""
        exceeded = []
        for field_name in KAH_FIELDS:
            remark = self.get_remark(field_name)
            if remark["status"] == "exceed":
                exceeded.append(KAH_FIELD_LABELS[field_name])
        return exceeded

    def get_remark_summary(self):
        exceeded = self.get_exceeded_fields()
        if exceeded:
            return "Melebihi ambang: " + ", ".join(exceeded)
        return "Semua parameter normal"


class SPMSeriesData(models.Model):
    """Data Suspended Particulate Matter (SPM) harian per stasiun."""

    stasiun = models.CharField(max_length=100, db_index=True)
    timestamp = models.DateField(db_index=True, verbose_name="Tanggal")
    spm = models.FloatField(null=True, blank=True, db_column="SPM", verbose_name="SPM (µg/m³)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kualitas_udara_spm"
        verbose_name = "SPM (Partikulat)"
        verbose_name_plural = "SPM (Partikulat)"
        ordering = ["-timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["stasiun", "timestamp"],
                name="uniq_spm_stasiun_timestamp",
            ),
        ]

    def __str__(self):
        return f"SPM {self.stasiun} {self.timestamp}"

    def get_remark(self):
        """Kembalikan dict status remark untuk kolom SPM."""
        if self.spm is None:
            return {"status": "na", "text": "Tidak ada data", "label": SPM_THRESHOLD_LABEL}
        if self.spm > SPM_THRESHOLD:
            return {
                "status": "exceed",
                "text": f"Melebihi ambang (> {SPM_THRESHOLD:g} µg/m³)",
                "label": SPM_THRESHOLD_LABEL,
            }
        return {
            "status": "normal",
            "text": "Normal",
            "label": SPM_THRESHOLD_LABEL,
        }

    def get_remark_summary(self):
        remark = self.get_remark()
        if remark["status"] == "exceed":
            return "SPM melebihi ambang batas"
        if remark["status"] == "na":
            return "Tidak ada data SPM"
        return "SPM normal"
