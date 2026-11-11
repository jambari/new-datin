"""Tatanan tektonik singkat untuk gempa di Papua (halaman peta isoseismal).

Isi mengikuti pola ringkasan tektonik USGS NEIC: kelas kedalaman, lempeng yang terlibat dan kecepatan
relatifnya, lalu gempa besar terdahulu di sekitarnya. Kecepatan lempeng, batas lempeng mikro, dan
gempa terdahulu diambil dari Hayes dkk. (2017), Tectonic Summaries of Magnitude 7 and Greater
Earthquakes from 2000 to 2015, USGS Open-File Report 2016-1192 (MORVEL, DeMets dkk. 2010).

Wilayah dipilih dengan kotak lintang/bujur sederhana (urutan di ZONA penting). Ini petunjuk umum,
bukan penentuan mekanisme gempa: tanpa tensor momen, jenis sesar penyebab tidak diketahui.
Python murni, seperti gempa/faults.py.
"""
import math

from .faults import INTERMEDIATE_KM

DEEP_KM = 300
RIWAYAT_KM = 300                 # radius gempa terdahulu, sama dengan ringkasan USGS
RIWAYAT_MAKS = 3
SUMBER = ('Ringkasan tatanan tektonik mengacu pada Hayes dkk. (2017), USGS Open-File Report 2016-1192; '
          'petunjuk umum, bukan penentuan mekanisme gempa.')

UMUM = ('Papua berada di zona tektonik yang kompleks: gerak banyak lempeng mikro mengakomodasi konvergensi besar '
        'antara lempeng Australia, Pasifik, Laut Filipina, dan Sunda, sehingga semua jenis sesar '
        '(naik, geser, dan turun) dapat terjadi.')

# (kunci, uji(lat, lon), teks). Dicek berurutan; yang pertama cocok dipakai.
ZONA = [
    ('seram', lambda la, lo: lo < 131.0 or (la < -2.8 and lo < 132.5),
     'Episenter berada di sekitar Palung Seram, zona penunjaman berarah ke selatan antara lempeng mikro '
     'Kepala Burung dan Laut Banda.'),
    ('palung_utara', lambda la, lo: (la > -1.0 and lo >= 131.5) or (la > -3.0 and lo >= 137.0),
     'Episenter berada di zona konvergensi lempeng Pasifik (termasuk lempeng mikro Caroline) dan lempeng '
     'Australia di pesisir utara Papua. Lempeng Pasifik bergerak ke barat daya relatif terhadap Australia '
     'dengan kecepatan sekitar 110 mm/tahun dan menunjam perlahan ke selatan di Palung New Guinea.'),
    ('kepala_burung', lambda la, lo: la > -2.8 and 131.0 <= lo < 134.5,
     'Episenter berada di lempeng mikro Kepala Burung, salah satu blok kecil yang mengakomodasi gerak relatif '
     'lempeng Pasifik, Laut Filipina, Australia, dan Sunda. Di sekitarnya, lempeng Pasifik bergerak ke barat '
     'daya relatif terhadap Australia sekitar 113 mm/tahun; di selatan, blok ini dibatasi Palung Seram.'),
    ('kepala_burung_maoke', lambda la, lo: -4.3 <= la <= -1.0 and 132.5 <= lo < 137.0,
     'Episenter berada di dekat batas lempeng mikro Kepala Burung dan Maoke, batas berarah timur laut yang '
     'mengakomodasi gerak geser mengiri sekitar 80 mm/tahun.'),
    ('aru', lambda la, lo: la < -4.3 and lo < 136.0,
     'Episenter berada di dekat batas lempeng mikro Laut Banda dan lempeng Australia, batas berarah utara–'
     'timur laut yang bersifat memisah: lempeng mikro Laut Banda bergerak ke barat sekitar 15 mm/tahun '
     'relatif terhadap Australia.'),
    ('pegunungan', lambda la, lo: la >= -5.5 and lo >= 136.0,
     'Episenter berada di sabuk tumbukan busur–benua Papua bagian tengah. Konvergensi Australia–Pasifik '
     'sekitar 110 mm/tahun ke arah timur laut diakomodasi oleh pemendekan kerak selebar 250–350 km yang '
     'mengangkat Pegunungan Tengah 2–8 mm/tahun.'),
    ('australia', lambda la, lo: la < -5.5,
     'Episenter berada di bagian lempeng Australia di selatan sabuk tumbukan Papua, jauh dari batas '
     'lempeng utama.'),
]

