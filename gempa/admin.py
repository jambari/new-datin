from django.contrib import admin
from reversion.admin import VersionAdmin
from django.contrib.admin.views.main import ChangeList
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.shortcuts import redirect
from django.urls import path, reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from import_export.admin import ExportMixin
from import_export import resources
from datetime import datetime, timedelta
from django import forms
import os

from .models import Gempa, Balaigempa, Gempasorong, Gempanabire, Satudatagempa, Gempanganjuk, Significant, City
from .models import nearest_city_description, compute_delta
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from .sites import gempa_admin_site
from . import gmt

import logging

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

BULAN = {1:'Januari',2:'Februari',3:'Maret',4:'April',5:'Mei',6:'Juni',
         7:'Juli',8:'Agustus',9:'September',10:'Oktober',11:'November',12:'Desember'}
BULAN_SINGKAT = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"Mei",6:"Jun",
         7:"Jul",8:"Agu",9:"Sep",10:"Okt",11:"Nov",12:"Des"}
HARI = ['Minggu','Senin','Selasa','Rabu','Kamis',"Jum'at",'Sabtu']

# Direktori unggahan GMT milik aplikasi Laravel di .188 (tidak ada di .189;\n# atur lewat settings.GMT_UPLOADS_DIR bila nanti disalin).
GMT_UPLOADS = getattr(settings, 'GMT_UPLOADS_DIR', '/var/www/html/datin/public/uploads')

def gmt_image(prefix, tanggal, origin):
    try:
        dt = datetime.strptime(f"{tanggal} {str(origin)[:8]}", "%Y-%m-%d %H:%M:%S")
        base = f"{prefix}_{dt.strftime('%Y-%m-%d_%H%M')}"
        for s in range(60):
            fn = f"{base}{s:02d}UTC.png"
            if os.path.exists(f"{GMT_UPLOADS}/{fn}"):
                return fn
    except Exception:
        pass
    return None

def eq_datetime_context(tanggal, origin_str):
    """Return dict of formatted date/time fields used by all press/template views."""
    origin_clean = str(origin_str)[:8]
    dt_utc = datetime.strptime(f"{tanggal} {origin_clean}", "%Y-%m-%d %H:%M:%S")
    dt_wit = dt_utc + timedelta(hours=9)
    tanggal_wit = dt_wit if dt_wit.date() > dt_utc.date() else dt_utc
    return {
        'hari': HARI[tanggal_wit.weekday() + 1 if tanggal_wit.weekday() < 6 else 0],
        'tanggal_indo': f"{tanggal_wit.day:02d}-{BULAN_SINGKAT[tanggal_wit.month]}-{str(tanggal_wit.year)[-2:]}",
        'jam_wit': dt_wit.strftime("%H:%M:%S"),
        'jam_susulan': (dt_wit + timedelta(minutes=30)).strftime("%H:%M"),
        'jam_utc': dt_utc.strftime("%H:%M:%S"),
    }

def format_lat(lintang):
    try:
        v = float(lintang)
        return f"{abs(v):.2f} {'LS' if v < 0 else 'LU'}"
    except Exception:
        return str(lintang)

def format_lon(bujur):
    try:
        return f"{float(bujur):.2f} BT"
    except Exception:
        return f"{bujur} BT"

# ── Custom ChangeList: strip our GET params before Django tries them as ORM lookups ──

_CUSTOM_PARAMS = frozenset({
    'delta_filter','date_from', 'date_to', 'terasa', 'mag_range', 'depth_range', 'lat_min', 'lat_max', 'lon_min', 'lon_max', 'per_page'})

class GempaChangeList(ChangeList):
    def get_filters_params(self, params=None):
        result = super().get_filters_params(params)
        for k in _CUSTOM_PARAMS:
            result.pop(k, None)
        return result

# ── Top-bar filter mixin (replaces sidebar list_filter entirely) ──────────────

