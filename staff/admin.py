from django.contrib import admin
from .models import StaffProfile, ClassAssignment, ClassCover, SubjectLead


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "role"]
    list_filter = ["role"]
    search_fields = ["user__first_name", "user__last_name", "user__username"]


@admin.register(ClassAssignment)
class ClassAssignmentAdmin(admin.ModelAdmin):
    list_display = ["user", "class_group"]
    list_filter = ["class_group"]
    search_fields = ["user__first_name", "user__last_name"]


@admin.register(ClassCover)
class ClassCoverAdmin(admin.ModelAdmin):
    list_display = ["user", "class_group", "start_date", "end_date", "is_active"]
    list_filter = ["class_group", "start_date"]
    search_fields = ["user__first_name", "user__last_name"]


@admin.register(SubjectLead)
class SubjectLeadAdmin(admin.ModelAdmin):
    list_display = ["user", "subject"]
    list_filter = ["subject"]
    search_fields = ["user__first_name", "user__last_name"]
