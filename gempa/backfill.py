"""Isi ulang katalog Gempa JAY dari log tombol SeisComp (lihat scripts/seiscomp_backfill_extract.py).

Sebelum 2026-11-01 Send QC tidak mengirim ke website, jadi banyak baris masih memakai
nilai kiriman pertama. plan_event() hanya membaca; apply_event() menulis.

Aturan:
  * event_id kunci satu-satunya. Tanpa baris -> sisip, dengan baris -> perbarui baris itu.
  * Parameter = bulletin klik terakhir.
  * Baris yang berubah sesudah klik terakhir (edit admin / Send QC langsung) tidak
    ditimpa parameternya; petugas yang masih kosong tetap diisi.
  * petugas_kirim = jadwal pada klik pertama, petugas_qc & qc_at = klik QC terakhir.
"""
from decimal import Decimal, InvalidOperation

from django.utils.dateparse import parse_datetime

from .models import Gempa, nearest_city_description
from .seiscomp import STAGE_SEND, _on_duty_at, ingest, parse_bulletin

INSERT = 'insert'
UPDATE = 'update'
OFFICERS_ONLY = 'officers_only'
KEEP_NEWER = 'keep_newer'
NO_CHANGE = 'no_change'
INVALID = 'invalid'


def _same_number(a, b, places):
    try:
        q = Decimal(1).scaleb(-places)
        return Decimal(str(a)).quantize(q) == Decimal(str(b)).quantize(q)
    except (InvalidOperation, TypeError):
        return False


def _param_changes(row, data):
    """{field: (lama, baru)} untuk parameter yang berbeda dari bulletin."""
    changes = {}
    pairs = [
        ('tanggal', str(row.tanggal), str(data['tanggal'])),
        ('origin', str(row.origin)[:8], str(data['origin'])[:8]),
    ]
    for name, old, new in pairs:
        if old != new:
            changes[name] = (old, new)
    for name, places in (('lintang', 2), ('bujur', 2), ('magnitudo', 1)):
        if not _same_number(getattr(row, name), data[name], places):
            changes[name] = (str(getattr(row, name)), str(data[name]))
    if row.depth != data['depth']:
        changes['depth'] = (row.depth, data['depth'])
    ket = nearest_city_description(data['lintang'], data['bujur'])
    if row.ket != ket:
        changes['ket'] = (row.ket, ket)
    return changes


def plan_event(item, row=None) -> dict:
    """Rencana satu event, tanpa menulis apa pun. `row` = baris Gempa atau None."""
    event_id = item['event_id']
    data = parse_bulletin(item['last_text'])
    first = parse_datetime(item['first_click'])
    last = parse_datetime(item['last_click'])
    last_qc = parse_datetime(item['last_qc']) if item.get('last_qc') else None

    plan = {'event_id': event_id, 'clicks': item['clicks'], 'first_click': first,
            'last_click': last, 'last_qc': last_qc, 'changes': {}, 'set_kirim': False,
            'set_qc': False, 'pk': getattr(row, 'pk', None), 'data': data}

    required = ('tanggal', 'origin', 'lintang', 'bujur', 'magnitudo', 'depth')
    missing = [f for f in required if data.get(f) in (None, '')]
    if data.get('event_id') != event_id or missing:
        plan['action'] = INVALID
        plan['reason'] = f'bulletin tidak cocok/kurang: {missing}'
        return plan

    if row is None:
        plan.update(action=INSERT, set_kirim=True, set_qc=bool(last_qc))
        return plan

    plan['set_kirim'] = not row.petugas_kirim.exists()
    plan['set_qc'] = bool(last_qc and (row.qc_at is None or row.qc_at < last_qc))
    newer = bool(row.updated_at and row.updated_at > last)
    changes = _param_changes(row, data)
    plan['changes'] = changes
    plan['updated_at'] = row.updated_at
    if newer:
        plan['action'] = KEEP_NEWER
    elif changes:
        plan['action'] = UPDATE
    elif plan['set_kirim'] or plan['set_qc']:
        plan['action'] = OFFICERS_ONLY
    else:
        plan['action'] = NO_CHANGE
    return plan


def apply_event(item, plan) -> None:
    """Tulis satu rencana. Aman diulang: kedua kalinya menjadi no_change."""
    if plan['action'] == INVALID:
        return
    if plan['action'] == INSERT:
        ingest('jay', item['last_text'], stage=STAGE_SEND, clicked_at=plan['first_click'])
    elif plan['action'] == UPDATE:
        ingest('jay', item['last_text'], stage=STAGE_SEND)
    row = Gempa.objects.get(event_id=plan['event_id'])
    if plan['set_kirim'] and plan['action'] != INSERT:
        row.petugas_kirim.set(_on_duty_at(plan['first_click']))
    if plan['set_qc']:
        row.petugas_qc.set(_on_duty_at(plan['last_qc']))
        row.qc_at = plan['last_qc']
        row.save(update_fields=['qc_at'])
