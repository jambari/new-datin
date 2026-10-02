from django.apps import AppConfig


class MagnetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'magnet'

    def ready(self):
        # Kabar Telegram tiap ada observasi absolut Bartington baru.
        import magnet.signals  # noqa: F401
