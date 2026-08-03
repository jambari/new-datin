from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from .models import Pengaduan


def form(request):
    if request.method == 'POST':
        Pengaduan.objects.create(
            tanggal=request.POST.get('tanggal') or timezone.now().date(),
            nama_pelapor=request.POST.get('nama_pelapor'),
            alamat=request.POST.get('alamat'),
            no_hp=request.POST.get('no_hp'),
            email=request.POST.get('email', ''),
            nama_terlapor=request.POST.get('nama_terlapor'),
            jabatan=request.POST.get('jabatan'),
            materi_pengaduan=request.POST.get('materi_pengaduan'),
            isi_pengaduan=request.POST.get('isi_pengaduan'),
        )
        messages.success(request, 'Pengaduan berhasil dikirim. Tim kami akan menindaklanjuti.')
        return redirect('pengaduan_success')
    return render(request, 'pengaduan/form.html')


def success(request):
    return render(request, 'pengaduan/success.html')
