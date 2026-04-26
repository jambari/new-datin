from django.contrib import admin
from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display  = ('timestamp', 'username', 'action', 'description', 'path', 'ip_address')
    list_filter   = ('action', 'timestamp')
    search_fields = ('username', 'description', 'path', 'ip_address')
    readonly_fields = ('user', 'username', 'action', 'path', 'description', 'ip_address', 'timestamp')
    ordering      = ('-timestamp',)
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
