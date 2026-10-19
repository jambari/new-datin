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
  window.gmtReliefLayer = function () {
    return L.layerGroup([
      L.tileLayer(URL, {maxNativeZoom: 5, maxZoom: 18, attribution: ATTRIBUTION}),
      L.tileLayer(URL, {minZoom: 6, minNativeZoom: 6, maxNativeZoom: 10, maxZoom: 18,
                        bounds: [[-13, 122], [6, 152]], attribution: ATTRIBUTION})
    ]);
  };
})();
