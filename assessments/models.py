from django.db import models
from django.conf import settings
from students.models import ClassGroup, Student, Subject
from core.models import Term


class AssessmentFramework(models.Model):
    """A framework for assessment (e.g. National Curriculum, Small Steps, EHCP, MAPP)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class FrameworkAssignment(models.Model):
    """Assigns a framework to a class group or individual student."""

    framework = models.ForeignKey(
        AssessmentFramework, on_delete=models.CASCADE, related_name="assignments"
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE,
        null=True, blank=True, related_name="framework_assignments",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        null=True, blank=True, related_name="framework_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(class_group__isnull=False, student__isnull=True)
                    | models.Q(class_group__isnull=True, student__isnull=False)
                ),
                name="assignment_target_required",
            ),
        ]

    def __str__(self):
        target = self.class_group or self.student
        return f"{self.framework.name} → {target}"


class PersonalisedFramework(models.Model):
    """Per-student statement selection within a framework.

    When a framework is assigned to a student (directly or via class),
    the teacher can pick which statements are relevant to that individual.
    If no PersonalisedFramework row exists the student sees ALL statements
    (backward-compatible default).
    """

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="personalised_frameworks"
    )
    framework = models.ForeignKey(
        AssessmentFramework, on_delete=models.CASCADE, related_name="personalisations"
    )
    statements = models.ManyToManyField(
        "AssessmentStatement", blank=True, related_name="personalisations"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "framework")
        ordering = ["student", "framework"]

    def __str__(self):
        return f"{self.student} — {self.framework.name} personalisation"


class AssessmentArea(models.Model):
    """An area within a framework+subject (e.g. 'Reading — Year 3')."""

    framework = models.ForeignKey(
        AssessmentFramework, on_delete=models.CASCADE, related_name="areas"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="assessment_areas"
    )
    name = models.CharField(max_length=200, help_text="e.g. 'Reading — Year 3'")
    year_group = models.PositiveSmallIntegerField(
        blank=True, null=True, help_text="Applicable year group"
    )
    phase = models.PositiveSmallIntegerField(
        blank=True, null=True, help_text="Applicable phase (1 or 2)"
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["subject", "order", "name"]

    def __str__(self):
        return f"{self.name} ({self.framework})"


class SubArea(models.Model):
    """A level/sub-area within an assessment area (e.g. 'Foundation', 'Level 1')."""

    area = models.ForeignKey(
        AssessmentArea, on_delete=models.CASCADE, related_name="sub_areas"
    )
    name = models.CharField(max_length=200, help_text="e.g. 'Foundation', 'Level 1'")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["area", "order", "name"]

    def __str__(self):
        return f"{self.name} ({self.area.name})"


class AssessmentStatement(models.Model):
    """An individual statement to assess against (e.g. 'I can link what I read to my experiences')."""

    area = models.ForeignKey(
        AssessmentArea, on_delete=models.CASCADE, related_name="statements"
    )
    sub_area = models.ForeignKey(
        SubArea, on_delete=models.CASCADE, null=True, blank=True,
        related_name="statements",
        help_text="Optional level within the area",
    )
    statement_text = models.TextField()
    order = models.PositiveIntegerField(default=0, help_text="Display order within the area")

    class Meta:
        ordering = ["area", "order"]

    def __str__(self):
        truncated = (
            self.statement_text[:80] + "..."
            if len(self.statement_text) > 80
            else self.statement_text
        )
        return truncated


class AssessmentRecord(models.Model):
    """A single assessment entry: student + statement + status."""

    STATUS_CHOICES = [
        ("NYA", "Not Yet Assessed"),
        ("EME", "Emerging"),
        ("DEV", "Developing"),
        ("SEC", "Secure"),
    ]

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="assessment_records"
    )
    statement = models.ForeignKey(
        AssessmentStatement, on_delete=models.CASCADE, related_name="records"
    )
    status = models.CharField(max_length=3, choices=STATUS_CHOICES, default="NYA")
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assessments_made",
    )
    assessed_date = models.DateField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assessed_date", "-created_at"]

    def __str__(self):
        return f"{self.student} — {self.get_status_display()} — {self.statement}"


class AssessmentSnapshot(models.Model):
    """Termly snapshot of a student's assessment status per area."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="snapshots"
    )
    area = models.ForeignKey(
        AssessmentArea, on_delete=models.CASCADE, related_name="snapshots"
    )
    term = models.ForeignKey(
        Term, on_delete=models.CASCADE, related_name="snapshots"
    )
    # Counts at time of snapshot
    total_statements = models.PositiveIntegerField(default=0)
    secure_count = models.PositiveIntegerField(default=0)
    developing_count = models.PositiveIntegerField(default=0)
    emerging_count = models.PositiveIntegerField(default=0)
    not_assessed_count = models.PositiveIntegerField(default=0)
    snapshot_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["student", "area", "term"]
        ordering = ["student", "area", "term"]

    def __str__(self):
        return f"{self.student} — {self.area} — {self.term}"

    @property
    def secure_percentage(self):
        if self.total_statements == 0:
            return 0
        return round((self.secure_count / self.total_statements) * 100)
