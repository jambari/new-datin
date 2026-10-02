from django.apps import AppConfig


class HujanConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hujan'

    def ready(self):
        # Kabar Telegram tiap ada data hujan baru (input manual).
        import hujan.signals  # noqa: F401
