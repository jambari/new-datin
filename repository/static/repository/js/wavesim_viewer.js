/* Wave-propagation viewer: animates SPECFEM surface-velocity frames as a
 * Leaflet image overlay, toggles the PGV map and draws station seismograms.
 * Data comes from the #wavesim-data json_script (repository/wavesim.py). */
(function () {
  var el = document.getElementById('wavesim-data');
  if (!el || !window.L) return;
  var d = JSON.parse(el.textContent);
  if (!d.bounds || !d.frame_times.length) return;

  var n = d.frame_times.length;
  var frameUrl = function (i) { return d.frame_url + 'f' + String(i).padStart(3, '0') + '.png'; };

  var map = L.map('ws-map', { zoomSnap: 0.25 }).fitBounds(d.bounds);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors', maxZoom: 12,
    referrerPolicy: 'strict-origin-when-cross-origin',
  }).addTo(map);
  L.rectangle(d.bounds, { color: '#475569', weight: 1, fill: false, dashArray: '4 4' }).addTo(map);

  var overlay = L.imageOverlay(frameUrl(0), d.bounds, { opacity: 1 }).addTo(map);
  var pgv = L.imageOverlay(d.pgv_url, d.bounds, { opacity: 1 });

  if (d.source) {
    L.marker([d.source.latitude, d.source.longitude], {
      icon: L.divIcon({ className: '', html: '<div style="font-size:22px;line-height:22px;color:#dc2626;text-shadow:0 0 3px #fff">★</div>', iconSize: [22, 22], iconAnchor: [11, 11] }),
    }).addTo(map).bindTooltip('Episentrum · M' + d.source.magnitude + ' · ' + d.source.depth_km + ' km');
  }
  Object.keys(d.seismograms).forEach(function (key) {
    var s = d.seismograms[key];
    if (s.latitude == null) return;
    L.marker([s.latitude, s.longitude], {
      icon: L.divIcon({ className: '', html: '<div style="font-size:15px;line-height:15px;color:#0f172a;text-shadow:0 0 3px #fff">▲</div>', iconSize: [15, 15], iconAnchor: [7, 10] }),
    }).addTo(map).bindTooltip(key, { permanent: true, direction: 'right', offset: [6, 0], className: '' });
  });

  // Preload frames so playback is smooth.
  var cache = [];
  for (var i = 0; i < n; i++) { var im = new Image(); im.src = frameUrl(i); cache.push(im); }

  var slider = document.getElementById('ws-slider');
  var timeEl = document.getElementById('ws-time');
  var playBtn = document.getElementById('ws-play');
  var cur = 0, timer = null;

  function show(i) {
    cur = i;
    overlay.setUrl(frameUrl(i));
    slider.value = i;
    timeEl.textContent = d.frame_times[i].toFixed(1) + ' s';
  }
  function stop() { clearInterval(timer); timer = null; playBtn.textContent = '▶ Putar'; }
  function play() {
    if (cur >= n - 1) show(0);
    playBtn.textContent = '❚❚ Jeda';
    timer = setInterval(function () { if (cur >= n - 1) { stop(); return; } show(cur + 1); }, 120);
  }
  playBtn.addEventListener('click', function () { timer ? stop() : play(); });
  slider.addEventListener('input', function () { stop(); show(+slider.value); });

  function mms(v) { v *= 1000; return (v >= 10 ? v.toFixed(0) : v >= 1 ? v.toFixed(1) : v.toFixed(2)) + ' mm/s'; }
  if (d.pgv_scale) {
    document.getElementById('ws-pgv-min').textContent = mms(d.pgv_scale.min);
    document.getElementById('ws-pgv-max').textContent = mms(d.pgv_scale.max);
  }

  var btnWave = document.getElementById('ws-mode-wave');
  var btnPgv = document.getElementById('ws-mode-pgv');
  function mode(m) {
    var wave = m === 'wave';
    btnWave.classList.toggle('on', wave); btnPgv.classList.toggle('on', !wave);
    document.getElementById('ws-legend-wave').hidden = !wave;
    document.getElementById('ws-legend-pgv').hidden = wave;
    if (wave) { map.removeLayer(pgv); overlay.addTo(map); }
    else { stop(); map.removeLayer(overlay); pgv.addTo(map); }
  }
  btnWave.addEventListener('click', function () { mode('wave'); });
  btnPgv.addEventListener('click', function () { mode('pgv'); });
  show(0);

  // Seismograms: Z, N, E velocity traces per station, sorted by distance.
  var box = document.getElementById('ws-seis');
  var src = d.source || {};
  function dist(s) {
    var dy = (s.latitude - src.latitude) * 111.19;
    var dx = (s.longitude - src.longitude) * 111.19 * Math.cos(src.latitude * Math.PI / 180);
    return Math.sqrt(dx * dx + dy * dy);
  }
  var colors = { Z: '#dc2626', N: '#2563eb', E: '#059669' };
  Object.keys(d.seismograms)
    .sort(function (a, b) { return dist(d.seismograms[a]) - dist(d.seismograms[b]); })
    .forEach(function (key) {
      var s = d.seismograms[key];
      var comps = ['Z', 'N', 'E'].filter(function (c) { return s[c]; });
      var peak = Math.max.apply(null, comps.map(function (c) { return s[c].pgv; }));
      var fig = document.createElement('figure');
      fig.innerHTML = '<figcaption>' + key + ' · ' + dist(s).toFixed(0) + ' km · PGV ' +
        (peak * 1000).toFixed(2) + ' mm/s <span style="font-weight:400;color:#94a3b8">(Z merah, N biru, E hijau)</span></figcaption>';
      var cv = document.createElement('canvas');
      fig.appendChild(cv); box.appendChild(fig);
      var w = cv.clientWidth * 2, h = 220;
      cv.width = w; cv.height = h;
      var ctx = cv.getContext('2d');
      comps.forEach(function (c, row) {
        var tr = s[c], mid = (row + 0.5) * h / comps.length, amp = h / comps.length / 2.2;
        ctx.strokeStyle = colors[c]; ctx.lineWidth = 1.4; ctx.beginPath();
        tr.v.forEach(function (v, k) {
          var x = k / (tr.v.length - 1) * w, y = mid - (peak ? v / peak : 0) * amp;
          k ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        });
        ctx.stroke();
      });
    });
})();