class TopFilterMixin:
    """All filtering via GET params rendered in a top bar; no sidebar."""
    change_list_template = 'admin/gempa/change_list.html'
    list_filter = ()
    report_source = None  # Laporan Bulanan source code (JAY/NBPI/PGR5/SWI); None hides the button

    # Per-page dropdown (10/15/25/50). Honors ?per_page=N from the filter bar.
    PER_PAGE_OPTIONS = (10, 15, 25, 50)
    def get_paginator(self, request, queryset, per_page, orphans=0, allow_empty_first_page=True):
        try:
            n = int(request.GET.get('per_page', per_page))
            if n in self.PER_PAGE_OPTIONS:
                per_page = n
        except (TypeError, ValueError):
            pass
        return super().get_paginator(request, queryset, per_page, orphans, allow_empty_first_page)

    # Force English-decimal display ("." not ",") for scientific data.
    @staticmethod
    def _eng_dec(val, places=None):
        if val is None or val == "":
            return "-"
        try:
            v = float(val)
            return f"{v}" if places is None else f"{v:.{places}f}"
        except (TypeError, ValueError):
            return str(val)
    @staticmethod
    def _places_of(obj, field_name):
        """Return DecimalField decimal_places for this field, or None if not a Decimal."""
        try:
            return getattr(type(obj)._meta.get_field(field_name), "decimal_places", None)
        except Exception:
            return None
    def magnitudo_en(self, obj):  return self._eng_dec(obj.magnitudo, self._places_of(obj, "magnitudo"))
    magnitudo_en.short_description = "Magnitudo"
    magnitudo_en.admin_order_field = "magnitudo"
    def bujur_en(self, obj):      return self._eng_dec(obj.bujur, self._places_of(obj, "bujur"))
    bujur_en.short_description = "Bujur"
    bujur_en.admin_order_field = "bujur"

    def get_changelist(self, request, **kwargs):
        return GempaChangeList

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        g = request.GET.get
        df, dt = g('date_from', '').strip(), g('date_to', '').strip()
        if df: qs = qs.filter(tanggal__gte=df)
        if dt: qs = qs.filter(tanggal__lte=dt)
        terasa = g('terasa', '').strip()
        if terasa in ('0', '1'):
            try:
                qs = qs.filter(terasa=terasa)
            except Exception:
                pass
        mag = g('mag_range', '').strip()
        if mag == 'lt3':   qs = qs.filter(magnitudo__lt=3.0)
        elif mag == '3to5': qs = qs.filter(magnitudo__gte=3.0, magnitudo__lt=5.0)
        elif mag == '5to6': qs = qs.filter(magnitudo__gte=5.0, magnitudo__lt=6.0)
        elif mag == 'ge6':  qs = qs.filter(magnitudo__gte=6.0)
        delta_val = g('delta_filter', '').strip()
        if delta_val:
            qs = qs.filter(delta__contains=delta_val)
        depth = g('depth_range', '').strip()
        if depth == 'shallow':      qs = qs.filter(depth__lt=60)
        elif depth == 'intermediate': qs = qs.filter(depth__gte=60, depth__lte=300)
        elif depth == 'deep':        qs = qs.filter(depth__gt=300)
        try:
            lat_min = g('lat_min', '').strip()
            if lat_min: qs = qs.filter(lintang__gte=float(lat_min))
        except (ValueError, TypeError): pass
        try:
            lat_max = g('lat_max', '').strip()
            if lat_max: qs = qs.filter(lintang__lte=float(lat_max))
        except (ValueError, TypeError): pass
        try:
            lon_min = g('lon_min', '').strip()
            if lon_min: qs = qs.filter(bujur__gte=float(lon_min))
        except (ValueError, TypeError): pass
        try:
            lon_max = g('lon_max', '').strip()
            if lon_max: qs = qs.filter(bujur__lte=float(lon_max))
        except (ValueError, TypeError): pass
        return qs

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        g = request.GET.get
        extra_context.update({
            'date_from':    g('date_from', ''),
            'date_to':      g('date_to', ''),
            'filter_terasa': g('terasa', ''),
            'filter_mag':   g('mag_range', ''),
            'filter_depth': g('depth_range', ''),
            'filter_delta': g('delta_filter', ''),
            'filter_lat_min': g('lat_min', ''),
            'filter_lat_max': g('lat_max', ''),
            'filter_lon_min': g('lon_min', ''),
            'filter_lon_max': g('lon_max', ''),
            'report_source':  self.report_source,
        })
        return super().changelist_view(request, extra_context=extra_context)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "tanggal":
            field.widget = forms.DateInput(
                attrs={"class": "vDateField flatpickr-date", "placeholder": "Klik pilih tanggal", "autocomplete": "off"},
                format="%Y-%m-%d",
            )
        elif db_field.name == "created_at":
            from django.forms import DateTimeField
            widget = forms.DateTimeInput(
                attrs={"type": "datetime-local", "step": "1"},
                format="%Y-%m-%dT%H:%M:%S"
            )
            field = DateTimeField(
                widget=widget,
                input_formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"],
                required=False,
            )
        return field

    def save_model(self, request, obj, form, change):
        if not obj.ket:
            obj.ket = nearest_city_description(obj.lintang, obj.bujur)
        # Upsert: if event_id already exists, update that record instead of inserting
        if obj.event_id and not change:
            existing = obj.__class__.objects.filter(event_id=obj.event_id).first()
            if existing:
                obj.pk = existing.pk
        super().save_model(request, obj, form, change)

    @admin.action(description='Isi Keterangan otomatis dari kota terdekat')
    def isi_keterangan(self, request, queryset):
        updated = 0
        for obj in queryset:
            ket = nearest_city_description(obj.lintang, obj.bujur)
            if ket != '-':
                obj.ket = ket
                obj.save(update_fields=['ket'])
                updated += 1
        self.message_user(request, f"{updated} keterangan berhasil diperbarui.")

    actions = ['isi_keterangan']

# ── Resources for export ─────────────────────────────────────────────────────

class GempaResource(resources.ModelResource):
    class Meta:
        model = Gempa
        fields = ('id','tanggal','origin','lintang','bujur','magnitudo','type',
                  'depth','ket','terasa','terdampak','sumber','petugas','delta','created_at')
    # Force English decimal '.' in CSV export (django-import-export 4.x defaults to locale)
    def dehydrate_magnitudo(self, obj): return f'{obj.magnitudo}' if obj.magnitudo is not None else ''
    def dehydrate_bujur(self, obj):     return f'{obj.bujur}' if obj.bujur is not None else ''

class BalaigempaResource(resources.ModelResource):
    class Meta:
        model = Balaigempa
        fields = ('id','tanggal','origin','lintang','bujur','magnitudo','type',
                  'depth','ket','terasa','terdampak','delta','created_at')
    def dehydrate_magnitudo(self, obj): return f'{obj.magnitudo}' if obj.magnitudo is not None else ''
    def dehydrate_bujur(self, obj):     return f'{obj.bujur}' if obj.bujur is not None else ''

class SatudatagempaResource(resources.ModelResource):
    class Meta:
        model = Satudatagempa
        fields = ('id','tanggal','origin','lintang','bujur','magnitudo','depth',
                  'ket','terasa','sumber','created_at')
    def dehydrate_magnitudo(self, obj): return f'{obj.magnitudo}' if obj.magnitudo is not None else ''

