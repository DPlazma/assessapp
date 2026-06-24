from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("search/", views.search_global, name="search"),
    path("dashboard/save-layout/", views.save_widget_layout, name="save_widget_layout"),
    path("dashboard/toggle-widget/", views.toggle_widget, name="toggle_widget"),
    path("dashboard/resize-widget/", views.resize_widget, name="resize_widget"),
    path("dashboard/reset-layout/", views.reset_widget_layout, name="reset_widget_layout"),
    path("insights/class/<int:class_id>/", views.class_insight_generate, name="class_insight"),
    path("setup/", views.setup_hub, name="setup_hub"),
    path("setup/classes/", views.classes_manage, name="classes_manage"),
    path("setup/subjects/", views.subjects_manage, name="subjects_manage"),
    path("setup/users/", views.users_manage, name="users_manage"),
    path("setup/academic-years/", views.academic_year_setup, name="academic_year_setup"),
    path("setup/academic-years/add/", views.create_academic_year, name="create_academic_year"),
    path("setup/academic-years/<int:pk>/edit/", views.edit_academic_year, name="edit_academic_year"),
    path("setup/academic-years/<int:pk>/delete/", views.delete_academic_year, name="delete_academic_year"),
    path("setup/academic-years/sync-arbor/", views.sync_academic_years_from_arbor, name="sync_academic_years_from_arbor"),
    path("setup/ai/", views.ai_settings, name="ai_settings"),
    path("setup/ai/test/", views.ai_test_connection, name="ai_test_connection"),

    # Arbor integration
    path("setup/arbor/", views.arbor_settings, name="arbor_settings"),
    path("setup/arbor/test/", views.arbor_test_connection, name="arbor_test_connection"),
    path("setup/arbor/discover/", views.arbor_discover, name="arbor_discover"),
    path("setup/arbor/save-mappings/", views.arbor_save_mappings, name="arbor_save_mappings"),
    path("setup/arbor/sync/", views.arbor_sync, name="arbor_sync"),
    path("setup/arbor/sync/run/", views.arbor_run_sync, name="arbor_run_sync"),
    path("setup/arbor/import/", views.arbor_import_preview, name="arbor_import_preview"),
    path("setup/arbor/import/run/", views.arbor_import_run, name="arbor_import_run"),
]
