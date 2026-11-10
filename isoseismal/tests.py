import datetime
import io
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from .felt import collect_felt, parse_felt_text, roman
from .models import IsoseismalMap
from .services import generate, store_shakemap
from .shakemap_io import parse_grid, parse_stations

WIB_ID = '20260522071031'                    # 22 Mei 2026 07:10:31 WIB = 00:10:31 UTC
EVENT_UTC = datetime.datetime(2026, 5, 22, 0, 10, 31, tzinfo=datetime.timezone.utc)


def grid_xml(nlon=9, nlat=9, lon0=140.1, lat1=-1.9, step=0.1, peak=4.6):
    """grid.xml ShakeMap kecil: MMI menurun dari pusat (140.5, -2.3)."""
    rows = []
    for j in range(nlat):
        lat = lat1 - j * step
        for i in range(nlon):
            lon = lon0 + i * step
            d = ((lon - 140.5) ** 2 + (lat + 2.3) ** 2) ** 0.5
            rows.append(f'{lon:.4f} {lat:.4f} 0.5 0.2 {max(1.0, peak - 6 * d):.2f} 0 0 0 0.6 1 600')
    return f'''<?xml version="1.0" encoding="US-ASCII" standalone="yes"?>
<shakemap_grid xmlns="http://earthquake.usgs.gov/eqcenter/shakemap" event_id="x" shakemap_version="1">
<event event_id="x" magnitude="3.7" depth="10" lat="-2.320000" lon="140.500000"
  event_timestamp="2026-05-22T07:10:31WIB" event_network="" event_description="31 km TimurLaut KAB-JAYAPURA-PAPUA" />
<grid_specification lon_min="{lon0}" lat_min="{lat1 - (nlat - 1) * step:.4f}" lon_max="{lon0 + (nlon - 1) * step:.4f}"
  lat_max="{lat1}" nominal_lon_spacing="{step}" nominal_lat_spacing="{step}" nlon="{nlon}" nlat="{nlat}" />
<grid_field index="1" name="LON" units="dd" />
<grid_field index="2" name="LAT" units="dd" />
<grid_field index="3" name="PGA" units="pctg" />
<grid_field index="4" name="PGV" units="cms" />
<grid_field index="5" name="MMI" units="intensity" />
<grid_field index="6" name="PSA03" units="pctg" />
<grid_field index="7" name="PSA10" units="pctg" />
<grid_field index="8" name="PSA30" units="pctg" />
<grid_field index="9" name="STDPGA" units="pctg" />
<grid_field index="10" name="URAT" units="" />
<grid_field index="11" name="SVEL" units="ms" />
<grid_data>
{chr(10).join(rows)}
</grid_data>
</shakemap_grid>
'''


