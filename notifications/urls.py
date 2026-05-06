from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("unread-count/", views.unread_count, name="unread_count"),
    path("mark-all-read/", views.mark_all_read, name="mark_all_read"),
    path("<int:pk>/read/", views.mark_read, name="mark_read"),
    path("<int:pk>/dismiss/", views.dismiss, name="dismiss"),
]
