from django.db import models


class ClassGroup(models.Model):
    """A class group (e.g. 'Class 3B')."""

    name = models.CharField(max_length=100)
    year_group = models.PositiveSmallIntegerField(
        blank=True, null=True, help_text="Year group number (e.g. 3)"
    )

    class Meta:
        ordering = ["year_group", "name"]

    def __str__(self):
        return self.name


class Student(models.Model):
    """A student at the school."""

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
