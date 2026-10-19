/*
 * Bingkai peta bergaya layout cetak untuk Leaflet: margin putih, border checkered hitam-putih,
 * garis grid putus-putus, dan label derajat (lintang di kiri, bujur di atas).
 * Diadaptasi dari laporan bulanan (gempa/laporan_bulanan.html).
 *
 * Pemakaian: attachMapGridOverlay(map, wrapperEl, canvasEl)
 *   wrapperEl: elemen position:relative yang membungkus div peta dan canvas.
 */
(function () {
  var PAD = 40, PAD_LEFT = 60, THICK = 8, BLOCK = 15;

  function gridStep(span) {
    var steps = [0.25, 0.5, 1, 2, 5, 10, 20, 30];
    for (var i = 0; i < steps.length; i++) {
      if (span / steps[i] <= 8) return steps[i];
    }
    return 45;
  }

  function fmt(v, step) {
    var d = step < 1 ? 2 : 0;
    return Math.abs(v).toFixed(d).replace(/\.?0+$/, '').replace('.', ',') + '°';
  }

  function draw(map, wrapper, canvas) {
    var rect = wrapper.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    canvas.width = rect.width;
    canvas.height = rect.height;
    var ctx = canvas.getContext('2d');
    var W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // 1. Margin putih (menutup basemap di luar bingkai)
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, W, PAD);
    ctx.fillRect(0, H - PAD, W, PAD);
    ctx.fillRect(0, 0, PAD_LEFT, H);
    ctx.fillRect(W - PAD, 0, PAD, H);

    // 2. Border checkered
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#000000';
    ctx.setLineDash([]);
    var x, y, w, h;
    for (x = PAD_LEFT; x < W - PAD; x += BLOCK) {
      w = Math.min(BLOCK, (W - PAD) - x);
      ctx.fillStyle = (Math.floor((x - PAD_LEFT) / BLOCK) % 2 === 0) ? '#000000' : '#ffffff';
      ctx.fillRect(x, PAD - THICK, w, THICK); ctx.strokeRect(x, PAD - THICK, w, THICK);
      ctx.fillRect(x, H - PAD, w, THICK); ctx.strokeRect(x, H - PAD, w, THICK);
    }
    for (y = PAD; y < H - PAD; y += BLOCK) {
      h = Math.min(BLOCK, (H - PAD) - y);
      ctx.fillStyle = (Math.floor((y - PAD) / BLOCK) % 2 === 0) ? '#000000' : '#ffffff';
      ctx.fillRect(PAD_LEFT - THICK, y, THICK, h); ctx.strokeRect(PAD_LEFT - THICK, y, THICK, h);
      ctx.fillRect(W - PAD, y, THICK, h); ctx.strokeRect(W - PAD, y, THICK, h);
    }

    // 3. Grid dan label derajat
    var b = map.getBounds(), c = map.getCenter();
    var sw = b.getSouthWest(), ne = b.getNorthEast();
    var step = gridStep(Math.max(ne.lat - sw.lat, ne.lng - sw.lng));
    ctx.font = 'bold 11px Arial, sans-serif';
    ctx.fillStyle = '#000000';
    ctx.strokeStyle = 'rgba(0,0,0,0.3)';
    ctx.setLineDash([4, 4]);

    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (var lat = Math.ceil(sw.lat / step) * step; lat <= ne.lat; lat += step) {
      y = Math.round(map.latLngToContainerPoint([lat, c.lng]).y);
      if (y <= PAD || y >= H - PAD) continue;
      ctx.beginPath(); ctx.moveTo(PAD_LEFT, y); ctx.lineTo(W - PAD, y); ctx.stroke();
      var r = Math.round(lat * 1e6) / 1e6;
      ctx.fillText(fmt(r, step) + (r > 0 ? ' LU' : r < 0 ? ' LS' : ''), PAD_LEFT - THICK - 6, y);
    }

    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    for (var lng = Math.ceil(sw.lng / step) * step; lng <= ne.lng; lng += step) {
      x = Math.round(map.latLngToContainerPoint([c.lat, lng]).x);
      if (x <= PAD_LEFT || x >= W - PAD) continue;
      ctx.beginPath(); ctx.moveTo(x, PAD); ctx.lineTo(x, H - PAD); ctx.stroke();
      var n = Math.round((((lng + 180) % 360 + 360) % 360 - 180) * 1e6) / 1e6;
      ctx.fillText(fmt(n, step) + (n >= 0 ? ' BT' : ' BB'), x, PAD - THICK - 6);
    }
    ctx.setLineDash([]);
  }

  window.attachMapGridOverlay = function (map, wrapper, canvas) {
    var redraw = function () { draw(map, wrapper, canvas); };
    map.on('move moveend zoom zoomend resize viewreset', redraw);
    window.addEventListener('resize', redraw);
    setTimeout(redraw, 200);
    return redraw;
  };
})();
