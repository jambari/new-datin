from django.db import models
from django.contrib.auth.models import User


class ActivityLog(models.Model):
    LOGIN  = 'LOGIN'
    LOGOUT = 'LOGOUT'
    ACTION = 'ACTION'
    ACTION_CHOICES = [
        (LOGIN,  'Login'),
        (LOGOUT, 'Logout'),
        (ACTION, 'Action'),
    ]

    user        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    username    = models.CharField(max_length=150)          # kept even after user deletion
    action      = models.CharField(max_length=10, choices=ACTION_CHOICES, db_index=True)
    path        = models.CharField(max_length=500, blank=True)
    description = models.CharField(max_length=500, blank=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    timestamp   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.username} — {self.get_action_display()} {self.description}"
