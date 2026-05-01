from django.db import models


class Event(models.Model):
    """One earthquake. Identified by SeisComP public_id. Stable across
    re-commits — magnitude/hypocenter may be updated, but the event row
    persists so QC history is preserved."""
    public_id = models.CharField(max_length=64, unique=True, db_index=True)
    origin_time = models.DateTimeField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    depth_km = models.FloatField()
    magnitude = models.FloatField(null=True, blank=True)
    magnitude_type = models.CharField(max_length=8, null=True, blank=True)
    region = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_committed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-origin_time"]

    def __str__(self) -> str:
        mag = f"  M{self.magnitude:.1f}" if self.magnitude is not None else ""
        return f"{self.public_id}{mag}  {self.origin_time:%Y-%m-%d %H:%M}"

    @property
    def latest_run(self):
        return self.runs.order_by("-run_number").first()

    @property
    def run_count(self):
        return self.runs.count()

    @property
    def qc_summary(self) -> dict:
        latest = self.latest_run
        if not latest:
            return {"green": 0, "yellow": 0, "red": 0, "unknown": 0, "total": 0}
        return latest.qc_summary

    @property
    def has_final_review(self) -> bool:
        """True if any run on this event has status 'reviewed' or 'final'.
        Useful for the event list — events with a final review are settled
        and no longer need junior-analyst attention."""
        return self.runs.filter(
            evaluation_status__in=("reviewed", "final")
        ).exists()

    @property
    def latest_status(self) -> str:
        latest = self.latest_run
        return latest.evaluation_status if latest else ""


class QCRun(models.Model):
    """One QC pass — created each time the worker POSTs after an analyst
    commit. Re-commits create new runs, preserving history.

    A QCRun also captures a snapshot of the event parameters as they
    were AT commit time. The parent Event row keeps the latest values
    for convenience, but each historical run shows whichever values
    were committed alongside that run's picks. This gives users a
    proper audit trail of how location, depth, and magnitude evolved
    across commits.
    """
    event = models.ForeignKey(Event, related_name="runs",
                              on_delete=models.CASCADE)
    run_number = models.PositiveIntegerField(
        help_text="1, 2, 3, … for successive commits on this event",
    )
    committed_at = models.DateTimeField(auto_now_add=True)
    overview_image = models.ImageField(
        upload_to="overview_images/", null=True, blank=True,
        help_text="Multi-station record-section plot for this run",
    )
    notes = models.TextField(
        blank=True, default="",
        help_text="Optional note from the worker (e.g. 'after re-pick of ABCD')",
    )

    # ---------- Event-parameter snapshot (frozen at commit time) ----------
    # The Event row is mutable (always reflects the latest commit), but
    # these fields preserve what the parameters WERE for this run.
    snap_origin_time = models.DateTimeField(null=True, blank=True)
    snap_latitude = models.FloatField(null=True, blank=True)
    snap_longitude = models.FloatField(null=True, blank=True)
    snap_depth_km = models.FloatField(null=True, blank=True)
    snap_magnitude = models.FloatField(null=True, blank=True)
    snap_magnitude_type = models.CharField(max_length=8, null=True, blank=True)
    snap_region = models.CharField(max_length=255, null=True, blank=True)

    # ---------- SeisComP evaluation state at commit time ----------
    # mode  = 'automatic' | 'manual'
    # status = 'preliminary' | 'confirmed' | 'reviewed' | 'final' | 'rejected'
    evaluation_mode = models.CharField(max_length=16, null=True, blank=True)
    evaluation_status = models.CharField(max_length=16, null=True, blank=True)

    class Meta:
        ordering = ["-run_number"]
        unique_together = [("event", "run_number")]

    def __str__(self) -> str:
        return f"{self.event.public_id} · run #{self.run_number}"

    @property
    def qc_summary(self) -> dict:
        flags = self.station_results.values_list("qc_flag", flat=True)
        return {
            "green":   sum(1 for f in flags if f == "green"),
            "yellow":  sum(1 for f in flags if f == "yellow"),
            "red":     sum(1 for f in flags if f == "red"),
            "unknown": sum(1 for f in flags if f == "unknown"),
            "total":   len(flags),
        }

    # ----- Convenience accessors for templates: prefer snapshot, fall
    #       back to parent Event for very old runs that pre-date the
    #       snapshot fields.
    @property
    def origin_time_at_commit(self):
        return self.snap_origin_time or self.event.origin_time

    @property
    def latitude_at_commit(self):
        return self.snap_latitude if self.snap_latitude is not None else self.event.latitude

    @property
    def longitude_at_commit(self):
        return self.snap_longitude if self.snap_longitude is not None else self.event.longitude

    @property
    def depth_at_commit(self):
        return self.snap_depth_km if self.snap_depth_km is not None else self.event.depth_km

    @property
    def magnitude_at_commit(self):
        return self.snap_magnitude if self.snap_magnitude is not None else self.event.magnitude

    @property
    def magnitude_type_at_commit(self):
        return self.snap_magnitude_type or self.event.magnitude_type

    @property
    def region_at_commit(self):
        return self.snap_region or self.event.region

    @property
    def is_final(self) -> bool:
        """True when the analyst marked this commit as 'reviewed' or 'final' —
        i.e. the senior signed off and no further changes are expected."""
        s = (self.evaluation_status or "").lower()
        return s in ("reviewed", "final")

    @property
    def is_preliminary(self) -> bool:
        s = (self.evaluation_status or "").lower()
        return s == "preliminary"

    def diff_to_previous(self):
        """Return a dict describing what parameters changed since the
        previous run, or None if this is the first run."""
        prev = (self.event.runs
                .filter(run_number=self.run_number - 1)
                .first())
        if prev is None:
            return None
        diffs = {}
        pairs = [
            ("latitude",      self.latitude_at_commit,   prev.latitude_at_commit),
            ("longitude",     self.longitude_at_commit,  prev.longitude_at_commit),
            ("depth_km",      self.depth_at_commit,      prev.depth_at_commit),
            ("magnitude",     self.magnitude_at_commit,  prev.magnitude_at_commit),
            ("origin_time",   self.origin_time_at_commit, prev.origin_time_at_commit),
        ]
        for name, cur, old in pairs:
            if cur is None or old is None:
                continue
            if isinstance(cur, float):
                if abs(cur - old) > 1e-6:
                    diffs[name] = {"old": old, "new": cur, "delta": cur - old}
            elif cur != old:
                diffs[name] = {"old": old, "new": cur}
        return diffs if diffs else None


