from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from .models import Student, Subject
from assessments.models import (
    AssessmentRecord,
    AssessmentArea,
    AssessmentSnapshot,
)
from core.models import AcademicYear, Term


@login_required
def student_detail(request, pk):
    """Redirect to student hub (student_subjects)."""
    return redirect("assessments:student_subjects", student_id=pk)


@login_required
def student_progress(request, pk):
    """Student progress over time — assessments + EHCP, with tracker grids."""
    student = get_object_or_404(Student, pk=pk)
    from collections import OrderedDict
    from evidence.models import EHCPTarget, EHCPTargetReview

    active_view = request.GET.get("view", "assessments")  # "assessments" or "ehcp"

    # ── Shared date filtering ────────────────────────────────────────
    date_from = None
    date_to = None
    active_period = ""
    default_term = None
    raw_from = request.GET.get("date_from", "").strip()
    raw_to = request.GET.get("date_to", "").strip()
    has_any_filter = any(
        request.GET.get(k) for k in ("date_from", "date_to", "term", "academic_year", "show")
    )

    if raw_from or raw_to:
        from datetime import date as dt_date
        try:
            if raw_from:
                date_from = dt_date.fromisoformat(raw_from)
            if raw_to:
                date_to = dt_date.fromisoformat(raw_to)
        except ValueError:
            pass
        active_period = "custom"
    elif request.GET.get("term"):
        try:
            term = Term.objects.get(pk=int(request.GET["term"]))
            date_from, date_to = term.start_date, term.end_date
            active_period = str(term)
        except (Term.DoesNotExist, ValueError):
            pass
    elif request.GET.get("academic_year"):
        try:
            ay = AcademicYear.objects.get(pk=int(request.GET["academic_year"]))
            date_from, date_to = ay.start_date, ay.end_date
            active_period = ay.name
        except (AcademicYear.DoesNotExist, ValueError):
            pass
    elif request.GET.get("show") == "all":
        active_period = "all time"
    elif not has_any_filter:
        default_term = Term.get_current()
        if default_term:
            date_from, date_to = default_term.start_date, default_term.end_date
            active_period = str(default_term)

    # ── Shared context ───────────────────────────────────────────────
    subjects = Subject.objects.filter(
        is_active=True,
        applicable_pathways__contains=[student.pathway],
        applicable_phases__contains=[student.phase],
    )

    context = {
        "student": student,
        "active_view": active_view,
        "subjects": subjects,
        "academic_years": AcademicYear.objects.all(),
        "terms": Term.objects.select_related("academic_year").all(),
        "selected_academic_year": request.GET.get("academic_year", ""),
        "selected_term": request.GET.get("term", "") or (
            str(default_term.pk) if default_term else ""
        ),
        "date_from": raw_from,
        "date_to": raw_to,
        "active_period": active_period,
        "default_term": default_term,
    }

    # ==================================================================
    # EHCP VIEW
    # ==================================================================
    if active_view == "ehcp":
        EHCP_ORDER = {
            "NOT_STARTED": 0, "IN_PROGRESS": 1,
            "PARTIALLY_MET": 2, "MET": 3, "EXCEEDED": 4,
        }
        EHCP_DISPLAY = dict(EHCPTarget.STATUS_CHOICES)

        targets = (
            EHCPTarget.objects.filter(student=student)
            .select_related("outcome", "created_by")
            .prefetch_related("reviews")
            .order_by("outcome__order", "set_date")
        )

        # Build reviews queryset with date filtering
        reviews_qs = EHCPTargetReview.objects.filter(
            target__student=student
        ).select_related("target__outcome", "reviewed_by").order_by(
            "review_date", "created_at"
        )

        if date_from:
            reviews_qs = reviews_qs.filter(review_date__gte=date_from)
        if date_to:
            reviews_qs = reviews_qs.filter(review_date__lte=date_to)

        reviews_list = list(reviews_qs)

        # All review dates for the grid columns
        ehcp_dates = sorted(set(r.review_date for r in reviews_list))

        # Also include set_date for targets set within the range
        for t in targets:
            if date_from and t.set_date < date_from:
                continue
            if date_to and t.set_date > date_to:
                continue
            ehcp_dates.append(t.set_date)
        ehcp_dates = sorted(set(ehcp_dates))

        # Build per-target, per-date status map
        target_date_map = {}
        target_info = {}
        for t in targets:
            target_info[t.pk] = (
                t.title,
                t.outcome.name if t.outcome else "General",
            )
            target_date_map[t.pk] = {}
            if t.set_date in ehcp_dates:
                target_date_map[t.pk][t.set_date] = (
                    "NOT_STARTED", "Not Started", "Target set", ""
                )

        for r in reviews_list:
            tid = r.target_id
            if tid not in target_date_map:
                target_date_map[tid] = {}
                tgt = r.target
                target_info[tid] = (
                    tgt.title,
                    tgt.outcome.name if tgt.outcome else "General",
                )
            by_name = r.reviewed_by.get_full_name() if r.reviewed_by else ""
            target_date_map[tid][r.review_date] = (
                r.status, EHCP_DISPLAY.get(r.status, r.status), r.notes, by_name,
            )

        # Build grid grouped by outcome
        ehcp_grid_by_outcome = OrderedDict()
        for tid, dates in target_date_map.items():
            if tid not in target_info:
                continue
            title, outcome_name = target_info[tid]
            if outcome_name not in ehcp_grid_by_outcome:
                ehcp_grid_by_outcome[outcome_name] = []
            cells = []
            prev_status = None
            for d in ehcp_dates:
                if d in dates:
                    status, display, notes, by = dates[d]
                    if prev_status is None:
                        change = "new"
                    elif EHCP_ORDER.get(status, 0) > EHCP_ORDER.get(prev_status, 0):
                        change = "improved"
                    elif EHCP_ORDER.get(status, 0) < EHCP_ORDER.get(prev_status, 0):
                        change = "regressed"
                    else:
                        change = "same"
                    cells.append({
                        "date": d, "status": status, "display": display,
                        "has_data": True, "change": change,
                        "notes": notes, "by": by,
                    })
                    prev_status = status
                else:
                    cells.append({"has_data": False, "carried": prev_status})
            ehcp_grid_by_outcome[outcome_name].append({
                "text": title, "tid": tid, "cells": cells,
            })

        ehcp_grid = [
            {"outcome": name, "targets": tgts}
            for name, tgts in ehcp_grid_by_outcome.items()
        ]

        # EHCP Timeline (grouped by date, newest first)
        ehcp_timeline_map = OrderedDict()
        target_history = {}

        for t in targets:
            if t.set_date not in ehcp_dates:
                continue
            d = t.set_date
            target_history[t.pk] = "NOT_STARTED"
            if d not in ehcp_timeline_map:
                ehcp_timeline_map[d] = {
                    "date": d, "entries": [],
                    "improved": 0, "new": 0, "maintained": 0, "regressed": 0,
                }
            ehcp_timeline_map[d]["entries"].append({
                "outcome": t.outcome.name if t.outcome else "General",
                "target": t.title, "target_id": t.pk,
                "status": "NOT_STARTED",
                "status_display": "Not Started",
                "prev_status": None, "prev_display": "",
                "change_type": "new", "notes": "Target set",
                "reviewed_by": (
                    t.created_by.get_full_name() if t.created_by else ""
                ),
            })
            ehcp_timeline_map[d]["new"] += 1

        for r in reviews_list:
            d = r.review_date
            tid = r.target_id
            prev = target_history.get(tid)

            if prev is None:
                change_type = "new"
            elif EHCP_ORDER.get(r.status, 0) > EHCP_ORDER.get(prev, 0):
                change_type = "improved"
            elif EHCP_ORDER.get(r.status, 0) < EHCP_ORDER.get(prev, 0):
                change_type = "regressed"
            else:
                change_type = "maintained"

            target_history[tid] = r.status

            if d not in ehcp_timeline_map:
                ehcp_timeline_map[d] = {
                    "date": d, "entries": [],
                    "improved": 0, "new": 0, "maintained": 0, "regressed": 0,
                }
            tgt_title = target_info.get(tid, (r.target.title, ""))[0]
            tgt_outcome = target_info.get(tid, ("", "General"))[1]

            ehcp_timeline_map[d]["entries"].append({
                "outcome": tgt_outcome,
                "target": tgt_title, "target_id": tid,
                "status": r.status,
                "status_display": EHCP_DISPLAY.get(r.status, r.status),
                "prev_status": prev,
                "prev_display": EHCP_DISPLAY.get(prev, "") if prev else "",
                "change_type": change_type,
                "notes": r.notes,
                "reviewed_by": (
                    r.reviewed_by.get_full_name() if r.reviewed_by else ""
                ),
            })
            ehcp_timeline_map[d][change_type] += 1

        for entry in ehcp_timeline_map.values():
            entry["entries"].sort(key=lambda e: e["outcome"])

        ehcp_timeline = list(reversed(ehcp_timeline_map.values()))

        # EHCP Summary stats
        ehcp_counts = {
            "NOT_STARTED": 0, "IN_PROGRESS": 0,
            "PARTIALLY_MET": 0, "MET": 0, "EXCEEDED": 0,
        }
        for t in targets:
            ehcp_counts[t.status] = ehcp_counts.get(t.status, 0) + 1
        ehcp_total = targets.count()
        ehcp_improvements = sum(e["improved"] for e in ehcp_timeline_map.values())
        ehcp_met_exceeded = ehcp_counts.get("MET", 0) + ehcp_counts.get("EXCEEDED", 0)

        context.update({
            "ehcp_grid": ehcp_grid,
            "ehcp_dates": ehcp_dates,
            "ehcp_timeline": ehcp_timeline,
            "ehcp_counts": ehcp_counts,
            "ehcp_total": ehcp_total,
            "ehcp_improvements": ehcp_improvements,
            "ehcp_met_exceeded": ehcp_met_exceeded,
        })

    # ==================================================================
    # ASSESSMENTS VIEW (default)
    # ==================================================================
    elif active_view == "assessments" or active_view not in ("ehcp", "summary"):
        STATUS_ORDER = {"NYA": 0, "EME": 1, "DEV": 2, "SEC": 3}
        STATUS_DISPLAY = dict(AssessmentRecord.STATUS_CHOICES)

        records_qs = (
            AssessmentRecord.objects.filter(student=student)
            .select_related("statement__area__subject", "assessed_by")
            .order_by("assessed_date", "created_at")
        )

        if date_from:
            records_qs = records_qs.filter(assessed_date__gte=date_from)
        if date_to:
            records_qs = records_qs.filter(assessed_date__lte=date_to)

        subject_id = request.GET.get("subject")
        selected_subject = None
        if subject_id:
            selected_subject = Subject.objects.filter(pk=subject_id).first()

        records_list = list(records_qs)
        if selected_subject:
            records_list = [
                r for r in records_list
                if r.statement.area.subject == selected_subject
            ]

        # Deduplicate: keep latest record per statement+date
        latest_map = {}
        for r in records_list:
            latest_map[(r.statement_id, r.assessed_date)] = r
        deduped = sorted(
            latest_map.values(), key=lambda r: (r.assessed_date, r.created_at)
        )

        # Chart data (per subject)
        progress_data = {}
        for record in deduped:
            subject_name = record.statement.area.subject.name
            date_str = record.assessed_date.isoformat()
            if subject_name not in progress_data:
                progress_data[subject_name] = []
            progress_data[subject_name].append({
                "date": date_str,
                "status": record.status,
                "status_display": record.get_status_display(),
                "statement": record.statement.statement_text,
            })

        # Statement Progress Grid
        all_dates = sorted(set(r.assessed_date for r in deduped))

        stmt_date_map = {}
        stmt_info = {}
        for r in deduped:
            sid = r.statement_id
            if sid not in stmt_date_map:
                stmt_date_map[sid] = {}
                stmt_info[sid] = (
                    r.statement.statement_text, r.statement.area.subject.name
                )
            stmt_date_map[sid][r.assessed_date] = (r.status, r.get_status_display())

        grid_by_subject = OrderedDict()
        for sid, dates in stmt_date_map.items():
            text, subj_name = stmt_info[sid]
            if subj_name not in grid_by_subject:
                grid_by_subject[subj_name] = []
            cells = []
            prev_status = None
            for d in all_dates:
                if d in dates:
                    status, display = dates[d]
                    if prev_status is None:
                        change = "new"
                    elif STATUS_ORDER[status] > STATUS_ORDER[prev_status]:
                        change = "improved"
                    elif STATUS_ORDER[status] < STATUS_ORDER[prev_status]:
                        change = "regressed"
                    else:
                        change = "same"
                    cells.append({
                        "date": d, "status": status, "display": display,
                        "has_data": True, "change": change,
                    })
                    prev_status = status
                else:
                    cells.append({"has_data": False, "carried": prev_status})
            grid_by_subject[subj_name].append({"text": text, "cells": cells})

        progress_grid = [
            {"subject": name, "statements": stmts}
            for name, stmts in grid_by_subject.items()
        ]

        # Activity Timeline
        stmt_history = {}
        timeline_map = OrderedDict()

        for r in deduped:
            d = r.assessed_date
            sid = r.statement_id
            prev = stmt_history.get(sid)

            if prev is None:
                change_type = "new"
            elif STATUS_ORDER[r.status] > STATUS_ORDER.get(prev, 0):
                change_type = "improved"
            elif STATUS_ORDER[r.status] < STATUS_ORDER.get(prev, 0):
                change_type = "regressed"
            else:
                change_type = "maintained"

            stmt_history[sid] = r.status

            if d not in timeline_map:
                timeline_map[d] = {
                    "date": d, "entries": [],
                    "improved": 0, "new": 0, "maintained": 0, "regressed": 0,
                }
            timeline_map[d]["entries"].append({
                "subject": r.statement.area.subject.name,
                "statement": r.statement.statement_text,
                "status": r.status,
                "status_display": r.get_status_display(),
                "prev_status": prev,
                "prev_display": STATUS_DISPLAY.get(prev, "") if prev else "",
                "change_type": change_type,
                "assessed_by": (
                    r.assessed_by.get_full_name() if r.assessed_by else ""
                ),
            })
            timeline_map[d][change_type] += 1

        for entry in timeline_map.values():
            entry["entries"].sort(key=lambda e: e["subject"])

        timeline = list(reversed(timeline_map.values()))

        current_counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
        for status in stmt_history.values():
            current_counts[status] += 1
        total_assessed = len(stmt_history)
        total_improvements = sum(e["improved"] for e in timeline_map.values())

        context.update({
            "selected_subject": selected_subject,
            "progress_data": progress_data,
            "progress_grid": progress_grid,
            "all_dates": all_dates,
            "timeline": timeline,
            "current_counts": current_counts,
            "total_assessed": total_assessed,
            "total_improvements": total_improvements,
        })

    # ==================================================================
    # SUMMARY VIEW (merged Learning Journey)
    # ==================================================================
    else:
        # Override active_view to canonical name
        active_view = "summary"
        context["active_view"] = active_view

        # RAG summary per subject
        subject_summaries = []
        for subject in subjects:
            areas = AssessmentArea.objects.filter(subject=subject)
            total_stmts = 0
            status_counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
            for area in areas:
                stmts = area.statements.all()
                total_stmts += stmts.count()
                for stmt in stmts:
                    latest = (
                        AssessmentRecord.objects.filter(student=student, statement=stmt)
                        .order_by("-assessed_date", "-created_at")
                        .first()
                    )
                    if latest:
                        status_counts[latest.status] += 1
                    else:
                        status_counts["NYA"] += 1
            subject_summaries.append({
                "subject": subject,
                "total": total_stmts,
                "secure": status_counts["SEC"],
                "developing": status_counts["DEV"],
                "emerging": status_counts["EME"],
                "not_yet": status_counts["NYA"],
            })

        overall_total = sum(s["total"] for s in subject_summaries)
        overall_secure = sum(s["secure"] for s in subject_summaries)
        overall_developing = sum(s["developing"] for s in subject_summaries)
        overall_emerging = sum(s["emerging"] for s in subject_summaries)
        overall_nya = sum(s["not_yet"] for s in subject_summaries)

        # Snapshot history grouped by term
        snapshots = (
            AssessmentSnapshot.objects.filter(student=student)
            .select_related("area__subject", "term__academic_year")
            .order_by("-term__academic_year__start_date", "-term__start_date", "area__subject__name")
        )
        snapshot_by_term = {}
        for snap in snapshots:
            term_label = str(snap.term)
            if term_label not in snapshot_by_term:
                snapshot_by_term[term_label] = []
            snapshot_by_term[term_label].append(snap)

        # Check if AI is available
        from core.models import AISettings
        ai = AISettings.load()
        ai_available = ai.enabled and ai.provider != "none"

        context.update({
            "subject_summaries": subject_summaries,
            "overall_total": overall_total,
            "overall_secure": overall_secure,
            "overall_developing": overall_developing,
            "overall_emerging": overall_emerging,
            "overall_nya": overall_nya,
            "snapshot_by_term": snapshot_by_term,
            "ai_available": ai_available,
            "cached_ai_summary": request.session.get(f'ai_summary_{student.pk}', ''),
            "cached_ai_patterns": request.session.get(f'ai_patterns_{student.pk}', ''),
        })

    return render(request, "students/student_progress.html", context)


