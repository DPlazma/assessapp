from django.urls import path
from . import views

app_name = "staff"

urlpatterns = [
    path("cover/", views.cover_class, name="cover_class"),
    path("cover/<int:cover_id>/end/", views.end_cover, name="end_cover"),
]
