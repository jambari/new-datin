import json

# Nama file input (file lama yang isinya titik-titik)
# Pastikan file ini ada di folder yang sama atau sesuaikan path-nya
INPUT_FILE = 'monitor/static/pgr5.geojson' 
# Nama file output (file baru yang sudah jadi Polygon)
OUTPUT_FILE = 'monitor/static/pgr5_fixed.geojson'

try:
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)

    # Ambil semua koordinat dari setiap "Point"
    all_coords = []
    
    # Cek apakah ini FeatureCollection
    if data.get('type') == 'FeatureCollection':
        features = data.get('features', [])
        print(f"Ditemukan {len(features)} titik. Sedang menggabungkan...")
        
        for feature in features:
            geom = feature.get('geometry', {})
            # Ambil koordinat jika tipenya Point
            if geom.get('type') == 'Point':
                coord = geom.get('coordinates')
                # Koordinat Point biasanya [lon, lat] atau [lon, lat, alt]
                # Kita ambil 2 elemen pertama saja (lon, lat)
                all_coords.append(coord[:2])
    else:
        print("Format JSON tidak dikenali sebagai FeatureCollection.")

    # Pastikan koordinat awal dan akhir sama agar polygon tertutup (closed loop)
    if all_coords:
        if all_coords[0] != all_coords[-1]:
            all_coords.append(all_coords[0])

        # Buat Struktur GeoJSON Baru (Polygon)
        new_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"name": "Wilayah PGR5"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [all_coords] # Perhatikan kurung siku ganda untuk Polygon
                    }
                }
            ]
        }

        # Simpan ke file baru
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(new_geojson, f, indent=4)
            
        print(f"SUKSES! File baru disimpan sebagai: {OUTPUT_FILE}")
        print("Silakan rename file ini menjadi 'pgr5.geojson' untuk menggantikan yang lama.")
        
    else:
        print("Gagal: Tidak ada koordinat yang ditemukan.")

except FileNotFoundError:
    print(f"Error: File {INPUT_FILE} tidak ditemukan. Cek path-nya.")
except Exception as e:
    print(f"Terjadi kesalahan: {e}")