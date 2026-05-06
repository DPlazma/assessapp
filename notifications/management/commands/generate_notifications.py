"""
Management command: generate_notifications

Checks various conditions and creates notifications for staff.
Designed to run daily via cron or Docker entrypoint.

Checks:
  1. Academic year expiry — warns SLT when current year is within 30/14/7 days of ending
  2. Recording gap nudges — notifies teachers with no assessments in the last 14 days
  3. Snapshot reminders — prompts SLT when a term is ending and no snapshots exist
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import AcademicYear, Term
from assessments.models import AssessmentRecord, AssessmentSnapshot
from staff.models import StaffProfile, ClassAssignment
from notifications.models import Notification

User = get_user_model()


class Command(BaseCommand):
    help = "Generate notifications for recording gaps, snapshot reminders, and academic year expiry."

    def handle(self, *args, **options):
        today = timezone.now().date()
        total = 0
        total += self._check_year_expiry(today)
        total += self._check_recording_gaps(today)
        total += self._check_snapshot_reminders(today)
        self.stdout.write(self.style.SUCCESS(f"Generated {total} notification(s)."))

    # ── Academic Year Expiry ────────────────────────────────────────

    def _check_year_expiry(self, today):
        count = 0
        try:
            year = AcademicYear.objects.get(is_current=True)
        except AcademicYear.DoesNotExist:
            return 0

        days_left = (year.end_date - today).days
        if days_left < 0:
            return 0

        # Alert thresholds — 30, 14, and 7 days
        thresholds = [
            (30, "LOW", "ends in about a month"),
            (14, "MEDIUM", "ends in two weeks"),
            (7, "HIGH", "ends in one week"),
        ]

        slt_users = User.objects.filter(staffprofile__role="slt")

        for threshold, priority, label in thresholds:
            if days_left <= threshold:
                dedupe = f"year_expiry_{year.pk}_{threshold}"
                for user in slt_users:
                    if not Notification.objects.filter(
                        recipient=user, dedupe_key=dedupe
                    ).exists():
                        Notification.objects.create(
                            recipient=user,
                            category="YEAR_EXPIRY",
                            priority=priority,
                            title=f"Academic year {label}",
                            message=(
                                f'The current academic year "{year.name}" ends on '
                                f"{year.end_date:%d %b %Y} ({days_left} day{'s' if days_left != 1 else ''} left). "
                                f"Please set up the next academic year if you haven't already."
                            ),
                            link="/setup/academic-years/",
                            dedupe_key=dedupe,
                        )
                        count += 1
                break  # Only fire the most urgent threshold
        return count

    # ── Recording Gap Nudges ────────────────────────────────────────

    def _check_recording_gaps(self, today):
        count = 0
        cutoff = today - timedelta(days=14)
        dedupe_prefix = f"recording_gap_{today.isocalendar()[1]}"  # weekly dedupe

        # Get all teachers/TAs with class assignments
        assigned_users = User.objects.filter(
            class_assignments__isnull=False
        ).distinct()

        for user in assigned_users:
            recent = AssessmentRecord.objects.filter(
                assessed_by=user,
                assessed_date__gte=cutoff,
            ).exists()

            if not recent:
                dedupe = f"{dedupe_prefix}_{user.pk}"
                if not Notification.objects.filter(
                    recipient=user, dedupe_key=dedupe
                ).exists():
                    Notification.objects.create(
                        recipient=user,
                        category="RECORDING_GAP",
                        priority="MEDIUM",
                        title="No recent assessments recorded",
                        message=(
                            "You haven't recorded any assessments in the last 14 days. "
                            "Regular assessment recording helps track student progress accurately."
                        ),
                        link="/",
                        dedupe_key=dedupe,
                    )
                    count += 1
        return count

    # ── Snapshot Reminders ──────────────────────────────────────────

    def _check_snapshot_reminders(self, today):
        count = 0

        # Find current or recently ended term (within 7 days of end)
        terms = Term.objects.filter(
            end_date__gte=today - timedelta(days=7),
            end_date__lte=today + timedelta(days=7),
        )

        slt_users = User.objects.filter(staffprofile__role="slt")

        for term in terms:
            has_snapshots = AssessmentSnapshot.objects.filter(term=term).exists()
            if has_snapshots:
                continue

            days_to_end = (term.end_date - today).days
            if days_to_end > 0:
                priority = "MEDIUM"
                label = f"ends in {days_to_end} day{'s' if days_to_end != 1 else ''}"
            else:
                priority = "HIGH"
                label = "has ended"

            dedupe = f"snapshot_reminder_{term.pk}"
            for user in slt_users:
                if not Notification.objects.filter(
                    recipient=user, dedupe_key=dedupe
                ).exists():
                    Notification.objects.create(
                        recipient=user,
                        category="SNAPSHOT_REMINDER",
                        priority=priority,
                        title=f"Snapshot needed: {term}",
                        message=(
                            f"{term.get_name_display()} term {label}. "
                            f"No assessment snapshots have been created for this term yet. "
                            f"Please create snapshots to preserve student progress data."
                        ),
                        link="/assessments/statements/",
                        dedupe_key=dedupe,
                    )
                    count += 1
        return count