# Gempa besar terdahulu (ComCat/USGS; korban menurut ringkasan USGS di atas).
RIWAYAT = [
    ('1976-06-25', 7.1, -4.60, 140.09, 'Jayawijaya', 'sekitar 6.000 korban jiwa'),
    ('1979-09-12', 7.9, -1.68, 136.04, 'Yapen', '15 korban jiwa'),
    ('1981-01-19', 6.7, -4.58, 139.24, 'Jayawijaya', 'sekitar 1.300 korban jiwa'),
    ('1996-02-17', 8.2, -0.89, 136.95, 'Biak', 'tsunami, 166 korban jiwa'),
    ('2002-10-10', 7.6, -1.76, 134.30, 'Ransiki', ''),
    ('2004-02-05', 7.0, -3.62, 135.54, 'Nabire', 'sekitar 37 korban jiwa'),
    ('2004-02-07', 7.3, -4.00, 135.02, 'Nabire', ''),
    ('2004-11-26', 7.1, -3.57, 135.35, 'Nabire', ''),
    ('2009-01-03', 7.7, -0.41, 132.89, 'Manokwari', ''),
    ('2009-01-03', 7.4, -0.71, 133.36, 'Manokwari', ''),
    ('2010-06-16', 7.0, -2.17, 136.55, 'Yapen', ''),
    ('2010-09-29', 7.0, -4.92, 133.78, 'pesisir selatan Papua', ''),
    ('2013-04-06', 7.0, -3.51, 138.48, 'Mamberamo', ''),
    ('2015-07-27', 7.0, -2.63, 138.53, 'barat Abepura', ''),
]

BULAN = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September',
         'Oktober', 'November', 'Desember']
ARAH8 = ['utara', 'timur laut', 'timur', 'tenggara', 'selatan', 'barat daya', 'barat', 'barat laut']


def _jarak_arah(lat1, lon1, lat2, lon2):
    """Jarak (km) dan arah mata angin dari titik 1 ke titik 2."""
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * 6371.0 * math.asin(math.sqrt(a))
    az = math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                 math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)))
    return km, ARAH8[round((az % 360) / 45) % 8]


def _tanggal(iso):
    y, m, d = (int(x) for x in iso.split('-'))
    return f'{d} {BULAN[m]} {y}'


def zona(lat, lon):
    for key, test, _text in ZONA:
        if test(lat, lon):
            return key
    return None


def _kedalaman(depth):
    d = f'{depth:.0f}'
    if depth >= DEEP_KM:
        return (f'Dengan kedalaman {d} km, gempabumi ini termasuk gempa dalam (lebih dari {DEEP_KM} km) yang terjadi '
                'di dalam lempeng yang menunjam. Gempa seperti ini jarang merusak, tetapi dapat dirasakan hingga jauh '
                'dari episenter.')
    if depth >= INTERMEDIATE_KM:
        return (f'Dengan kedalaman {d} km, gempabumi ini termasuk gempa menengah ({INTERMEDIATE_KM}–{DEEP_KM} km) '
                'yang kemungkinan terjadi di dalam lempeng yang menunjam, bukan di sesar kerak dangkal. Gempa menengah '
                'umumnya kurang merusak dibanding gempa dangkal, tetapi dapat dirasakan hingga jauh dari episenter.')
    return (f'Dengan kedalaman {d} km, gempabumi ini termasuk gempa dangkal (kurang dari {INTERMEDIATE_KM} km).')


def riwayat(lat, lon, event_date=None):
    """Gempa besar terdahulu dalam RIWAYAT_KM, terdekat dulu (maks. RIWAYAT_MAKS)."""
    rows = []
    for iso, mag, la, lo, tempat, dampak in RIWAYAT:
        if event_date is not None and iso >= event_date.isoformat():
            continue
        km, arah = _jarak_arah(lat, lon, la, lo)
        if km <= RIWAYAT_KM:
            rows.append({'tanggal': _tanggal(iso), 'mag': mag, 'tempat': tempat, 'dampak': dampak,
                         'km': km, 'arah': arah})
    rows.sort(key=lambda r: r['km'])
    return rows[:RIWAYAT_MAKS]


def _kalimat_riwayat(rows):
    if not rows:
        return (f'Dalam radius {RIWAYAT_KM} km dari episenter tidak ada gempa besar (M 7 atau lebih, atau yang '
                'menimbulkan korban jiwa) dalam daftar gempa Papua sejak 1976.')
    parts = []
    for r in rows:
        jarak = 'di dekat episenter' if r['km'] < 20 else f"±{round(r['km'] / 10) * 10:.0f} km di {r['arah']}"
        dampak = f", {r['dampak']}" if r['dampak'] else ''
        parts.append(f"M {r['mag']:.1f} {r['tempat']} {r['tanggal']} ({jarak}{dampak})")
    daftar = parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ', dan ' + parts[-1]
    return f'Gempa besar yang pernah terjadi dalam radius {RIWAYAT_KM} km antara lain {daftar}.'


def ringkasan_tektonik(lat, lon, depth, event_date=None):
    """Paragraf tatanan tektonik (list of str), [] bila lokasi tidak valid atau di luar Papua."""
    try:
        lat, lon, depth = float(lat), float(lon), float(depth or 0)
    except (TypeError, ValueError):
        return []
    if not (-11.0 <= lat <= 2.0 and 129.0 <= lon <= 143.0):     # sampai PNG dekat perbatasan
        return []
    key = zona(lat, lon)
    text = next((t for k, _test, t in ZONA if k == key), '')
    return [f'{UMUM} {text}'.strip(), _kedalaman(depth), _kalimat_riwayat(riwayat(lat, lon, event_date))]
