from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_index, name="index"),
    path("cohort/", views.cohort_report, name="cohort_report"),
    path("cohort/update-cell/", views.cohort_update_cell, name="cohort_update_cell"),
    path("subject-progress/", views.subject_progress, name="subject_progress"),
    path("cohort/export/", views.cohort_export_excel, name="cohort_export_excel"),
    path("subject-progress/export/", views.subject_progress_export_excel, name="subject_progress_export_excel"),
    path("cohort/pdf/", views.cohort_export_pdf, name="cohort_export_pdf"),
    path("subject-progress/pdf/", views.subject_progress_export_pdf, name="subject_progress_export_pdf"),
]
