from django.contrib import admin
from .models import AcademicYear, Term


class TermInline(admin.TabularInline):
    model = Term
    extra = 3


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_current"]
    list_filter = ["is_current"]
    inlines = [TermInline]


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ["__str__", "start_date", "end_date"]
    list_filter = ["academic_year", "name"]
