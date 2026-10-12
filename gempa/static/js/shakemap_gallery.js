function openLightbox(src, caption) {
  document.getElementById("lightboxImg").src = src;
  document.getElementById("lightboxCaption").textContent = caption;
  document.getElementById("lightboxModal").style.display = "block";
}
function closeLightbox() {
  document.getElementById("lightboxModal").style.display = "none";
}
function renderShakemapGallery() {
  var gallery = document.getElementById("shakemapGallery");
  if (!gallery) return;
  var events = FELT_EVENTS.filter(function(ev) { return ev.shakemap && ev.shakemap.length > 0; });
  events.sort(function(a,b) { return (a.tanggal + a.origin) < (b.tanggal + b.origin) ? -1 : 1; });
  if (events.length === 0) {
    gallery.innerHTML = '<div class="shakemap-empty">Tidak ada gambar shakemap untuk periode ini.</div>';
    return;
  }
  var html = "";
  events.forEach(function(ev, i) {
    html += '<div class="shakemap-card lightbox-card" data-shakemap-idx="' + i + '">';
    html += '<img src="' + ev.shakemap + '" alt="Shakemap M' + ev.mag + '" loading="lazy">';
    html += '<div class="info">M' + ev.mag + ' | ' + ev.tanggal + ' ' + ev.origin + '<br>' + (ev.wilayah || '') + '</div>';
    html += '</div>';
  });
  gallery.innerHTML = html;
  var cards = gallery.querySelectorAll(".lightbox-card");
  cards.forEach(function(card) {
    card.addEventListener("click", function() {
      var idx = parseInt(this.getAttribute("data-shakemap-idx"));
      var ev = events[idx];
      var cap = "M" + ev.mag + " | " + ev.tanggal + " " + ev.origin;
      openLightbox(ev.shakemap, cap);
    });
  });
}
