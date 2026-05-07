from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Count
from .models import Album, Foto


def _media_url(path):
    return settings.MEDIA_URL + path if path else ''


@login_required
def album_list(request):
    q = request.GET.get('q', '').strip()
    albums = Album.objects.prefetch_related('cover_photo').annotate(foto_count=Count('fotos'))
    if q:
        albums = albums.filter(name__icontains=q)
    for a in albums:
        if a.cover_photo and a.cover_photo.thumbnail_path:
            a.cover_url      = _media_url(a.cover_photo.thumbnail_path)
            a.cover_is_video = a.cover_photo.is_video
        elif a.cover_photo and not a.cover_photo.is_video:
            a.cover_url      = _media_url(a.cover_photo.file_path)
            a.cover_is_video = False
        else:
            a.cover_url      = ''
            a.cover_is_video = a.cover_photo.is_video if a.cover_photo else False
    return render(request, 'arsip/album_list.html', {'albums': albums, 'q': q})


def album_detail(request, pk):
    album = get_object_or_404(Album, pk=pk)
    fotos = album.fotos.all()
    for f in fotos:
        if f.thumbnail_path:
            f.thumb_url = _media_url(f.thumbnail_path)
        elif not f.is_video:
            f.thumb_url = _media_url(f.file_path)
        else:
            f.thumb_url = ''   # no thumbnail yet — show play icon
        f.full_url = _media_url(f.file_path)
    return render(request, 'arsip/album_detail.html', {'album': album, 'fotos': fotos})
