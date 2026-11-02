(function () {
  'use strict';

  function init() {
    var holder = document.getElementById('quill-editor');
    var input = document.getElementById('id_content');
    if (!holder || !input || typeof Quill === 'undefined') return;

    var uploadUrl = holder.getAttribute('data-upload-url');

    var quill = new Quill(holder, {
      theme: 'snow',
      placeholder: 'Tulis isi berita di sini…',
      modules: {
        toolbar: {
          container: [
            [{ header: [2, 3, false] }],
            ['bold', 'italic', 'underline', 'strike'],
            [{ list: 'ordered' }, { list: 'bullet' }],
            ['blockquote', 'code-block'],
            ['link', 'image'],
            ['clean']
          ]
        }
      }
    });

    function sync() {
      input.value = quill.root.innerHTML;
    }

    // Isi awal (mode edit)
    if (input.value && input.value.trim()) {
      try {
        quill.setContents(quill.clipboard.convert({ html: input.value }));
      } catch (e) {
        quill.root.innerHTML = input.value;
      }
    }
    sync();

    quill.on('text-change', sync);
    var form = input.form || input.closest('form');
    if (form) form.addEventListener('submit', sync);

    // Unggah gambar ke server, sisipkan URL hasilnya.
    var toolbar = quill.getModule('toolbar');
    if (toolbar && uploadUrl) {
      toolbar.addHandler('image', function () {
        var picker = document.createElement('input');
        picker.type = 'file';
        picker.accept = 'image/*';
        picker.onchange = function () {
          var file = picker.files && picker.files[0];
          if (!file) return;
          if (file.size > 5 * 1024 * 1024) {
            window.alert('Ukuran gambar maksimal 5 MB.');
            return;
          }
          var data = new FormData();
          data.append('image', file);
          var token = document.querySelector('input[name=csrfmiddlewaretoken]');
          var headers = token ? { 'X-CSRFToken': token.value } : {};

          fetch(uploadUrl, {
            method: 'POST',
            body: data,
            headers: headers,
            credentials: 'same-origin'
          })
            .then(function (res) {
              return res.json().then(function (body) {
                return { ok: res.ok, body: body };
              });
            })
            .then(function (res) {
              if (!res.ok || !res.body.url) {
                window.alert((res.body && res.body.error) || 'Gagal mengunggah gambar.');
                return;
              }
              var range = quill.getSelection(true) || { index: quill.getLength() };
              quill.insertEmbed(range.index, 'image', res.body.url, 'user');
              quill.setSelection(range.index + 1, 0, 'user');
            })
            .catch(function () {
              window.alert('Gagal mengunggah gambar.');
            });
        };
        picker.click();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
