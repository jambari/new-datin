from django.contrib import admin

from .models import Berita


@admin.register(Berita)
class BeritaAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'status', 'published_at', 'views', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'excerpt', 'content')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('views', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    list_per_page = 25
