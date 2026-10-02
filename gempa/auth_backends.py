"""Login dengan email ATAU username.

Diport dari datin_django/gempa/auth_backends.py (.188). Di .188 operator
terbiasa mengetik alamat email (halaman login-nya memang berlabel "Email:" dan
memakai input type=email), jadi backend ini wajib ada — tanpa itu login dengan
angkasa@bmkg.go.id akan ditolak walaupun passwordnya benar.

Dipasang sebagai backend pertama, dengan ModelBackend standar sebagai cadangan:

    AUTHENTICATION_BACKENDS = [
        'gempa.auth_backends.EmailOrUsernameBackend',   # email dulu, lalu username
        'django.contrib.auth.backends.ModelBackend',    # stok Django
    ]

Catatan keamanan: autentikasi tetap menuntut password yang benar; backend ini
hanya memperluas cara menyebut identitas (email selain username). Pencarian
email case-insensitive; bila ada beberapa akun dengan email sama, dipilih id
terkecil (mengikuti perilaku .188).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

UserModel = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    """Cocokkan lewat email (case-insensitive) lebih dulu, lalu username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None:
            return None

        try:
            user = UserModel.objects.get(email__iexact=username)
        except UserModel.DoesNotExist:
            try:
                user = UserModel.objects.get(username=username)
            except UserModel.DoesNotExist:
                return None
        except UserModel.MultipleObjectsReturned:
            user = UserModel.objects.filter(email__iexact=username).order_by('id').first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
