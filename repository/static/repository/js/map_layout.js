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
  var PAPUA = [[-9.5, 129.0], [1.0, 141.5]];        // Papua (Indonesia) dan sekitarnya
  var KEY_LAYOUT = 'map_layout', KEY_SETTINGS = 'map_settings_hidden';
  var maps = [], aux = [];

  function get(key, def) { try { return localStorage.getItem(key) || def; } catch (e) { return def; } }
  function put(key, val) { try { localStorage.setItem(key, val); } catch (e) {} }
  function mode() { return get(KEY_LAYOUT, 'bottom') === 'side' ? 'side' : 'bottom'; }
  function settingsHidden() { return get(KEY_SETTINGS, '0') === '1'; }
  function visible(map) { var c = map.getContainer(); return c.offsetWidth > 0 && c.offsetHeight > 0; }

  function fit(entry) {
    var map = entry.map;
    if (!visible(map)) { entry.pending = true; return; }
    entry.pending = false;
    if (mode() === 'side') {
      map.fitBounds(PAPUA, { paddingTopLeft: [70, 50], paddingBottomRight: [50, 50], animate: false });
    } else if (entry.fittedSide) {
      map.setView(entry.center, entry.zoom, { animate: false });
    }
    entry.fittedSide = mode() === 'side';
  }

  function remeasure(refit) {
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

  window.MapLayout = {
    PAPUA: PAPUA,
    register: function (map) {
      var c = map.getCenter();
      var entry = { map: map, center: [c.lat, c.lng], zoom: map.getZoom(), fittedSide: false, pending: false };
      maps.push(entry);
      if (mode() === 'side') setTimeout(function () { map.invalidateSize(); fit(entry); }, 120);
      return map;
    },
    registerAux: function (map) { aux.push({ map: map }); return map; },
    set: function (m) { put(KEY_LAYOUT, m === 'side' ? 'side' : 'bottom'); apply(true); },
    toggleSettings: function () { put(KEY_SETTINGS, settingsHidden() ? '0' : '1'); apply(true); },
    refresh: function () { setTimeout(function () { remeasure(false); }, 80); },
    mode: mode,
  };

  document.addEventListener('DOMContentLoaded', function () { apply(false); });
})();
