/* Tombol "Copy Info Gempa" untuk halaman peta/press gempa.
 *
 * Kenapa ada: operator mengirim info gempa ke WhatsApp dan sebelumnya menyalin
 * teksnya sendiri, karakter per karakter. Tombol ini menyalin baris
 * "Info Gempa Mag: ... ::BMKG-XXX" sekali klik.
 *
 * Tombolnya diletakkan di dalam kolom peta, tepat DI BAWAH peta (lihat
 * template), jadi tata letak dua kolom halaman tidak tergeser.
 *
 * Catatan: fitur "Capture Peta" (screenshot peta) sudah DIHAPUS. html2canvas
 * tidak bisa menggambar ubin Esri dengan benar sehingga gambar yang dihasilkan
 * tidak sesuai kenyataan; lebih baik tidak ada daripada menyesatkan operator.
 *
 * Teks yang disalin diambil dari elemen yang ditunjuk data-target, jadi berkas
 * ini sama untuk semua template:
 *   <button id="btn-copy-info" data-target="info-gempa">
 */
(function () {
    'use strict';

    var MSG_TIMEOUT = 6000;

    function normalise(text) {
        return String(text || '').replace(/\s+/g, ' ').trim();
    }

    function injectStyles() {
        if (document.getElementById('peta-copy-style')) return;
        var style = document.createElement('style');
        style.id = 'peta-copy-style';
        style.textContent = [
            // in-flow (bukan fixed/absolute), jadi tidak mengubah tata letak
            '.peta-copy-bar{display:flex;align-items:center;justify-content:center;',
            'gap:8px;flex-wrap:wrap;margin:16px 0 0;padding:0 10px;font-family:inherit;}',
            '.peta-btn{background:#0d6efd;color:#fff;border:none;border-radius:8px;',
            'padding:8px 14px;font-size:.85rem;font-weight:600;cursor:pointer;',
            'transition:opacity .15s ease,transform .15s ease;}',
            '.peta-btn:hover{opacity:.92;}',
            '.peta-btn:active{transform:scale(.97);}',
            '.peta-btn[disabled]{opacity:.6;cursor:progress;}',
            '.peta-msg{font-size:.78rem;font-weight:600;color:#0f5132;}',
            '.peta-msg.is-error{color:#b02a37;}',
            '@media print{.peta-copy-bar{display:none !important;}}'
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
        // Fallback browser lama / konteks tidak aman
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

    function init() {
        var button = document.getElementById('btn-copy-info');
        if (!button) return;

        injectStyles();
        var msg = document.getElementById('peta-action-msg');

        button.addEventListener('click', function () {
            var el = document.getElementById(button.getAttribute('data-target') || 'info-gempa');
            var text = normalise(el && el.innerText);
            if (!text) {
                say(msg, 'Teks info gempa tidak ditemukan.', true);
                return;
            }
            button.disabled = true;
            copyText(text).then(function () {
                say(msg, 'Info gempa tersalin — tempel di WhatsApp.');
            }).catch(function (err) {
                say(msg, 'Gagal menyalin: ' + err.message, true);
            }).then(function () {
                button.disabled = false;
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
