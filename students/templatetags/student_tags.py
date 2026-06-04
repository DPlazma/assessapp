"""Template helpers for student navigation.

`student_url` chooses the right landing page for a student link based on the
current user.  For most users (teachers, TAs, SLT, superusers) this is the
Assess page, matching previous behaviour.  Subject Leads and Pathway Leads
land on the Progress page instead, *unless* they teach the student's class
(via `ClassAssignment`) or are actively covering it (`ClassCover`).
"""

from django import template
from django.urls import reverse
from django.utils import timezone

register = template.Library()


def _can_assess_student_class(user, student):
    """True if the user teaches or is actively covering this student's class."""
    cg_id = getattr(student, "class_group_id", None)
    if not cg_id:
        return False
    from staff.models import ClassAssignment, ClassCover

    if ClassAssignment.objects.filter(user=user, class_group_id=cg_id).exists():
        return True
    today = timezone.now().date()
    return ClassCover.objects.filter(
        user=user,
        class_group_id=cg_id,
        start_date__lte=today,
        end_date__gte=today,
    ).exists()


def student_landing_url(user, student, subject=None):
    """Return the URL a given user should land on when opening this student.

    If `subject` is provided, go straight to the subject-specific Assess page.
    Otherwise, everyone lands on the student's Progress page — the consolidated
    hub with the per-subject grid and Record buttons. The old per-role split
    (assess hub vs progress) has been retired.
    """

    if subject is not None:
        subj_pk = getattr(subject, "pk", subject)
        return reverse("assessments:assess_student", args=[student.pk, subj_pk])
    return reverse("students:progress", args=[student.pk])


@register.simple_tag(takes_context=True)
def student_url(context, student, subject=None):
    request = context.get("request")
    user = getattr(request, "user", None) if request else None
    return student_landing_url(user, student, subject)
