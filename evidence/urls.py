from django.urls import path
from . import views

app_name = "evidence"

urlpatterns = [
    # EHCP targets
    path(
        "student/<int:student_pk>/ehcp/",
        views.ehcp_overview,
        name="ehcp_overview",
    ),
    path(
        "student/<int:student_pk>/ehcp/create/",
        views.ehcp_target_create,
        name="ehcp_target_create",
    ),
    path("ehcp/<int:pk>/", views.ehcp_target_detail, name="ehcp_target_detail"),
    path("ehcp/<int:pk>/edit/", views.ehcp_target_edit, name="ehcp_target_edit"),
    path(
        "ehcp/<int:pk>/review/",
        views.ehcp_target_review,
        name="ehcp_target_review",
    ),
    # Evidence
    path(
        "student/<int:student_pk>/gallery/",
        views.evidence_gallery,
        name="evidence_gallery",
    ),
    path(
        "student/<int:student_pk>/upload/",
        views.evidence_upload,
        name="evidence_upload",
    ),
    path("<int:pk>/", views.evidence_detail, name="evidence_detail"),
    path("<int:pk>/share/", views.evidence_toggle_share, name="evidence_toggle_share"),
    path("<int:pk>/delete/", views.evidence_delete, name="evidence_delete"),
    # Face blur
    path("<int:pk>/blur/", views.evidence_blur, name="evidence_blur"),
    path("<int:pk>/apply-blur/", views.evidence_apply_blur, name="evidence_apply_blur"),
    path("<int:pk>/detect-faces/", views.evidence_detect_faces_api, name="evidence_detect_faces"),
    # Manual blur brush
    path("<int:pk>/manual-blur/", views.evidence_manual_blur, name="evidence_manual_blur"),
    path("<int:pk>/apply-manual-blur/", views.evidence_apply_manual_blur, name="evidence_apply_manual_blur"),
    # Video blur region
    path("<int:pk>/video-blur/", views.video_blur_region, name="video_blur_region"),
    path("<int:pk>/video-apply-blur/", views.video_apply_blur_region, name="video_apply_blur_region"),
    # Video AI face blur
    path("<int:pk>/video-face-blur/", views.video_face_blur, name="video_face_blur"),
    path("<int:pk>/video-apply-face-blur/", views.video_apply_face_blur, name="video_apply_face_blur"),
    # Quick capture (no student pre-selected)
    path("quick-upload/", views.quick_evidence_upload, name="quick_evidence_upload"),
    path("<int:pk>/link-students/", views.evidence_link_students, name="evidence_link_students"),
    path("api/student/<int:student_pk>/ehcp-targets/", views.student_ehcp_targets_api, name="student_ehcp_targets_api"),
    # General evidence gallery
    path("gallery/", views.evidence_gallery_all, name="evidence_gallery_all"),
    # EHCP documents (OCR)
    path(
        "student/<int:student_pk>/ehcp/documents/",
        views.ehcp_document_list,
        name="ehcp_document_list",
    ),
    path(
        "student/<int:student_pk>/ehcp/documents/upload/",
        views.ehcp_document_upload,
        name="ehcp_document_upload",
    ),
    path("ehcp-doc/<int:pk>/", views.ehcp_document_view, name="ehcp_document_view"),
    path("ehcp-doc/<int:pk>/process/", views.ehcp_document_process, name="ehcp_document_process"),
    path("ehcp-doc/<int:pk>/delete/", views.ehcp_document_delete, name="ehcp_document_delete"),
    path("ehcp-doc/<int:pk>/extract/", views.ehcp_document_extract_targets, name="ehcp_document_extract"),
    path("ehcp-doc/<int:pk>/annotations/", views.ehcp_annotations_api, name="ehcp_annotations_api"),
    path("ehcp-doc/<int:pk>/export/", views.ehcp_document_export_pdf, name="ehcp_document_export"),
    path("ehcp-annotation/<int:pk>/delete/", views.ehcp_annotation_delete, name="ehcp_annotation_delete"),
    path("ehcp-annotation/<int:pk>/update/", views.ehcp_annotation_update, name="ehcp_annotation_update"),
    # Small Steps
    path("ehcp/<int:target_pk>/small-steps/", views.small_steps_manage, name="small_steps_manage"),
    path("small-step/<int:pk>/status/", views.small_step_update_status, name="small_step_update_status"),
    path("ehcp/<int:target_pk>/small-steps/panel/", views.small_steps_panel, name="small_steps_panel"),
    path("ehcp/<int:target_pk>/small-steps/add-inline/", views.small_step_add_inline, name="small_step_add_inline"),
    path("small-step/<int:pk>/delete-inline/", views.small_step_delete_inline, name="small_step_delete_inline"),
    path("small-step/<int:pk>/edit-inline/", views.small_step_edit_inline, name="small_step_edit_inline"),
    # MAPP
    path("student/<int:student_pk>/mapp/", views.mapp_overview, name="mapp_overview"),
    path("student/<int:student_pk>/mapp/create/", views.mapp_priority_create, name="mapp_priority_create"),
    path("mapp/<int:pk>/", views.mapp_priority_detail, name="mapp_priority_detail"),
    path("mapp/<int:pk>/delete/", views.mapp_priority_delete, name="mapp_priority_delete"),
    # Interventions
    path("student/<int:student_pk>/interventions/", views.intervention_list, name="intervention_list"),
    path("student/<int:student_pk>/interventions/enrol/", views.intervention_enrol, name="intervention_enrol"),
    path("intervention/<int:pk>/", views.intervention_detail, name="intervention_detail"),
    path("intervention/<int:pk>/delete/", views.intervention_delete, name="intervention_delete"),
]