@login_required
def generate_ai_summary(request, pk):
    """HTMX endpoint: generate an AI progress summary for a student."""
    import re
    from core.ai import ai_chat

    student = get_object_or_404(Student, pk=pk)

    # Gather student data for the prompt
    subjects = Subject.objects.filter(
        is_active=True,
        applicable_pathways__contains=[student.pathway],
        applicable_phases__contains=[student.phase],
    )

    summary_lines = []
    for subject in subjects:
        areas = AssessmentArea.objects.filter(subject=subject)
        counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
        for area in areas:
            for stmt in area.statements.all():
                latest = (
                    AssessmentRecord.objects.filter(student=student, statement=stmt)
                    .order_by("-assessed_date", "-created_at")
                    .first()
                )
                if latest:
                    counts[latest.status] += 1
                else:
                    counts["NYA"] += 1
        total = sum(counts.values())
        if total:
            summary_lines.append(
                f"- {subject.name}: {counts['SEC']} Secure, {counts['DEV']} Developing, "
                f"{counts['EME']} Emerging, {counts['NYA']} Not Yet Assessed (of {total})"
            )

    # EHCP targets
    from evidence.models import EHCPTarget
    ehcp_targets = EHCPTarget.objects.filter(student=student).select_related("outcome")
    if ehcp_targets.exists():
        summary_lines.append("\nEHCP Targets:")
        for t in ehcp_targets:
            outcome = t.outcome.name if t.outcome else "General"
            summary_lines.append(f"- [{outcome}] {t.title}: {t.get_status_display()}")

    # Recent assessments (last 20)
    recent = (
        AssessmentRecord.objects.filter(student=student)
        .select_related("statement__area__subject")
        .order_by("-assessed_date")[:20]
    )
    if recent:
        summary_lines.append("\nRecent Assessment Activity:")
        for r in recent:
            summary_lines.append(
                f"- {r.assessed_date.strftime('%d-%m-%Y')}: {r.statement.area.subject.name} - "
                f"{r.statement.statement_text[:60]} = {r.get_status_display()}"
            )

    data_text = "\n".join(summary_lines)

    prompt = (
        f"Student: {student.full_name}\n"
        f"Pathway: {student.get_pathway_display()}, Phase {student.phase}\n"
        f"Year Group: {student.year_group or 'N/A'}\n\n"
        f"Assessment Data:\n{data_text}\n\n"
        "Write a concise, professional progress summary (3-5 paragraphs) that:\n"
        "1. Highlights areas of strength and secure knowledge\n"
        "2. Notes areas showing progress or development\n"
        "3. Identifies areas that may need additional support\n"
        "4. If EHCP targets exist, comments on progress towards them\n"
        "5. Uses encouraging, person-centred language appropriate for SEN contexts\n\n"
        "Do not invent data. Only reference what is provided above. "
        "Format with simple HTML paragraphs (<p> tags). Do not use markdown."
    )

    system = (
        "You are a special educational needs (SEN) teaching assistant writing a brief, "
        "supportive progress summary for a student's learning journey report."
    )

    reply, err = ai_chat(prompt, system=system, max_tokens=2000, timeout=60)
    if err:
        return HttpResponse(f'<div class="alert alert-danger">{err}</div>')

    # Sanitize: only allow safe tags
    reply = re.sub(r'<(?!/?(?:p|strong|em|br|ul|li|ol)\b)[^>]+>', '', reply)

    html = f'<div class="ai-summary-content">{reply}</div>'
    request.session[f'ai_summary_{pk}'] = html
    return HttpResponse(html)


