from django.conf import settings
from django.db import models
from django.utils import timezone


class AcademicYear(models.Model):
    """Represents an academic year (e.g. 2025-2026)."""

    name = models.CharField(max_length=20, unique=True, help_text="e.g. 2025-2026")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_current:
            AcademicYear.objects.filter(is_current=True).exclude(pk=self.pk).update(
                is_current=False
            )
        super().save(*args, **kwargs)


class Term(models.Model):
    """A term within an academic year (Autumn, Spring, Summer)."""

    TERM_CHOICES = [
        ("AUT", "Autumn"),
        ("SPR", "Spring"),
        ("SUM", "Summer"),
    ]

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="terms"
    )
    name = models.CharField(max_length=3, choices=TERM_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["start_date"]
        unique_together = ["academic_year", "name"]

    def __str__(self):
        return f"{self.get_name_display()} {self.academic_year}"

    @classmethod
    def get_current(cls):
        today = timezone.now().date()
        return cls.objects.filter(start_date__lte=today, end_date__gte=today).first()


class AISettings(models.Model):
    """Singleton model for AI / LLM configuration."""

    PROVIDER_CHOICES = [
        ("none", "Disabled"),
        ("openai", "OpenAI"),
        ("azure", "Azure OpenAI"),
        ("copilot", "Microsoft 365 Copilot"),
        ("gemini", "Google Gemini"),
        ("ollama", "Ollama (local)"),
        ("custom", "Custom endpoint"),
    ]

    provider = models.CharField(
        max_length=10, choices=PROVIDER_CHOICES, default="none"
    )
    api_key = models.CharField(
        max_length=255, blank=True, default="",
        help_text="API key (stored encrypted at rest in production).",
    )
    endpoint_url = models.URLField(
        blank=True, default="",
        help_text="Base URL for API calls (required for Azure / Ollama / Custom).",
    )
    model_name = models.CharField(
        max_length=100, blank=True, default="",
        help_text="e.g. gpt-4o, gpt-3.5-turbo, llama3.",
    )
    enabled = models.BooleanField(
        default=False,
        help_text="Master switch — must be on for any AI features to work.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI settings"
        verbose_name_plural = "AI settings"

    def __str__(self):
        return f"AI Settings ({self.get_provider_display()})"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class DashboardPreference(models.Model):
    """Per-user dashboard widget layout preferences."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboard_preference",
    )
    widget_layout = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered list of {widget_id, visible} dicts.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Dashboard prefs — {self.user}"


# ── Arbor Integration ──────────────────────────────────────────────


class ArborSettings(models.Model):
    """Singleton model for Arbor MIS API configuration."""

    base_url = models.URLField(
        blank=True,
        default="",
        help_text="School Arbor URL, e.g. https://west-gate.uk.arbor.sc",
    )
    app_username = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Arbor app username (from developer portal).",
    )
    api_key = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Arbor API key for your school.",
    )
    enabled = models.BooleanField(
        default=False,
        help_text="Master switch — must be on for Arbor sync to work.",
    )
    last_connected = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Arbor settings"
        verbose_name_plural = "Arbor settings"

    def __str__(self):
        return f"Arbor Settings (enabled={self.enabled})"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ArborMapping(models.Model):
    """Maps an AssessApp entity to its Arbor counterpart."""

    ENTITY_CHOICES = [
        ("assessment", "Assessment (Subject)"),
        ("grade", "Grade (Status)"),
        ("period", "Progress Measurement Period (Term)"),
        ("grade_set", "Grade Set"),
    ]

    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    local_id = models.CharField(
        max_length=100,
        help_text="AssessApp identifier (e.g. subject PK, status code, term PK).",
    )
    local_label = models.CharField(
        max_length=200,
        blank=True,
        help_text="Human-readable label from AssessApp.",
    )
    arbor_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Arbor entity ID.",
    )
    arbor_label = models.CharField(
        max_length=200,
        blank=True,
        help_text="Human-readable label from Arbor.",
    )
    arbor_href = models.CharField(
        max_length=500,
        blank=True,
        help_text="Arbor REST href for this entity.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["entity_type", "local_id"]
        ordering = ["entity_type", "local_label"]

    def __str__(self):
        return f"{self.get_entity_type_display()}: {self.local_label} → {self.arbor_label or '(unmapped)'}"


class ArborSyncLog(models.Model):
    """Tracks each sync attempt and its results."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("success", "Success"),
        ("partial", "Partial (some errors)"),
        ("failed", "Failed"),
    ]

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    records_attempted = models.PositiveIntegerField(default=0)
    records_succeeded = models.PositiveIntegerField(default=0)
    records_failed = models.PositiveIntegerField(default=0)
    error_details = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {student, error} dicts for failed records.",
    )
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Sync {self.started_at:%Y-%m-%d %H:%M} — {self.get_status_display()}"