class GmtMapMixin:
    """Tombol "Buat Peta GMT" di halaman press/template.

    Port dari alur .188: di sana peta dibuat otomatis oleh `ingest_gempa`.
    Di .189 tidak ada feed SeisComp, jadi operator bisa membuat/menyegarkan
    peta sendiri lewat tombol ini. Region diambil dari `report_source`
    (JAY/PGR5/SWI/NBPI) yang sudah ada di tiap ModelAdmin.
    """

    _PREFIX_TO_REGION = {prefix: region for region, prefix in gmt.REGIONS.items()}

    @property
    def gmt_region(self):
        prefix = getattr(self, 'report_source', None)
        region = self._PREFIX_TO_REGION.get(prefix)
        if region is None:
            raise ImproperlyConfigured(
                f'{type(self).__name__}: report_source {prefix!r} tidak dikenal '
                f'(pilihan: {sorted(self._PREFIX_TO_REGION)})')
        return region

    def gmt_event_args(self, obj):
        """(tanggal, origin) yang menentukan nama berkas peta."""
        return obj.tanggal, obj.origin

    def buat_peta_context(self, obj):
        """Konteks tombol untuk halaman template/press."""
        tanggal, origin = self.gmt_event_args(obj)
        return {
            'buat_peta_url': reverse(
                f'gempa_admin:{self.model._meta.model_name}-buat-peta', args=[obj.pk]),
            'gmt_map_exists': gmt.map_exists(self.gmt_region, tanggal, origin),
        }

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/buat-peta/',
                 self.admin_site.admin_view(self.buat_peta_view),
                 name=f'{self.model._meta.model_name}-buat-peta'),
        ]
        return custom + urls

    def buat_peta_view(self, request, pk):
        """POST saja: buat ulang peta GMT untuk satu event."""
        changelist = reverse(
            f'gempa_admin:{self.model._meta.app_label}_'
            f'{self.model._meta.model_name}_changelist')
        obj = self.model.objects.filter(pk=pk).first()
        if obj is None:
            messages.error(request, f'Event pk={pk} tidak ditemukan.')
            return redirect(changelist)

        back = request.META.get('HTTP_REFERER') or changelist
        if request.method != 'POST':
            messages.error(request, 'Peta dibuat lewat tombol "Buat Peta GMT", bukan URL langsung.')
            return redirect(back)

        tanggal, origin = self.gmt_event_args(obj)
        try:
            result = gmt.generate(
                self.gmt_region,
                lat=obj.lintang, lon=obj.bujur, mag=obj.magnitudo,
                tanggal=tanggal, origin=origin, depth=obj.depth,
                force=True,
            )
        except gmt.GmtError as exc:
            logger.warning('Peta GMT gagal untuk %s pk=%s: %s',
                           self.model.__name__, pk, exc)
            messages.error(request, f'Gagal membuat peta GMT: {exc}')
        else:
            messages.success(
                request,
                f'Peta GMT dibuat: {result.filename} ({result.seconds:.1f} detik). '
                f'Muat ulang halaman untuk melihatnya.')
        return redirect(back)


# ── Gempa JAY ─────────────────────────────────────────────────────────────────

