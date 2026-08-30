from django import forms

from .models import ManajemenSukuCadang, Peminjaman, Peralatan, PeralatanSukuCadang


KOTA_TUJUAN_CHOICES = [
    ("Boven Digoel", "Boven Digoel"),
    ("Kabupaten Jayapura", "Kabupaten Jayapura"),
    ("Kabupaten Keerom", "Kabupaten Keerom"),
    ("Kabupaten Mimika", "Kabupaten Mimika"),
    ("Kota Jayapura", "Kota Jayapura"),
    ("Lainnya", "Lainnya"),
    ("Merauke", "Merauke"),
]


class BaseStyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        common_class = (
            "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 "
            "text-sm text-gray-900 focus:border-indigo-500 focus:outline-none "
            "focus:ring-2 focus:ring-indigo-200"
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({"class": "h-4 w-4 rounded border-gray-300 text-indigo-600"})
            elif isinstance(field.widget, forms.CheckboxSelectMultiple):
                # CheckboxSelectMultiple dirender sebagai daftar checkbox,
                # jadi jangan diberi class input/select penuh.
                field.widget.attrs.pop("class", None)
            elif isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs.update({"class": common_class, "size": 6})
            else:
                field.widget.attrs.update({"class": common_class})


class PeralatanForm(BaseStyledFormMixin, forms.ModelForm):
    class Meta:
        model = Peralatan
        fields = ["nama_alat", "status"]


class PeminjamanForm(BaseStyledFormMixin, forms.ModelForm):
    peralatan_choices = forms.ModelMultipleChoiceField(
        queryset=Peralatan.objects.none(),
        label="Nama Alat",
        required=True,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Peminjaman
        fields = ["tanggal_peminjaman", "surat_tugas", "peralatan_choices", "status", "keterangan"]
        widgets = {
            "tanggal_peminjaman": forms.DateInput(attrs={"type": "date"}),
            "keterangan": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "tanggal_peminjaman": "Tanggal Peminjaman",
            "surat_tugas": "No. ST",
            "status": "Status",
            "keterangan": "Keterangan",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pastikan selalu menggunakan widget checklist untuk multi-pilih.
        self.fields["peralatan_choices"].widget = forms.CheckboxSelectMultiple()
        queryset = Peralatan.objects.all().order_by("created_at", "id")
        self.fields["peralatan_choices"].queryset = queryset
        self.peralatan_options = queryset

        if self.instance and self.instance.pk:
            self.initial["peralatan_choices"] = self.instance.get_peralatan_ids()

        selected_ids = []
        if self.is_bound:
            selected_ids = self.data.getlist("peralatan_choices")
        elif self.instance and self.instance.pk:
            selected_ids = [str(item_id) for item_id in self.instance.get_peralatan_ids()]
        self.peralatan_selected_ids = set(selected_ids)

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected_peralatan = self.cleaned_data.get("peralatan_choices")
        instance.peralatan = [item.id for item in selected_peralatan] if selected_peralatan else []

        if commit:
            instance.save()
        return instance


class LaporanPMUploadForm(BaseStyledFormMixin, forms.Form):
    tahun = forms.TypedChoiceField(
        choices=[],
        coerce=int,
        label="Tahun",
        required=True,
    )
    kota_tujuan = forms.ChoiceField(
        choices=KOTA_TUJUAN_CHOICES,
        label="Kota Tujuan",
        required=True,
    )
    dokumen = forms.FileField(
        label="Dokumen",
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tahun"].choices = [(year, year) for year in range(2026, 2036)]


class PeralatanSukuCadangForm(BaseStyledFormMixin, forms.ModelForm):
    class Meta:
        model = PeralatanSukuCadang
        fields = ["jenis_alat"]
        labels = {
            "jenis_alat": "Jenis Alat",
        }


class ManajemenSukuCadangForm(BaseStyledFormMixin, forms.ModelForm):
    class Meta:
        model = ManajemenSukuCadang
        fields = [
            "tanggal_masuk",
            "jenis",
            "merk",
            "serial_number",
            "jumlah",
            "status",
            "keterangan",
        ]
        widgets = {
            "tanggal_masuk": forms.DateInput(attrs={"type": "date"}),
            "keterangan": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "tanggal_masuk": "Tanggal Masuk",
            "jenis": "Jenis",
            "merk": "Merk",
            "serial_number": "Serial Number",
            "jumlah": "Jumlah",
            "status": "Status",
            "keterangan": "Keterangan",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["jenis"].queryset = PeralatanSukuCadang.objects.all().order_by("jenis_alat")
        self.fields["jenis"].empty_label = "Pilih jenis alat"


class UnduhDataForm(BaseStyledFormMixin, forms.Form):
    tanggal_mulai = forms.DateField(
        label="Tanggal Awal",
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    tanggal_selesai = forms.DateField(
        label="Tanggal Akhir",
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    format = forms.ChoiceField(
        label="Format",
        choices=[("excel", "Excel"), ("pdf", "PDF")],
        required=True,
    )

    def clean(self):
        cleaned_data = super().clean()
        tanggal_mulai = cleaned_data.get("tanggal_mulai")
        tanggal_selesai = cleaned_data.get("tanggal_selesai")
        if tanggal_mulai and tanggal_selesai and tanggal_mulai > tanggal_selesai:
            raise forms.ValidationError("Tanggal awal tidak boleh lebih besar dari tanggal akhir.")
        return cleaned_data
