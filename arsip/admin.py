from django.contrib import admin
from .models import Album, Foto


class FotoInline(admin.TabularInline):
    model = Foto
    fields = ('file_path', 'thumbnail_path', 'caption', 'taken_at', 'file_size')
    readonly_fields = ('file_path', 'thumbnail_path', 'taken_at', 'file_size')
    extra = 0
    can_delete = False


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display  = ('name', 'folder_name', 'foto_count', 'created_at')
    search_fields = ('name', 'folder_name')
    fields        = ('folder_name', 'name', 'description', 'cover_photo')
    inlines       = [FotoInline]

    def foto_count(self, obj):
        return obj.foto_count()
    foto_count.short_description = 'Foto'


@admin.register(Foto)
class FotoAdmin(admin.ModelAdmin):
    list_display  = ('file_path', 'album', 'taken_at', 'file_size')
    list_filter   = ('album',)
    search_fields = ('file_path', 'caption')
    readonly_fields = ('file_path', 'thumbnail_path', 'taken_at', 'file_size', 'width', 'height', 'imported_at')
