/*
 * Tata letak peta cetak bersama (Event Browser, Laporan Bulanan, Gempa Susulan).
 *
 * Markup:
 *   .formal-frame[data-map-frame]   bingkai peta (header-grid, map-wrapper, legend-grid)
 *   [data-map-settings]             kolom panel pengaturan (boleh tidak ada)
 *   [data-map-main]                 kolom bingkai peta
 *   tombol [data-layout="bottom|side"] dan [data-toggle-settings] (includes/map_layout_toggle.html)
 *
 * JS halaman: MapLayout.register(map)      peta utama (dipusatkan ke Papua pada tata letak samping)
 *             MapLayout.registerAux(map)   peta pendukung (inset) yang hanya perlu diukur ulang
 *             MapLayout.refresh()          panggil saat tab peta dibuka
 * Pilihan disimpan di localStorage dan berlaku untuk semua halaman tersebut.
 */
(function () {
  var PAPUA = [[-9.3, 129.8], [0.4, 141.3]];        // Pulau Papua bagian Indonesia + Raja Ampat
  // Ruang bingkai grid (map_grid_overlay / drawOverlayGridLayout): kiri 60, atas/kanan/bawah 40 px.
  var PAD = { left: 65, top: 45, right: 45, bottom: 45 };
  // Halaman dapat menetapkan bawaan & kunci simpanan sendiri sebelum skrip ini dimuat:
  //   window.MAP_LAYOUT_CONFIG = {key: 'eb', layout: 'side', settingsHidden: true}
  var CFG = window.MAP_LAYOUT_CONFIG || {};
  var SUFFIX = CFG.key ? '_' + CFG.key : '';
  var KEY_LAYOUT = 'map_layout' + SUFFIX, KEY_SETTINGS = 'map_settings_hidden' + SUFFIX;
  var DEF_LAYOUT = CFG.layout === 'side' ? 'side' : 'bottom', DEF_SETTINGS = CFG.settingsHidden ? '1' : '0';
  var maps = [], aux = [];

  function get(key, def) { try { return localStorage.getItem(key) || def; } catch (e) { return def; } }
  function put(key, val) { try { localStorage.setItem(key, val); } catch (e) {} }
  function mode() { return get(KEY_LAYOUT, DEF_LAYOUT) === 'side' ? 'side' : 'bottom'; }
  function settingsHidden() { return get(KEY_SETTINGS, DEF_SETTINGS) === '1'; }
  function visible(map) { var c = map.getContainer(); return c.offsetWidth > 0 && c.offsetHeight > 0; }

  function fit(entry) {
    var map = entry.map;
    if (!visible(map)) { entry.pending = true; return; }
    entry.pending = false;
    if (mode() === 'side') {
      map.fitBounds(PAPUA, { paddingTopLeft: [PAD.left, PAD.top], paddingBottomRight: [PAD.right, PAD.bottom],
                             animate: false });
    } else if (entry.fittedSide) {
      map.setView(entry.center, entry.zoom, { animate: false });
    }
    entry.fittedSide = mode() === 'side';
  }

  // Tinggi bingkai peta tata letak samping = lebar × rasio Papua (Mercator), agar tidak ada laut
  // berlebih di selatan/utara.
  function mercY(lat) { var r = lat * Math.PI / 180; return Math.log(Math.tan(Math.PI / 4 + r / 2)); }
  var RATIO = (mercY(PAPUA[1][0]) - mercY(PAPUA[0][0])) / ((PAPUA[1][1] - PAPUA[0][1]) * Math.PI / 180);
  function sizeFrames() {
    document.querySelectorAll('.formal-frame[data-map-frame] > .map-wrapper').forEach(function (w) {
      if (mode() !== 'side' || !w.offsetWidth) { w.style.removeProperty('height'); return; }
      var inner = w.offsetWidth - PAD.left - PAD.right;
      w.style.setProperty('height', Math.round(inner * RATIO + PAD.top + PAD.bottom) + 'px', 'important');
    });
  }

  // Tata letak samping: panah utara + skala di kanan atas peta; kotak ringkasan/statistik yang ada
  // di kanan atas dipindah ke kiri bawah (dan dikembalikan saat kembali ke tata letak bawah).
  function furniture(entry) {
    var side = mode() === 'side', map = entry.map, corners = map._controlCorners;
    if (side && !entry.controls) {
      var frame = map.getContainer().closest('.formal-frame');
      var arrow = frame && frame.querySelector('.header-grid .text-end img');
      var north = L.control({ position: 'topright' });
      north.onAdd = function () {
        var d = L.DomUtil.create('div', 'map-north-arrow');
        if (arrow) d.innerHTML = '<img src="' + arrow.src + '" alt="Utara">';
        return d;
      };
      entry.controls = [north, L.control.scale({ position: 'topright', imperial: false, maxWidth: 140 })];
      entry.controls.forEach(function (c) { c.addTo(map); });
    } else if (!side && entry.controls) {
      entry.controls.forEach(function (c) { c.remove(); });
      entry.controls = null;
    }
    if (!corners) return;
    entry.moved = entry.moved || [];
    if (side) {
      var mine = (entry.controls || []).map(function (c) { return c.getContainer(); });
      Array.prototype.slice.call(corners.topright.children).forEach(function (el) {
        if (mine.indexOf(el) >= 0) return;
        corners.bottomleft.appendChild(el);
        entry.moved.push(el);
      });
    } else {
      entry.moved.forEach(function (el) { corners.topright.appendChild(el); });
      entry.moved = [];
    }
  }

  function remeasure(refit) {
    sizeFrames();
    maps.forEach(furniture);
    maps.concat(aux).forEach(function (e) { if (visible(e.map)) e.map.invalidateSize(); });
    maps.forEach(function (e) { if (refit || e.pending) fit(e); else if (visible(e.map)) e.map.fire('moveend'); });
  }

  function apply(refit) {
    var side = mode() === 'side', hide = settingsHidden();
    document.querySelectorAll('.formal-frame[data-map-frame]').forEach(function (f) {
      f.classList.toggle('layout-side', side);
    });
    document.querySelectorAll('[data-map-settings]').forEach(function (c) { c.classList.toggle('d-none', hide); });
    document.querySelectorAll('[data-map-main]').forEach(function (c) {
      var row = c.parentElement, hasSettings = row && row.querySelector('[data-map-settings]');
      c.classList.toggle('map-main-wide', hasSettings ? hide : side);
    });
    document.querySelectorAll('[data-layout]').forEach(function (b) {
      b.classList.toggle('active', b.dataset.layout === mode());
    });
    document.querySelectorAll('[data-toggle-settings]').forEach(function (b) {
      b.classList.toggle('active', hide);
      b.innerHTML = hide ? '<i class="bi bi-layout-sidebar"></i> Tampilkan pengaturan'
                         : '<i class="bi bi-arrows-angle-expand"></i> Sembunyikan pengaturan';
    });
    setTimeout(function () { remeasure(refit); }, 80);
  }

  // --- Tangkapan layar bingkai peta (PNG) dengan html-to-image (dimuat saat pertama dipakai) ---
  var H2I_URL = 'https://cdn.jsdelivr.net/npm/html-to-image@1.11.11/dist/html-to-image.js';
  var h2iPromise = null;
  function loadH2I() {
    if (window.htmlToImage) return Promise.resolve(window.htmlToImage);
    if (!h2iPromise) {
      h2iPromise = new Promise(function (resolve, reject) {
        var sc = document.createElement('script');
        sc.src = H2I_URL;
        sc.onload = function () { resolve(window.htmlToImage); };
        sc.onerror = function () { h2iPromise = null; reject(new Error('html-to-image gagal dimuat')); };
        document.head.appendChild(sc);
      });
    }
    return h2iPromise;
  }
  function slug(text) {
    return (text || 'peta').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60) || 'peta';
  }
  function screenshot(btn) {
    var col = btn.closest('[data-map-main]');
    var frame = col && col.querySelector('.formal-frame[data-map-frame]');
    if (!frame) return;
    var label = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Memproses…';
    var title = frame.querySelector('.t-main'), sub = frame.querySelector('.t-sub');
    var name = slug((title ? title.textContent : '') + ' ' + (sub ? sub.textContent : '')) + '.png';
    loadH2I().then(function (h2i) {
      return h2i.toPng(frame, {
        pixelRatio: 2, cacheBust: false, backgroundColor: '#ffffff',
        // Tombol zoom & elemen no-print tidak ikut di gambar.
        filter: function (n) {
          return !(n.classList && (n.classList.contains('leaflet-control-zoom') || n.classList.contains('no-print')));
        }
      });
    }).then(function (url) {
      var a = document.createElement('a');
      a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
    }).catch(function (e) {
      alert('Gagal membuat gambar peta: ' + (e && e.message ? e.message : e));
    }).finally(function () {
      btn.disabled = false; btn.innerHTML = label;
    });
  }

  window.MapLayout = {
    screenshot: screenshot,
    PAPUA: PAPUA,
    register: function (map) {
      var c = map.getCenter();
      var entry = { map: map, center: [c.lat, c.lng], zoom: map.getZoom(), fittedSide: false, pending: false };
      maps.push(entry);
      if (mode() === 'side') setTimeout(function () { sizeFrames(); furniture(entry); map.invalidateSize(); fit(entry); }, 120);
      return map;
    },
    registerAux: function (map) { aux.push({ map: map }); return map; },
    set: function (m) { put(KEY_LAYOUT, m === 'side' ? 'side' : 'bottom'); apply(true); },
    toggleSettings: function () { put(KEY_SETTINGS, settingsHidden() ? '0' : '1'); apply(true); },
    refresh: function () { setTimeout(function () { remeasure(false); }, 80); },
    mode: mode,
  };

  document.addEventListener('DOMContentLoaded', function () { apply(false); });
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (mode() === 'side') remeasure(true); }, 200);
  });
})();
