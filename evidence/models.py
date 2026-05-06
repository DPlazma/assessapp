import os
import uuid
from datetime import date

from django.conf import settings
from django.db import models

from students.models import Student, Subject
from assessments.models import AssessmentArea


def evidence_upload_path(instance, filename):
    """Upload evidence files to media/evidence/<year>/<month>/<uuid>.<ext>"""
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    today = date.today()
    return f"evidence/{today.year}/{today.month:02d}/{safe_name}"


def ehcp_document_upload_path(instance, filename):
    """Upload EHCP PDF files to media/ehcp_documents/<year>/<uuid>.pdf"""
    safe_name = f"{uuid.uuid4().hex}.pdf"
    today = date.today()
    return f"ehcp_documents/{today.year}/{safe_name}"


# ── EHCP Targets ────────────────────────────────────────────────────

class EHCPOutcome(models.Model):
    """A broad EHCP outcome area (e.g. 'Communication & Interaction')."""

    name = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class EHCPTarget(models.Model):
    """An individual EHCP target for a student."""

    STATUS_CHOICES = [
        ("NOT_STARTED", "Not Started"),
        ("IN_PROGRESS", "In Progress"),
        ("PARTIALLY_MET", "Partially Met"),
        ("MET", "Met"),
        ("EXCEEDED", "Exceeded"),
    ]

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="ehcp_targets"
    )
    outcome = models.ForeignKey(
        EHCPOutcome, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="targets",
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="NOT_STARTED")
    set_date = models.DateField(help_text="Date target was set")
    review_date = models.DateField(blank=True, null=True, help_text="Next review date")
    met_date = models.DateField(blank=True, null=True, help_text="Date target was met")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="ehcp_targets_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional link to assessment areas
    linked_areas = models.ManyToManyField(
        AssessmentArea, blank=True, related_name="ehcp_targets",
        help_text="Assessment areas that support this target",
    )

    class Meta:
        ordering = ["student", "outcome", "-set_date"]

    def __str__(self):
        return f"{self.student} — {self.title[:60]}"


class EHCPTargetReview(models.Model):
    """A review entry for an EHCP target — tracks status changes over time."""

    target = models.ForeignKey(
        EHCPTarget, on_delete=models.CASCADE, related_name="reviews"
    )
    status = models.CharField(max_length=15, choices=EHCPTarget.STATUS_CHOICES)
    notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
    )
    review_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-review_date", "-created_at"]

    def __str__(self):
        return f"Review: {self.target.title[:40]} — {self.get_status_display()}"


# ── EHCP Documents (OCR) ───────────────────────────────────────────

class EHCPDocument(models.Model):
    """An uploaded EHCP PDF for a student, with OCR text extraction."""

    STATUS_CHOICES = [
        ("UPLOADED", "Uploaded"),
        ("PROCESSING", "Processing OCR"),
        ("COMPLETED", "OCR Complete"),
        ("FAILED", "OCR Failed"),
    ]

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="ehcp_documents",
    )
    file = models.FileField(upload_to=ehcp_document_upload_path)
    original_filename = models.CharField(max_length=255)
    title = models.CharField(max_length=300, blank=True)
    ocr_text = models.TextField(
        blank=True, default="",
        help_text="Raw text extracted via OCR / PDF text layer.",
    )
    edited_text = models.TextField(
        blank=True, default="",
        help_text="User-edited version of the OCR text.",
    )
    processing_status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="UPLOADED",
    )
    page_count = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="ehcp_documents_uploaded",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or self.original_filename

    def get_page_image_urls(self):
        """Return a list of URLs for rendered page images."""
        import os as _os
        pages_dir = _os.path.join(
            settings.MEDIA_ROOT, "ehcp_pages", str(self.pk)
        )
        if not _os.path.isdir(pages_dir):
            return []
        files = sorted(
            f for f in _os.listdir(pages_dir) if f.endswith(".jpg")
        )
        return [
            f"{settings.MEDIA_URL}ehcp_pages/{self.pk}/{f}" for f in files
        ]