STATIONLIST = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<shakemap-data code_version="3.5" map_version="1">
<earthquake id="x" lat="-2.32" lon="140.5" mag="3.7" />
<stationlist created="1">
<station code="SJPM" name="SJPM" insttype="Titan" lat="-2.5698" lon="140.502" dist="27.8" source="BMKG" netid="IA" intensity="3.3">
<comp name="--.HNZ"><acc value="0.7175" flag="0" /><vel value="0.3398" flag="0" /></comp>
<comp name="--.HNE"><acc value="0.5" flag="0" /><vel value="NaN" flag="0" /></comp>
</station>
<station code="EDMPI" name="EDMPI" insttype="Titan" lat="-7.175" lon="139.585" dist="549.3" source="BMKG" netid="IA" intensity="4.2" intensity_flag="T">
<comp name="--.HNE"><acc value="1.68" flag="T" /><vel value="1.45" flag="T" /></comp>
</station>
<station code="OBS_5" name="Depapre (Intensity 2)" insttype="Observed" lat="-2.4665" lon="140.3421" dist="23.9" source="bmkg" netid="INTENSITY" intensity="2.0">
<comp name="DERIVED"><acc value="NaN" flag="0" /><vel value="NaN" flag="0" /></comp>
</station>
</stationlist>
</shakemap-data>
'''


def _tile(*_args):
    return Image.new('RGB', (256, 256), (230, 230, 230))


class MediaMixin:
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp(prefix='iso-media-')
        self.addCleanup(shutil.rmtree, self.media, True)
        ctx = override_settings(MEDIA_ROOT=self.media, OSM_TILE_CACHE=Path(self.media) / 'tiles')
        ctx.enable()
        self.addCleanup(ctx.disable)
        patcher = mock.patch('reporting.osm._tile', side_effect=_tile)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_inputs(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'grid.xml').write_text(grid_xml())
        (folder / 'stationlist.xml').write_text(STATIONLIST)
        return folder / 'grid.xml', folder / 'stationlist.xml'


class ShakemapIoTest(TestCase):
    def test_grid_is_north_up_with_event_info(self):
        info, mmi, bounds = parse_grid(io.StringIO(grid_xml()))
        self.assertEqual(mmi.shape, (9, 9))
        self.assertAlmostEqual(float(mmi.max()), 4.6, places=2)
        self.assertEqual(tuple(int(v) for v in divmod(int(mmi.argmax()), 9)), (4, 4))
        self.assertEqual(bounds, [140.1, -2.7, 140.9, -1.9])
        self.assertEqual((info['magnitude'], info['depth'], info['lokasi']), (3.7, 10.0, '31 km TimurLaut KAB-JAYAPURA-PAPUA'))

    def test_stations_split_from_observed_and_flags_dropped(self):
        stations, observed = parse_stations(io.StringIO(STATIONLIST))
        self.assertEqual([s['code'] for s in stations], ['SJPM', 'EDMPI'])
        self.assertEqual((stations[0]['mmi'], stations[0]['pga'], stations[0]['pgv']), (3.3, 0.7175, 0.3398))
        self.assertIsNone(stations[1]['mmi'])                     # intensity_flag="T"
        self.assertIsNone(stations[1]['pga'])
        self.assertEqual(observed, [{'place': 'Depapre', 'lat': -2.4665, 'lon': 140.3421, 'mmi': 2.0,
                                     'source': 'shakemap'}])


class FeltParseTest(TestCase):
    def rows(self, text):
        return [(r['place'], r['mmi_text'], r['lat'] is not None) for r in parse_felt_text(text)]

    def test_bmkg_style_scale_before_places(self):
        self.assertEqual(self.rows('III Jayapura, II - III Sentani, II Keerom'),
                         [('Kota Jayapura', 'III', True), ('Sentani', 'II-III', True), ('Kab. Keerom', 'II', True)])

    def test_catalogue_style_scale_after_places(self):
        self.assertEqual(
            self.rows('Dirasakan di Kabupaten Keerom dan Kota Jayapura III MMI, Kabupaten Jayapura II MMI'),
            [('Kab. Keerom', 'III', True), ('Kota Jayapura', 'III', True), ('Kab. Jayapura', 'II', True)])
        self.assertEqual(self.rows('dirasakan oleh masyarakat di Distrik Sarmi dengan skala intensitas II MMI'),
                         [('Kab. Sarmi', 'II', True)])

    def test_town_aliases_keep_written_name(self):
        self.assertEqual(self.rows('IV Timika, III Waena, II Kampung Baru'),
                         [('Timika', 'IV', True), ('Waena', 'III', True), ('Kampung Baru', 'II', False)])

    def test_no_intensity_no_rows(self):
        self.assertEqual(parse_felt_text('Dirasakan'), [])
        self.assertEqual(parse_felt_text(''), [])
        self.assertEqual(roman(3.4), 'III')
        self.assertEqual(roman(None), '')


class FeltMatchTest(TestCase):
    def test_bmkg_and_catalogue_reports_are_matched_by_time_and_place(self):
        from gempa.models import Gempa
        from repository.models import FeltEarthquake
        FeltEarthquake.objects.create(event_datetime=EVENT_UTC + datetime.timedelta(seconds=20), latitude=-2.3,
                                      longitude=140.5, magnitude=3.7, depth_km=10, wilayah='Kab. Jayapura',
                                      dirasakan='III Jayapura, II Sentani')
        FeltEarthquake.objects.create(event_datetime=EVENT_UTC + datetime.timedelta(minutes=10), latitude=-2.3,
                                      longitude=140.5, magnitude=3.0, depth_km=10, wilayah='x',
                                      dirasakan='V Sarmi')                         # kejadian lain
        Gempa.objects.create(tanggal=EVENT_UTC.date(), origin='00:10:33', lintang='-2.32', bujur=140.5,
                             magnitudo=3.7, depth=10, terasa=True, terdampak='Dirasakan di Sentani III MMI')
        felt, text, sources = collect_felt(EVENT_UTC, -2.32, 140.5,
                                           [{'place': 'Depapre', 'lat': -2.4, 'lon': 140.3, 'mmi': 2.0}])
        self.assertEqual([(f['place'], f['mmi_text']) for f in felt],
                         [('Kota Jayapura', 'III'), ('Sentani', 'III'), ('Depapre', 'II')])
        self.assertIn('III Jayapura', text)
        self.assertNotIn('Sarmi', text)
        self.assertEqual(sources, ['ShakeMap (intensitas teramati)', 'BMKG (gempabumi dirasakan)',
                                   'Katalog Stasiun Geofisika Jayapura'])


class GenerateAndPagesTest(MediaMixin, TestCase):
    def test_store_generate_and_public_pages(self):
        grid, stations = self.write_inputs(Path(self.media) / 'in')
        obj = store_shakemap(WIB_ID, grid, stations)
        self.assertEqual(obj.event_time, EVENT_UTC)
        self.assertEqual(obj.slug, 'peta-isoseismal-gempabumi-kab-jayapura-22-mei-2026')
        self.assertEqual(obj.title, 'Peta Isoseismal Gempabumi Kab. Jayapura, 22 Mei 2026')
        self.assertEqual(obj.tanggal_panjang, 'Jumat, 22 Mei 2026')
        self.assertEqual(obj.wilayah[0]['name'], 'Kab. Jayapura')
        self.assertTrue(obj.grid.name.endswith('.npz'))

        self.assertIn('digambar', generate(obj))                  # titik teramati ShakeMap = dirasakan
        self.assertTrue(obj.image.read(8).startswith(b'\x89PNG'))
        self.assertEqual(generate(obj), 'skip: tidak berubah')

        page = self.client.get('/peta-isoseismal/')
        self.assertContains(page, obj.title)
        detail = self.client.get(obj.get_absolute_url())
        self.assertContains(detail, 'Depapre')
        self.assertContains(detail, 'SJPM')
        self.assertContains(detail, '2.32 LS – 140.50 BT')
        self.assertContains(detail, 'Sumber gempa terdekat')

        obj.is_hidden = True
        obj.save()
        self.assertEqual(self.client.get(obj.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get('/peta-isoseismal/'), obj.title)
        staff = User.objects.create_user('iso_staff', password='pw12345!', is_staff=True)
        self.client.force_login(staff)
        self.assertContains(self.client.get(obj.get_absolute_url()), 'PRATINJAU STAF')

    def test_event_without_felt_reports_gets_no_map(self):
        grid, _stations = self.write_inputs(Path(self.media) / 'in')
        obj = store_shakemap(WIB_ID, grid, None)
        self.assertEqual(generate(obj), 'skip: tidak dirasakan')
        self.assertFalse(obj.image)
        self.assertEqual(self.client.get(obj.get_absolute_url()).status_code, 404)

    def test_ingest_command_stores_grid_and_queues_render(self):
        folder = Path(self.media) / 'shakemaps' / WIB_ID
        self.write_inputs(folder)
        out = io.StringIO()
        with mock.patch('isoseismal.tasks.generate_isoseismal_task.delay') as delay:
            call_command('ingest_pushed_event', WIB_ID, '--quiet', stdout=out)
        summary = json.loads(out.getvalue().split('INGEST_SUMMARY ', 1)[1])
        self.assertEqual(summary['isoseismal'], 'peta-isoseismal-gempabumi-kab-jayapura-22-mei-2026')
        delay.assert_called_once_with(WIB_ID, force=True)
        self.assertFalse((folder / 'grid.xml').exists())             # diringkas ke .npz
        self.assertTrue((folder / 'stationlist.xml').exists())
        obj = IsoseismalMap.objects.get(wib_id=WIB_ID)
        self.assertEqual(len(obj.stations), 2)

    def test_new_grid_forces_redraw_same_grid_does_not(self):
        folder = Path(self.media) / 'shakemaps' / WIB_ID
        with mock.patch('isoseismal.tasks.generate_isoseismal_task.delay') as delay:
            self.write_inputs(folder)
            call_command('ingest_pushed_event', WIB_ID, '--quiet', stdout=io.StringIO())
            self.write_inputs(folder)                                  # PUSH ulang, data sama
            call_command('ingest_pushed_event', WIB_ID, '--quiet', stdout=io.StringIO())
            (folder / 'grid.xml').parent.mkdir(parents=True, exist_ok=True)
            (folder / 'grid.xml').write_text(grid_xml(peak=5.2))       # run baru, grid berubah
            call_command('ingest_pushed_event', WIB_ID, '--quiet', stdout=io.StringIO())
        self.assertEqual([c.kwargs['force'] for c in delay.call_args_list], [True, False, True])

    def test_scan_task_draws_when_felt_report_arrives_later(self):
        from repository.models import FeltEarthquake
        from .tasks import scan_isoseismal_task
        grid, _stations = self.write_inputs(Path(self.media) / 'in')
        obj = store_shakemap(WIB_ID, grid, None)
        with mock.patch('isoseismal.tasks.SCAN_DAYS', 99999):
            self.assertEqual(scan_isoseismal_task(days=99999), [])
            FeltEarthquake.objects.create(event_datetime=EVENT_UTC, latitude=-2.32, longitude=140.5, magnitude=3.7,
                                          depth_km=10, wilayah='x', dirasakan='III Jayapura')
            self.assertEqual(len(scan_isoseismal_task(days=99999)), 1)
        obj.refresh_from_db()
        self.assertTrue(obj.image)
