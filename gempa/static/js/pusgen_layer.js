/* L.pusgenLayer: layer sesar/palung PuSGeN 2024 dengan simbol gigi, pengganti langsung L.geoJSON.
 *
 *   L.pusgenLayer(indoFaults, { pane: 'pFaults', style: { color: '#000', weight: 0.8 } }).addTo(map);
 *
 * Garis digambar persis seperti L.geoJSON. Untuk fitur dengan properti "gigi" (sesar naik, sesar turun,
 * palung subduksi; disiapkan oleh scripts/geodata/pusgen_faults_js.py), simbol digambar di sisi KIRI arah
 * garis, yaitu sisi hanging wall / lempeng atas:
 *   naik, subduksi  segitiga terisi
 *   turun           garis tegak (tick)
 * Ukuran simbol tetap dalam piksel, jadi dihitung ulang setiap zoom/geser, hanya untuk garis yang terlihat.
 * setStyle({color}) ikut mengganti warna simbol (dipakai pemilih warna di event browser).
 * Sesar yang berimpit palung (properti "palung", mis. North Papua Thrust) tidak diberi gigi selama layer
 * palung ada di peta yang sama, supaya gigi tidak dobel dengan warna berbeda.
 */
(function () {
    'use strict';
    if (typeof L === 'undefined') return;

    var GAP = { naik: 26, turun: 18, subduksi: 34 };     // jarak antar simbol (px)
    var SIZE = { naik: 6, turun: 5, subduksi: 8 };       // setengah alas / panjang tick (px)

    function styleOf(style, feature) {
        return (typeof style === 'function' ? style(feature) : style) || {};
    }

    function parts(geometry) {
        return geometry.type === 'LineString' ? [geometry.coordinates] : geometry.coordinates;
    }

    L.PusgenLayer = L.FeatureGroup.extend({
        initialize: function (data, options) {
            this._data = (Array.isArray(data) ? data : [data]).filter(Boolean);
            this._options = options || {};
            this._lines = L.geoJSON(this._data, this._options);
            this._teeth = L.layerGroup();
            this._renderer = L.svg({ pane: this._options.pane || 'overlayPane', padding: 0.3 });
            this._override = {};
            L.FeatureGroup.prototype.initialize.call(this, [this._lines, this._teeth]);
        },

        onAdd: function (map) {
            L.FeatureGroup.prototype.onAdd.call(this, map);
            map.on('zoomend moveend pusgen:palung', this._redraw, this);
            if (this._isTrench()) {
                map._pusgenPalung = (map._pusgenPalung || 0) + 1;
                map.fire('pusgen:palung');
            } else {
                this._redraw();
            }
        },

        onRemove: function (map) {
            map.off('zoomend moveend pusgen:palung', this._redraw, this);
            L.FeatureGroup.prototype.onRemove.call(this, map);
            if (this._isTrench()) {
                map._pusgenPalung = Math.max(0, (map._pusgenPalung || 1) - 1);
                map.fire('pusgen:palung');
            }
        },

        _isTrench: function () {
            return this._data.some(function (c) {
                return (c.features || []).some(function (f) { return (f.properties || {}).tipe === 'subduksi'; });
            });
        },

        setStyle: function (style) {
            L.Util.extend(this._override, style);
            this._lines.setStyle(style);
            this._redraw();
            return this;
        },

        _redraw: function () {
            var map = this._map;
            if (!map) return;
            this._teeth.clearLayers();
            var view = map.getBounds().pad(0.2);
            var trenchShown = (map._pusgenPalung || 0) > 0;
            var self = this;
            this._data.forEach(function (collection) {
                (collection.features || []).forEach(function (feature) {
                    var p = feature.properties || {};
                    if (!p.gigi || !GAP[p.tipe] || (p.palung && trenchShown)) return;
                    var st = L.Util.extend({}, styleOf(self._options.style, feature), self._override);
                    parts(feature.geometry).forEach(function (coords) {
                        var latlngs = coords.map(function (c) { return L.latLng(c[1], c[0]); });
                        if (view.intersects(L.latLngBounds(latlngs))) self._drawTeeth(map, latlngs, p.tipe, st);
                    });
                });
            });
        },

        _drawTeeth: function (map, latlngs, tipe, st) {
            var gap = GAP[tipe], size = SIZE[tipe];
            var color = st.color || '#000', opacity = st.opacity === undefined ? 1 : st.opacity;
            var pts = latlngs.map(function (ll) { return map.latLngToLayerPoint(ll); });
            var shapes = [], next = gap / 2;          // jarak simbol berikutnya dari awal ruas
            for (var i = 1; i < pts.length; i++) {
                var a = pts[i - 1], b = pts[i];
                var dx = b.x - a.x, dy = b.y - a.y, len = Math.sqrt(dx * dx + dy * dy);
                if (!len) continue;
                var ux = dx / len, uy = dy / len, lx = uy, ly = -ux;   // kiri arah garis (sumbu y layar ke bawah)
                var t = next;
                for (; t < len; t += gap) {
                    var mx = a.x + ux * t, my = a.y + uy * t;
                    if (tipe === 'turun') {
                        shapes.push([[mx, my], [mx + lx * size * 1.4, my + ly * size * 1.4]]);
                    } else {
                        shapes.push([[mx - ux * size, my - uy * size], [mx + ux * size, my + uy * size],
                                     [mx + lx * size * 1.5, my + ly * size * 1.5]]);
                    }
                }
                next = t - len;
            }
            var toLatLng = function (xy) { return map.layerPointToLatLng(L.point(xy[0], xy[1])); };
            var opts = { renderer: this._renderer, color: color, opacity: opacity, interactive: false };
            if (!shapes.length) return;
            if (tipe === 'turun') {
                this._teeth.addLayer(L.polyline(shapes.map(function (s) { return s.map(toLatLng); }),
                    L.Util.extend({ weight: Math.max(1, st.weight || 1) }, opts)));
            } else {
                this._teeth.addLayer(L.polygon(shapes.map(function (s) { return [s.map(toLatLng)]; }),   // multipolygon
                    L.Util.extend({ weight: 0.5, fill: true, fillColor: color, fillOpacity: opacity }, opts)));
            }
        }
    });

    L.pusgenLayer = function (data, options) { return new L.PusgenLayer(data, options); };
})();
