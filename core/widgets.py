"""
Dashboard widget registry.

Each widget is a dict with:
    id          – unique slug
    title       – display name
    icon        – Bootstrap Icons class
    description – short blurb for the gallery
    template    – path to the partial template
    default     – whether it's visible by default
    size        – default size: 'sm' (1 col), 'md' (2 cols), 'lg' (full row)
    min_size    – smallest allowed size
    max_size    – largest allowed size
    fetch       – callable(request, context) → dict of extra template context
    category    – widget category for visual grouping (data/people/activity/targets/actions)

Size order: sm < md < lg.  Users cycle through allowed sizes.

Role groups:
    teacher   – Teacher, TA, HLTA
    lead      – Subject Lead / Pathway Lead
    slt       – Senior Leadership Team (+ Governors)
"""

from django.db.models import Count, Q
from django.utils import timezone

# ── Category colours (used for left-border on cards) ────────────────
CATEGORY_COLOURS = {
    "data": "#0d6efd",      # blue
    "people": "#198754",     # green
    "activity": "#6f42c1",   # purple
    "targets": "#fd7e14",    # orange
    "actions": "#20c997",    # teal
}

# ── Role group helper ──────────────────────────────────────────────

def get_role_group(user):
    """Return the role group for a user: 'slt', 'lead', or 'teacher'."""
    profile = getattr(user, "staffprofile", None)
    if not profile:
        return "teacher"
    if profile.is_slt:
        return "slt"
    if profile.is_subject_lead:
        return "lead"
    return "teacher"


# ── Data-fetching helpers ───────────────────────────────────────────

def _fetch_class_overview(request, ctx):
    """Counts for the stat cards: students, assessments this term, evidence."""
    from assessments.models import AssessmentRecord
    from evidence.models import Evidence
    from core.models import Term

    students = ctx.get("students", [])
    student_ids = [s.pk for s in students] if students else []
    term = Term.get_current()

    assessments_this_term = 0
    evidence_this_term = 0

    if term and student_ids:
        assessments_this_term = AssessmentRecord.objects.filter(
            student_id__in=student_ids,
            assessed_date__gte=term.start_date,
            assessed_date__lte=term.end_date,
        ).count()
        evidence_this_term = Evidence.objects.filter(
            student_links__student_id__in=student_ids,
            captured_date__gte=term.start_date,
            captured_date__lte=term.end_date,
        ).distinct().count()

    return {
        "student_count": len(student_ids),
        "assessments_this_term": assessments_this_term,
        "evidence_this_term": evidence_this_term,
        "current_term": term,
    }


def _fetch_assessment_summary(request, ctx):
    """RAG breakdown across the class (latest record per student+statement)."""
    from assessments.models import AssessmentRecord

    students = ctx.get("students", [])
    student_ids = [s.pk for s in students] if students else []

    counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
    if student_ids:
        qs = (
            AssessmentRecord.objects.filter(student_id__in=student_ids)
            .values("status")
            .annotate(n=Count("id"))
        )
        for row in qs:
            counts[row["status"]] = row["n"]

    total = sum(counts.values()) or 1
    return {
        "rag_counts": counts,
        "rag_total": total,
        "rag_pcts": {k: round(v / total * 100) for k, v in counts.items()},
    }


def _fetch_recent_activity(request, ctx):
    """Already in main context; just pass through."""
    return {}


def _fetch_ehcp_overview(request, ctx):
    """EHCP target status summary for class students."""
    from evidence.models import EHCPTarget

    students = ctx.get("students", [])
    student_ids = [s.pk for s in students] if students else []

    targets = []
    status_counts = {}
    if student_ids:
        targets = list(
            EHCPTarget.objects.filter(student_id__in=student_ids)
            .select_related("student")
            .order_by("student__last_name", "status")[:20]
        )
        status_counts = dict(
            EHCPTarget.objects.filter(student_id__in=student_ids)
            .values_list("status")
            .annotate(n=Count("id"))
            .order_by()
        )

    return {
        "ehcp_targets": targets,
        "ehcp_status_counts": status_counts,
        "ehcp_total": sum(status_counts.values()) if status_counts else 0,
    }


