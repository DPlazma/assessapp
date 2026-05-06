from django.db import models
from django.conf import settings


class Notification(models.Model):
    """A notification for a staff member."""

    CATEGORY_CHOICES = [
        ("RECORDING_GAP", "Recording Gap"),
        ("SNAPSHOT_REMINDER", "Snapshot Reminder"),
        ("YEAR_EXPIRY", "Academic Year Expiry"),
        ("COVER_ASSIGNED", "Cover Assigned"),
        ("GENERAL", "General"),
    ]
    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    priority = models.CharField(max_length=6, choices=PRIORITY_CHOICES, default="MEDIUM")
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=300, blank=True, help_text="URL to navigate to")
    is_read = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # De-duplication key — prevents the same notification being generated repeatedly
    dedupe_key = models.CharField(
        max_length=200, blank=True, db_index=True,
        help_text="Unique key to prevent duplicate notifications",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "is_dismissed"]),
        ]

    def __str__(self):
        return f"{self.title} → {self.recipient}"

    @property
    def icon(self):
        icons = {
            "RECORDING_GAP": "bi-exclamation-triangle",
            "SNAPSHOT_REMINDER": "bi-camera",
            "YEAR_EXPIRY": "bi-calendar-event",
            "COVER_ASSIGNED": "bi-arrow-left-right",
            "GENERAL": "bi-info-circle",
        }
        return icons.get(self.category, "bi-bell")

    @property
    def badge_class(self):
        classes = {
            "HIGH": "bg-danger",
            "MEDIUM": "bg-warning text-dark",
            "LOW": "bg-info text-dark",
        }
        return classes.get(self.priority, "bg-secondary")
