"""Terima event SeisComp (bulletin) lewat HTTP — pengganti alur .188.

Di .188 alurnya: exportevent.sh (host SeisComp) scp `mailexportfile.txt` lalu
ssh menjalankan `insertgempa.php` -> `manage.py ingest_gempa <region>`. Modul ini
melakukan hal yang sama, tapi lewat POST ber-token sehingga tidak perlu SSH key,
PHP, maupun shell_exec:

    POST /api/gempa/ingest/<region>/
    Authorization: Bearer <SEISCOMP_INGEST_TOKEN>
    body: isi mentah mailexportfile.txt

Parsernya adalah port dari .188 `gempa/management/commands/_parse_seiscomp.py`
(parse_file + compute_delta) supaya kedua server membaca format yang sama.
`ket` memakai nearest_city_description() yang sudah ada di models.py.

Idempoten: kunci utamanya event_id, jadi kiriman ulang (retry, atau event yang
sama dari dua jalur) hanya memperbarui baris yang ada.
"""
from __future__ import annotations

import logging
from datetime import datetime

from django.apps import apps

from .models import compute_delta, nearest_city_description

logger = logging.getLogger(__name__)

#: region pada URL -> model katalog (sama dengan STATIONS di .188).
INGEST_REGIONS = {
    'jay': 'Gempa',
    'balai': 'Balaigempa',
    'sorong': 'Gempasorong',
    'nabire': 'Gempanabire',
    'nganjuk': 'Gempanganjuk',
}

#: Field yang wajib ada supaya barisnya layak disimpan.
REQUIRED_FIELDS = ('tanggal', 'origin', 'lintang', 'bujur', 'magnitudo', 'depth')

#: Nilai tambahan per region (mengikuti cfg['extra'] di .188).
REGION_EXTRA = {
    'jay': {'sumber': 'angkasa', 'petugas': 'umum', 'type': 'M'},
}
DEFAULT_EXTRA = {'type': 'M'}


class SeiscompError(Exception):
    """Bulletin tidak bisa diparse / disimpan."""


def parse_bulletin(text: str) -> dict:
    """Ubah isi mailexportfile.txt menjadi dict field katalog.

    Port dari _parse_seiscomp.parse_file() — hanya sumbernya string, bukan path.

    Bedanya: di .188 satu baris pendek/aneh membuat parse_file melempar
    IndexError dan seluruh ingest gagal. Di sini baris seperti itu dilewati dan
    dicatat, lalu field wajib diperiksa di ingest() — jadi operator mendapat
    pesan "kurang lengkap: [...]" alih-alih error 500.
    """
    data = {}
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            if line.startswith('Date'):
                data['tanggal'] = line.split()[1]
            elif line.startswith('Time'):
                data['origin'] = line.split()[1][:8]
            elif line.startswith('Latitude'):
                parts = line.split()
                data['lintang'] = parts[1]
                if len(parts) >= 5:
                    data['eliplat'] = parts[4]
            elif line.startswith('Longitude'):
                parts = line.split()
                data['bujur'] = parts[1]
                if len(parts) >= 5:
                    data['eliplon'] = parts[4]
            elif line.startswith('Depth'):
                parts = line.split()
                data['depth'] = int(float(parts[1]))
                if len(parts) >= 5:
                    data['elipdepth'] = parts[4]
            elif 'preferred' in line.lower():
                data['magnitudo'] = round(float(line.split()[1]), 1)
            elif line.startswith('Public ID'):
                data['event_id'] = line.split()[-1]
            elif line.startswith('Residual'):
                data['rms'] = line.split()[2]
        except (IndexError, ValueError) as exc:
            # Baris opsional yang bentuknya lain tidak boleh menggagalkan
            # seluruh bulletin — field wajib tetap diperiksa di ingest().
            logger.warning('Baris bulletin dilewati (%s): %r', exc, line)
    return data


def ingest(region: str, text: str) -> dict:
    """Simpan satu event dari bulletin mentah. Kembalikan ringkasan hasilnya."""
    if region not in INGEST_REGIONS:
        raise SeiscompError(f'Region tidak dikenal: {region!r}')
    model = apps.get_model('gempa', INGEST_REGIONS[region])

    data = parse_bulletin(text)
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise SeiscompError(f'Data bulletin kurang lengkap: {missing}')

    fields = {f: data[f] for f in REQUIRED_FIELDS}
    fields['ket'] = nearest_city_description(data['lintang'], data['bujur'])
    fields.update(REGION_EXTRA.get(region, DEFAULT_EXTRA))

    event_id = data.get('event_id')
    if not event_id:
        obj = model.objects.create(**fields)
        created = True
    else:
        # created_at = waktu sebar pertama; sinkronisasi tidak boleh menimpanya
        existing = model.objects.filter(event_id=event_id).only('created_at').first()
        obj, created = model.objects.update_or_create(
            event_id=event_id, defaults=fields)
        if not created and existing is not None and existing.created_at:
            obj.created_at = existing.created_at
            obj.save(update_fields=['created_at'])

    if hasattr(obj, 'delta'):
        obj.delta = compute_delta(obj.tanggal, obj.origin, obj.created_at)
        obj.save(update_fields=['delta'])

    logger.info('SeisComp ingest %s: %s event_id=%s M%s',
                region, 'INSERT' if created else 'UPDATE', event_id, obj.magnitudo)

    return {
        'region': region,
        'model': model.__name__,
        'action': 'inserted' if created else 'updated',
        'event_id': event_id,
        'pk': obj.pk,
        'tanggal': str(obj.tanggal),
        'origin': str(obj.origin),
        'magnitudo': str(obj.magnitudo),
        'depth': obj.depth,
        'ket': fields['ket'],
        'delta': getattr(obj, 'delta', None),
    }
