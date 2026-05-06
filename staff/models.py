from django.db import models
from django.conf import settings
from students.models import ClassGroup, Subject


class StaffProfile(models.Model):
    """Extended profile for staff users."""

    ROLE_CHOICES = [
        ("teacher", "Teacher"),
        ("ta", "Teaching Assistant"),
        ("hlta", "HLTA"),
        ("subject_lead", "Subject Lead"),
        ("pathway_lead", "Pathway Lead"),
        ("slt", "Senior Leadership Team"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staffprofile",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="teacher")
    arbor_staff_id = models.PositiveIntegerField(
        unique=True,
        null=True,
        blank=True,
        help_text="Arbor Staff ID (matches Entra Employee ID without the 'Stf_' prefix).",
    )
    lead_pathway = models.CharField(
        max_length=4,
        blank=True,
        choices=[
            ("PREP", "Preparations"),
            ("EXP", "Explorers"),
            ("FUT", "Futures"),
            ("HOR", "Horizons"),
        ],
        help_text="For Pathway Leads: which pathway they oversee.",
    )

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_role_display()})"

    @property
    def is_slt(self):
        return self.role == "slt"

    @property
    def is_subject_lead(self):
        return self.role == "subject_lead"

    @property
    def is_pathway_lead(self):
        return self.role == "pathway_lead"


class SubjectLead(models.Model):
    """Links a subject lead to the subject(s) they are responsible for."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subject_leads",
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="leads"
    )

    class Meta:
        unique_together = ["user", "subject"]

    def __str__(self):
        return f"{self.user.get_full_name()} → {self.subject.name}"


class ClassAssignment(models.Model):
    """Links a staff member to their designated class(es)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="class_assignments",
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="assignments"
    )

    class Meta:
        unique_together = ["user", "class_group"]

    def __str__(self):
        return f"{self.user.get_full_name()} → {self.class_group}"


class ClassCover(models.Model):
    """Temporary class cover — ad-hoc, self-service, auto-expiring."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="class_covers",
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="covers"
    )
    start_date = models.DateField()
    end_date = models.DateField(help_text="Cover expires at end of this date")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.user.get_full_name()} covering {self.class_group} ({self.start_date} to {self.end_date})"

    @property
    def is_active(self):
        from django.utils import timezone

        today = timezone.now().date()
        return self.start_date <= today <= self.end_date
