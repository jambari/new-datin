"""Admin site terpisah untuk katalog gempa (cermin /gempa-admin/ di .188).

Kenapa AdminSite sendiri, bukan `admin.site`:

1. `datin_project/urls.py` mengubah `admin.site` menjadi `OTPAdminSite`, sehingga
   siapa pun yang membuka /admin/ wajib menyiapkan perangkat OTP. Operator
   katalog gempa tidak boleh dipaksa begitu — mereka cukup login username/email
   + password di /gempa-admin/.
2. Terpisah berarti halaman admin yang sudah ada (/admin/ dengan OTP, dashboard,
   dsb.) sama sekali tidak berubah.
3. Model katalog hanya didaftarkan di site ini, jadi daftar model di /admin/
   tidak bertambah.
"""
from django.contrib.admin import AdminSite


class GempaAdminSite(AdminSite):
    """Admin katalog gempa: login biasa (tanpa OTP), hanya model katalog."""

    site_header = 'Welcome To Mobel Lejen'
    site_title = 'Welcome To Mobel Lejen'
    index_title = 'Welcome To Mobel Lejen'

    # Template login kustom (label "Email:", input type=email). Diletakkan di
    # namespace sendiri supaya tidak menimpa halaman login /admin/ yang ada.
    login_template = 'admin/gempa/login.html'


gempa_admin_site = GempaAdminSite(name='gempa_admin')
