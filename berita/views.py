import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from theme.seo_views import absolute_url

from .forms import BeritaForm
from .models import Berita

PER_PAGE = 9
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}


# ── Publik ────────────────────────────────────────────────────────────────

def berita_list(request):
    qs = Berita.objects.published().select_related('author')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(excerpt__icontains=q)
                       | Q(content__icontains=q))
    paginator = Paginator(qs, PER_PAGE)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'berita/list.html', {
        'page_obj': page,
        'berita_list': page.object_list,
        'query': q,
    })


def berita_detail(request, slug):
    berita = get_object_or_404(
        Berita.objects.select_related('author'), slug=slug)
    can_preview = (berita.is_published
                   or (request.user.is_authenticated
                       and berita.can_edit(request.user)))
    if not can_preview:
        raise Http404('Berita tidak ditemukan.')

    if berita.is_published:
        Berita.objects.filter(pk=berita.pk).update(views=F('views') + 1)
        berita.views += 1

    latest = (Berita.objects.published()
              .exclude(pk=berita.pk)
              .select_related('author')[:5])

    return render(request, 'berita/detail.html', {
        'berita': berita,
        'latest': latest,
        'share_url': absolute_url(request, berita.get_absolute_url()),
        'facebook_app_id': getattr(settings, 'FACEBOOK_APP_ID', ''),
    })


# ── CRUD staff ────────────────────────────────────────────────────────────

@login_required
def berita_manage(request):
    qs = Berita.objects.select_related('author')
    status = request.GET.get('status', '').strip()
    if status in {Berita.STATUS_DRAFT, Berita.STATUS_PUBLISHED}:
        qs = qs.filter(status=status)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(excerpt__icontains=q))

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    items = list(page.object_list)
    for item in items:
        item.user_can_edit = item.can_edit(request.user)

    return render(request, 'berita/manage.html', {
        'page_obj': page,
        'items': items,
        'status': status,
        'query': q,
        'draft_count': Berita.objects.filter(status=Berita.STATUS_DRAFT).count(),
        'published_count': Berita.objects.filter(status=Berita.STATUS_PUBLISHED).count(),
    })


@login_required
def berita_create(request):
    if request.method == 'POST':
        form = BeritaForm(request.POST, request.FILES)
        if form.is_valid():
            berita = form.save(commit=False)
            berita.author = request.user
            berita.save()
            messages.success(request, f'Berita “{berita.title}” berhasil disimpan.')
            return redirect('berita:manage')
    else:
        form = BeritaForm()
    return render(request, 'berita/form.html', {
        'form': form,
        'is_update': False,
    })


@login_required
def berita_update(request, slug):
    berita = get_object_or_404(Berita, slug=slug)
    if not berita.can_edit(request.user):
        return HttpResponseForbidden('Anda tidak berhak mengubah berita ini.')
    if request.method == 'POST':
        form = BeritaForm(request.POST, request.FILES, instance=berita)
        if form.is_valid():
            berita = form.save()
            messages.success(request, f'Berita “{berita.title}” berhasil diperbarui.')
            return redirect('berita:manage')
    else:
        form = BeritaForm(instance=berita)
    return render(request, 'berita/form.html', {
        'form': form,
        'berita': berita,
        'is_update': True,
    })


@login_required
def berita_delete(request, slug):
    berita = get_object_or_404(Berita, slug=slug)
    if not berita.can_edit(request.user):
        return HttpResponseForbidden('Anda tidak berhak mengubah berita ini.')
    if request.method == 'POST':
        title = berita.title
        berita.delete()
        messages.success(request, f'Berita “{title}” dihapus.')
        return redirect('berita:manage')
    return render(request, 'berita/confirm_delete.html', {'berita': berita})


@login_required
@require_POST
def berita_upload_image(request):
    """Unggah gambar dari editor WYSIWYG; balas JSON {url}."""
    upload = request.FILES.get('image')
    if upload is None:
        return JsonResponse({'error': 'Tidak ada berkas gambar.'}, status=400)
    if upload.size > MAX_IMAGE_BYTES:
        return JsonResponse({'error': 'Ukuran gambar maksimal 5 MB.'}, status=400)
    if (upload.content_type or '').lower() not in ALLOWED_IMAGE_TYPES:
        return JsonResponse({'error': 'Format gambar harus JPG, PNG, WebP, atau GIF.'}, status=400)

    # Pastikan berkas benar-benar gambar (bukan skrip yang diberi ekstensi).
    try:
        from PIL import Image
        Image.open(upload).verify()
        upload.seek(0)
    except Exception:
        return JsonResponse({'error': 'Berkas bukan gambar yang valid.'}, status=400)

    ext = Path(upload.name).suffix.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        ext = '.jpg'
    name = f'berita/content/{timezone.now():%Y/%m}/{uuid.uuid4().hex[:16]}{ext}'
    saved = default_storage.save(name, ContentFile(upload.read()))
    return JsonResponse({'url': default_storage.url(saved)})
