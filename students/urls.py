from django.urls import path
from . import views

app_name = "students"

urlpatterns = [
    path("<int:pk>/", views.student_detail, name="detail"),
    path("<int:pk>/progress/", views.student_progress, name="progress"),
    path("<int:pk>/progress/ai-summary/", views.generate_ai_summary, name="ai_summary"),
    path("<int:pk>/progress/ai-patterns/", views.ai_detect_patterns, name="ai_patterns"),
    path("<int:pk>/journey/", views.learning_journey, name="learning_journey"),
    path("<int:pk>/journey/pdf/", views.learning_journey_pdf, name="learning_journey_pdf"),
]
