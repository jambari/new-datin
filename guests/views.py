from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from .models import Guest


def index(request):
    guests = Guest.objects.all()
    paginator = Paginator(guests, 9)
    page = request.GET.get('page', 1)
    guest_list = paginator.get_page(page)
    return render(request, 'guests/index.html', {
        'guests': guest_list,
    })


def create(request):
    if request.method == 'POST':
        Guest.objects.create(
            nama=request.POST.get('nama'),
            dari=request.POST.get('dari'),
            keperluan=request.POST.get('keperluan'),
            keterangan=request.POST.get('keterangan', ''),
            foto=request.POST.get('foto', ''),
        )
        messages.success(request, 'Data berhasil ditambahkan')
        return redirect('guests_index')
    return render(request, 'guests/create.html')


def search(request):
    q = request.GET.get('q', '').strip()
    guests = Guest.objects.none()
    if q:
        guests = Guest.objects.filter(nama__icontains=q) | Guest.objects.filter(dari__icontains=q)
        if not guests.exists():
            messages.warning(request, 'Tidak ada tamu yang anda cari!')
        else:
            messages.info(request, f'Ditemukan {guests.count()} tamu')
    paginator = Paginator(guests, 9)
    page = request.GET.get('page', 1)
    return render(request, 'guests/index.html', {
        'guests': paginator.get_page(page),
        'search_query': q,
    })
