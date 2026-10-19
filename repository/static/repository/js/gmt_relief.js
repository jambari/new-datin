/*
 * Basemap relief bergaya GMT untuk Leaflet: tile statis hasil scripts/gmt/build_relief_tiles.py
 * (GMT Earth Relief, palet dem2, iluminasi barat laut, laut datar). Tidak menjalankan GMT saat dibuka.
 * Dunia z0–5 di bawah, Papua dan sekitarnya (122–152°BT, 13°LS–6°LU) z6–10 di atasnya.
 *
 * Pemakaian: gmtReliefLayer().addTo(map)
 */
(function () {
  var URL = '/media/tiles/gmt_relief/{z}/{x}/{y}.webp';
  var ATTRIBUTION = 'Relief: GMT Earth Relief / SRTM15+ (Tozer dkk., 2019)';
  var SEA = '#a9d3ea';   // warna laut pada tile

  window.gmtReliefLayer = function () {
    var opts = {attribution: ATTRIBUTION};
    var layers = [
      L.tileLayer(URL, L.extend({maxNativeZoom: 5, maxZoom: 18}, opts)),
      L.tileLayer(URL, L.extend({minZoom: 6, minNativeZoom: 6, maxNativeZoom: 10, maxZoom: 18,
                                 bounds: [[-13, 122], [6, 152]]}, opts))
    ];
    // Tile yang diperbesar (zoom pecahan / di atas maxNativeZoom) dirender browser dengan tepi
    // yang tercampur sehingga tampak garis tipis. Lebihkan 1 px dari ukuran yang dipasang Leaflet
    // agar tile bertumpuk sedikit dengan tetangganya.
    layers.forEach(function (layer) {
      layer.on('tileloadstart', function (e) {
        var w = parseFloat(e.tile.style.width), h = parseFloat(e.tile.style.height);
        if (w && h) { e.tile.style.width = (w + 1) + 'px'; e.tile.style.height = (h + 1) + 'px'; }
      });
    });
    var group = L.layerGroup(layers);
    // Zoom pecahan (zoomSnap 0.1) menyisakan celah sub-piksel antar-tile; latar container diberi
    // warna laut agar celah itu tidak tampak sebagai garis putih/abu-abu.
    var prev = null;
    group.on('add', function (e) {
      var c = e.target._map && e.target._map.getContainer();
      if (c) { prev = c.style.background; c.style.background = SEA; }
    });
    group.on('remove', function (e) {
      var m = e.target._map || this._mapToAdd;
      var c = m && m.getContainer();
      if (c) c.style.background = prev || '';
    });
    return group;
  };
})();