def _fetch_evidence_stats(request, ctx):
    """Evidence uploaded this term by type."""
    from evidence.models import Evidence
    from core.models import Term

    students = ctx.get("students", [])
    student_ids = [s.pk for s in students] if students else []
    term = Term.get_current()

    by_type = {}
    total = 0
    if term and student_ids:
        rows = (
            Evidence.objects.filter(
                student_links__student_id__in=student_ids,
                captured_date__gte=term.start_date,
                captured_date__lte=term.end_date,
            )
            .distinct()
            .values("evidence_type")
            .annotate(n=Count("id"))
        )
        by_type = {r["evidence_type"]: r["n"] for r in rows}
        total = sum(by_type.values())

    return {"evidence_by_type": by_type, "evidence_total": total}


def _fetch_upcoming_reviews(request, ctx):
    """EHCP targets due for review in the next 30 days."""
    from evidence.models import EHCPTarget

    students = ctx.get("students", [])
    student_ids = [s.pk for s in students] if students else []
    today = timezone.now().date()

    upcoming = []
    if student_ids:
        upcoming = list(
            EHCPTarget.objects.filter(
                student_id__in=student_ids,
                review_date__gte=today,
                review_date__lte=today + timezone.timedelta(days=30),
            )
            .exclude(status__in=["MET", "EXCEEDED"])
            .select_related("student")
            .order_by("review_date")[:10]
        )

    return {"upcoming_reviews": upcoming}


def _fetch_assessment_gaps(request, ctx):
    """Students with fewest assessment records this term."""
    from assessments.models import AssessmentRecord
    from core.models import Term

    students = ctx.get("students", [])
    term = Term.get_current()

    gaps = []
    if students and term:
        student_ids = [s.pk for s in students]
        counts = dict(
            AssessmentRecord.objects.filter(
                student_id__in=student_ids,
                assessed_date__gte=term.start_date,
                assessed_date__lte=term.end_date,
            )
            .values_list("student_id")
            .annotate(n=Count("id"))
            .order_by()
        )
        gaps = sorted(
            [(s, counts.get(s.pk, 0)) for s in students],
            key=lambda x: x[1],
        )[:5]

    return {"assessment_gaps": gaps}


def _fetch_notifications(request, ctx):
    """Latest unread notifications for the user."""
    from notifications.models import Notification

    notifs = list(
        Notification.objects.filter(
            recipient=request.user,
            is_read=False,
            is_dismissed=False,
        ).order_by("-created_at")[:5]
    )
    return {"dashboard_notifications": notifs}


def _fetch_quick_actions(request, ctx):
    """Build role-aware quick action links."""
    role_group = get_role_group(request.user)
    return {"role_group": role_group}


def _fetch_my_class(request, ctx):
    return {}


def _fetch_covering(request, ctx):
    return {}


def _fetch_school_overview(request, ctx):
    """Whole-school stats for SLT/leads: total students, classes, staff activity."""
    from students.models import Student, ClassGroup
    from assessments.models import AssessmentRecord
    from evidence.models import Evidence
    from core.models import Term
    from django.contrib.auth import get_user_model

    User = get_user_model()
    term = Term.get_current()
    total_students = Student.objects.filter(is_active=True).count()
    total_classes = ClassGroup.objects.count()

    assessments_school = 0
    evidence_school = 0
    active_assessors = 0
    if term:
        assessments_school = AssessmentRecord.objects.filter(
            assessed_date__gte=term.start_date,
            assessed_date__lte=term.end_date,
        ).count()
        evidence_school = Evidence.objects.filter(
            captured_date__gte=term.start_date,
            captured_date__lte=term.end_date,
        ).count()
        active_assessors = (
            AssessmentRecord.objects.filter(
                assessed_date__gte=term.start_date,
                assessed_date__lte=term.end_date,
            )
            .values("assessed_by")
            .distinct()
            .count()
        )

    return {
        "total_students": total_students,
        "total_classes": total_classes,
        "assessments_school": assessments_school,
        "evidence_school": evidence_school,
        "active_assessors": active_assessors,
        "current_term": term,
    }