@login_required
def ai_detect_patterns(request, pk):
    """HTMX endpoint: analyse progress data and detect patterns/trends."""
    import re
    from core.ai import ai_chat

    student = get_object_or_404(Student, pk=pk)

    subjects = Subject.objects.filter(
        is_active=True,
        applicable_pathways__contains=[student.pathway],
        applicable_phases__contains=[student.phase],
    )

    # Build per-subject status summary
    subject_lines = []
    for subject in subjects:
        areas = AssessmentArea.objects.filter(subject=subject)
        counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
        for area in areas:
            for stmt in area.statements.all():
                latest = (
                    AssessmentRecord.objects.filter(student=student, statement=stmt)
                    .order_by("-assessed_date", "-created_at")
                    .first()
                )
                if latest:
                    counts[latest.status] += 1
                else:
                    counts["NYA"] += 1
        total = sum(counts.values())
        if total:
            pct_secure = round(counts["SEC"] / total * 100)
            subject_lines.append(
                f"- {subject.name}: {pct_secure}% secure, "
                f"{counts['SEC']}S/{counts['DEV']}D/{counts['EME']}E/{counts['NYA']}N (of {total})"
            )

    # Recent trajectory: last 60 assessments with dates
    recent = (
        AssessmentRecord.objects.filter(student=student)
        .select_related("statement__area__subject")
        .order_by("-assessed_date")[:60]
    )
    trajectory_lines = []
    for r in recent:
        trajectory_lines.append(
            f"- {r.assessed_date.strftime('%d-%m-%Y')}: {r.statement.area.subject.name} / "
            f"{r.statement.area.name}: {r.get_status_display()}"
        )

    # Snapshot comparison if available
    from assessments.models import AssessmentSnapshot
    snapshots = (
        AssessmentSnapshot.objects.filter(student=student)
        .select_related("area__subject", "term")
        .order_by("term__start_date", "area__subject__name")
    )
    snapshot_lines = []
    for s in snapshots:
        snapshot_lines.append(
            f"- {s.term}: {s.area.subject.name} / {s.area.name}: "
            f"{s.secure_count}S/{s.developing_count}D/{s.emerging_count}E/{s.not_assessed_count}N"
        )

    data_text = "Subject Summary:\n" + "\n".join(subject_lines)
    if trajectory_lines:
        data_text += "\n\nRecent Assessments (newest first):\n" + "\n".join(trajectory_lines)
    if snapshot_lines:
        data_text += "\n\nTermly Snapshots:\n" + "\n".join(snapshot_lines)

    prompt = (
        f"Student: {student.full_name}\n"
        f"Pathway: {student.get_pathway_display()}, Phase {student.phase}\n\n"
        f"{data_text}\n\n"
        "Analyse this data and identify:\n"
        "1. Subjects or areas accelerating (improving faster than others)\n"
        "2. Subjects or areas stalling (little progress over time)\n"
        "3. Cross-subject patterns (e.g. strong in practical, weaker in written)\n"
        "4. Any snapshot trends showing term-on-term changes\n"
        "5. Priority areas for intervention\n\n"
        "Format as HTML with clear headings (<h6>) for each pattern type found. "
        "Use <ul><li> for specific findings. Be concise and data-driven. "
        "Only report patterns you can evidence from the data provided."
    )
    system = (
        "You are a UK SEN data analyst helping teachers understand student progress patterns. "
        "Be specific, reference actual subjects and areas, and focus on actionable insights."
    )

    reply, err = ai_chat(prompt, system=system, max_tokens=1500, timeout=60)
    if err:
        return HttpResponse(f'<div class="alert alert-danger">{err}</div>')

    reply = re.sub(r'<(?!/?(?:h6|p|strong|em|br|ul|ol|li)\b)[^>]+>', '', reply)

    html = f'<div class="ai-patterns-content">{reply}</div>'
    request.session[f'ai_patterns_{pk}'] = html
    return HttpResponse(html)


