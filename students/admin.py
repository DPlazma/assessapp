from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from .models import ClassGroup, Student, Subject


class StudentResource(resources.ModelResource):
    class Meta:
        model = Student
        import_id_fields = ["upn"]
        fields = (
            "first_name", "last_name", "upn", "date_of_birth",
            "pathway", "phase", "year_group", "class_group", "is_active",
        )


@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "year_group", "student_count"]
    list_filter = ["year_group"]
    search_fields = ["name"]

    def student_count(self, obj):
        return obj.students.count()

    student_count.short_description = "Students"


@admin.register(Student)
class StudentAdmin(ImportExportModelAdmin):
    resource_class = StudentResource
    list_display = [
        "last_name", "first_name", "pathway", "phase",
        "year_group", "class_group", "is_active",
    ]
    list_filter = ["pathway", "phase", "year_group", "class_group", "is_active"]
    search_fields = ["first_name", "last_name", "upn"]
    list_editable = ["is_active"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name", "order", "is_active"]
    list_editable = ["order", "is_active"]
    search_fields = ["name"]