@admin.register(Gempa, site=gempa_admin_site)
class GempaAdmin(GmtMapMixin, TopFilterMixin, ExportMixin, VersionAdmin):
    report_source = 'JAY'

    def get_changeform_initial_data(self, request):
        data = super().get_changeform_initial_data(request)
        if request.user.is_superuser:
            from django.utils import timezone
            data["created_at"] = timezone.now().strftime("%Y-%m-%dT%H:%M:%S")
        return data

    def get_form(self, request, obj=None, change=False, **kwargs):
        if request.user.is_superuser:
            f = self.model._meta.get_field("created_at")
            f.editable = True
        form_class = super().get_form(request, obj=obj, change=change, **kwargs)
        # Ensure created_at shows existing value (not blank) by patching form init
        if request.user.is_superuser:
            orig_init = form_class.__init__
            def patched_init(self_form, *a, **kw):
                orig_init(self_form, *a, **kw)
                if "created_at" in self_form.fields and not self_form.initial.get("created_at"):
                    from django.utils import timezone
                    val = getattr(self_form.instance, "created_at", None) if self_form.instance else None
                    if val is None:
                        val = timezone.now()
                    if hasattr(val, "strftime"):
                        val = val.strftime("%Y-%m-%dT%H:%M:%S")
                    self_form.initial["created_at"] = val
            form_class.__init__ = patched_init
        return form_class

    def get_fieldsets(self, request, obj=None):
        fs = list(super().get_fieldsets(request, obj))
        if request.user.is_superuser:
            # Add created_at + delta to Administrasi section for admins
            fs = [(n, {**o, "fields": o["fields"] + ("created_at", "delta")
                       if n == "Administrasi" and "created_at" not in o["fields"] and "delta" not in o["fields"]
                       else o["fields"]})
                  for n, o in fs]
        else:
            fs = [(n, {**o, "fields": tuple(f for f in o["fields"] if f not in ("created_at", "delta"))})
                  for n, o in fs]
        return fs

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if request.user.is_superuser and "delta" not in ro:
            ro.append("delta")
        return ro

    def save_model(self, request, obj, form, change):
        from .models import compute_delta
        if "created_at" in form.cleaned_data and form.cleaned_data["created_at"] is not None:
            obj.created_at = form.cleaned_data["created_at"]
        obj.delta = compute_delta(obj.tanggal, obj.origin, obj.created_at)
        super().save_model(request, obj, form, change)

    class Media:
        css = {"all": ("https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",)}
        js = (
            "/static/js/gempa_notify.js",
            "https://cdn.jsdelivr.net/npm/flatpickr",
            "https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/id.js",
            "/static/js/flatpickr_init.js",
        )
    resource_class = GempaResource
    list_display = ('action_buttons', 'tanggal', 'origin', 'lintang', 'bujur_en', 'magnitudo_en',
                    'depth', 'ket', 'terasa_display', 'terdampak', 'delta', 'created_at')
    list_per_page = 10
    list_filter = ()
    search_fields = ('event_id', 'tanggal', 'ket', 'terdampak')
    ordering = ('-tanggal', '-origin')
    date_hierarchy = 'tanggal'

    fieldsets = (
        ('Lokasi & Waktu', {
            'fields': ('tanggal', 'origin', 'lintang', 'bujur', 'depth')
        }),
        ('Parameter', {
            'fields': ('magnitudo', 'type', 'ket')
        }),
        ('Dampak', {
            'fields': ('terasa', 'terdampak', 'narasi')
        }),
        ('Administrasi', {
            'fields': ('sumber', 'petugas', 'created_at')
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/press/', self.admin_site.admin_view(self.press_view), name='gempa-press'),
            path('<int:pk>/template-balai/', self.admin_site.admin_view(self.template_balai_view), name='gempa-template-balai'),
            path('<int:pk>/kirim-sdg/', self.admin_site.admin_view(self.kirim_sdg_view), name='gempa-kirim-sdg'),
        ]
        return custom + urls

    @admin.display(description='Terasa')
    def terasa_display(self, obj):
        return "Dirasakan" if obj.terasa else "Tidak"
    @admin.display(description='Aksi')
    def action_buttons(self, obj):
        tmpl_url  = reverse('gempa_admin:gempa-template-balai', args=[obj.pk])
        edit_url  = reverse('gempa_admin:gempa_gempa_change', args=[obj.pk])
        del_url   = reverse('gempa_admin:gempa_gempa_delete', args=[obj.pk])
        hist_url  = reverse('gempa_admin:gempa_gempa_history', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Peta</a> '
            '<a class="button" href="{}">Commits</a> '
            '<a class="button" href="{}">Edit</a> '
            '<a class="button" href="{}" style="background:#ba2121;color:white;">Hapus</a>',
            tmpl_url, hist_url, edit_url, del_url
        )

    def press_view(self, request, pk):
        from django.shortcuts import render
        obj = Gempa.objects.get(pk=pk)
        ctx = eq_datetime_context(obj.tanggal, obj.origin)
        ctx.update({
            'event': obj,
            'lat': format_lat(obj.lintang),
            'lon': format_lon(obj.bujur),
            'mag': round(float(obj.magnitudo), 1),
            'ket_parts': str(obj.ket).split(),
        })
        return render(request, 'gempa/press.html', ctx)

    def template_balai_view(self, request, pk):
        from django.shortcuts import render
        obj = Gempa.objects.get(pk=pk)
        ctx = eq_datetime_context(obj.tanggal, obj.origin)
        
        import json
        # Compute all timezone times for client-side switching
        origin_clean = str(obj.origin)[:8]
        dt_utc = datetime.strptime(f"{obj.tanggal} {origin_clean}", "%Y-%m-%d %H:%M:%S")
        tz_data = {}
        for name, hours in [('WIB', 7), ('WITA', 8), ('WIT', 9)]:
            dt = dt_utc + timedelta(hours=hours)
            tz_data[name] = {
                'date': f"{dt.day:02d}-{BULAN_SINGKAT[dt.month]}-{str(dt.year)[-2:]}",
                'time': dt.strftime("%H:%M:%S"),
                'susulan': (dt + timedelta(minutes=30)).strftime("%H:%M"),
            }
        ctx.update({'event': obj, 'lat': format_lat(obj.lintang),
                    'lon': format_lon(obj.bujur), 'mag': round(float(obj.magnitudo), 1),
                    'epic_map': gmt_image('JAY', obj.tanggal, obj.origin),
                    'tz_data': tz_data,
                    'default_tz': 'WIT',
                    **self.buat_peta_context(obj)})
        tpl = 'gempa/angkasatemplatebalai_gfz.html' if request.GET.get('gfz') else 'gempa/angkasatemplatebalai.html'
        return render(request, tpl, ctx)

    def kirim_sdg_view(self, request, pk):
        obj = Gempa.objects.get(pk=pk)
        Satudatagempa.objects.create(
            tanggal=obj.tanggal, origin=obj.origin,
            lintang=obj.lintang, bujur=obj.bujur,
            magnitudo=obj.magnitudo, depth=obj.depth,
            ket=obj.ket or '.', sumber='BMKG-JAY',
        )
        messages.success(request, f"Gempa {obj} dikirim ke Satu Data Gempa.")
        return HttpResponseRedirect(reverse('gempa_admin:gempa_satudatagempa_changelist'))

# ── Form untuk DatePicker ───────────────────────────────────────────────────
class BalaigempaForm(forms.ModelForm):
    class Meta:
        model = Balaigempa
        fields = "__all__"
        widgets = {
            "tanggal": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": "vDateField flatpickr-date", "placeholder": "Klik pilih tanggal", "autocomplete": "off"},
            ),
        }

@admin.register(Balaigempa, site=gempa_admin_site)
class BalaigempaAdmin(GmtMapMixin, TopFilterMixin, ExportMixin, VersionAdmin):
    report_source = 'PGR5'

    class Media:
        css = {"all": ("https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",)}
        js = (
            "/static/js/gempa_notify.js",
            "https://cdn.jsdelivr.net/npm/flatpickr",
            "https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/id.js",
            "/static/js/flatpickr_init.js",
        )
    form = BalaigempaForm
    resource_class = BalaigempaResource
    list_display = ("action_buttons", "tanggal", "origin", "lintang", "bujur_en", "magnitudo_en",
                    "depth", "ket", "terasa_display", "terdampak", "delta")
    list_per_page = 10
    list_filter = ()
    search_fields = ("event_id", "tanggal", "ket", "terdampak")
    ordering = ("-tanggal", "-origin")
    date_hierarchy = "tanggal"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/sms/', self.admin_site.admin_view(self.sms_view), name='balaigempa-sms'),
            path('<int:pk>/press/', self.admin_site.admin_view(self.press_view), name='balaigempa-press'),
            path('<int:pk>/inject/', self.admin_site.admin_view(self.inject_view), name='balaigempa-inject'),
            path('<int:pk>/kirim-sdg/', self.admin_site.admin_view(self.kirim_sdg_view), name='balaigempa-kirim-sdg'),
        ]
        return custom + urls

    @admin.display(description='Terasa')
    def terasa_display(self, obj):
        return 'Dirasakan' if obj.terasa else 'Tidak'

    @admin.display(description='Aksi')
    def action_buttons(self, obj):
        sms_url    = reverse('gempa_admin:balaigempa-sms', args=[obj.pk])
        inject_url = reverse('gempa_admin:balaigempa-inject', args=[obj.pk])
        edit_url   = reverse('gempa_admin:gempa_balaigempa_change', args=[obj.pk])
        del_url    = reverse('gempa_admin:gempa_balaigempa_delete', args=[obj.pk])
        hist_url = reverse('gempa_admin:gempa_balaigempa_history', args=[obj.pk])
        html = (f'<a class="button" href="{sms_url}">Peta</a> '
                f'<a class="button" href="{hist_url}">Commits</a> '
                f'<a class="button" href="{edit_url}">Edit</a> '
                f'<a class="button" href="{del_url}" style="background:#ba2121;color:white;">Hapus</a>')
        if request := getattr(self, '_current_request', None):
            if request.user.username == 'angkasa':
                html += f' <a class="button" href="{inject_url}">→ JAY</a>'
        return mark_safe(html)

    def changeform_view(self, request, *args, **kwargs):
        self._current_request = request
        return super().changeform_view(request, *args, **kwargs)

    def changelist_view(self, request, *args, **kwargs):
        self._current_request = request
        return super().changelist_view(request, *args, **kwargs)

    def sms_view(self, request, pk):
        from django.shortcuts import render
        import json
        obj = Balaigempa.objects.get(pk=pk)
        ctx = eq_datetime_context(obj.tanggal, obj.origin)
        # Compute all timezone times for client-side switching
        origin_clean = str(obj.origin)[:8]
        dt_utc = datetime.strptime(f"{obj.tanggal} {origin_clean}", "%Y-%m-%d %H:%M:%S")
        tz_data = {}
        for name, hours in [('WIB', 7), ('WITA', 8), ('WIT', 9)]:
            dt = dt_utc + timedelta(hours=hours)
            tz_data[name] = {
                'date': f"{dt.day:02d}-{BULAN_SINGKAT[dt.month]}-{str(dt.year)[-2:]}",
                'time': dt.strftime("%H:%M:%S"),
                'susulan': (dt + timedelta(minutes=30)).strftime("%H:%M"),
            }
        ctx.update({'event': obj, 'mag': round(float(obj.magnitudo), 1), 'lat': format_lat(obj.lintang), 'lon': format_lon(obj.bujur),
                    'depth': obj.depth, 'terdampak': obj.terdampak,
                    'epic_map': gmt_image('PGR5', obj.tanggal, obj.origin),
                    'tz_data': json.dumps(tz_data),
                    'default_tz': 'WIT',
                    **self.buat_peta_context(obj)})
        return render(request, 'gempa/balaisms.html', ctx)

    def press_view(self, request, pk):
        from django.shortcuts import render
        obj = Balaigempa.objects.get(pk=pk)
        ctx = eq_datetime_context(obj.tanggal, obj.origin)
        ket_parts = str(obj.ket or '').split()
        ctx.update({'event': obj, 'lat': format_lat(obj.lintang),
                    'lon': format_lon(obj.bujur), 'mag': round(float(obj.magnitudo), 1),
                    'ket_parts': ket_parts})
        return render(request, 'gempa/press.html', ctx)

    def inject_view(self, request, pk):
        if request.user.username != 'angkasa':
            messages.error(request, "Akses ditolak.")
            return HttpResponseRedirect(reverse('gempa_admin:gempa_balaigempa_changelist'))
        obj = Balaigempa.objects.get(pk=pk)
        Gempa.objects.create(
            tanggal=obj.tanggal, origin=obj.origin, lintang=obj.lintang,
            bujur=obj.bujur, magnitudo=obj.magnitudo, depth=obj.depth,
            ket=obj.ket or '.', sumber='PGR V',
        )
        messages.success(request, "Gempa PGR V disalin ke tabel JAY.")
        return HttpResponseRedirect(reverse('gempa_admin:gempa_gempa_changelist'))

    def kirim_sdg_view(self, request, pk):
        obj = Balaigempa.objects.get(pk=pk)
        Satudatagempa.objects.create(
            tanggal=obj.tanggal, origin=obj.origin, lintang=obj.lintang,
            bujur=obj.bujur, magnitudo=obj.magnitudo, depth=obj.depth,
            ket=obj.ket or '.', sumber='BMKG-PGR V',
        )
        messages.success(request, f"Gempa {obj} dikirim ke Satu Data Gempa.")
        return HttpResponseRedirect(reverse('gempa_admin:gempa_satudatagempa_changelist'))

