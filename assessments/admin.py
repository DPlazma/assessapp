from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from .models import (
    AssessmentFramework,
    AssessmentArea,
    SubArea,
    AssessmentStatement,
    AssessmentRecord,
    AssessmentSnapshot,
    FrameworkAssignment,
    PersonalisedFramework,
)


class SubAreaInline(admin.TabularInline):
    model = SubArea
    extra = 1
    fields = ["name", "order"]


class AssessmentStatementInline(admin.TabularInline):
    model = AssessmentStatement
    extra = 3
    fields = ["sub_area", "statement_text", "order"]


class StatementResource(resources.ModelResource):
    class Meta:
        model = AssessmentStatement
        fields = ("id", "area", "statement_text", "order")


@admin.register(AssessmentFramework)
class AssessmentFrameworkAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "area_count"]
    list_filter = ["is_active"]

    def area_count(self, obj):
        return obj.areas.count()

    area_count.short_description = "Areas"


@admin.register(AssessmentArea)
class AssessmentAreaAdmin(admin.ModelAdmin):
    list_display = ["name", "framework", "subject", "year_group", "phase", "statement_count"]
    list_filter = ["framework", "subject", "year_group", "phase"]
    search_fields = ["name"]
    inlines = [SubAreaInline, AssessmentStatementInline]

    def statement_count(self, obj):
        return obj.statements.count()

    statement_count.short_description = "Statements"


@admin.register(AssessmentStatement)
class AssessmentStatementAdmin(ImportExportModelAdmin):
    resource_class = StatementResource
    list_display = ["truncated_text", "area", "sub_area", "order"]
    list_filter = ["area__framework", "area__subject", "sub_area"]
    search_fields = ["statement_text"]
    list_editable = ["order"]

    def truncated_text(self, obj):
        return str(obj)

    truncated_text.short_description = "Statement"


@admin.register(AssessmentRecord)
class AssessmentRecordAdmin(admin.ModelAdmin):
    list_display = ["student", "statement_preview", "status", "assessed_by", "assessed_date"]
    list_filter = ["status", "assessed_date", "statement__area__subject"]
    search_fields = ["student__first_name", "student__last_name"]
    date_hierarchy = "assessed_date"
    raw_id_fields = ["student", "statement"]

    def statement_preview(self, obj):
        text = obj.statement.statement_text
        return text[:60] + "..." if len(text) > 60 else text

    statement_preview.short_description = "Statement"


@admin.register(AssessmentSnapshot)
class AssessmentSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "student", "area", "term", "secure_count",
        "developing_count", "emerging_count", "snapshot_date",
    ]
    list_filter = ["term", "area__subject"]
    search_fields = ["student__first_name", "student__last_name"]


@admin.register(FrameworkAssignment)
class FrameworkAssignmentAdmin(admin.ModelAdmin):
    list_display = ["framework", "class_group", "student", "assigned_by", "created_at"]
    list_filter = ["framework"]
    raw_id_fields = ["student"]


@admin.register(PersonalisedFramework)
class PersonalisedFrameworkAdmin(admin.ModelAdmin):
    list_display = ["student", "framework", "statement_count", "updated_at"]
    list_filter = ["framework"]
    raw_id_fields = ["student"]
    filter_horizontal = ["statements"]

    def statement_count(self, obj):
        return obj.statements.count()

    statement_count.short_description = "Selected"