def _fetch_my_subjects(request, ctx):
    """Cross-class data for the subjects a lead is responsible for."""
    from staff.models import SubjectLead
    from assessments.models import AssessmentRecord, AssessmentArea
    from core.models import Term

    user = request.user
    term = Term.get_current()
    lead_subjects = list(
        SubjectLead.objects.filter(user=user)
        .select_related("subject")
        .values_list("subject__id", "subject__name", named=True)
    )

    subjects_data = []
    for row in lead_subjects:
        subj_id, subj_name = row.subject__id, row.subject__name
        # Count areas, students assessed, latest statuses
        area_count = AssessmentArea.objects.filter(subject_id=subj_id).count()

        counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
        total_records = 0
        if term:
            qs = (
                AssessmentRecord.objects.filter(
                    statement__area__subject_id=subj_id,
                    assessed_date__gte=term.start_date,
                    assessed_date__lte=term.end_date,
                )
                .values("status")
                .annotate(n=Count("id"))
            )
            for r in qs:
                counts[r["status"]] = r["n"]
            total_records = sum(counts.values())

        t = total_records or 1
        subjects_data.append({
            "name": subj_name,
            "area_count": area_count,
            "counts": counts,
            "total": total_records,
            "pcts": {k: round(v / t * 100) for k, v in counts.items()},
        })

    return {"lead_subjects": subjects_data}


def _fetch_attention(request, ctx):
    """Role-specific attention items: EHCP reviews, assessment gaps, covers."""
    from evidence.models import EHCPTarget
    from staff.models import ClassCover

    user = request.user
    role_group = get_role_group(user)
    today = timezone.now().date()
    items = []

    students = ctx.get("students", [])
    student_ids = [s.pk for s in students] if students else []

    # EHCP reviews due within 14 days (all roles that have students)
    if student_ids:
        overdue = EHCPTarget.objects.filter(
            student_id__in=student_ids,
            review_date__lte=today + timezone.timedelta(days=14),
            review_date__gte=today - timezone.timedelta(days=30),
        ).exclude(status__in=["MET", "EXCEEDED"]).count()
        if overdue:
            items.append({
                "icon": "bi-exclamation-triangle-fill",
                "colour": "warning",
                "text": f"{overdue} EHCP review{'s' if overdue != 1 else ''} due soon",
                "link": "#",
            })

    # Students with zero assessments this term
    if student_ids:
        from assessments.models import AssessmentRecord
        from core.models import Term
        term = Term.get_current()
        if term:
            assessed_ids = set(
                AssessmentRecord.objects.filter(
                    student_id__in=student_ids,
                    assessed_date__gte=term.start_date,
                    assessed_date__lte=term.end_date,
                ).values_list("student_id", flat=True)
            )
            unassessed = len(student_ids) - len(assessed_ids & set(student_ids))
            if unassessed:
                items.append({
                    "icon": "bi-person-exclamation",
                    "colour": "danger",
                    "text": f"{unassessed} student{'s' if unassessed != 1 else ''} with no assessments this term",
                    "link": "#",
                })

    # Currently covering a class (teacher/TA)
    if role_group == "teacher":
        covers_today = ClassCover.objects.filter(
            user=user, start_date__lte=today, end_date__gte=today,
        ).select_related("class_group")
        for cover in covers_today:
            items.append({
                "icon": "bi-arrow-left-right",
                "colour": "info",
                "text": f"Covering {cover.class_group.name} today",
                "link": "#",
            })

    # SLT: total unassessed students across school
    if role_group == "slt":
        from students.models import Student
        from assessments.models import AssessmentRecord
        from core.models import Term
        term = Term.get_current()
        if term:
            all_active = Student.objects.filter(is_active=True).count()
            assessed_all = (
                AssessmentRecord.objects.filter(
                    assessed_date__gte=term.start_date,
                    assessed_date__lte=term.end_date,
                )
                .values("student_id")
                .distinct()
                .count()
            )
            gap = all_active - assessed_all
            if gap > 0:
                items.append({
                    "icon": "bi-people-fill",
                    "colour": "warning",
                    "text": f"{gap} student{'s' if gap != 1 else ''} school-wide with no assessments this term",
                    "link": "#",
                })

    return {"attention_items": items}