# ── Gempasorong SWI ───────────────────────────────────────────────────────────

@admin.register(Gempasorong, site=gempa_admin_site)
class GempasorongAdmin(GmtMapMixin, TopFilterMixin, ExportMixin, VersionAdmin):
    report_source = 'SWI'

    class Media:
        css = {"all": ("https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",)}
        js = (
            "/static/js/gempa_notify.js",
            "https://cdn.jsdelivr.net/npm/flatpickr",
            "https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/id.js",
            "/static/js/flatpickr_init.js",
        )
    list_display = ('action_buttons', 'tanggal', 'origin', 'lintang', 'bujur_en', 'magnitudo_en',
                    'depth', 'ket', 'terasa_display', 'terdampak', 'delta')
    list_per_page = 10
    list_filter = ()
    search_fields = ('event_id', 'tanggal', 'ket')
    ordering = ('-tanggal', '-origin')
    date_hierarchy = 'tanggal'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/info/', self.admin_site.admin_view(self.info_view), name='gempasorong-info'),
            path('<int:pk>/inject/', self.admin_site.admin_view(self.inject_view), name='gempasorong-inject'),
            path('<int:pk>/kirim-sdg/', self.admin_site.admin_view(self.kirim_sdg_view), name='gempasorong-kirim-sdg'),
        ]
        return custom + urls

    @admin.display(description='Terasa')
    def terasa_display(self, obj):
        return 'Dirasakan' if obj.terasa else 'Tidak'

    @admin.display(description='Aksi')
    def action_buttons(self, obj):
        info_url   = reverse('gempa_admin:gempasorong-info', args=[obj.pk])
        edit_url   = reverse('gempa_admin:gempa_gempasorong_change', args=[obj.pk])
        del_url    = reverse('gempa_admin:gempa_gempasorong_delete', args=[obj.pk])
        hist_url   = reverse('gempa_admin:gempa_gempasorong_history', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Peta</a> '
            '<a class="button" href="{}">Commits</a> '
            '<a class="button" href="{}">Edit</a> '
            '<a class="button" href="{}" style="background:#ba2121;color:white;">Hapus</a>',
            info_url, hist_url, edit_url, del_url
        )

    def info_view(self, request, pk):
        from django.shortcuts import render
        obj = Gempasorong.objects.get(pk=pk)
        ctx = eq_datetime_context(obj.tanggal, obj.origin)
        
        import json
        # Compute all timezone times for client-side switching
        origin_clean = str(obj.origin)[:8]
        dt_utc = datetime.strptime(f"{obj.tanggal} {origin_clean}", "%Y-%m-%d %H:%M:%S")
        tz_data = {}
        for name, hours in [('WIB', 7), ('WITA', 8), ('WIT', 9)]:
            dt = dt_utc + timedelta(hours=hours)
            tz_data[name] = {
                'date': f"{dt.day:02d}-{BULAN_SINGKAT[dt.month]}-{str(dt.year)[-2:]}",
                'time': dt.strftime("%H:%M:%S"),
                'susulan': (dt + timedelta(minutes=30)).strftime("%H:%M"),
            }
        ctx.update({'event': obj, 'lat': format_lat(obj.lintang),
                    'lon': format_lon(obj.bujur), 'mag': round(float(obj.magnitudo), 1),
                    'latmap': obj.lintang, 'lonmap': obj.bujur,
                    'epic_map': gmt_image('SWI', obj.tanggal, obj.origin),
                    'tz_data': tz_data,
                    'default_tz': 'WIT',
                    **self.buat_peta_context(obj)})
        return render(request, 'gempa/sorongtemplatebalai.html', ctx)

    def inject_view(self, request, pk):
        if request.user.username != 'angkasa':
            messages.error(request, "Akses ditolak.")
            return HttpResponseRedirect(reverse('gempa_admin:gempa_gempasorong_changelist'))
        obj = Gempasorong.objects.get(pk=pk)
        Gempa.objects.create(
            tanggal=obj.tanggal, origin=obj.origin, lintang=obj.lintang,
            bujur=obj.bujur, magnitudo=obj.magnitudo, depth=obj.depth,
            ket=obj.ket or '.', sumber='pgn',
        )
        messages.success(request, "Gempa Sorong disalin ke tabel JAY.")
        return HttpResponseRedirect(reverse('gempa_admin:gempa_gempa_changelist'))

    def kirim_sdg_view(self, request, pk):
        obj = Gempasorong.objects.get(pk=pk)
        Satudatagempa.objects.create(
            tanggal=obj.tanggal, origin=obj.origin, lintang=obj.lintang,
            bujur=obj.bujur, magnitudo=obj.magnitudo, depth=obj.depth,
            ket=obj.ket or '.', sumber='BMKG-SWI',
        )
        messages.success(request, "Gempa Sorong dikirim ke Satu Data Gempa.")
        return HttpResponseRedirect(reverse('gempa_admin:gempa_satudatagempa_changelist'))

