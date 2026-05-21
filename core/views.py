from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import JsonResponse
from students.models import ClassGroup
from staff.models import ClassAssignment, ClassCover
from assessments.models import AssessmentRecord
from .models import AcademicYear, Term, AISettings, DashboardPreference
from .decorators import slt_required
from .widgets import WIDGET_MAP, WIDGET_REGISTRY, SIZE_ORDER, get_user_layout, DEFAULT_LAYOUT, get_role_group, get_role_default_layout, CATEGORY_COLOURS
from django.utils import timezone
import json
import logging

logger = logging.getLogger(__name__)


# ── Setup hub ──────────────────────────────────────────────────────

@slt_required
def setup_hub(request):
    """Central setup page listing all configuration sections."""
    sections = [
        {
            "title": "Academic Year Setup",
            "icon": "bi-calendar3",
            "desc": "Manage academic years and terms.",
            "url": "core:academic_year_setup",
            "colour": "primary",
        },
        {
            "title": "Classes & Pathways",
            "icon": "bi-diagram-3",
            "desc": "Assign each class to a pathway (Explorers, Horizons, Futures, Preparations) and phase.",
            "url": "core:classes_manage",
            "colour": "primary",
        },
        {
            "title": "Subjects",
            "icon": "bi-book",
            "desc": "Manage taught subjects, applicable pathways/phases, and ordering.",
            "url": "core:subjects_manage",
            "colour": "primary",
        },
        {
            "title": "Users",
            "icon": "bi-people",
            "desc": "Manage staff accounts and permissions.",
            "url": "core:users_manage",
            "colour": "primary",
        },
        {
            "title": "AI Settings",
            "icon": "bi-robot",
            "desc": "Configure AI provider, API key and model.",
            "url": "core:ai_settings",
            "colour": "info",
        },
        {
            "title": "Arbor Integration",
            "icon": "bi-cloud-arrow-up",
            "desc": "Push assessment data to Arbor MIS for parent portal.",
            "url": "core:arbor_settings",
            "colour": "success",
        },
    ]
    return render(request, "core/setup_hub.html", {"sections": sections})


@slt_required
def classes_manage(request):
    """SLT page to set the pathway + phase for each class.

    Students inherit pathway/phase from their class on save.
    """
    from students.models import Student, PATHWAY_CHOICES, PHASE_CHOICES

    classes = ClassGroup.objects.all().order_by("name")

    if request.method == "POST":
        updated = 0
        for cg in classes:
            pw = request.POST.get(f"pathway_{cg.pk}", "").strip()
            ph_raw = request.POST.get(f"phase_{cg.pk}", "").strip()
            ph = int(ph_raw) if ph_raw.isdigit() else None

            valid_pw = {code for code, _ in PATHWAY_CHOICES}
            if pw and pw not in valid_pw:
                pw = ""
            # Phase only meaningful for Preparations
            if pw != "PREP":
                ph = None

            changed = False
            if cg.pathway != pw:
                cg.pathway = pw
                changed = True
            if cg.phase != ph:
                cg.phase = ph
                changed = True
            if changed:
                cg.save(update_fields=["pathway", "phase"])
                # Re-save students so their pathway/phase mirrors the class
                for s in cg.students.all():
                    s.save(update_fields=["pathway", "phase"])
                updated += 1

        messages.success(request, f"Updated {updated} class(es).")
        return redirect("core:classes_manage")

    rows = []
    for cg in classes:
        rows.append({
            "cg": cg,
            "student_count": cg.students.count(),
        })

    return render(request, "core/classes_manage.html", {
        "rows": rows,
        "pathway_choices": PATHWAY_CHOICES,
        "phase_choices": PHASE_CHOICES,
    })


@slt_required
def subjects_manage(request):
    """SLT page to manage Subjects: name, applicable pathways/phases, order, active state.

    Also supports adding / deleting subjects (with safety checks).
    """
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from students.models import Subject, PATHWAY_CHOICES, PHASE_CHOICES
    from assessments.models import AssessmentArea, AssessmentRecord
    from staff.models import SubjectLead

    User = get_user_model()

    # Candidates for "Subject Lead" assignment: active users whose
    # StaffProfile.role is subject_lead (or SLT, who often also lead a
    # subject). Superusers are included for completeness.
    lead_candidates = list(
        User.objects.filter(is_active=True)
        .filter(
            Q(staffprofile__role__in=["subject_lead", "slt"])
            | Q(is_superuser=True)
        )
        .distinct()
        .order_by("last_name", "first_name", "username")
    )

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "add":
            name = request.POST.get("new_name", "").strip()
            if not name:
                messages.error(request, "Subject name is required.")
            elif Subject.objects.filter(name__iexact=name).exists():
                messages.error(request, f"A subject called {name!r} already exists.")
            else:
                Subject.objects.create(
                    name=name,
                    short_name=request.POST.get("new_short_name", "").strip()[:20],
                    applicable_pathways=[c for c, _ in PATHWAY_CHOICES],
                    applicable_phases=[1, 2],
                    is_active=True,
                    order=Subject.objects.count(),
                )
                messages.success(request, f"Created subject {name!r}.")
            return redirect("core:subjects_manage")

        if action == "delete":
            sid = request.POST.get("subject_id")
            try:
                subj = Subject.objects.get(pk=sid)
            except Subject.DoesNotExist:
                messages.error(request, "Subject not found.")
                return redirect("core:subjects_manage")
            n_records = AssessmentRecord.objects.filter(statement__area__subject=subj).count()
            n_areas = AssessmentArea.objects.filter(subject=subj).count()
            if n_records > 0 or n_areas > 0:
                messages.error(
                    request,
                    f"Cannot delete {subj.name!r}: it has {n_areas} assessment area(s) "
                    f"and {n_records} record(s). Move or delete those first."
                )
            else:
                subj.delete()
                messages.success(request, f"Deleted subject {subj.name!r}.")
            return redirect("core:subjects_manage")

        # action == "save" — bulk update existing subjects
        valid_pw = {c for c, _ in PATHWAY_CHOICES}
        valid_ph = {n for n, _ in PHASE_CHOICES}
        updated = 0
        for s in Subject.objects.all():
            new_name = request.POST.get(f"name_{s.pk}", s.name).strip() or s.name
            new_short = request.POST.get(f"short_{s.pk}", "").strip()[:20]
            new_order_raw = request.POST.get(f"order_{s.pk}", "").strip()
            new_order = int(new_order_raw) if new_order_raw.isdigit() else s.order
            new_active = request.POST.get(f"active_{s.pk}") == "on"
            new_pathways = [p for p in request.POST.getlist(f"pathways_{s.pk}") if p in valid_pw]
            new_phases = [int(p) for p in request.POST.getlist(f"phases_{s.pk}") if p.isdigit() and int(p) in valid_ph]

            changed = False
            if new_name != s.name:
                # Avoid duplicate names
                if Subject.objects.exclude(pk=s.pk).filter(name__iexact=new_name).exists():
                    messages.warning(request, f"Skipped rename of {s.name!r}: another subject already uses {new_name!r}.")
                else:
                    s.name = new_name
                    changed = True
            if new_short != s.short_name:
                s.short_name = new_short
                changed = True
            if new_order != s.order:
                s.order = new_order
                changed = True
            if new_active != s.is_active:
                s.is_active = new_active
                changed = True
            if list(new_pathways) != list(s.applicable_pathways or []):
                s.applicable_pathways = new_pathways
                changed = True
            if list(new_phases) != list(s.applicable_phases or []):
                s.applicable_phases = new_phases
                changed = True
            if changed:
                s.save()
                updated += 1

            # Sync subject leads for this subject. Posted IDs that aren't in
            # lead_candidates are ignored (defence against tampering).
            valid_lead_ids = {u.id for u in lead_candidates}
            posted_lead_ids = set()
            for raw in request.POST.getlist(f"leads_{s.pk}"):
                if raw.isdigit():
                    uid = int(raw)
                    if uid in valid_lead_ids:
                        posted_lead_ids.add(uid)
            current_lead_ids = set(
                SubjectLead.objects.filter(subject=s).values_list("user_id", flat=True)
            )
            to_add = posted_lead_ids - current_lead_ids
            to_remove = current_lead_ids - posted_lead_ids
            if to_add:
                SubjectLead.objects.bulk_create(
                    [SubjectLead(user_id=uid, subject=s) for uid in to_add],
                    ignore_conflicts=True,
                )
            if to_remove:
                SubjectLead.objects.filter(subject=s, user_id__in=to_remove).delete()

        messages.success(request, f"Updated {updated} subject(s).")
        return redirect("core:subjects_manage")

    rows = []
    leads_by_subject = {}
    for sl in SubjectLead.objects.select_related("user").all():
        leads_by_subject.setdefault(sl.subject_id, []).append(sl.user)

    for s in Subject.objects.all().order_by("order", "name"):
        n_areas = AssessmentArea.objects.filter(subject=s).count()
        n_records = AssessmentRecord.objects.filter(statement__area__subject=s).count()
        current_leads = leads_by_subject.get(s.pk, [])
        current_lead_ids = {u.id for u in current_leads}
        rows.append({
            "s": s,
            "n_areas": n_areas,
            "n_records": n_records,
            "deletable": (n_areas == 0 and n_records == 0),
            "current_leads": current_leads,
            "current_lead_ids": current_lead_ids,
        })

    return render(request, "core/subjects_manage.html", {
        "rows": rows,
        "pathway_choices": PATHWAY_CHOICES,
        "phase_choices": PHASE_CHOICES,
        "lead_candidates": lead_candidates,
    })