def _fetch_class_progress(request, ctx):
    """Per-area NEDS breakdown for the class, for dashboard widget."""
    from assessments.models import (
        AssessmentArea, AssessmentRecord, FrameworkAssignment,
    )

    active_class = ctx.get("active_class")
    students = ctx.get("students", [])
    student_ids = [s.pk for s in students] if students else []

    if not active_class or not student_ids:
        return {"cp_areas": [], "cp_class": active_class}

    # Frameworks assigned to this class
    fw_ids = set(
        FrameworkAssignment.objects.filter(
            class_group=active_class, framework__is_active=True
        ).values_list("framework_id", flat=True)
    )

    if fw_ids:
        areas = AssessmentArea.objects.filter(
            framework_id__in=fw_ids
        ).select_related("subject").prefetch_related("statements")
    else:
        areas = AssessmentArea.objects.filter(
            framework__is_active=True
        ).select_related("subject").prefetch_related("statements")

    # Latest status per student+statement
    from django.db.models import Max
    latest_qs = (
        AssessmentRecord.objects.filter(student_id__in=student_ids)
        .values("student_id", "statement_id")
        .annotate(latest_id=Max("id"))
    )
    latest_ids = [r["latest_id"] for r in latest_qs]
    status_lookup = {}
    if latest_ids:
        for rec in AssessmentRecord.objects.filter(id__in=latest_ids).values(
            "student_id", "statement_id", "status"
        ):
            status_lookup[(rec["student_id"], rec["statement_id"])] = rec["status"]

    cp_areas = []
    for area in areas:
        stmt_ids = [s.pk for s in area.statements.all()]
        if not stmt_ids:
            continue
        counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
        total = len(stmt_ids) * len(student_ids)
        for sid in student_ids:
            for stid in stmt_ids:
                st = status_lookup.get((sid, stid), "NYA")
                counts[st] += 1
        t = total or 1
        cp_areas.append({
            "name": area.name,
            "subject": area.subject.name,
            "counts": counts,
            "total": total,
            "pcts": {k: round(v / t * 100) for k, v in counts.items()},
        })

    return {"cp_areas": cp_areas[:8], "cp_class": active_class}


# ── Widget Registry ─────────────────────────────────────────────────

SIZE_ORDER = ["sm", "md", "lg"]