@login_required
def learning_journey(request, pk):
    """Consolidated profile page: demographics, RAG overview, progress chart,
    assessment timeline, and snapshot history — all in one place."""
    student = get_object_or_404(Student, pk=pk)

    # ── Applicable subjects ──────────────────────────────────────────
    subjects = Subject.objects.filter(
        is_active=True,
        applicable_pathways__contains=[student.pathway],
        applicable_phases__contains=[student.phase],
    )

    # ── RAG summary per subject (mirrored from student_detail) ───────
    subject_summaries = []
    for subject in subjects:
        areas = AssessmentArea.objects.filter(subject=subject)
        total_statements = 0
        status_counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}

        for area in areas:
            stmts = area.statements.all()
            total_statements += stmts.count()
            for stmt in stmts:
                latest = (
                    AssessmentRecord.objects.filter(student=student, statement=stmt)
                    .order_by("-assessed_date", "-created_at")
                    .first()
                )
                if latest:
                    status_counts[latest.status] += 1
                else:
                    status_counts["NYA"] += 1

        subject_summaries.append({
            "subject": subject,
            "total": total_statements,
            "secure": status_counts["SEC"],
            "developing": status_counts["DEV"],
            "emerging": status_counts["EME"],
            "not_yet": status_counts["NYA"],
        })

    # ── Overall totals ───────────────────────────────────────────────
    overall_total = sum(s["total"] for s in subject_summaries)
    overall_secure = sum(s["secure"] for s in subject_summaries)
    overall_developing = sum(s["developing"] for s in subject_summaries)
    overall_emerging = sum(s["emerging"] for s in subject_summaries)
    overall_nya = sum(s["not_yet"] for s in subject_summaries)

    # ── Progress chart data (all time, per subject) ──────────────────
    records = (
        AssessmentRecord.objects.filter(student=student)
        .select_related("statement__area__subject", "assessed_by")
        .order_by("assessed_date")
    )

    progress_data = {}
    for record in records:
        subject_name = record.statement.area.subject.name
        date_str = record.assessed_date.isoformat()
        if subject_name not in progress_data:
            progress_data[subject_name] = []
        progress_data[subject_name].append({
            "date": date_str,
            "status": record.status,
        })

    # ── Recent assessments timeline (last 50) ────────────────────────
    recent_records = (
        AssessmentRecord.objects.filter(student=student)
        .select_related("statement__area__subject", "assessed_by")
        .order_by("-assessed_date", "-created_at")[:50]
    )

    # ── Snapshot history ─────────────────────────────────────────────
    snapshots = (
        AssessmentSnapshot.objects.filter(student=student)
        .select_related("area__subject", "term__academic_year")
        .order_by("-term__academic_year__start_date", "-term__start_date", "area__subject__name")
    )

    # Group snapshots by term for display
    snapshot_by_term = {}
    for snap in snapshots:
        term_label = str(snap.term)
        if term_label not in snapshot_by_term:
            snapshot_by_term[term_label] = []
        snapshot_by_term[term_label].append(snap)

    context = {
        "student": student,
        "subject_summaries": subject_summaries,
        "overall_total": overall_total,
        "overall_secure": overall_secure,
        "overall_developing": overall_developing,
        "overall_emerging": overall_emerging,
        "overall_nya": overall_nya,
        "progress_data": progress_data,
        "recent_records": recent_records,
        "snapshot_by_term": snapshot_by_term,
    }
    return render(request, "students/learning_journey.html", context)


