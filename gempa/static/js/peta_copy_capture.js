/* Tombol "Copy Info Gempa" + "Capture Peta" untuk halaman peta/press gempa.
 *
 * Kenapa ada: operator mengirim info gempa ke WhatsApp. Sebelumnya mereka
 * menyalin teks secara manual dan screenshot layar sendiri; dua tombol ini
 * melakukannya sekali klik, dan gambarnya persis elemen #streetmap-baru
 * (header + peta + baris Info Gempa) tanpa tombolnya ikut terfoto.
 *
 * Elemen yang di-capture dan teks yang disalin ditentukan lewat data-attribute
 * di tombolnya, jadi berkas ini sama untuk semua template:
 *   <button id="btn-copy-info"     data-target="info-gempa">
 *   <button id="btn-capture-peta"  data-target="streetmap-baru"
 *           data-filename="peta-BMKG-JAY">
 *
 * Catatan teknis:
 * - Salin teks memakai Clipboard API (butuh HTTPS — produksi sudah HTTPS) dan
 *   fallback textarea+execCommand untuk browser lama.
 * - Salin GAMBAR ke clipboard hanya didukung Chrome/Edge; kalau tidak bisa,
 *   berkasnya otomatis diunduh (Firefox/Safari) supaya operator tetap dapat
 *   gambarnya dan bisa lampirkan ke WhatsApp.
 * - html2canvas dimuat baru saat tombol capture diklik (halaman tetap ringan).
 * - Ubin peta (Esri/OSM) mengirim Access-Control-Allow-Origin: *, jadi
 *   useCORS:true membuat petanya ikut terfoto (tanpa itu canvas jadi kosong).
 * - Lapisan SHP digambar Leaflet ke <canvas> (preferCanvas di template), bukan
 *   SVG: html2canvas menyalin canvas apa adanya, sedangkan SVG digambar ulang
 *   dan posisinya bisa meleset dari ubin.
 */