class EHCPAnnotation(models.Model):
    """An annotation (highlight, strikethrough, text box, sticky note) on an EHCP document page."""

    TYPE_CHOICES = [
        ("highlight", "Highlight"),
        ("strikethrough", "Strikethrough"),
        ("textbox", "Text Box"),
        ("note", "Sticky Note"),
    ]

    COLOR_CHOICES = [
        ("#ffeb3b", "Yellow"),
        ("#4caf50", "Green"),
        ("#f48fb1", "Pink"),
        ("#64b5f6", "Blue"),
        ("#ff8a65", "Orange"),
    ]

    document = models.ForeignKey(
        EHCPDocument, on_delete=models.CASCADE, related_name="annotations",
    )
    annotation_type = models.CharField(max_length=15, choices=TYPE_CHOICES)
    page = models.PositiveIntegerField(help_text="1-based page number")
    # Position & size as percentages of page dimensions (0-100)
    x = models.FloatField(help_text="Left position as % of page width")
    y = models.FloatField(help_text="Top position as % of page height")
    width = models.FloatField(help_text="Width as % of page width")
    height = models.FloatField(help_text="Height as % of page height")
    color = models.CharField(max_length=7, default="#ffeb3b")
    text = models.TextField(blank=True, default="", help_text="Text content for text boxes / notes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["page", "y", "x"]

    def __str__(self):
        return f"{self.get_annotation_type_display()} p{self.page} — {self.document}"


# ── Evidence ────────────────────────────────────────────────────────

class Evidence(models.Model):
    """A piece of evidence (photo, video, document) linked to students."""

    TYPE_CHOICES = [
        ("PHOTO", "Photo"),
        ("VIDEO", "Video"),
        ("DOCUMENT", "Document"),
    ]

    # Legacy FK — kept nullable for backward compat; use students M2M instead
    student = models.ForeignKey(
        Student, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="evidence_items"
    )
    # New M2M via through model
    students = models.ManyToManyField(
        Student, through="EvidenceStudentLink",
        related_name="linked_evidence", blank=True,
    )
    evidence_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to=evidence_upload_path)
    thumbnail = models.ImageField(
        upload_to="evidence/thumbnails/", blank=True, null=True,
        help_text="Auto-generated or manually set thumbnail",
    )

    # Sharing
    is_shared_with_family = models.BooleanField(
        default=False,
        help_text="If True, visible in the parent/family portal",
    )
    shared_at = models.DateTimeField(blank=True, null=True)
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="evidence_shared",
    )

    # Links
    ehcp_target = models.ForeignKey(
        EHCPTarget, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="evidence_items",
        help_text="Link to an EHCP target (optional)",
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="evidence_items",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="evidence_uploaded",
    )
    captured_date = models.DateField(
        help_text="Date the evidence was captured/observed"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-captured_date", "-created_at"]
        verbose_name_plural = "evidence"

    def __str__(self):
        names = ", ".join(
            s.full_name for s in self.students.all()[:3]
        )
        return self.title or f"{self.get_evidence_type_display()} — {names or 'Unlinked'}"

    @property
    def file_extension(self):
        return os.path.splitext(self.file.name)[1].lower() if self.file else ""

    @property
    def is_image(self):
        return self.file_extension in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif")

    @property
    def is_video(self):
        return self.file_extension in (".mp4", ".webm", ".mov", ".avi")

    @property
    def is_linked(self):
        """True if this evidence is linked to at least one student."""
        return self.student_links.exists()


class EvidenceStudentLink(models.Model):
    """Links an evidence item to a student, with an optional EHCP target."""

    evidence = models.ForeignKey(
        Evidence, on_delete=models.CASCADE, related_name="student_links"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="evidence_links"
    )
    ehcp_target = models.ForeignKey(
        EHCPTarget, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="evidence_student_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["evidence", "student"]
        ordering = ["student__last_name", "student__first_name"]

    def __str__(self):
        return f"{self.evidence} → {self.student}"


# ── Small Steps ─────────────────────────────────────────────────────

class SmallStep(models.Model):
    """A small step linked to an EHCP target — lettered steps (A, B, C…) that
    break down a target into granular, measurable milestones."""

    STATUS_CHOICES = [
        ("NOT_STARTED", "Not Started"),
        ("WORKING_ON", "Working On"),
        ("ACHIEVED", "Achieved"),
    ]

    target = models.ForeignKey(
        EHCPTarget, on_delete=models.CASCADE, related_name="small_steps",
    )
    letter = models.CharField(
        max_length=2, help_text="Step letter, e.g. A, B, C",
    )
    description = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="NOT_STARTED")
    status_date = models.DateField(blank=True, null=True, help_text="Date status last changed")
    notes = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["target", "order", "letter"]
        unique_together = ["target", "letter"]

    def __str__(self):
        return f"Step {self.letter}: {self.description[:60]}"


# ── MAPP Configuration ───────────────────────────────────────────────

class MAPPConfig(models.Model):
    """School-level MAPP configuration. Exactly one active config at a time.
    Defines the CSD scale range and which dimensions to use."""

    name = models.CharField(max_length=100, help_text="e.g. 'Standard MAPP', 'MAPP with 5 dimensions'")
    scale_min = models.PositiveSmallIntegerField(default=1, help_text="Lowest CSD scale value")
    scale_max = models.PositiveSmallIntegerField(default=10, help_text="Highest CSD scale value")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "name"]
        verbose_name = "MAPP configuration"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_active:
            MAPPConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Return the active MAPP config, or None if none exists."""
        return cls.objects.filter(is_active=True).first()

    @property
    def scale_range(self):
        return range(self.scale_min, self.scale_max + 1)

    @property
    def scale_size(self):
        return self.scale_max - self.scale_min + 1


class MAPPDimensionConfig(models.Model):
    """A dimension in a MAPP configuration (e.g. Independence, Fluency).
    Schools can add/remove/rename dimensions."""

    config = models.ForeignKey(MAPPConfig, on_delete=models.CASCADE, related_name="dimension_configs")
    code = models.CharField(max_length=5, help_text="Short code, e.g. IND, FLU")
    name = models.CharField(max_length=100, help_text="Full name, e.g. Independence")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["config", "order"]
        unique_together = ["config", "code"]
        verbose_name = "MAPP dimension"

    def __str__(self):
        return f"{self.name} ({self.code})"


# ── MAPP (Mapping and Assessing Personal Progress) ──────────────────

class MAPPLearningPriority(models.Model):
    """A MAPP learning priority — a specific measurable goal under an EHCP
    target.  Each target typically has 2 learning priorities."""

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="mapp_priorities",
    )
    ehcp_target = models.ForeignKey(
        EHCPTarget, on_delete=models.CASCADE, related_name="mapp_priorities",
        blank=True, null=True,
    )
    title = models.TextField(help_text="Learning priority description")
    academic_year = models.CharField(
        max_length=10, blank=True, help_text="e.g. 23/24",
    )
    term = models.CharField(
        max_length=20, blank=True, help_text="e.g. Spring, Summer",
    )
    ehcp_year = models.CharField(
        max_length=10, blank=True, help_text="EHCP year this was taken from",
    )
    baseline_date = models.DateField(blank=True, null=True)
    final_assessment_date = models.DateField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student", "ehcp_target", "order"]
        verbose_name = "MAPP learning priority"
        verbose_name_plural = "MAPP learning priorities"

    def __str__(self):
        return f"{self.student} — {self.title[:60]}"

    @property
    def total_progress_pct(self):
        """Average percentage across all 4 dimensions."""
        dims = self.dimensions.all()
        if not dims:
            return 0
        return sum(d.progress_pct for d in dims) / len(dims)


class MAPPDimensionScore(models.Model):
    """Tracks progress on one dimension for a MAPP learning priority.
    Baseline sits on the CSD scale; progress = steps from baseline."""

    # Legacy choices — used as fallback when no MAPPConfig exists
    DIMENSION_CHOICES = [
        ("IND", "Independence"),
        ("FLU", "Fluency"),
        ("MAI", "Maintenance"),
        ("GEN", "Generalisation"),
    ]

    priority = models.ForeignKey(
        MAPPLearningPriority, on_delete=models.CASCADE, related_name="dimensions",
    )
    dimension = models.CharField(max_length=5, choices=DIMENSION_CHOICES)
    dimension_config = models.ForeignKey(
        MAPPDimensionConfig, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Links to the config dimension (if using configurable MAPP)",
    )
    baseline_csd = models.PositiveSmallIntegerField(
        help_text="Baseline position on CSD scale",
    )
    current_score = models.PositiveSmallIntegerField(
        default=0, help_text="Steps progressed from baseline",
    )

    class Meta:
        ordering = ["priority", "dimension"]
        unique_together = ["priority", "dimension"]
        verbose_name = "MAPP dimension score"

    def __str__(self):
        label = self.dimension_config.name if self.dimension_config else self.get_dimension_display()
        return f"{label}: b={self.baseline_csd}, +{self.current_score}"

    @property
    def dimension_label(self):
        """Human-readable dimension name — from config if available, else legacy choices."""
        if self.dimension_config:
            return self.dimension_config.name
        return self.get_dimension_display()

    @property
    def scale_max(self):
        """Get the max CSD scale value from config, default 10."""
        config = MAPPConfig.get_active()
        return config.scale_max if config else 10

    @property
    def current_csd(self):
        """Current position on the CSD scale."""
        return min(self.baseline_csd + self.current_score, self.scale_max)

    @property
    def max_steps(self):
        """Maximum possible steps from baseline to scale max."""
        return self.scale_max - self.baseline_csd

    @property
    def progress_pct(self):
        """Progress as percentage of possible steps."""
        mx = self.max_steps
        if mx <= 0:
            return 100 if self.current_score > 0 else 0
        return round((self.current_score / mx) * 100)


# ── Intervention Tracker ────────────────────────────────────────────

class InterventionProgram(models.Model):
    """A type of intervention offered by the school
    (e.g. Speech & Language Therapy, Sensory Diet, ELSA)."""

    CATEGORY_CHOICES = [
        ("SALT", "Speech & Language"),
        ("OT", "Occupational Therapy"),
        ("PHYSIO", "Physiotherapy"),
        ("SOCIAL", "Social Skills"),
        ("ELSA", "Emotional Literacy"),
        ("READING", "Reading"),
        ("MATHS", "Maths"),
        ("SENSORY", "Sensory"),
        ("BEHAVIOUR", "Behaviour"),
        ("OTHER", "Other"),
    ]

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default="OTHER")
    description = models.TextField(blank=True)
    default_frequency = models.CharField(
        max_length=50, blank=True, help_text="e.g. '3x per week', 'Daily'",
    )
    default_duration_mins = models.PositiveIntegerField(
        blank=True, null=True, help_text="Default session length in minutes",
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class InterventionEnrolment(models.Model):
    """A student enrolled in an intervention program for a period of time."""

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("COMPLETED", "Completed"),
        ("PAUSED", "Paused"),
        ("WITHDRAWN", "Withdrawn"),
    ]

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="interventions",
    )
    program = models.ForeignKey(
        InterventionProgram, on_delete=models.CASCADE, related_name="enrolments",
    )
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="interventions_delivering",
        help_text="Staff member delivering this intervention",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="ACTIVE")
    frequency = models.CharField(max_length=50, blank=True, help_text="e.g. '2x per week'")
    duration_mins = models.PositiveIntegerField(
        blank=True, null=True, help_text="Session length in minutes",
    )
    goals = models.TextField(blank=True, help_text="What this intervention aims to achieve")
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    ehcp_target = models.ForeignKey(
        EHCPTarget, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="interventions",
        help_text="Link to an EHCP target (optional)",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "intervention enrolment"

    def __str__(self):
        return f"{self.student} — {self.program.name}"

    @property
    def session_count(self):
        return self.sessions.count()

    @property
    def attended_count(self):
        return self.sessions.filter(attended=True).count()

    @property
    def attendance_pct(self):
        total = self.session_count
        if total == 0:
            return 0
        return round((self.attended_count / total) * 100)


class InterventionSession(models.Model):
    """A single session/occurrence of an intervention."""

    enrolment = models.ForeignKey(
        InterventionEnrolment, on_delete=models.CASCADE, related_name="sessions",
    )
    session_date = models.DateField()
    attended = models.BooleanField(default=True)
    duration_mins = models.PositiveIntegerField(
        blank=True, null=True, help_text="Actual session length (if different from planned)",
    )
    notes = models.TextField(blank=True, help_text="Brief session notes")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-session_date"]

    def __str__(self):
        status = "Attended" if self.attended else "Absent"
        return f"{self.enrolment.program.name} — {self.session_date} ({status})"


class InterventionReview(models.Model):
    """A periodic impact review for an intervention enrolment."""

    IMPACT_CHOICES = [
        ("SIGNIFICANT", "Significant Progress"),
        ("GOOD", "Good Progress"),
        ("SOME", "Some Progress"),
        ("LIMITED", "Limited Progress"),
        ("NONE", "No Progress"),
        ("REGRESSION", "Regression"),
    ]

    enrolment = models.ForeignKey(
        InterventionEnrolment, on_delete=models.CASCADE, related_name="reviews",
    )
    review_date = models.DateField()
    impact = models.CharField(max_length=15, choices=IMPACT_CHOICES)
    progress_notes = models.TextField(help_text="Evidence of progress / impact")
    next_steps = models.TextField(blank=True, help_text="Recommended next actions")
    continue_intervention = models.BooleanField(
        default=True, help_text="Should this intervention continue?",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-review_date"]

    def __str__(self):
        return f"Review: {self.enrolment} — {self.get_impact_display()}"
