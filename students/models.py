from django.db import models
from django.conf import settings


PATHWAY_CHOICES = [
    ("PREP", "Preparations"),
    ("EXP", "Explorers"),
    ("FUT", "Futures"),
    ("HOR", "Horizons"),
]

PHASE_CHOICES = [
    (1, "Phase 1"),
    (2, "Phase 2"),
]


class ClassGroup(models.Model):
    """A class group (e.g. 'Class 3B')."""

    name = models.CharField(max_length=100)
    year_group = models.PositiveSmallIntegerField(
        blank=True, null=True, help_text="Year group number (e.g. 3)"
    )
    pathway = models.CharField(
        max_length=4, choices=PATHWAY_CHOICES, blank=True,
        help_text="West Gate pathway / house this class belongs to.",
    )
    phase = models.PositiveSmallIntegerField(
        choices=PHASE_CHOICES, blank=True, null=True,
        help_text="Only used for the Preparations pathway (Phase 1 or 2).",
    )

    class Meta:
        ordering = ["year_group", "name"]

    def __str__(self):
        return self.name

    @property
    def pathway_label(self):
        """Display label like 'Preparations · Phase 2' or 'Explorers'."""
        if not self.pathway:
            return ""
        label = self.get_pathway_display()
        if self.pathway == "PREP" and self.phase:
            label += f" · Phase {self.phase}"
        return label

class StudentGroup(models.Model):
    """A teacher-defined custom group of students.

    Unlike a ClassGroup, a StudentGroup can contain any students across the
    school. It gives teachers a class-style progress view for an arbitrary
    cohort. Groups are private to their owner unless marked as shared.
    """

    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_groups",
    )
    students = models.ManyToManyField(
        "Student",
        related_name="custom_groups",
        blank=True,
    )
    is_shared = models.BooleanField(
        default=False,
        help_text="If on, all staff can view this group.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def visible_to(self, user):
        """Whether ``user`` may view this group."""
        return self.is_shared or self.owner_id == getattr(user, "pk", None)

    def editable_by(self, user):
        """Whether ``user`` may edit/delete this group."""
        return self.owner_id == getattr(user, "pk", None) or getattr(
            user, "is_superuser", False
        )

class Student(models.Model):
    """A student at the school."""

    PATHWAY_CHOICES = PATHWAY_CHOICES
    PHASE_CHOICES = PHASE_CHOICES

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    upn = models.CharField(
        "UPN", max_length=13, blank=True, unique=True, null=True,
        help_text="Unique Pupil Number"
    )
    date_of_birth = models.DateField(blank=True, null=True)
    pathway = models.CharField(max_length=4, choices=PATHWAY_CHOICES, default="PREP")
    phase = models.PositiveSmallIntegerField(choices=PHASE_CHOICES, default=1)
    year_group = models.PositiveSmallIntegerField(
        blank=True, null=True, help_text="Current year group"
    )
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        # Keep student.pathway / phase in sync with their class group so
        # existing per-pathway subject filters keep working.
        if self.class_group_id:
            cg = self.class_group
            if cg.pathway:
                self.pathway = cg.pathway
            if cg.phase:
                self.phase = cg.phase
        super().save(*args, **kwargs)


class Subject(models.Model):
    """A taught subject (e.g. English, Mathematics)."""

    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=20, blank=True)
    applicable_pathways = models.JSONField(
        default=list,
        blank=True,
        help_text='List of pathway codes, e.g. ["PREP", "FUT"]',
    )
    applicable_phases = models.JSONField(
        default=list,
        blank=True,
        help_text="List of phase numbers, e.g. [1, 2]",
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name