@slt_required
def users_manage(request):
    """SLT page to manage staff users: role, lead pathway, active state, Arbor link.

    SLT cannot demote themselves below 'slt' (avoids accidentally locking
    the system out of admin). Superusers are listed but their role-edit
    fields are disabled in the UI; they are always treated as having
    full access regardless of StaffProfile.role.
    """
    from django.contrib.auth import get_user_model
    from staff.models import StaffProfile

    User = get_user_model()
    PATHWAY_LEAD_CHOICES = [
        ("", "—"),
        ("PREP", "Preparations"),
        ("EXP", "Explorers"),
        ("FUT", "Futures"),
        ("HOR", "Horizons"),
    ]

    if request.method == "POST":
        action = request.POST.get("action", "save")
        valid_roles = {c for c, _ in StaffProfile.ROLE_CHOICES}
        valid_lead_pw = {c for c, _ in PATHWAY_LEAD_CHOICES if c}

        if action == "save":
            updated = 0
            for u in User.objects.select_related("staffprofile").all():
                profile, _ = StaffProfile.objects.get_or_create(
                    user=u, defaults={"role": "teacher"},
                )
                changed = False

                # is_active toggle (do not allow toggling self off)
                new_active = request.POST.get(f"active_{u.pk}") == "on"
                if u.id != request.user.id and new_active != u.is_active:
                    u.is_active = new_active
                    u.save(update_fields=["is_active"])
                    changed = True

                # Don't let SLT change role/lead on superusers via this page
                if u.is_superuser:
                    if changed:
                        updated += 1
                    continue

                new_role = request.POST.get(f"role_{u.pk}", profile.role).strip()
                if new_role not in valid_roles:
                    new_role = profile.role
                # Don't let users demote themselves out of SLT
                if u.id == request.user.id and profile.role == "slt" and new_role != "slt":
                    new_role = "slt"
                if new_role != profile.role:
                    profile.role = new_role
                    changed = True

                new_lead = request.POST.get(f"lead_pathway_{u.pk}", "").strip()
                if new_lead and new_lead not in valid_lead_pw:
                    new_lead = ""
                if new_role != "pathway_lead":
                    new_lead = ""
                if new_lead != (profile.lead_pathway or ""):
                    profile.lead_pathway = new_lead
                    changed = True

                aid_raw = request.POST.get(f"arbor_{u.pk}", "").strip()
                if aid_raw == "":
                    new_aid = None
                elif aid_raw.isdigit():
                    new_aid = int(aid_raw)
                else:
                    new_aid = profile.arbor_staff_id
                # Avoid stamping a duplicate arbor_staff_id
                if new_aid != profile.arbor_staff_id:
                    if new_aid is not None and StaffProfile.objects.filter(
                        arbor_staff_id=new_aid
                    ).exclude(pk=profile.pk).exists():
                        messages.warning(
                            request,
                            f"Skipped Arbor ID {new_aid} for {u.get_full_name() or u.username} "
                            f"— already used by another profile."
                        )
                    else:
                        profile.arbor_staff_id = new_aid
                        changed = True

                if changed:
                    profile.save()
                    updated += 1

            messages.success(request, f"Updated {updated} user(s).")
            return redirect("core:users_manage")

    users = User.objects.select_related("staffprofile").order_by(
        "is_active", "last_name", "first_name", "username"
    )
    rows = []
    for u in users:
        profile = getattr(u, "staffprofile", None)
        rows.append({
            "u": u,
            "profile": profile,
            "role": profile.role if profile else "teacher",
            "lead_pathway": profile.lead_pathway if profile else "",
            "arbor_staff_id": profile.arbor_staff_id if profile else None,
            "n_classes": u.class_assignments.count() if hasattr(u, "class_assignments") else 0,
            "is_self": u.id == request.user.id,
        })

    return render(request, "core/users_manage.html", {
        "rows": rows,
        "role_choices": StaffProfile.ROLE_CHOICES,
        "pathway_lead_choices": PATHWAY_LEAD_CHOICES,
        "active_count": sum(1 for r in rows if r["u"].is_active),
        "total_count": len(rows),
    })


