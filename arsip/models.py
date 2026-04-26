from django.db import models


class Album(models.Model):
    folder_name = models.CharField(max_length=255, unique=True)
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cover_photo = models.ForeignKey(
        'Foto', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+'
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def foto_count(self):
        return self.fotos.count()


VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.3gp', '.wmv', '.mts', '.m4v'}


class Foto(models.Model):
    album          = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='fotos')
    file_path      = models.CharField(max_length=512, unique=True)   # relative to MEDIA_ROOT
    thumbnail_path = models.CharField(max_length=512, blank=True)
    caption        = models.CharField(max_length=500, blank=True)
    taken_at       = models.DateTimeField(null=True, blank=True)
    file_size      = models.PositiveIntegerField(default=0)
    width          = models.PositiveIntegerField(default=0)
    height         = models.PositiveIntegerField(default=0)
    is_video       = models.BooleanField(default=False)
    imported_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['taken_at', 'file_path']

    def __str__(self):
        return self.file_path