WIDGET_REGISTRY = [
    {
        "id": "school_overview",
        "title": "School Overview",
        "icon": "bi-building",
        "description": "Whole-school stats: students, assessments & staff activity.",
        "template": "core/widgets/school_overview.html",
        "default": True,
        "size": "lg",
        "min_size": "md",
        "max_size": "lg",
        "fetch": _fetch_school_overview,
        "category": "data",
        "roles": ["slt"],
    },
    {
        "id": "attention_banner",
        "title": "Attention Needed",
        "icon": "bi-exclamation-circle",
        "description": "Items that need your attention: reviews, gaps, covers.",
        "template": "core/widgets/attention_banner.html",
        "default": True,
        "size": "lg",
        "min_size": "md",
        "max_size": "lg",
        "fetch": _fetch_attention,
        "category": "targets",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "class_overview",
        "title": "Class Overview",
        "icon": "bi-speedometer2",
        "description": "Key stats: students, assessments & evidence this term.",
        "template": "core/widgets/class_overview.html",
        "default": True,
        "size": "lg",
        "min_size": "md",
        "max_size": "lg",
        "fetch": _fetch_class_overview,
        "category": "data",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "my_subjects",
        "title": "My Subjects",
        "icon": "bi-journal-bookmark",
        "description": "Cross-class overview for your subjects.",
        "template": "core/widgets/my_subjects.html",
        "default": True,
        "size": "md",
        "min_size": "sm",
        "max_size": "lg",
        "fetch": _fetch_my_subjects,
        "category": "data",
        "roles": ["lead"],
    },
    {
        "id": "my_class",
        "title": "My Class",
        "icon": "bi-people-fill",
        "description": "Your student list with quick links.",
        "template": "core/widgets/my_class.html",
        "default": True,
        "size": "md",
        "min_size": "md",
        "max_size": "lg",
        "fetch": _fetch_my_class,
        "category": "people",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "assessment_summary",
        "title": "Assessment Summary",
        "icon": "bi-pie-chart-fill",
        "description": "RAG status breakdown across your class.",
        "template": "core/widgets/assessment_summary.html",
        "default": True,
        "size": "sm",
        "min_size": "sm",
        "max_size": "lg",
        "fetch": _fetch_assessment_summary,
        "category": "data",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "quick_actions",
        "title": "Quick Actions",
        "icon": "bi-lightning-charge",
        "description": "Shortcuts to common tasks.",
        "template": "core/widgets/quick_actions.html",
        "default": True,
        "size": "sm",
        "min_size": "sm",
        "max_size": "sm",
        "fetch": _fetch_quick_actions,
        "category": "actions",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "class_progress",
        "title": "Class Progress",
        "icon": "bi-bar-chart-line",
        "description": "Assessment progress breakdown for your class by area.",
        "template": "core/widgets/class_progress.html",
        "default": True,
        "size": "lg",
        "min_size": "md",
        "max_size": "lg",
        "fetch": _fetch_class_progress,
        "category": "data",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "recent_activity",
        "title": "Recent Activity",
        "icon": "bi-clock-history",
        "description": "Your latest assessment recordings.",
        "template": "core/widgets/recent_activity.html",
        "default": True,
        "size": "sm",
        "min_size": "sm",
        "max_size": "md",
        "fetch": _fetch_recent_activity,
        "category": "activity",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "ehcp_overview",
        "title": "EHCP Targets",
        "icon": "bi-bullseye",
        "description": "EHCP target status summary for your class.",
        "template": "core/widgets/ehcp_overview.html",
        "default": True,
        "size": "sm",
        "min_size": "sm",
        "max_size": "lg",
        "fetch": _fetch_ehcp_overview,
        "category": "targets",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "evidence_stats",
        "title": "Evidence This Term",
        "icon": "bi-camera-video",
        "description": "Evidence capture stats for the current term.",
        "template": "core/widgets/evidence_stats.html",
        "default": False,
        "size": "sm",
        "min_size": "sm",
        "max_size": "md",
        "fetch": _fetch_evidence_stats,
        "category": "data",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "covering",
        "title": "Currently Covering",
        "icon": "bi-arrow-left-right",
        "description": "Classes you are currently covering.",
        "template": "core/widgets/covering.html",
        "default": True,
        "size": "sm",
        "min_size": "sm",
        "max_size": "sm",
        "fetch": _fetch_covering,
        "category": "people",
        "roles": ["teacher", "lead"],
    },
    {
        "id": "upcoming_reviews",
        "title": "Upcoming Reviews",
        "icon": "bi-calendar-event",
        "description": "EHCP targets due for review soon.",
        "template": "core/widgets/upcoming_reviews.html",
        "default": False,
        "size": "sm",
        "min_size": "sm",
        "max_size": "md",
        "fetch": _fetch_upcoming_reviews,
        "category": "targets",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "assessment_gaps",
        "title": "Assessment Gaps",
        "icon": "bi-exclamation-triangle",
        "description": "Students with fewest assessments this term.",
        "template": "core/widgets/assessment_gaps.html",
        "default": False,
        "size": "sm",
        "min_size": "sm",
        "max_size": "md",
        "fetch": _fetch_assessment_gaps,
        "category": "targets",
        "roles": ["teacher", "lead", "slt"],
    },
    {
        "id": "notifications_widget",
        "title": "Notifications",
        "icon": "bi-bell",
        "description": "Your latest unread notifications.",
        "template": "core/widgets/notifications_widget.html",
        "default": False,
        "size": "sm",
        "min_size": "sm",
        "max_size": "sm",
        "fetch": _fetch_notifications,
        "category": "activity",
        "roles": ["teacher", "lead", "slt"],
    },
]

