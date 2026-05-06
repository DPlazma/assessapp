from django.urls import path
from . import views

app_name = "assessments"

urlpatterns = [
    # ── Frameworks hub ──
    path("frameworks/", views.framework_hub, name="framework_hub"),
    path("frameworks/<int:framework_id>/", views.framework_detail, name="framework_detail"),
    path("frameworks/<int:framework_id>/assign/", views.framework_assign, name="framework_assign"),
    path("frameworks/assignment/<int:assignment_id>/remove/", views.framework_unassign, name="framework_unassign"),
    path("frameworks/mapp-configure/", views.mapp_configure, name="mapp_configure"),
    path("frameworks/<int:framework_id>/personalise/<int:student_id>/", views.personalise_framework, name="personalise_framework"),

    # Subject lead: see all students across school for your subjects
    path("my-subjects/", views.my_subjects, name="my_subjects"),
    # Individual student assessment: select subject → see statements → mark
    path(
        "student/<int:student_id>/",
        views.student_subjects,
        name="student_subjects",
    ),
    path(
        "student/<int:student_id>/subject/<int:subject_id>/",
        views.assess_student,
        name="assess_student",
    ),
    # HTMX endpoint: AI next-step suggestions for a student + subject
    path(
        "student/<int:student_id>/subject/<int:subject_id>/ai-next-steps/",
        views.ai_next_steps,
        name="ai_next_steps",
    ),
    # Save AI-generated suggestions as EHCP targets + small steps
    path(
        "student/<int:student_id>/subject/<int:subject_id>/ai-save/",
        views.ai_save_suggestions,
        name="ai_save_suggestions",
    ),
    # HTMX endpoint: record a single assessment
    path(
        "record/<int:student_id>/<int:statement_id>/",
        views.record_assessment,
        name="record_assessment",
    ),
    # Bulk mode: select a statement → mark all students in class
    path(
        "bulk/<int:class_id>/<int:statement_id>/",
        views.bulk_assess,
        name="bulk_assess",
    ),
    # Statement management (for subject leads)
    path("statements/", views.manage_statements, name="manage_statements"),
    # Framework CRUD
    path("statements/framework/add/", views.create_framework, name="create_framework"),
    path("statements/framework/<int:framework_id>/edit/", views.edit_framework, name="edit_framework"),
    path("statements/framework/<int:framework_id>/delete/", views.delete_framework, name="delete_framework"),
    # Area CRUD
    path("statements/framework/<int:framework_id>/area/add/", views.create_area, name="create_area"),
    path("statements/area/<int:area_id>/edit/", views.edit_area, name="edit_area"),
    path("statements/area/<int:area_id>/delete/", views.delete_area, name="delete_area"),
    # Sub-area (level) management within an area
    path("statements/area/<int:area_id>/levels/", views.manage_sub_areas, name="manage_sub_areas"),
    # Statements within an area
    path(
        "statements/area/<int:area_id>/statements/",
        views.edit_area_statements,
        name="edit_area_statements",
    ),
    # CSV import
    path("import/", views.import_statements_view, name="import_statements"),
    # Snapshot
    path("snapshot/create/", views.create_snapshot, name="create_snapshot"),
    # Class progress
    path("class/<int:class_id>/progress/", views.class_progress, name="class_progress"),
    path("class/<int:class_id>/progress/export/excel/", views.class_progress_export_excel, name="class_progress_export_excel"),
    path("class/<int:class_id>/progress/export/pdf/", views.class_progress_export_pdf, name="class_progress_export_pdf"),
    # Whole-school progress (SLT / subject leads)
    path("school/progress/", views.school_progress, name="school_progress"),
    path("school/progress/export/excel/", views.school_progress_export_excel, name="school_progress_export_excel"),
    path("school/progress/export/pdf/", views.school_progress_export_pdf, name="school_progress_export_pdf"),
]