(function () {
    'use strict';

    var MSG_TIMEOUT = 6000;

    function normalise(text) {
        return String(text || '').replace(/\s+/g, ' ').trim();
    }

    function injectStyles() {
        if (document.getElementById('peta-actions-style')) return;
        var style = document.createElement('style');
        style.id = 'peta-actions-style';
        style.textContent = [
            // position:fixed -> keluar dari alur flex dua kolom halaman peta,
            // jadi margin/tata letak aslinya tidak tergeser sama sekali.
            '.peta-actions{position:fixed;top:10px;right:12px;z-index:2147483000;',
            'display:flex;flex-wrap:nowrap;gap:8px;align-items:center;justify-content:flex-end;',
            'margin:0;padding:6px 9px;background:rgba(255,255,255,.94);',
            'border:1px solid #d0d7de;border-radius:10px;font-family:inherit;',
            'box-shadow:0 2px 10px rgba(0,0,0,.12);}',
            '.peta-btn{background:#0d6efd;color:#fff;border:none;border-radius:8px;',
            'padding:8px 14px;font-size:.85rem;font-weight:600;cursor:pointer;',
            'transition:transform .15s ease,opacity .15s ease;}',
            '.peta-btn:hover{opacity:.92;}',
            '.peta-btn:active{transform:scale(.97);}',
            '.peta-btn[disabled]{opacity:.6;cursor:progress;}',
            '.peta-btn.is-secondary{background:#198754;}',
            '.peta-msg{font-size:.78rem;font-weight:600;color:#0f5132;max-width:46vw;',
            'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}',
            '.peta-msg.is-error{color:#b02a37;}',
            '@media print{.peta-actions{display:none !important;}}'
        ].join('');
        document.head.appendChild(style);
    }

    function say(el, text, isError) {
        if (!el) return;
        el.textContent = text;
        el.className = 'peta-msg' + (isError ? ' is-error' : '');
        if (el._timer) clearTimeout(el._timer);
        if (text) {
            el._timer = setTimeout(function () { el.textContent = ''; }, MSG_TIMEOUT);
        }
    }

    function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve, reject) {
            var area = document.createElement('textarea');
            area.value = text;
            area.setAttribute('readonly', 'readonly');
            area.style.position = 'fixed';
            area.style.top = '-1000px';
            document.body.appendChild(area);
            area.select();
            try {
                document.execCommand('copy') ? resolve() : reject(new Error('perintah copy ditolak'));
            } catch (err) {
                reject(err);
            } finally {
                document.body.removeChild(area);
            }
        });
    }

    function html2canvasUrl() {
        var tag = document.querySelector('script[data-h2c-url]');
        return (tag && tag.getAttribute('data-h2c-url')) || '/static/js/html2canvas.min.js';
    }

    function loadHtml2Canvas() {
        if (window.html2canvas) return Promise.resolve(window.html2canvas);
        return new Promise(function (resolve, reject) {
            var script = document.createElement('script');
            script.src = html2canvasUrl();
            script.onload = function () {
                window.html2canvas ? resolve(window.html2canvas)
                                   : reject(new Error('html2canvas tidak tersedia'));
            };
            script.onerror = function () { reject(new Error('gagal memuat html2canvas')); };
            document.head.appendChild(script);
        });
    }

    function toBlob(canvas) {
        return new Promise(function (resolve, reject) {
            canvas.toBlob(function (blob) {
                blob ? resolve(blob) : reject(new Error('canvas kosong'));
            }, 'image/png');
        });
    }

    function download(blob, filename) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
    }

    function stamp() {
        var d = new Date();
        function two(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + two(d.getMonth() + 1) + two(d.getDate()) + '-' +
               two(d.getHours()) + two(d.getMinutes());
    }

    var SCALE = 2;                         // tajam untuk WhatsApp

    // Catatan: jangan mengoper width/height/windowWidth/windowHeight. Nilai itu
    // memaksa html2canvas membuat ulang halaman pada lebar 756px (bukan lebar
    // jendela sebenarnya), sehingga tata letak di klon berbeda dari yang
    // dilihat operator. Biarkan html2canvas memakai ukuran jendela asli lalu
    // memotong sesuai elemennya.
    function render(target, options) {
        return loadHtml2Canvas().then(function (h2c) {
            return h2c(target, Object.assign({
                useCORS: true,             // ubin Esri/OSM mengirim ACAO: *
                allowTaint: false,
                backgroundColor: '#ffffff',
                scale: SCALE,
                logging: false
            }, options || {}));
        });
    }

    /**
     * Apakah area peta kosong/satu warna?
     *
     * Dipakai untuk memutuskan perlu fallback: mode render bawaan browser
     * (foreignObject) paling akurat, tapi kalau ubinnya gagal dimuat hasilnya
     * bisa rata satu warna. Kalau begitu, ambil ulang dengan mode html2canvas
     * biasa supaya operator tetap dapat gambar.
     */
    function mapLooksBlank(canvas, target) {
        var mapEl = document.getElementById('map-baru');
        if (!mapEl) return false;
        var tr = target.getBoundingClientRect();
        var mr = mapEl.getBoundingClientRect();
        var x = Math.max(0, Math.round((mr.left - tr.left) * SCALE));
        var y = Math.max(0, Math.round((mr.top - tr.top) * SCALE));
        var w = Math.min(Math.round(mr.width * SCALE), 220);
        var h = Math.min(Math.round(mr.height * SCALE), 220);
        if (w < 4 || h < 4) return false;
        var data;
        try {
            data = canvas.getContext('2d').getImageData(x, y, w, h).data;
        } catch (err) {
            return false;                  // canvas tercemar -> jangan mengarang
        }
        var seen = {}, distinct = 0;
        for (var i = 0; i < data.length; i += 4) {
            var key = data[i] + ',' + data[i + 1] + ',' + data[i + 2];
            if (!seen[key]) {
                seen[key] = 1;
                if (++distinct > 12) return false;   // ada isi
            }
        }
        return true;                       // <=12 warna -> kemungkinan kosong
    }

    async function capture(target, filename, button) {
        var canvas, mode;
        try {
            // Mode 1: biarkan browser menggambar sendiri (paling mirip layar,
            // termasuk lapisan SHP dan penanda). Didukung Chrome/Edge.
            canvas = await render(target, { foreignObjectRendering: true });
            if (mapLooksBlank(canvas, target)) {
                throw new Error('hasil mode foreignObject kosong');
            }
            mode = 'browser';
        } catch (primaryError) {
            // Mode 2: cara lama, html2canvas menggambar ulang DOM.
            canvas = await render(target, {});
            mode = 'kompatibilitas';
        }
        var blob = await toBlob(canvas);
        var name = (filename || 'peta') + '-' + stamp() + '.png';

        // Mode ditulis di pesan supaya operator bisa melaporkan mana yang dipakai.
        var note = mode === 'browser' ? ' (mode: browser)' : ' (mode: kompatibilitas)';

        if (navigator.clipboard && window.ClipboardItem) {
            try {
                await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
                return 'Gambar tersalin ke clipboard — tempel di WhatsApp.' + note;
            } catch (err) {
                /* Chrome menolak kalau dokumen tidak fokus, dsb. -> unduh saja */
            }
        }
        download(blob, name);
        return 'Gambar diunduh (' + name + ') — lampirkan ke WhatsApp.' + note;
    }

    function init() {
        var copyBtn = document.getElementById('btn-copy-info');
        var shotBtn = document.getElementById('btn-capture-peta');
        if (!copyBtn && !shotBtn) return;

        injectStyles();
        var msg = document.getElementById('peta-action-msg');

        if (copyBtn) {
            copyBtn.addEventListener('click', function () {
                var el = document.getElementById(copyBtn.getAttribute('data-target') || 'info-gempa');
                var text = normalise(el && el.innerText);
                if (!text) { say(msg, 'Teks info gempa tidak ditemukan.', true); return; }
                copyBtn.disabled = true;
                copyText(text).then(function () {
                    say(msg, 'Info gempa tersalin — tempel di WhatsApp.');
                }).catch(function (err) {
                    say(msg, 'Gagal menyalin: ' + err.message, true);
                }).then(function () { copyBtn.disabled = false; });
            });
        }

        if (shotBtn) {
            shotBtn.addEventListener('click', function () {
                var target = document.getElementById(shotBtn.getAttribute('data-target') || 'streetmap-baru');
                if (!target) { say(msg, 'Area peta tidak ditemukan.', true); return; }
                var label = shotBtn.textContent;
                shotBtn.disabled = true;
                shotBtn.textContent = 'Menyiapkan gambar...';
                say(msg, 'Mengambil gambar peta...');
                capture(target, shotBtn.getAttribute('data-filename'), shotBtn)
                    .then(function (note) { say(msg, note); })
                    .catch(function (err) { say(msg, 'Gagal capture: ' + err.message, true); })
                    .then(function () {
                        shotBtn.disabled = false;
                        shotBtn.textContent = label;
                    });
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
