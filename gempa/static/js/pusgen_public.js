/* Lapisan sesar aktif & palung subduksi PuSGeN 2024 untuk peta publik (beranda, /gempa/).
 *
 *   var pusgen = addPusgenLayers(map, {
 *     faults: '{% static_v "gjson/indofaults.js" %}', trench: '...subduksi.js', layer: '...pusgen_layer.js',
 *     dark: false,                    // warna garis: kuning di peta gelap/citra, coklat di peta terang
 *     position: 'topright',           // letak kontrol layer (opsional)
 *   });
 *   pusgen.setDark(true);             // saat ganti tema / basemap
 *
 * Berkas sesar (±250 KB) dimuat setelah peta tampil supaya halaman tidak tertahan. Garis digambar
 * di pane tersendiri di bawah marker gempa dan tidak bisa diklik, jadi popup marker tetap mudah dibuka.
 * Kontrol layer (bawaan kanan atas) untuk menyalakan/mematikan kedua lapisan.
 */
(function () {
    'use strict';

    var COLOR_DARK = '#facc15';     // sama dengan peta template balai (kuning di atas citra)
    var COLOR_LIGHT = '#9a3412';    // coklat tua: terbaca di OSM tanpa menyerupai warna magnitudo

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = function () { reject(new Error('gagal memuat ' + src)); };
            document.head.appendChild(s);
        });
    }

    function swatch(color, weight, label) {
        return '<span class="pusgen-key" style="display:inline-block;width:18px;height:0;border-top:' + weight +
            'px solid ' + color + ';vertical-align:middle;margin-right:6px;"></span>' + label;
    }

    window.addPusgenLayers = function (map, opts) {
        var dark = !!opts.dark, faults = null, trench = null, control = null;
        var color = function () { return dark ? COLOR_DARK : COLOR_LIGHT; };

        if (!map.getPane('pusgen')) {
            map.createPane('pusgen');
            map.getPane('pusgen').style.zIndex = 350;          // di bawah overlayPane (400) tempat marker
            map.getPane('pusgen').style.pointerEvents = 'none';
        }

        function labels() {
            return {
                faults: swatch(color(), 1, 'Sesar aktif (PuSGeN 2024)'),
                trench: swatch(color(), 2, 'Palung subduksi'),
            };
        }

        function buildControl() {
            if (control) map.removeControl(control);
            var l = labels(), overlays = {};
            overlays[l.faults] = faults;
            overlays[l.trench] = trench;
            control = L.control.layers(null, overlays, { position: opts.position || 'topright', collapsed: true }).addTo(map);
        }

        var ready = loadScript(opts.trench)
            .then(function () { return loadScript(opts.faults); })
            .then(function () { return typeof L.pusgenLayer === 'function' ? null : loadScript(opts.layer); })
            .then(function () {
                var common = { pane: 'pusgen', interactive: false };
                faults = L.pusgenLayer(indoFaults, L.Util.extend({
                    style: { color: color(), weight: 1, opacity: 0.7, fillColor: 'transparent' },
                }, common)).addTo(map);
                trench = L.pusgenLayer(subDuksi, L.Util.extend({
                    style: { color: color(), weight: 1.6, opacity: 0.8 },
                }, common)).addTo(map);
                buildControl();
            })
            .catch(function (err) { if (window.console) console.warn('[pusgen]', err); });

        return {
            ready: ready,
            setDark: function (value) {
                dark = !!value;
                if (!faults) return;
                faults.setStyle({ color: color() });
                trench.setStyle({ color: color() });
                buildControl();
            },
        };
    };
})();