# ── Gempanabire NBPI ──────────────────────────────────────────────────────────

@admin.register(Gempanabire, site=gempa_admin_site)
class GempanahireAdmin(GmtMapMixin, TopFilterMixin, ExportMixin, VersionAdmin):
    report_source = 'NBPI'

    class Media:
        css = {"all": ("https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",)}
        js = (
            "/static/js/gempa_notify.js",
            "https://cdn.jsdelivr.net/npm/flatpickr",
            "https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/id.js",
            "/static/js/flatpickr_init.js",
        )
    list_display = ('action_buttons', 'tanggal', 'origin', 'lintang', 'bujur_en', 'magnitudo_en',
                    'depth', 'ket', 'terasa_display', 'delta')
    list_per_page = 10
    list_filter = ()
    search_fields = ('event_id', 'tanggal', 'ket')
    ordering = ('-tanggal', '-origin')
    date_hierarchy = 'tanggal'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/info/', self.admin_site.admin_view(self.info_view), name='gempanabire-info'),
            path('<int:pk>/kirim-sdg/', self.admin_site.admin_view(self.kirim_sdg_view), name='gempanabire-kirim-sdg'),
        ]
        return custom + urls

    @admin.display(description='Terasa')
    def terasa_display(self, obj):
        return 'Dirasakan' if obj.terasa else 'Tidak'

    @admin.display(description='Aksi')
    def action_buttons(self, obj):
        info_url  = reverse('gempa_admin:gempanabire-info', args=[obj.pk])
        edit_url  = reverse('gempa_admin:gempa_gempanabire_change', args=[obj.pk])
        del_url   = reverse('gempa_admin:gempa_gempanabire_delete', args=[obj.pk])
        hist_url  = reverse('gempa_admin:gempa_gempanabire_history', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Peta</a> '
            '<a class="button" href="{}">Commits</a> '
            '<a class="button" href="{}">Edit</a> '
            '<a class="button" href="{}" style="background:#ba2121;color:white;">Hapus</a>',
            info_url, hist_url, edit_url, del_url
        )

    def info_view(self, request, pk):
        from django.shortcuts import render
        obj = Gempanabire.objects.get(pk=pk)
        ctx = eq_datetime_context(obj.tanggal, obj.origin)
        
        import json
        # Compute all timezone times for client-side switching
        origin_clean = str(obj.origin)[:8]
        dt_utc = datetime.strptime(f"{obj.tanggal} {origin_clean}", "%Y-%m-%d %H:%M:%S")
        tz_data = {}
        for name, hours in [('WIB', 7), ('WITA', 8), ('WIT', 9)]:
            dt = dt_utc + timedelta(hours=hours)
            tz_data[name] = {
                'date': f"{dt.day:02d}-{BULAN_SINGKAT[dt.month]}-{str(dt.year)[-2:]}",
                'time': dt.strftime("%H:%M:%S"),
                'susulan': (dt + timedelta(minutes=30)).strftime("%H:%M"),
            }
        ctx.update({'event': obj, 'lat': format_lat(obj.lintang),
                    'lon': format_lon(obj.bujur), 'mag': round(float(obj.magnitudo), 1),
                    'latmap': obj.lintang, 'lonmap': obj.bujur,
                    'epic_map': gmt_image('NBPI', obj.tanggal, obj.origin),
                    'tz_data': tz_data,
                    'default_tz': 'WIT',
                    **self.buat_peta_context(obj)})
        return render(request, 'gempa/nabiretemplatebalai.html', ctx)

    def kirim_sdg_view(self, request, pk):
        obj = Gempanabire.objects.get(pk=pk)
        Satudatagempa.objects.create(
            tanggal=obj.tanggal, origin=obj.origin, lintang=obj.lintang,
            bujur=obj.bujur, magnitudo=obj.magnitudo, depth=obj.depth,
            ket=obj.ket or '.', sumber='BMKG-NBPI',
        )
        messages.success(request, "Gempa Nabire dikirim ke Satu Data Gempa.")
        return HttpResponseRedirect(reverse('gempa_admin:gempa_satudatagempa_changelist'))

