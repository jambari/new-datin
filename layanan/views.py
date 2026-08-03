from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.conf import settings
from django.contrib import messages
from .models import Layanan

JENIS_DATA_MAP = {
    1: ("Peta Kegempaan", "kegempaan.jpg"),
    2: ("Peta Tingkat Kerawanan Petir", "kerawananpetir.jpg"),
    3: ("Waktu Terbit dan Terbenam Matahari atau Bulan", "terbit.jpg"),
    4: ("Peta Kejadian Petir", "petirharian.jpg"),
    5: ("Teropong Rukyat (low grade)", "page06.jpg"),
    6: ("Digital Portable Short Period Seismograph", "page07.jpg"),
    7: ("Deklinasi dan Inklinasi Magnetometer", "page08.jpg"),
}


# ── Public pages ──────────────────────────────────────────────

def landing(request):
    return render(request, 'layanan/landing.html')

def tentang(request):
    return render(request, 'layanan/tentang.html')

def tarif(request):
    return render(request, 'layanan/tarif.html')

def alur(request):
    return render(request, 'layanan/alur.html')

def data(request):
    return render(request, 'layanan/data.html')

def jasa(request):
    return render(request, 'layanan/jasa.html')

def magang(request):
    return render(request, 'layanan/magang.html')

def gts(request):
    return render(request, 'layanan/gts.html')

def formulir(request, id):
    jenis_data, jpg = JENIS_DATA_MAP.get(id, ("Deklinasi dan Inklinasi Magnetometer", "page08.jpg"))
    return render(request, 'layanan/formulir.html', {'jenis_data': jenis_data, 'jpg': jpg, 'id': id})

def daftar(request):
    permohonans = Layanan.objects.all()
    paginator = Paginator(permohonans, 10)
    page = request.GET.get('page', 1)
    return render(request, 'layanan/daftar.html', {'permohonans': paginator.get_page(page)})


# ── Dashboard CRUD ────────────────────────────────────────────

def dashboard_list(request):
    qs = Layanan.objects.all()
    paginator = Paginator(qs, 20)
    page = request.GET.get('page', 1)
    return render(request, 'layanan/dashboard_list.html', {
        'layanan_list': paginator.get_page(page),
    })


def dashboard_detail(request, pk):
    layanan = get_object_or_404(Layanan, pk=pk)
    if request.method == 'POST':
        layanan.status = request.POST.get('status', layanan.status)
        layanan.save(update_fields=['status'])
        messages.success(request, 'Status berhasil diperbarui.')
        return redirect('layanan_dashboard_detail', pk=pk)
    return render(request, 'layanan/dashboard_detail.html', {'layanan': layanan})
