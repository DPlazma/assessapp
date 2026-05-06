from django.contrib import admin
from .models import (
    EHCPAnnotation, EHCPDocument, EHCPOutcome, EHCPTarget, EHCPTargetReview,
    Evidence, EvidenceStudentLink,
    InterventionEnrolment, InterventionProgram, InterventionReview, InterventionSession,
    MAPPConfig, MAPPDimensionConfig, MAPPDimensionScore, MAPPLearningPriority,
    SmallStep,
)


@admin.register(EHCPOutcome)
class EHCPOutcomeAdmin(admin.ModelAdmin):
    list_display = ["name", "order"]
    list_editable = ["order"]


class EHCPTargetReviewInline(admin.TabularInline):
    model = EHCPTargetReview
    extra = 0
    readonly_fields = ["created_at"]


@admin.register(EHCPTarget)
class EHCPTargetAdmin(admin.ModelAdmin):
    list_display = ["student", "title_short", "outcome", "status", "set_date", "review_date"]
    list_filter = ["status", "outcome"]
    search_fields = ["title", "student__first_name", "student__last_name"]
    raw_id_fields = ["student"]
    inlines = [EHCPTargetReviewInline]

    def title_short(self, obj):
        return obj.title[:60] + ("..." if len(obj.title) > 60 else "")

    title_short.short_description = "Title"


class EvidenceStudentLinkInline(admin.TabularInline):
    model = EvidenceStudentLink
    extra = 0
    raw_id_fields = ["student", "ehcp_target"]


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ["evidence_type", "title", "captured_date", "is_shared_with_family"]
    list_filter = ["evidence_type", "is_shared_with_family"]
    search_fields = ["title"]
    inlines = [EvidenceStudentLinkInline]


@admin.register(EHCPDocument)
class EHCPDocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "student", "processing_status", "page_count", "created_at"]
    list_filter = ["processing_status"]
    search_fields = ["title", "original_filename", "student__first_name", "student__last_name"]
    raw_id_fields = ["student"]


@admin.register(EHCPAnnotation)
class EHCPAnnotationAdmin(admin.ModelAdmin):
    list_display = ["document", "annotation_type", "page", "color", "created_by", "created_at"]
    list_filter = ["annotation_type"]
    raw_id_fields = ["document"]


class SmallStepInline(admin.TabularInline):
    model = SmallStep
    extra = 0


@admin.register(SmallStep)
class SmallStepAdmin(admin.ModelAdmin):
    list_display = ["target", "letter", "description_short", "status", "status_date"]
    list_filter = ["status"]
    raw_id_fields = ["target"]

    def description_short(self, obj):
        return obj.description[:60] + ("..." if len(obj.description) > 60 else "")
    description_short.short_description = "Description"


class MAPPDimensionScoreInline(admin.TabularInline):
    model = MAPPDimensionScore
    extra = 0


@admin.register(MAPPLearningPriority)
class MAPPLearningPriorityAdmin(admin.ModelAdmin):
    list_display = ["student", "title_short", "academic_year", "term", "ehcp_year"]
    list_filter = ["academic_year", "term"]
    raw_id_fields = ["student", "ehcp_target"]
    inlines = [MAPPDimensionScoreInline]

    def title_short(self, obj):
        return obj.title[:60] + ("..." if len(obj.title) > 60 else "")
    title_short.short_description = "Title"


# ── MAPP Config ─────────────────────────────────────────────────────

class MAPPDimensionConfigInline(admin.TabularInline):
    model = MAPPDimensionConfig
    extra = 1


@admin.register(MAPPConfig)
class MAPPConfigAdmin(admin.ModelAdmin):
    list_display = ["name", "scale_min", "scale_max", "is_active"]
    list_filter = ["is_active"]
    inlines = [MAPPDimensionConfigInline]


# ── Interventions ───────────────────────────────────────────────────

@admin.register(InterventionProgram)
class InterventionProgramAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "default_frequency", "default_duration_mins", "is_active"]
    list_filter = ["category", "is_active"]
    list_editable = ["is_active"]


class InterventionSessionInline(admin.TabularInline):
    model = InterventionSession
    extra = 0
    readonly_fields = ["created_at"]


class InterventionReviewInline(admin.TabularInline):
    model = InterventionReview
    extra = 0
    readonly_fields = ["created_at"]


@admin.register(InterventionEnrolment)
class InterventionEnrolmentAdmin(admin.ModelAdmin):
    list_display = ["student", "program", "status", "start_date", "end_date", "delivered_by"]
    list_filter = ["status", "program"]
    raw_id_fields = ["student", "ehcp_target"]
    inlines = [InterventionSessionInline, InterventionReviewInline]