# ── Satudatagempa ─────────────────────────────────────────────────────────────

@admin.register(Satudatagempa, site=gempa_admin_site)
class SatudatagempaAdmin(TopFilterMixin, ExportMixin, VersionAdmin):
    class Media:
        css = {"all": ("https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",)}
        js = (
            "https://cdn.jsdelivr.net/npm/flatpickr",
            "https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/id.js",
            "/static/js/flatpickr_init.js",
        )
    resource_class = SatudatagempaResource
    list_display = ('tanggal', 'origin', 'lintang', 'bujur_en', 'magnitudo_en',
                    'depth', 'ket', 'sumber', 'created_at')
    list_per_page = 10
    list_filter = ()
    search_fields = ('event_id', 'tanggal', 'ket', 'sumber')
    ordering = ('-tanggal', '-origin')
    date_hierarchy = 'tanggal'

# ── Gempanganjuk NGJ ──────────────────────────────────────────────────────────

@admin.register(Gempanganjuk, site=gempa_admin_site)
class GempanganjukAdmin(TopFilterMixin, ExportMixin, VersionAdmin):
    class Media:
        css = {"all": ("https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",)}
        js = (
            "https://cdn.jsdelivr.net/npm/flatpickr",
            "https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/id.js",
            "/static/js/flatpickr_init.js",
        )
    list_display = ('action_buttons', 'tanggal', 'origin', 'lintang', 'bujur_en', 'magnitudo_en',
                    'depth', 'ket', 'terasa_display', 'terdampak')
    list_per_page = 10
    list_filter = ()
    search_fields = ('event_id', 'tanggal', 'ket')
    ordering = ('-tanggal', '-origin')
    date_hierarchy = 'tanggal'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/kirim-sdg/', self.admin_site.admin_view(self.kirim_sdg_view), name='gempanganjuk-kirim-sdg'),
        ]
        return custom + urls

    @admin.display(description='Terasa')
    def terasa_display(self, obj):
        return 'Dirasakan' if obj.terasa else 'Tidak'

    @admin.display(description='Aksi')
    def action_buttons(self, obj):
        edit_url = reverse('gempa_admin:gempa_gempanganjuk_change', args=[obj.pk])
        del_url  = reverse('gempa_admin:gempa_gempanganjuk_delete', args=[obj.pk])
        hist_url = reverse('gempa_admin:gempa_gempanganjuk_history', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Commits</a> '
            '<a class="button" href="{}">Edit</a> '
            '<a class="button" href="{}" style="background:#ba2121;color:white;">Hapus</a>',
            hist_url, edit_url, del_url
        )

    def kirim_sdg_view(self, request, pk):
        obj = Gempanganjuk.objects.get(pk=pk)
        Satudatagempa.objects.create(
            tanggal=obj.tanggal, origin=obj.origin, lintang=obj.lintang,
            bujur=obj.bujur, magnitudo=obj.magnitudo, depth=obj.depth,
            ket=obj.ket or '.', sumber='BMKG-NGJ',
        )
        messages.success(request, "Gempa Nganjuk dikirim ke Satu Data Gempa.")
        return HttpResponseRedirect(reverse('gempa_admin:gempa_satudatagempa_changelist'))

