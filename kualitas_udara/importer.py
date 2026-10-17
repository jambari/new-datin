"""Impor CSV "Series data" KAH & SPM dari Database Kualitas Udara BMKG.

Dipakai bersama oleh perintah ``import_kualitas_udara`` dan API
``/kualitas-udara/api/import/``.
"""
import csv
from datetime import datetime

from .models import KAHSeriesData, SPMSeriesData

KAH_FIELD_MAP = {
    "PH": "ph",
    "DH": "dh",
    "CA": "ca",
    "MG": "mg",
    "NA": "na",
    "K": "k",
    "NH4": "nh4",
    "CL": "cl",
    "SO4": "so4",
    "NO3": "no3",
    "KT": "kt",
    "AC": "ac",
    "AL": "al",
    "CH": "ch",
    "OX": "ox",
}
KAH_COLUMNS = ["stasiun", "bulan", "minggu", *KAH_FIELD_MAP]
SPM_COLUMNS = ["stasiun", "timestamp", "SPM"]


class CSVFormatError(ValueError):
    """Header CSV tidak sesuai format Database Kualitas Udara."""


def parse_float(value):
    value = (value or "").strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _reader(lines, expected_columns, label):
    reader = csv.DictReader(lines)
    header = [(name or "").strip().lstrip("﻿") for name in (reader.fieldnames or [])]
    missing = [col for col in expected_columns if col not in header]
    if missing:
        raise CSVFormatError(f"CSV {label} tidak memuat kolom: {', '.join(missing)}")
    reader.fieldnames = header
    return reader


def _save(model, lookup, defaults, skip_existing):
    if skip_existing:
        if model.objects.filter(**lookup).exists():
            return "skipped"
        model.objects.create(**lookup, **defaults)
        return "created"
    _obj, was_created = model.objects.update_or_create(**lookup, defaults=defaults)
    return "created" if was_created else "updated"


def _new_counts():
    return {"created": 0, "updated": 0, "skipped": 0, "invalid": 0}


def import_kah(lines, skip_existing=False):
    """Impor baris CSV KAH (iterable of str). Kembalikan dict jumlah."""
    counts = _new_counts()
    for row in _reader(lines, KAH_COLUMNS, "KAH"):
        stasiun = (row.get("stasiun") or "").strip()
        bulan = (row.get("bulan") or "").strip()
        minggu = (row.get("minggu") or "").strip()
        if not stasiun or len(bulan) != 7 or not minggu:
            counts["invalid"] += 1
            continue
        defaults = {field: parse_float(row.get(col)) for col, field in KAH_FIELD_MAP.items()}
        lookup = {"stasiun": stasiun, "bulan": bulan, "minggu": minggu}
        counts[_save(KAHSeriesData, lookup, defaults, skip_existing)] += 1
    return counts


def import_spm(lines, skip_existing=False):
    """Impor baris CSV SPM (iterable of str). Kembalikan dict jumlah."""
    counts = _new_counts()
    for row in _reader(lines, SPM_COLUMNS, "SPM"):
        stasiun = (row.get("stasiun") or "").strip()
        try:
            timestamp = datetime.strptime((row.get("timestamp") or "").strip(), "%Y-%m-%d").date()
        except ValueError:
            counts["invalid"] += 1
            continue
        if not stasiun:
            counts["invalid"] += 1
            continue
        lookup = {"stasiun": stasiun, "timestamp": timestamp}
        defaults = {"spm": parse_float(row.get("SPM"))}
        counts[_save(SPMSeriesData, lookup, defaults, skip_existing)] += 1
    return counts
