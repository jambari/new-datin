from django.core.management.base import BaseCommand
from stations.models import Station

STATIONS = [
    {'network':'IA','code':'ARKPI','name':'Arsopura','latitude':-2.78,'longitude':140.59,'kota':'Keerom','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q10'},
    {'network':'IA','code':'ARPI','name':'Arso','latitude':-2.9,'longitude':140.75,'kota':'Keerom','provinsi':'Papua','sensor':'Titan','digitizer':'Centaur'},
    {'network':'IA','code':'BMPI','name':'Stamet Klas I Frans Kaisiepo Biak','latitude':-1.19,'longitude':136.1,'kota':'Biak Numfor','provinsi':'Papua','sensor':'Titan Open','digitizer':'Centaur'},
    {'network':'IA','code':'BTSPI','name':'Kantor Distrik Bonggo Timur','latitude':-2.38,'longitude':139.7,'kota':'Sarmi','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q19'},
    {'network':'IA','code':'DYPI','name':'Dekai','latitude':-4.85,'longitude':139.5,'kota':'Yahukimo','provinsi':'Papua','sensor':'Titan','digitizer':'Centaur'},
    {'network':'IA','code':'EDMPI','name':'Bade Airport','latitude':-7.18,'longitude':139.59,'kota':'Mappi','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q22'},
    {'network':'IA','code':'ELMPI','name':'Sipias','latitude':-7.49,'longitude':140.79,'kota':'Merauke','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q23'},
    {'network':'IA','code':'FKMPM','name':'Kurik - Kaptel','latitude':-8.25,'longitude':140.27,'kota':'Merauke','provinsi':'Papua','sensor':'Episensor FBA-ES-T','digitizer':'Kinemetrics Q330S+'},
    {'network':'IA','code':'GENI','name':'Genyem','latitude':-2.59,'longitude':140.17,'kota':'Jayapura','provinsi':'Papua','sensor':'FBA ES-T','digitizer':'Q330'},
    {'network':'IA','code':'JBPI','name':'Balai Besar Wilayah V Jayapura','latitude':-2.57,'longitude':140.68,'kota':'Jayapura','provinsi':'Papua','sensor':'Titan SMA','digitizer':'Titan SMA'},
    {'network':'IA','code':'JGPI','name':'Stasiun Geofisika Klas I Jayapura','latitude':-2.51,'longitude':140.7,'kota':'Jayapura','provinsi':'Papua','sensor':'Titan SMA','digitizer':'Titan SMA'},
    {'network':'IA','code':'JMPI','name':'Stamet Klas I Sentani','latitude':-2.58,'longitude':140.52,'kota':'Jayapura','provinsi':'Papua','sensor':'Titan','digitizer':'Centaur'},
    {'network':'IA','code':'KIMPI','name':'Kimaam Airport','latitude':-7.98,'longitude':138.85,'kota':'Merauke','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q32'},
    {'network':'IA','code':'LJPI','name':'Lereh','latitude':-3.13,'longitude':139.95,'kota':'Jayapura','provinsi':'Papua','sensor':'Titan','digitizer':'Centaur'},
    {'network':'IA','code':'MIBPI','name':'Bandara Mindiptana','latitude':-5.88,'longitude':140.71,'kota':'Boven Digoel','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q44'},
    {'network':'IA','code':'MMPI','name':'Merauke','latitude':-8.52,'longitude':140.41,'kota':'Merauke','provinsi':'Papua','sensor':'Titan','digitizer':'Trident'},
    {'network':'IA','code':'MTJPI','name':'Skow Mabo','latitude':-2.63,'longitude':140.86,'kota':'Jayapura','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q48'},
    {'network':'IA','code':'MTMPI','name':'Kasonaweja','latitude':-2.31,'longitude':138.04,'kota':'Mamberamo Raya','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q49'},
    {'network':'IA','code':'OBMPI','name':'Kepi','latitude':-6.56,'longitude':139.3,'kota':'Mappi','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q54'},
    {'network':'IA','code':'SATPI','name':'Kantor Distrik Muara Tor','latitude':-1.97,'longitude':138.87,'kota':'Sarmi','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q66'},
    {'network':'IA','code':'SKPM','name':'Senggi - Towe Hitam','latitude':-3.45,'longitude':140.73,'kota':'Keerom','provinsi':'Papua','sensor':'Episensor FBA-ES-T','digitizer':'Kinemetrics Q330S+'},
    {'network':'IA','code':'SMPI','name':'Sarmi','latitude':-1.98,'longitude':138.71,'kota':'Sarmi','provinsi':'Papua','sensor':'Titan','digitizer':'Centaur'},
    {'network':'IA','code':'SOMPI','name':'Kantor Distrik Sota','latitude':-8.43,'longitude':141.01,'kota':'Merauke','provinsi':'Papua','sensor':'Titan','digitizer':'Quanterra Q71'},
    {'network':'IA','code':'TMPI','name':'Stamet Klas III Timika','latitude':-4.53,'longitude':136.89,'kota':'Mimika','provinsi':'Papua','sensor':'Titan Open','digitizer':'Taurus'},
    {'network':'IA','code':'TRPI','name':'Tanah Merah','latitude':-6.1,'longitude':140.3,'kota':'Boven Digoel','provinsi':'Papua','sensor':'Titan','digitizer':'Centaur'},
    {'network':'IA','code':'WAMI','name':'Wamena','latitude':-4.1,'longitude':138.95,'kota':'Jayawijaya','provinsi':'Papua','sensor':'G210-S','digitizer':'G210-P'},
]


class Command(BaseCommand):
    help = 'Seed data stasiun akselerograf Papua dari SIMORA BMKG'

    def handle(self, *args, **options):
        created = updated = 0
        for s in STATIONS:
            obj, is_new = Station.objects.update_or_create(
                network=s['network'], code=s['code'],
                defaults={
                    'name': s['name'],
                    'latitude': s['latitude'],
                    'longitude': s['longitude'],
                    'kota': s['kota'],
                    'provinsi': s['provinsi'],
                    'sensor': s['sensor'],
                    'digitizer': s['digitizer'],
                    'channel': 'HNN',
                    'is_active': True,
                },
            )
            if is_new:
                created += 1
            else:
                updated += 1
        self.stdout.write(self.style.SUCCESS(
            f'Selesai. Created: {created}, Updated: {updated} stasiun.'
        ))