class StationResult(models.Model):
    QC_FLAGS = [
        ("green", "Green"),
        ("yellow", "Yellow"),
        ("red", "Red"),
        ("unknown", "Unknown"),
    ]
    DIST_CLASSES = [
        ("local", "Local"),
        ("regional", "Regional"),
        ("teleseismic", "Teleseismic"),
    ]

    run = models.ForeignKey(QCRun, related_name="station_results",
                            on_delete=models.CASCADE)
    network = models.CharField(max_length=4)
    station = models.CharField(max_length=8)
    # Optional station coordinates (filled in when available, e.g. from
    # an inventory lookup). Used by the map view.
    station_lat = models.FloatField(null=True, blank=True)
    station_lon = models.FloatField(null=True, blank=True)
    distance_deg = models.FloatField(null=True, blank=True)
    azimuth = models.FloatField(null=True, blank=True)
    distance_class = models.CharField(max_length=16, choices=DIST_CLASSES,
                                      default="regional")
    filter_freqmin = models.FloatField()
    filter_freqmax = models.FloatField()

    analyst_p = models.DateTimeField(null=True, blank=True)
    analyst_s = models.DateTimeField(null=True, blank=True)
    auto_p = models.DateTimeField(null=True, blank=True)
    auto_s = models.DateTimeField(null=True, blank=True)
    auto_p_prob = models.FloatField(null=True, blank=True)
    auto_s_prob = models.FloatField(null=True, blank=True)
    delta_p = models.FloatField(null=True, blank=True,
                                help_text="auto_P − analyst_P, seconds")
    delta_s = models.FloatField(null=True, blank=True,
                                help_text="auto_S − analyst_S, seconds")

    qc_flag = models.CharField(max_length=8, choices=QC_FLAGS,
                               default="unknown")
    image = models.ImageField(upload_to="waveform_images/", null=True, blank=True)
    waveform_file = models.FileField(upload_to="waveforms/", null=True, blank=True)

    reviewer_note = models.TextField(blank=True, default="")
    reviewer_action = models.CharField(
        max_length=16,
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted analyst pick"),
            ("revised", "Pick revision needed"),
            ("rejected", "Reject station"),
        ],
        default="pending",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_name = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["distance_deg", "station"]
        unique_together = [("run", "network", "station")]

    def __str__(self) -> str:
        return (f"{self.run.event.public_id} run#{self.run.run_number} "
                f":: {self.network}.{self.station}")

    @property
    def event(self):
        """Convenience accessor used by templates."""
        return self.run.event