@login_required
def dashboard(request):
    """Landing page — customisable widget dashboard."""
    user = request.user
    today = timezone.now().date()
    now = timezone.now()

    # ── Welcome greeting ────────────────────────────────────────
    hour = now.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    first_name = user.first_name or user.username
    role_group = get_role_group(user)
    profile = getattr(user, "staffprofile", None)
    role_display = profile.get_role_display() if profile else "Staff"

    # Get user's designated classes
    assigned_classes = ClassGroup.objects.filter(
        assignments__user=user
    ).distinct()

    # Get classes currently covered by this user
    covered_classes = ClassGroup.objects.filter(
        covers__user=user,
        covers__start_date__lte=today,
        covers__end_date__gte=today,
    ).distinct()

    # Primary class is the first assigned class (or first covered class)
    my_class = assigned_classes.first()
    active_class = my_class  # the class shown in the widget
    if not active_class and covered_classes.exists():
        active_class = covered_classes.first()

    # Recent assessments by this user
    recent_assessments = (
        AssessmentRecord.objects.filter(assessed_by=user)
        .select_related("student", "statement__area__subject")
        .order_by("-assessed_date")[:10]
    )

    # Students in my class OR covered class
    students = []
    if active_class:
        students = active_class.students.filter(is_active=True).order_by(
            "last_name", "first_name"
        )
    # SLT / pathway leads with no class see the pathway-tile view instead
    # (rendered by the my_class widget) — no flat student dump needed.

    base_context = {
        "my_class": my_class,
        "active_class": active_class,
        "assigned_classes": assigned_classes,
        "covered_classes": covered_classes,
        "students": students,
        "recent_assessments": recent_assessments,
    }

    # Build widget data based on user layout
    layout = get_user_layout(user)
    widgets = []
    for item in layout:
        widget_def = WIDGET_MAP.get(item["widget_id"])
        if not widget_def:
            continue
        visible = item.get("visible", True)
        user_size = item.get("size", widget_def["size"])
        widget_ctx = widget_def["fetch"](request, base_context)
        can_resize = widget_def["min_size"] != widget_def["max_size"]
        category = widget_def.get("category", "data")
        widgets.append({
            **widget_def,
            "visible": visible,
            "current_size": user_size,
            "can_resize": can_resize,
            "extra_context": widget_ctx,
            "category": category,
            "border_colour": CATEGORY_COLOURS.get(category, "#0d6efd"),
        })

    context = {
        **base_context,
        "widgets": widgets,
        "widget_registry": WIDGET_REGISTRY,
        "greeting": greeting,
        "first_name": first_name,
        "role_group": role_group,
        "role_display": role_display,
        "today": today,
        "category_colours": CATEGORY_COLOURS,
    }
    return render(request, "core/dashboard.html", context)


@login_required
@require_POST
def save_widget_layout(request):
    """Save the user's widget layout preferences (HTMX)."""
    try:
        body = json.loads(request.body)
        layout = body.get("layout", [])
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"ok": False}, status=400)

    # Validate: only allow known widget IDs and valid sizes
    clean = []
    for item in layout:
        wid = item.get("widget_id", "")
        if wid in WIDGET_MAP:
            size = item.get("size", WIDGET_MAP[wid]["size"])
            if size not in SIZE_ORDER:
                size = WIDGET_MAP[wid]["size"]
            clean.append({
                "widget_id": wid,
                "visible": bool(item.get("visible", True)),
                "size": size,
            })

    pref, _ = DashboardPreference.objects.get_or_create(
        user=request.user, defaults={"widget_layout": DEFAULT_LAYOUT}
    )
    pref.widget_layout = clean
    pref.save()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def toggle_widget(request):
    """Toggle a single widget's visibility (HTMX)."""
    widget_id = request.POST.get("widget_id", "")
    if widget_id not in WIDGET_MAP:
        return JsonResponse({"ok": False}, status=400)

    layout = get_user_layout(request.user)
    for item in layout:
        if item["widget_id"] == widget_id:
            item["visible"] = not item["visible"]
            break

    pref, _ = DashboardPreference.objects.get_or_create(
        user=request.user, defaults={"widget_layout": DEFAULT_LAYOUT}
    )
    pref.widget_layout = layout
    pref.save()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def resize_widget(request):
    """Cycle a widget to its next allowed size."""
    widget_id = request.POST.get("widget_id", "")
    if widget_id not in WIDGET_MAP:
        return JsonResponse({"ok": False}, status=400)

    w_def = WIDGET_MAP[widget_id]
    min_idx = SIZE_ORDER.index(w_def["min_size"])
    max_idx = SIZE_ORDER.index(w_def["max_size"])
    allowed = SIZE_ORDER[min_idx:max_idx + 1]

    layout = get_user_layout(request.user)
    new_size = w_def["size"]
    for item in layout:
        if item["widget_id"] == widget_id:
            cur = item.get("size", w_def["size"])
            cur_pos = allowed.index(cur) if cur in allowed else 0
            new_size = allowed[(cur_pos + 1) % len(allowed)]
            item["size"] = new_size
            break

    pref, _ = DashboardPreference.objects.get_or_create(
        user=request.user, defaults={"widget_layout": DEFAULT_LAYOUT}
    )
    pref.widget_layout = layout
    pref.save()
    return JsonResponse({"ok": True, "size": new_size})


@login_required
@require_POST
def reset_widget_layout(request):
    """Reset dashboard to default layout."""
    role_group = get_role_group(request.user)
    role_layout = get_role_default_layout(role_group)
    pref, _ = DashboardPreference.objects.get_or_create(
        user=request.user, defaults={"widget_layout": role_layout}
    )
    pref.widget_layout = role_layout
    pref.save()
    return JsonResponse({"ok": True})


# ── Academic Year Setup ──────────────────────────────────────────────

@login_required
@slt_required
def academic_year_setup(request):
    """Manage academic years and their terms."""
    years = AcademicYear.objects.prefetch_related("terms").all()
    context = {"years": years}
    return render(request, "core/academic_year_setup.html", context)


