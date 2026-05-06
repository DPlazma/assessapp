from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "recipient", "category", "priority", "is_read", "created_at"]
    list_filter = ["category", "priority", "is_read", "is_dismissed"]
    search_fields = ["title", "message", "recipient__username"]
    raw_id_fields = ["recipient"]