@login_required
def learning_journey_pdf(request, pk):
    """Export the student learning journey as a PDF."""
    import weasyprint

    student = get_object_or_404(Student, pk=pk)

    # Reuse the same data-gathering logic from learning_journey
    subjects = Subject.objects.filter(
        is_active=True,
        applicable_pathways__contains=[student.pathway],
        applicable_phases__contains=[student.phase],
    )

    subject_summaries = []
    for subject in subjects:
        areas = AssessmentArea.objects.filter(subject=subject)
        total_statements = 0
        status_counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
        for area in areas:
            stmts = area.statements.all()
            total_statements += stmts.count()
            for stmt in stmts:
                latest = (
                    AssessmentRecord.objects.filter(student=student, statement=stmt)
                    .order_by("-assessed_date", "-created_at")
                    .first()
                )
                if latest:
                    status_counts[latest.status] += 1
                else:
                    status_counts["NYA"] += 1
        subject_summaries.append({
            "subject": subject,
            "total": total_statements,
            "secure": status_counts["SEC"],
            "developing": status_counts["DEV"],
            "emerging": status_counts["EME"],
            "not_yet": status_counts["NYA"],
        })

    overall_total = sum(s["total"] for s in subject_summaries)
    overall_secure = sum(s["secure"] for s in subject_summaries)
    overall_developing = sum(s["developing"] for s in subject_summaries)
    overall_emerging = sum(s["emerging"] for s in subject_summaries)
    overall_nya = sum(s["not_yet"] for s in subject_summaries)

    recent_records = (
        AssessmentRecord.objects.filter(student=student)
        .select_related("statement__area__subject", "assessed_by")
        .order_by("-assessed_date", "-created_at")[:50]
    )

    snapshots = (
        AssessmentSnapshot.objects.filter(student=student)
        .select_related("area__subject", "term__academic_year")
        .order_by("-term__academic_year__start_date", "-term__start_date", "area__subject__name")
    )
    snapshot_by_term = {}
    for snap in snapshots:
        term_label = str(snap.term)
        if term_label not in snapshot_by_term:
            snapshot_by_term[term_label] = []
        snapshot_by_term[term_label].append(snap)

    context = {
        "student": student,
        "subject_summaries": subject_summaries,
        "overall_total": overall_total,
        "overall_secure": overall_secure,
        "overall_developing": overall_developing,
        "overall_emerging": overall_emerging,
        "overall_nya": overall_nya,
        "recent_records": recent_records,
        "snapshot_by_term": snapshot_by_term,
        "today": timezone.now().date(),
    }

    # Include AI narrative if cached or if AI is available
    ai_narrative = request.session.get(f'ai_summary_{student.pk}', '')
    if not ai_narrative:
        # Try to generate one on the fly for the PDF
        import re as re_mod
        from core.ai import ai_chat
        summary_lines = []
        for s in subject_summaries:
            if s["total"]:
                summary_lines.append(
                    f"- {s['subject'].name}: {s['secure']}S, {s['developing']}D, "
                    f"{s['emerging']}E, {s['not_yet']}N (of {s['total']})"
                )
        from evidence.models import EHCPTarget
        ehcp_targets = EHCPTarget.objects.filter(student=student).select_related("outcome")
        if ehcp_targets.exists():
            summary_lines.append("\nEHCP Targets:")
            for t in ehcp_targets:
                outcome = t.outcome.name if t.outcome else "General"
                summary_lines.append(f"- [{outcome}] {t.title}: {t.get_status_display()}")

        prompt = (
            f"Student: {student.full_name}\n"
            f"Pathway: {student.get_pathway_display()}, Phase {student.phase}\n\n"
            f"Assessment Data:\n" + "\n".join(summary_lines) + "\n\n"
            "Write a concise, professional progress narrative (2-3 paragraphs) suitable "
            "for a formal PDF learning journey report. Highlight strengths, areas of progress, "
            "and next steps. Use encouraging, person-centred SEN language. "
            "Format with HTML <p> tags only. Do not use markdown."
        )
        system = (
            "You are a UK SEN teacher writing a narrative for a student's formal progress report."
        )
        reply, err = ai_chat(prompt, system=system, max_tokens=1000, timeout=30)
        if not err and reply:
            reply = re_mod.sub(r'<(?!/?(?:p|strong|em|br)\b)[^>]+>', '', reply)
            ai_narrative = f'<div class="ai-narrative">{reply}</div>'

    context["ai_narrative"] = ai_narrative

    html_string = render_to_string("pdf/student_journey.html", context)
    pdf = weasyprint.HTML(string=html_string).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    safe_name = student.full_name.replace(" ", "_")
    response["Content-Disposition"] = f'attachment; filename="learning_journey_{safe_name}.pdf"'
    return response