@login_required
@slt_required
def create_academic_year(request):
    """Create a new academic year with its three terms."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        start_date = request.POST.get("start_date", "").strip()
        end_date = request.POST.get("end_date", "").strip()
        is_current = request.POST.get("is_current") == "on"

        if not name or not start_date or not end_date:
            messages.error(request, "Name, start date, and end date are required.")
            return redirect("core:create_academic_year")

        from datetime import date as dt_date
        try:
            sd = dt_date.fromisoformat(start_date)
            ed = dt_date.fromisoformat(end_date)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect("core:create_academic_year")

        if AcademicYear.objects.filter(name=name).exists():
            messages.warning(request, f'Academic year "{name}" already exists.')
            return redirect("core:academic_year_setup")

        ay = AcademicYear.objects.create(
            name=name, start_date=sd, end_date=ed, is_current=is_current
        )

        # Auto-create terms if provided
        for term_code in ["AUT", "SPR", "SUM"]:
            t_start = request.POST.get(f"{term_code}_start", "").strip()
            t_end = request.POST.get(f"{term_code}_end", "").strip()
            if t_start and t_end:
                try:
                    Term.objects.create(
                        academic_year=ay,
                        name=term_code,
                        start_date=dt_date.fromisoformat(t_start),
                        end_date=dt_date.fromisoformat(t_end),
                    )
                except ValueError:
                    pass

        messages.success(request, f'Academic year "{name}" created.')
        return redirect("core:academic_year_setup")

    return render(request, "core/academic_year_form.html")


@login_required
@slt_required
def edit_academic_year(request, pk):
    """Edit an existing academic year and its terms."""
    ay = get_object_or_404(AcademicYear, pk=pk)

    if request.method == "POST":
        ay.name = request.POST.get("name", ay.name).strip()
        start_date = request.POST.get("start_date", "").strip()
        end_date = request.POST.get("end_date", "").strip()
        ay.is_current = request.POST.get("is_current") == "on"

        from datetime import date as dt_date
        try:
            if start_date:
                ay.start_date = dt_date.fromisoformat(start_date)
            if end_date:
                ay.end_date = dt_date.fromisoformat(end_date)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect("core:edit_academic_year", pk=pk)

        ay.save()

        # Update or create terms
        for term_code in ["AUT", "SPR", "SUM"]:
            t_start = request.POST.get(f"{term_code}_start", "").strip()
            t_end = request.POST.get(f"{term_code}_end", "").strip()
            if t_start and t_end:
                try:
                    term, created = Term.objects.update_or_create(
                        academic_year=ay,
                        name=term_code,
                        defaults={
                            "start_date": dt_date.fromisoformat(t_start),
                            "end_date": dt_date.fromisoformat(t_end),
                        },
                    )
                except ValueError:
                    pass

        messages.success(request, f'Academic year "{ay.name}" updated.')
        return redirect("core:academic_year_setup")

    terms = {t.name: t for t in ay.terms.all()}
    context = {"ay": ay, "terms": terms}
    return render(request, "core/academic_year_form.html", context)


@login_required
@slt_required
@require_POST
def delete_academic_year(request, pk):
    """Delete an academic year and its terms."""
    ay = get_object_or_404(AcademicYear, pk=pk)
    name = ay.name
    ay.delete()
    messages.success(request, f'Academic year "{name}" deleted.')
    return redirect("core:academic_year_setup")


# ── Sync Academic Years from Arbor ─────────────────────────────────

@login_required
@slt_required
def sync_academic_years_from_arbor(request):
    """
    GET  → fetch academic years + terms from Arbor, show preview.
    POST → create/update local AcademicYear + Term records from Arbor data.
    """
    from datetime import date as dt_date
    from .arbor import get_arbor_client

    client, err = get_arbor_client()
    if err:
        messages.error(request, f"Arbor not available: {err}")
        return redirect("core:academic_year_setup")

    # ── POST: perform the sync ─────────────────────────────────────
    if request.method == "POST":
        selected_ids = request.POST.getlist("year_ids")
        if not selected_ids:
            messages.warning(request, "No academic years selected.")
            return redirect("core:sync_academic_years_from_arbor")

        try:
            arbor_years = client.fetch_academic_years()
            arbor_periods = client.fetch_measurement_periods()
        except Exception as e:
            messages.error(request, f"Failed to fetch from Arbor: {e}")
            return redirect("core:academic_year_setup")

        # Index periods by academic year Arbor ID
        periods_by_year = {}
        for p in arbor_periods:
            ay_ref = p.get("academicYear") or {}
            ay_id = str(ay_ref.get("id", ""))
            if ay_id:
                periods_by_year.setdefault(ay_id, []).append(p)

        created = 0
        updated = 0
        errors = []

        for ay in arbor_years:
            arbor_id = str(ay.get("id", ""))
            if arbor_id not in selected_ids:
                continue

            name = (ay.get("displayName") or "").strip()
            start_raw = ay.get("startDate", "")
            end_raw = ay.get("endDate", "")

            if not name or not start_raw or not end_raw:
                errors.append(f"Skipped year with missing data: {ay}")
                continue

            try:
                sd = dt_date.fromisoformat(start_raw[:10])
                ed = dt_date.fromisoformat(end_raw[:10])
            except (ValueError, TypeError):
                errors.append(f"Bad dates for {name}: {start_raw} / {end_raw}")
                continue

            local_ay, was_created = AcademicYear.objects.update_or_create(
                name=name,
                defaults={"start_date": sd, "end_date": ed},
            )
            if was_created:
                created += 1
            else:
                updated += 1

            # Sync terms from measurement periods
            TERM_MAP = {
                "autumn": "AUT", "aut": "AUT",
                "spring": "SPR", "spr": "SPR",
                "summer": "SUM", "sum": "SUM",
            }
            for period in periods_by_year.get(arbor_id, []):
                period_name = (period.get("periodName") or period.get("shortName") or "").strip()
                p_start = period.get("startDate", "")
                p_end = period.get("endDate", "")

                # Match to AUT/SPR/SUM
                term_code = None
                for keyword, code in TERM_MAP.items():
                    if keyword in period_name.lower():
                        term_code = code
                        break

                if not term_code or not p_start or not p_end:
                    continue

                try:
                    t_sd = dt_date.fromisoformat(p_start[:10])
                    t_ed = dt_date.fromisoformat(p_end[:10])
                except (ValueError, TypeError):
                    continue

                Term.objects.update_or_create(
                    academic_year=local_ay,
                    name=term_code,
                    defaults={"start_date": t_sd, "end_date": t_ed},
                )

        parts = []
        if created:
            parts.append(f"{created} created")
        if updated:
            parts.append(f"{updated} updated")
        if errors:
            parts.append(f"{len(errors)} skipped")
        messages.success(request, f"Arbor sync complete: {', '.join(parts) or 'nothing to sync'}.")

        if errors:
            messages.warning(request, "Some items skipped: " + "; ".join(errors[:5]))

        return redirect("core:academic_year_setup")

    # ── GET: fetch and show preview ────────────────────────────────
    try:
        arbor_years = client.fetch_academic_years()
        arbor_periods = client.fetch_measurement_periods()
    except Exception as e:
        messages.error(request, f"Could not fetch from Arbor: {e}")
        return redirect("core:academic_year_setup")

    # Index periods by academic year ID
    periods_by_year = {}
    for p in arbor_periods:
        ay_ref = p.get("academicYear") or {}
        ay_id = str(ay_ref.get("id", ""))
        if ay_id:
            periods_by_year.setdefault(ay_id, []).append(p)

    # Build preview list
    existing_names = set(AcademicYear.objects.values_list("name", flat=True))
    preview = []
    for ay in sorted(arbor_years, key=lambda x: x.get("startDate", ""), reverse=True):
        arbor_id = str(ay.get("id", ""))
        name = (ay.get("displayName") or "").strip()
        periods = periods_by_year.get(arbor_id, [])
        preview.append({
            "arbor_id": arbor_id,
            "name": name,
            "start_date": (ay.get("startDate") or "")[:10],
            "end_date": (ay.get("endDate") or "")[:10],
            "exists": name in existing_names,
            "periods": [
                {
                    "name": p.get("periodName") or p.get("shortName") or "?",
                    "start": (p.get("startDate") or "")[:10],
                    "end": (p.get("endDate") or "")[:10],
                }
                for p in periods
            ],
        })

    return render(request, "core/sync_academic_years.html", {"preview": preview})


# ── AI Settings ────────────────────────────────────────────────────

@slt_required
def ai_settings(request):
    """View / edit AI provider configuration (singleton)."""
    settings = AISettings.load()

    if request.method == "POST":
        settings.provider = request.POST.get("provider", "none")
        settings.api_key = request.POST.get("api_key", "").strip()
        settings.endpoint_url = request.POST.get("endpoint_url", "").strip()
        settings.model_name = request.POST.get("model_name", "").strip()
        settings.enabled = request.POST.get("enabled") == "on"
        settings.save()
        messages.success(request, "AI settings saved.")
        return redirect("core:ai_settings")

    return render(request, "core/ai_settings.html", {"settings": settings})


@slt_required
@require_POST
def ai_test_connection(request):
    """Test the configured AI provider connection. Returns JSON."""
    from django.http import JsonResponse
    from core.ai import ai_chat

    reply, err = ai_chat("Say OK", max_tokens=5, timeout=15)
    if err:
        return JsonResponse({"ok": False, "msg": err})
    return JsonResponse({
        "ok": True,
        "msg": f'Connected! Model replied: "{reply[:80]}"',
    })


# ── Arbor Integration ─────────────────────────────────────────────

@slt_required
def arbor_settings(request):
    """View / edit Arbor API configuration (singleton)."""
    from .models import ArborSettings

    cfg = ArborSettings.load()

    if request.method == "POST":
        cfg.base_url = request.POST.get("base_url", "").strip()
        cfg.app_username = request.POST.get("app_username", "").strip()
        cfg.api_key = request.POST.get("api_key", "").strip()
        cfg.enabled = request.POST.get("enabled") == "on"
        cfg.save()
        messages.success(request, "Arbor settings saved.")
        return redirect("core:arbor_settings")

    return render(request, "core/arbor_settings.html", {"arbor": cfg})


@slt_required
@require_POST
def arbor_test_connection(request):
    """Test Arbor credentials. Returns JSON."""
    from .arbor import get_arbor_client

    client, err = get_arbor_client()
    if err:
        return JsonResponse({"ok": False, "msg": err})

    ok, msg = client.test_connection()
    if ok:
        from .models import ArborSettings
        cfg = ArborSettings.load()
        cfg.last_connected = timezone.now()
        cfg.save()
    return JsonResponse({"ok": ok, "msg": msg})


@slt_required
def arbor_discover(request):
    """Discover entities from Arbor and present mapping UI."""
    from .arbor import get_arbor_client
    from .models import ArborMapping
    from students.models import Subject

    client, err = get_arbor_client()
    if err:
        messages.error(request, f"Cannot connect to Arbor: {err}")
        return redirect("core:arbor_settings")

    # Pull data from Arbor
    try:
        arbor_assessments = client.fetch_assessments()
        arbor_grade_sets = client.fetch_grade_sets()
        arbor_periods = client.fetch_measurement_periods()
    except Exception as e:
        messages.error(request, f"Error fetching from Arbor: {e}")
        return redirect("core:arbor_settings")

    # Serialise grades within each grade set for the template JS
    for gs in arbor_grade_sets:
        gs["grades_json"] = json.dumps(gs.get("grades", []))

    # Local data
    subjects = Subject.objects.all()
    terms = Term.objects.select_related("academic_year").all()
    statuses = [("NYA", "Not Yet Assessed"), ("EME", "Emerging"),
                ("DEV", "Developing"), ("SEC", "Secure")]

    # Existing mappings
    existing = {}
    for m in ArborMapping.objects.all():
        existing[(m.entity_type, m.local_id)] = m

    context = {
        "arbor_assessments": arbor_assessments,
        "arbor_grade_sets": arbor_grade_sets,
        "arbor_periods": arbor_periods,
        "subjects": subjects,
        "terms": terms,
        "statuses": statuses,
        "existing_mappings": existing,
    }
    return render(request, "core/arbor_mappings.html", context)


@slt_required
@require_POST
def arbor_save_mappings(request):
    """Save entity mappings from the discovery page."""
    from .models import ArborMapping

    body = json.loads(request.body)
    mappings = body.get("mappings", [])

    for item in mappings:
        entity_type = item.get("entity_type", "")
        local_id = item.get("local_id", "")
        if not entity_type or not local_id:
            continue
        ArborMapping.objects.update_or_create(
            entity_type=entity_type,
            local_id=str(local_id),
            defaults={
                "local_label": item.get("local_label", ""),
                "arbor_id": item.get("arbor_id", ""),
                "arbor_label": item.get("arbor_label", ""),
                "arbor_href": item.get("arbor_href", ""),
            },
        )
    return JsonResponse({"ok": True})


@slt_required
def arbor_sync(request):
    """Show sync status and trigger sync."""
    from .models import ArborSyncLog, ArborSettings

    cfg = ArborSettings.load()
    logs = ArborSyncLog.objects.all()[:20]
    return render(request, "core/arbor_sync.html", {
        "arbor": cfg,
        "logs": logs,
    })


@slt_required
@require_POST
def arbor_run_sync(request):
    """Execute the assessment data sync to Arbor."""
    from .arbor import get_arbor_client
    from .models import ArborMapping, ArborSyncLog
    from assessments.models import AssessmentRecord

    client, err = get_arbor_client()
    if err:
        return JsonResponse({"ok": False, "msg": err})

    log = ArborSyncLog.objects.create(
        status="running",
        triggered_by=request.user,
    )

    # Load mappings into lookups
    assessment_map = {}   # subject_id → arbor_href
    grade_map = {}        # status_code → arbor_href
    period_map = {}       # term_id → arbor_href
    grade_set_id = None   # the mapped grade set arbor id

    for m in ArborMapping.objects.all():
        if m.entity_type == "assessment" and m.arbor_href:
            assessment_map[m.local_id] = m.arbor_href
        elif m.entity_type == "grade" and m.arbor_href:
            grade_map[m.local_id] = m.arbor_href
        elif m.entity_type == "period" and m.arbor_href:
            period_map[m.local_id] = m.arbor_href

    if not assessment_map:
        log.status = "failed"
        log.summary = "No assessment mappings configured."
        log.finished_at = timezone.now()
        log.save()
        return JsonResponse({"ok": False, "msg": "No assessment mappings configured. Run discovery first."})

    if not grade_map:
        log.status = "failed"
        log.summary = "No grade mappings configured."
        log.finished_at = timezone.now()
        log.save()
        return JsonResponse({"ok": False, "msg": "No grade mappings configured. Run discovery first."})

    # Build student UPN → Arbor href lookup
    try:
        arbor_students = client.fetch_students()
    except Exception as e:
        log.status = "failed"
        log.summary = f"Failed to fetch students: {e}"
        log.finished_at = timezone.now()
        log.save()
        return JsonResponse({"ok": False, "msg": f"Failed to fetch students from Arbor: {e}"})

    upn_to_href = {}
    for s in arbor_students:
        upn = s.get("upn", "")
        sid = s.get("id", "")
        if upn and sid:
            upn_to_href[upn] = f"/rest-v2/students/{sid}"

    # Get assessment records to sync — only latest per student/subject
    records = (
        AssessmentRecord.objects
        .select_related("student", "statement__area__subject")
        .order_by("student", "statement__area__subject", "-assessed_date")
    )

    # Dedupe: latest record per (student, subject)
    seen = set()
    to_sync = []
    for rec in records:
        subject = rec.statement.area.subject
        key = (rec.student_id, subject.id)
        if key not in seen:
            seen.add(key)
            to_sync.append(rec)

    log.records_attempted = len(to_sync)
    errors = []
    success_count = 0

    for rec in to_sync:
        student_upn = rec.student.upn
        subject_id = str(rec.statement.area.subject.id)
        status_code = rec.status
        assessed_date = rec.assessed_date.isoformat()

        # Resolve hrefs
        student_href = upn_to_href.get(student_upn)
        assessment_href = assessment_map.get(subject_id)
        grade_href = grade_map.get(status_code)

        # Find period from assessed_date
        term = Term.objects.filter(
            start_date__lte=rec.assessed_date,
            end_date__gte=rec.assessed_date,
        ).first()
        period_href = period_map.get(str(term.id)) if term else None

        if not student_href:
            errors.append({"student": str(rec.student), "error": f"No UPN match in Arbor (UPN: {student_upn})"})
            continue
        if not assessment_href:
            errors.append({"student": str(rec.student), "error": f"No mapping for subject: {rec.statement.area.subject}"})
            continue
        if not grade_href:
            errors.append({"student": str(rec.student), "error": f"No mapping for status: {status_code}"})
            continue
        if not period_href:
            errors.append({"student": str(rec.student), "error": f"No mapping for term (date: {assessed_date})"})
            continue

        try:
            client.push_assessment_mark(
                student_href=student_href,
                assessment_href=assessment_href,
                period_href=period_href,
                grade_href=grade_href,
                assessment_date=assessed_date,
            )
            success_count += 1
        except Exception as e:
            errors.append({"student": str(rec.student), "error": str(e)})

    log.records_succeeded = success_count
    log.records_failed = len(errors)
    log.error_details = errors[:100]  # cap stored errors
    log.finished_at = timezone.now()
    if errors and success_count > 0:
        log.status = "partial"
        log.summary = f"{success_count} synced, {len(errors)} failed."
    elif errors:
        log.status = "failed"
        log.summary = f"All {len(errors)} records failed."
    else:
        log.status = "success"
        log.summary = f"All {success_count} records synced successfully."
    log.save()

    return JsonResponse({
        "ok": log.status != "failed",
        "msg": log.summary,
        "log_id": log.id,
    })


# ── Arbor Import (read from Arbor → AssessApp) ────────────────────

@slt_required
def arbor_import_preview(request):
    """Wizard-style Arbor import: step 1 = pick year, step 2 = preview."""
    from .arbor import get_arbor_client
    from students.models import Student, ClassGroup
    from django.contrib.auth import get_user_model

    User = get_user_model()

    client, err = get_arbor_client()
    if err:
        messages.error(request, f"Cannot connect to Arbor: {err}")
        return redirect("core:arbor_settings")

    # ── Step 1: Academic Year selection ─────────────────────────
    selected_year_id = request.GET.get("year")

    if not selected_year_id:
        try:
            arbor_years = client.fetch_academic_years()
        except Exception as e:
            messages.error(request, f"Error fetching academic years: {e}")
            return redirect("core:arbor_settings")

        # Sort by startDate descending (most recent first)
        arbor_years.sort(key=lambda y: y.get("startDate", ""), reverse=True)

        # Match against local academic years
        local_years = {ay.name: ay for ay in AcademicYear.objects.all()}
        for y in arbor_years:
            y["local_match"] = local_years.get(y.get("displayName"))

        return render(request, "core/arbor_import.html", {
            "step": 1,
            "arbor_years": arbor_years,
        })

    # ── Step 2: Filtered preview ───────────────────────────────
    try:
        arbor_years = client.fetch_academic_years()
        arbor_students = client.fetch_students_full()
        arbor_forms = client.fetch_registration_forms()
        arbor_staff = client.fetch_staff()
        arbor_tutors = client.fetch_staff_class_links()
    except Exception as e:
        logger.warning("Arbor preview fetch failed: %s", e)
        messages.warning(
            request,
            "Arbor is temporarily rate-limited. Please wait a minute and try again.",
        )
        return redirect("core:arbor_import_preview")

    # Find the selected academic year info
    selected_year = next(
        (y for y in arbor_years if str(y.get("id")) == str(selected_year_id)),
        None,
    )
    if not selected_year:
        messages.error(request, "Selected academic year not found in Arbor.")
        return redirect("core:arbor_import_preview")

    # Create or find matching local AcademicYear
    year_name = selected_year.get("displayName", "")
    from datetime import date as dt_date
    start_raw = selected_year.get("startDate")
    end_raw = selected_year.get("endDate")
    try:
        local_ay, ay_created = AcademicYear.objects.get_or_create(
            name=year_name,
            defaults={
                "start_date": dt_date.fromisoformat(start_raw) if start_raw else dt_date.today(),
                "end_date": dt_date.fromisoformat(end_raw) if end_raw else dt_date.today(),
                "is_current": True,
            },
        )
    except Exception:
        local_ay = AcademicYear.objects.filter(name=year_name).first()
        ay_created = False

    # Filter registration forms to selected academic year
    year_forms = [
        f for f in arbor_forms
        if str((f.get("academicYear") or {}).get("id")) == str(selected_year_id)
    ]
    year_form_ids = {str(f.get("id")) for f in year_forms}

    # ── Build class group preview ──
    local_classes = {cg.name: cg for cg in ClassGroup.objects.all()}
    class_preview = []
    for form in year_forms:
        name = form.get("displayName", "")
        if not name:
            continue
        existing = local_classes.get(name)
        class_preview.append({
            "arbor_id": form.get("id"),
            "name": name,
            "action": "skip" if existing else "create",
            "local_id": existing.id if existing else None,
        })

    # ── Build student preview ──
    local_students = {s.upn: s for s in Student.objects.select_related("class_group").all() if s.upn}
    student_preview = []
    for s in arbor_students:
        upn = (s.get("upn") or "").strip()
        first = s.get("legalFirstName", "")
        last = s.get("legalLastName", "")
        dob_raw = (s.get("person") or {}).get("dateOfBirth")

        # Class from registrationForm (directly on Student)
        reg = s.get("registrationForm") or {}
        class_name = reg.get("displayName") or None
        form_id = str(reg.get("id") or "")

        # Only include students whose registrationForm is in the selected year
        if form_id and form_id not in year_form_ids:
            continue

        existing = local_students.get(upn) if upn else None
        changes = []
        if existing:
            if first and existing.first_name != first:
                changes.append(f"first_name: {existing.first_name} → {first}")
            if last and existing.last_name != last:
                changes.append(f"last_name: {existing.last_name} → {last}")
            if class_name:
                current_class = existing.class_group.name if existing.class_group else None
                if current_class != class_name:
                    changes.append(f"class: {current_class} → {class_name}")

        if existing and not changes:
            action = "skip"
        elif existing:
            action = "update"
        elif upn:
            action = "create"
        else:
            action = "skip_no_upn"

        student_preview.append({
            "arbor_id": s.get("id"),
            "upn": upn,
            "first_name": first,
            "last_name": last,
            "dob": dob_raw,
            "class_name": class_name,
            "action": action,
            "changes": changes,
        })

    # ── Build staff preview ──
    local_staff_names = {}
    for u in User.objects.filter(is_active=True):
        full = f"{u.first_name} {u.last_name}".strip().lower()
        if full:
            local_staff_names[full] = u
    staff_preview = []
    for st in arbor_staff:
        person = st.get("person") or {}
        first = person.get("legalFirstName", "")
        last = person.get("legalLastName", "")
        display = st.get("displayName", "")
        full = f"{first} {last}".strip().lower()

        existing = local_staff_names.get(full)
        if existing:
            action = "skip"
        else:
            action = "create"

        staff_preview.append({
            "arbor_id": st.get("id"),
            "display_name": display,
            "first_name": first,
            "last_name": last,
            "action": action,
        })

    # ── Build staff → class assignments preview (filtered to year) ──
    assignment_preview = []
    for link in arbor_tutors:
        reg = link.get("registrationForm") or {}
        staff_info = link.get("staff") or {}
        form_id = str(reg.get("id") or "")

        # Only include assignments for classes in the selected year
        if form_id not in year_form_ids:
            continue

        class_name = reg.get("displayName", "")
        staff_name = staff_info.get("displayName", "")

        assignment_preview.append({
            "class_name": class_name,
            "staff_name": staff_name,
            "role": "Teacher",
        })

    # Counts for summary
    counts = {
        "classes_create": sum(1 for c in class_preview if c["action"] == "create"),
        "classes_skip": sum(1 for c in class_preview if c["action"] == "skip"),
        "students_create": sum(1 for s in student_preview if s["action"] == "create"),
        "students_update": sum(1 for s in student_preview if s["action"] == "update"),
        "students_skip": sum(1 for s in student_preview if s["action"] == "skip"),
        "students_no_upn": sum(1 for s in student_preview if s["action"] == "skip_no_upn"),
        "staff_create": sum(1 for s in staff_preview if s["action"] == "create"),
        "staff_skip": sum(1 for s in staff_preview if s["action"] == "skip"),
        "assignments": len(assignment_preview),
    }

    return render(request, "core/arbor_import.html", {
        "step": 2,
        "selected_year": selected_year,
        "local_ay": local_ay,
        "ay_created": ay_created,
        "class_preview": class_preview,
        "student_preview": student_preview,
        "staff_preview": staff_preview,
        "assignment_preview": assignment_preview,
        "counts": counts,
    })


@slt_required
@require_POST
def arbor_import_run(request):
    """Execute the import: create/update classes, students, staff, assignments."""
    from .arbor import get_arbor_client
    from students.models import Student, ClassGroup
    from staff.models import StaffProfile, ClassAssignment
    from django.contrib.auth import get_user_model
    import secrets

    User = get_user_model()

    client, err = get_arbor_client()
    if err:
        return JsonResponse({"ok": False, "msg": err})

    body = json.loads(request.body)
    import_classes = body.get("classes", True)
    import_students = body.get("students", True)
    import_staff = body.get("staff", True)
    import_assignments = body.get("assignments", True)
    selected_year_id = body.get("year_id")

    if not selected_year_id:
        return JsonResponse({"ok": False, "msg": "No academic year selected."})

    results = {
        "classes_created": 0,
        "students_created": 0,
        "students_updated": 0,
        "staff_created": 0,
        "assignments_created": 0,
        "errors": [],
    }

    try:
        # Fetch all registration forms and filter to selected year
        all_forms = client.fetch_registration_forms()
        year_forms = [
            f for f in all_forms
            if str((f.get("academicYear") or {}).get("id")) == str(selected_year_id)
        ]
        year_form_ids = {str(f.get("id")) for f in year_forms}

        # ── 1. Class groups (only from selected year) ──
        class_map = {}  # name → ClassGroup
        if import_classes or import_students:
            for form in year_forms:
                name = form.get("displayName", "").strip()
                if not name:
                    continue
                cg, created = ClassGroup.objects.get_or_create(name=name)
                class_map[name] = cg
                if created:
                    results["classes_created"] += 1
            # Also load existing ones not from Arbor
            for cg in ClassGroup.objects.all():
                class_map.setdefault(cg.name, cg)

        # ── 2. Students (filtered to year's registration forms) ──
        if import_students:
            arbor_students = client.fetch_students_full()
            local_students = {s.upn: s for s in Student.objects.all() if s.upn}

            for s in arbor_students:
                upn = (s.get("upn") or "").strip()
                if not upn:
                    continue

                reg = s.get("registrationForm") or {}
                form_id = str(reg.get("id") or "")

                # Skip students not in the selected year's forms
                if form_id and form_id not in year_form_ids:
                    continue

                first = s.get("legalFirstName", "").strip()
                last = s.get("legalLastName", "").strip()
                dob_raw = (s.get("person") or {}).get("dateOfBirth")
                class_name = reg.get("displayName") or None

                existing = local_students.get(upn)
                if existing:
                    updated = False
                    if first and existing.first_name != first:
                        existing.first_name = first
                        updated = True
                    if last and existing.last_name != last:
                        existing.last_name = last
                        updated = True
                    if dob_raw and str(existing.date_of_birth) != dob_raw:
                        existing.date_of_birth = dob_raw
                        updated = True
                    if class_name and class_name in class_map:
                        cg = class_map[class_name]
                        if existing.class_group_id != cg.id:
                            existing.class_group = cg
                            updated = True
                    if updated:
                        existing.save()
                        results["students_updated"] += 1
                else:
                    try:
                        Student.objects.create(
                            upn=upn,
                            first_name=first or "Unknown",
                            last_name=last or "Unknown",
                            date_of_birth=dob_raw or None,
                            class_group=class_map.get(class_name),
                            is_active=True,
                        )
                        results["students_created"] += 1
                    except Exception as e:
                        results["errors"].append(f"Student {upn}: {e}")

        # ── 3. Staff ──
        staff_name_map = {}  # lowercase full name → User
        arbor_staff = client.fetch_staff()
        try:
            staff_roles = client.fetch_staff_roles()
        except Exception:
            staff_roles = {}

        if import_staff:
            local_names = {}
            for u in User.objects.filter(is_active=True):
                full = f"{u.first_name} {u.last_name}".strip().lower()
                if full:
                    local_names[full] = u

            for st in arbor_staff:
                person = st.get("person") or {}
                first = person.get("legalFirstName", "").strip()
                last = person.get("legalLastName", "").strip()
                full = f"{first} {last}".strip().lower()

                if not full:
                    continue

                arbor_id = int(st["id"])
                role = staff_roles.get(arbor_id, "teacher")

                if full in local_names:
                    staff_name_map[full] = local_names[full]
                    user = local_names[full]
                    profile, _ = StaffProfile.objects.get_or_create(
                        user=user,
                        defaults={"role": role},
                    )
                    changed = False
                    # Stamp Arbor staff ID if missing
                    if not profile.arbor_staff_id:
                        profile.arbor_staff_id = arbor_id
                        changed = True
                    # Update role if currently default "teacher" but contract says otherwise
                    if profile.role == "teacher" and role in ("ta", "hlta"):
                        profile.role = role
                        changed = True
                    if changed:
                        profile.save()
                    continue

                # Create user + staff profile
                try:
                    username = f"{first.lower()}.{last.lower()}"
                    # Ensure unique username
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1

                    user = User.objects.create_user(
                        username=username,
                        first_name=first or "",
                        last_name=last or "",
                        password=secrets.token_urlsafe(16),
                    )
                    StaffProfile.objects.get_or_create(
                        user=user,
                        defaults={"role": role},
                    )
                    StaffProfile.objects.filter(user=user).update(
                        arbor_staff_id=arbor_id,
                    )
                    staff_name_map[full] = user
                    results["staff_created"] += 1
                except Exception as e:
                    results["errors"].append(f"Staff {first} {last}: {e}")
        else:
            # Still build name map for assignments
            for u in User.objects.filter(is_active=True):
                full = f"{u.first_name} {u.last_name}".strip().lower()
                if full:
                    staff_name_map[full] = u

        # ── 4. Class assignments (filtered to year) ──
        if import_assignments:
            # Teacher assignments (fast, GraphQL)
            try:
                arbor_tutors = client.fetch_staff_class_links()
            except Exception:
                arbor_tutors = []

            # TA / HLTA assignments from timetable (slower, REST batches)
            import_ta = body.get("ta_assignments", True)
            timetable_links = []
            if import_ta:
                try:
                    timetable_links = client.fetch_ta_class_links(
                        selected_year_id, arbor_staff=arbor_staff,
                    )
                except Exception as e:
                    results["errors"].append(f"TA discovery: {e}")

            # Merge — deduplicate via get_or_create
            all_links = arbor_tutors + timetable_links

            for link in all_links:
                reg = link.get("registrationForm") or {}
                staff_info = link.get("staff") or {}
                staff_person = staff_info.get("person") or {}

                form_id = str(reg.get("id") or "")
                # Only process assignments for the selected year
                if form_id not in year_form_ids:
                    continue

                class_name = (reg.get("displayName") or "").strip()
                first = staff_person.get("legalFirstName", "").strip()
                last = staff_person.get("legalLastName", "").strip()
                staff_full = f"{first} {last}".strip().lower()

                cg = class_map.get(class_name)
                user = staff_name_map.get(staff_full)

                if cg and user:
                    _, created = ClassAssignment.objects.get_or_create(
                        user=user,
                        class_group=cg,
                    )
                    if created:
                        results["assignments_created"] += 1

    except Exception as e:
        return JsonResponse({"ok": False, "msg": f"Import error: {e}"})

    total = (results["classes_created"] + results["students_created"] +
             results["students_updated"] + results["staff_created"] +
             results["assignments_created"])
    error_count = len(results["errors"])

    msg_parts = []
    if results["classes_created"]:
        msg_parts.append(f"{results['classes_created']} classes created")
    if results["students_created"]:
        msg_parts.append(f"{results['students_created']} students created")
    if results["students_updated"]:
        msg_parts.append(f"{results['students_updated']} students updated")
    if results["staff_created"]:
        msg_parts.append(f"{results['staff_created']} staff created")
    if results["assignments_created"]:
        msg_parts.append(f"{results['assignments_created']} class assignments created")
    if error_count:
        msg_parts.append(f"{error_count} errors")

    summary = ". ".join(msg_parts) + "." if msg_parts else "Nothing to import."

    return JsonResponse({
        "ok": error_count == 0 or total > 0,
        "msg": summary,
        "results": results,
    })
