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
  // Peta memakai zoom pecahan (zoomSnap 0.1): tanpa ini muncul garis putih tipis di batas tile.
  var style = document.createElement('style');
  // className Leaflet dipasang pada container layer, bukan pada <img> tile.
  style.textContent = '.gmt-relief-tile img.leaflet-tile{width:256.5px!important;height:256.5px!important}';
  document.head.appendChild(style);

  window.gmtReliefLayer = function () {
    var opts = {className: 'gmt-relief-tile', attribution: ATTRIBUTION};
    return L.layerGroup([
      L.tileLayer(URL, L.extend({maxNativeZoom: 5, maxZoom: 18}, opts)),
      L.tileLayer(URL, L.extend({minZoom: 6, minNativeZoom: 6, maxNativeZoom: 10, maxZoom: 18,
                                 bounds: [[-13, 122], [6, 152]]}, opts))
    ]);
  };
})();