WIDGET_MAP = {w["id"]: w for w in WIDGET_REGISTRY}

DEFAULT_LAYOUT = [
    {"widget_id": w["id"], "visible": w["default"], "size": w["size"]}
    for w in WIDGET_REGISTRY
]


# ── Role-based default layouts ──────────────────────────────────────

# Which widgets are visible by default for each role group
_ROLE_DEFAULTS = {
    "teacher": {
        "school_overview": False,
        "attention_banner": True,
        "class_overview": True,
        "my_subjects": False,
        "my_class": True,
        "assessment_summary": True,
        "quick_actions": True,
        "class_progress": True,
        "recent_activity": True,
        "ehcp_overview": True,
        "evidence_stats": False,
        "covering": True,
        "upcoming_reviews": False,
        "assessment_gaps": False,
        "notifications_widget": False,
    },
    "lead": {
        "school_overview": False,
        "attention_banner": True,
        "class_overview": True,
        "my_subjects": True,
        "my_class": True,
        "assessment_summary": True,
        "quick_actions": True,
        "class_progress": True,
        "recent_activity": True,
        "ehcp_overview": True,
        "evidence_stats": False,
        "covering": False,
        "upcoming_reviews": False,
        "assessment_gaps": True,
        "notifications_widget": False,
    },
    "slt": {
        "school_overview": True,
        "attention_banner": True,
        "class_overview": True,
        "my_subjects": False,
        "my_class": False,
        "assessment_summary": True,
        "quick_actions": True,
        "class_progress": True,
        "recent_activity": True,
        "ehcp_overview": True,
        "evidence_stats": False,
        "covering": False,
        "upcoming_reviews": True,
        "assessment_gaps": True,
        "notifications_widget": False,
    },
}


def get_role_default_layout(role_group):
    """Build the default widget layout for a given role group."""
    defaults = _ROLE_DEFAULTS.get(role_group, _ROLE_DEFAULTS["teacher"])
    layout = []
    for w in WIDGET_REGISTRY:
        visible = defaults.get(w["id"], w["default"])
        layout.append({
            "widget_id": w["id"],
            "visible": visible,
            "size": w["size"],
        })
    return layout


def get_user_layout(user):
    """Return the ordered widget layout for a user, back-filling any new widgets."""
    from .models import DashboardPreference

    role_group = get_role_group(user)
    default_layout = get_role_default_layout(role_group)

    pref, created = DashboardPreference.objects.get_or_create(
        user=user, defaults={"widget_layout": default_layout}
    )

    # If freshly created, return the role-based defaults
    if created:
        return default_layout

    layout = pref.widget_layout or []

    # Back-fill any widgets added since the user last saved
    existing_ids = {item["widget_id"] for item in layout}
    role_defaults = _ROLE_DEFAULTS.get(role_group, _ROLE_DEFAULTS["teacher"])
    for w in WIDGET_REGISTRY:
        if w["id"] not in existing_ids:
            visible = role_defaults.get(w["id"], w["default"])
            layout.append({"widget_id": w["id"], "visible": visible, "size": w["size"]})

    # Remove widgets that no longer exist in registry, back-fill missing size
    clean = []
    for item in layout:
        wid = item["widget_id"]
        if wid not in WIDGET_MAP:
            continue
        if "size" not in item:
            item["size"] = WIDGET_MAP[wid]["size"]
        # Clamp to allowed range
        w_def = WIDGET_MAP[wid]
        min_idx = SIZE_ORDER.index(w_def["min_size"])
        max_idx = SIZE_ORDER.index(w_def["max_size"])
        cur_idx = SIZE_ORDER.index(item["size"]) if item["size"] in SIZE_ORDER else min_idx
        item["size"] = SIZE_ORDER[max(min_idx, min(max_idx, cur_idx))]
        clean.append(item)

    return clean
