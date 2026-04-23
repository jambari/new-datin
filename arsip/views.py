from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .models import Album, Foto


def _media_url(path):
    return settings.MEDIA_URL + path if path else ''


@login_required
def album_list(request):
    albums = Album.objects.prefetch_related('cover_photo')
    for a in albums:
        if a.cover_photo:
            a.cover_url = _media_url(a.cover_photo.thumbnail_path or a.cover_photo.file_path)
        else:
            a.cover_url = ''
    return render(request, 'arsip/album_list.html', {'albums': albums})


@login_required
def album_detail(request, pk):
    album = get_object_or_404(Album, pk=pk)
    fotos = album.fotos.all()
    for f in fotos:
        f.thumb_url = _media_url(f.thumbnail_path or f.file_path)
        f.full_url  = _media_url(f.file_path)
    return render(request, 'arsip/album_detail.html', {'album': album, 'fotos': fotos})