# ── Gempa Signifikan ─────────────────────────────────────────────────────────

@admin.register(Significant, site=gempa_admin_site)
class SignificantAdmin(GmtMapMixin, TopFilterMixin, VersionAdmin):
    report_source = 'JAY'          # template significant memakai peta JAY

    def gmt_event_args(self, obj):
        """Significant menyimpan tanggal/jam sebagai teks, bukan date + origin."""
        BULAN_ID = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'Mei': 5, 'Jun': 6,
                    'Jul': 7, 'Agu': 8, 'Sep': 9, 'Okt': 10, 'Nov': 11, 'Des': 12}
        try:
            d, m, y = [x.strip() for x in str(obj.tanggal).split('-')]
            return f"20{y}-{BULAN_ID[m]:02d}-{int(d):02d}", obj.jam
        except Exception:
            return obj.tanggal, obj.jam

    class Media:
        css = {"all": ("https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css",)}
        js = (
            "/static/js/gempa_notify.js",
            "https://cdn.jsdelivr.net/npm/flatpickr",
            "https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/id.js",
            "/static/js/flatpickr_init.js",
        )
    list_display = ('action_buttons', 'tanggal', 'jam', 'lintang', 'bujur_en', 'magnitudo_en',
                    'depth', 'lokasi', 'dirasakan', 'created_at')
    list_per_page = 10
    search_fields = ('tanggal', 'lokasi', 'dirasakan')
    ordering = ('-created_at',)

    def get_queryset(self, request):
        return admin.ModelAdmin.get_queryset(self, request)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/template/', self.admin_site.admin_view(self.template_view), name='significant-template'),
        ]
        return custom + urls

    @admin.display(description='Aksi')
    def action_buttons(self, obj):
        tmpl_url = reverse('gempa_admin:significant-template', args=[obj.pk])
        edit_url = reverse('gempa_admin:gempa_significant_change', args=[obj.pk])
        del_url  = reverse('gempa_admin:gempa_significant_delete', args=[obj.pk])
        hist_url = reverse('gempa_admin:gempa_significant_history', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Peta</a> '
            '<a class="button" href="{}">Commits</a> '
            '<a class="button" href="{}">Edit</a> '
            '<a class="button" href="{}" style="background:#ba2121;color:white;">Hapus</a>',
            tmpl_url, hist_url, edit_url, del_url
        )

    def template_view(self, request, pk):
        from django.shortcuts import render
        obj = Significant.objects.get(pk=pk)
        BULAN_ID = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'Mei':5,'Jun':6,
                    'Jul':7,'Agu':8,'Sep':9,'Okt':10,'Nov':11,'Des':12}
        try:
            d, m, y = [x.strip() for x in obj.tanggal.split('-')]
            tanggal_iso = f"20{y}-{BULAN_ID[m]:02d}-{int(d):02d}"
        except Exception:
            tanggal_iso = obj.tanggal
        ctx = eq_datetime_context(tanggal_iso, obj.jam)
        ctx.update({
            'event': obj,
            'lat': format_lat(obj.lintang),
            'lon': format_lon(obj.bujur),
            'mag': round(float(obj.magnitudo), 1),
            'latmap': obj.lintang,
            'lonmap': obj.bujur,
            'epic_map': gmt_image('JAY', tanggal_iso, obj.jam),
            **self.buat_peta_context(obj),
        })
        return render(request, 'gempa/significanttemplate.html', ctx)

    def save_model(self, request, obj, form, change):
        if not obj.lokasi:
            obj.lokasi = nearest_city_description(obj.lintang, obj.bujur)
        admin.ModelAdmin.save_model(self, request, obj, form, change)

# ── City ──────────────────────────────────────────────────────────────────────

@admin.register(City, site=gempa_admin_site)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'latitude', 'longitude')
    search_fields = ('name',)

# ── Admin site branding ───────────────────────────────────────────────────────

# Branding (site_header/title/index_title) dipindah ke gempa/sites.py


from .models import FocalMechanism

@admin.register(FocalMechanism, site=gempa_admin_site)
class FocalMechanismAdmin(admin.ModelAdmin):
    list_display = ("source", "event_pk", "strike", "dip", "rake", "is_auto", "origin_label", "updated_at")
    list_filter = ("source", "is_auto")
    search_fields = ("origin_label", "source", "event_pk")
