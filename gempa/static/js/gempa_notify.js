(function () {
  'use strict';

  const MODEL_MAP = {
    '/gempa-admin/gempa/gempa/':           'gempa',
    '/gempa-admin/gempa/balaigempa/':      'balaigempa',
    '/gempa-admin/gempa/gempasorong/':     'gempasorong',
    '/gempa-admin/gempa/gempanabire/':     'gempanabire',
    '/gempa-admin/gempa/satudatagempa/':   'satudatagempa',
    '/gempa-admin/gempa/significant/':     'significant',
  };

  const path = window.location.pathname;
  let modelKey = null;
  for (const prefix of Object.keys(MODEL_MAP)) {
    if (path.startsWith(prefix)) { modelKey = MODEL_MAP[prefix]; break; }
  }
  if (!modelKey) return;

  const STORAGE_KEY = 'gempa_last_id_' + modelKey;
  let lastId = parseInt(localStorage.getItem(STORAGE_KEY) || '0', 10);

  function timeAgo(isoStr) {
    if (isoStr && !isoStr.endsWith('Z') && !isoStr.match(/[+-]\d{2}:\d{2}$/)) isoStr += 'Z';
    const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
    if (diff < 60)   return diff + ' detik lalu';
    if (diff < 3600) return Math.floor(diff / 60) + ' menit lalu';
    return Math.floor(diff / 3600) + ' jam lalu';
  }

  function showBanner(data) {
    const old = document.getElementById('gempa-notify-bar');
    if (old) old.remove();

    const style = document.createElement('style');
    style.textContent = '@keyframes slideDown{from{transform:translateY(-100%);opacity:0}to{transform:translateY(0);opacity:1}}';
    document.head.appendChild(style);

    const mag  = data.mag  ? 'Mag ' + parseFloat(data.mag).toFixed(1) : '';
    const ket  = data.ket  ? ' — ' + data.ket : '';
    const when = data.created_at ? ' (' + timeAgo(data.created_at) + ')' : '';
    const label = '🔔 <strong>Event baru!</strong> ' + mag + ket + when;

    const bar = document.createElement('div');
    bar.id = 'gempa-notify-bar';
    bar.style.cssText = 'position:sticky;top:0;z-index:9999;background:#166534;color:#fff;padding:11px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;font-family:sans-serif;font-size:13.5px;box-shadow:0 2px 8px rgba(0,0,0,.35);animation:slideDown .3s ease';

    const left = document.createElement('span');
    left.innerHTML = label;

    const right = document.createElement('div');
    right.style.cssText = 'display:flex;gap:8px;flex-shrink:0';

    const viewBtn = document.createElement('a');
    viewBtn.href = data.template_url;
    viewBtn.textContent = 'Lihat Template →';
    viewBtn.style.cssText = 'background:#fff;color:#166534;padding:5px 16px;border-radius:5px;text-decoration:none;font-weight:700;font-size:13px;white-space:nowrap';

    const closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = 'background:transparent;border:1px solid rgba(255,255,255,.6);color:#fff;border-radius:5px;padding:4px 10px;cursor:pointer;font-size:15px';
    closeBtn.onclick = function() { bar.remove(); };

    right.appendChild(viewBtn);
    right.appendChild(closeBtn);
    bar.appendChild(left);
    bar.appendChild(right);

    const target = document.getElementById('content') || document.querySelector('.content') || document.body;
    target.insertBefore(bar, target.firstChild);
  }

  function poll() {
    fetch('/gempa-notify/latest/?model=' + modelKey)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.id) return;
        if (data.id > lastId) {
          showBanner(data);
          lastId = data.id;
          localStorage.setItem(STORAGE_KEY, lastId);
        }
      })
      .catch(function() {});
  }

  poll();
  setInterval(poll, 10000);
})();
