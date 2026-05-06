import json
import os

import cv2
import numpy as np
from PIL import Image, ImageOps
from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from assessments.models import AssessmentArea, AssessmentRecord
from students.models import ClassGroup, Student, Subject

from .blur import apply_blur_to_faces, detect_faces
from .models import (
    EHCPAnnotation, EHCPDocument, EHCPOutcome, EHCPTarget, EHCPTargetReview,
    Evidence, EvidenceStudentLink,
    InterventionEnrolment, InterventionProgram, InterventionReview, InterventionSession,
    MAPPConfig, MAPPDimensionConfig, MAPPDimensionScore, MAPPLearningPriority,
    SmallStep,
)

# Register HEIC/HEIF support with Pillow
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


# ── Helpers ─────────────────────────────────────────────────────────

def _normalise_image(item):
    """Auto-orient via EXIF and convert HEIC/HEIF to JPEG.

    Overwrites the file on disk and updates the model field if the
    filename changed (HEIC → .jpg). Call immediately after upload.
    """
    ext = item.file_extension
    is_heic = ext in (".heic", ".heif")

    try:
        img = Image.open(item.file.path)
        # Apply EXIF orientation (fixes iPad upside-down photos)
        img = ImageOps.exif_transpose(img) or img

        if is_heic or img.format == "HEIF":
            # Convert to JPEG: change path, save, update model
            old_path = item.file.path
            new_path = os.path.splitext(old_path)[0] + ".jpg"
            img = img.convert("RGB")
            img.save(new_path, "JPEG", quality=90)
            # Remove original HEIC file
            if old_path != new_path and os.path.exists(old_path):
                os.remove(old_path)
            # Update the file field to point to the new .jpg
            item.file.name = os.path.splitext(item.file.name)[0] + ".jpg"
            item.save(update_fields=["file"])
        else:
            # Just re-save oriented image in place
            fmt = img.format or ("PNG" if ext == ".png" else "JPEG")
            save_kwargs = {"quality": 92} if fmt == "JPEG" else {}
            img.save(item.file.path, fmt, **save_kwargs)
    except Exception:
        pass  # Non-critical — original file is still usable

def _regenerate_thumbnail(item):
    """Create / overwrite the Evidence thumbnail from the current main file."""
    try:
        img = Image.open(item.file.path)
        img.thumbnail((400, 400), Image.LANCZOS)
        from io import BytesIO
        buf = BytesIO()
        fmt = "JPEG"
        if item.file_extension in (".png",):
            fmt = "PNG"
        img.save(buf, format=fmt, quality=85)
        buf.seek(0)
        thumb_name = f"evidence/thumbnails/{item.pk}_thumb{'.png' if fmt == 'PNG' else '.jpg'}"
        # Delete old thumbnail file if present
        if item.thumbnail:
            item.thumbnail.delete(save=False)
        item.thumbnail.save(thumb_name, ContentFile(buf.read()), save=False)
    except Exception:
        pass  # Non-critical — gallery falls back to main file


def _generate_video_thumbnail(item):
    """Extract first frame of a video and save as thumbnail."""
    try:
        cap = cv2.VideoCapture(item.file.path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img = ImageOps.exif_transpose(img) or img
        img.thumbnail((400, 400), Image.LANCZOS)
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        thumb_name = f"evidence/thumbnails/{item.pk}_thumb.jpg"
        if item.thumbnail:
            item.thumbnail.delete(save=False)
        item.thumbnail.save(thumb_name, ContentFile(buf.read()), save=False)
    except Exception:
        pass


# ── EHCP Targets ────────────────────────────────────────────────────

@login_required
def ehcp_overview(request, student_pk):
    """Overview of all EHCP targets for a student, grouped by outcome."""
    student = get_object_or_404(Student, pk=student_pk)
    targets = (
        student.ehcp_targets
        .select_related("outcome", "created_by")
        .prefetch_related("reviews", "evidence_items", "small_steps")
    )

    # Group by outcome
    outcomes = EHCPOutcome.objects.all()
    grouped = []
    for outcome in outcomes:
        outcome_targets = [t for t in targets if t.outcome_id == outcome.pk]
        if outcome_targets:
            grouped.append({"outcome": outcome, "targets": outcome_targets})

    # Targets without an outcome
    unlinked = [t for t in targets if t.outcome_id is None]
    if unlinked:
        grouped.append({"outcome": None, "targets": unlinked})

    # Summary stats
    total = targets.count()
    met_count = targets.filter(status__in=["MET", "EXCEEDED"]).count()
    in_progress_count = targets.filter(status="IN_PROGRESS").count()

    context = {
        "student": student,
        "grouped": grouped,
        "total": total,
        "met_count": met_count,
        "in_progress_count": in_progress_count,
    }
    return render(request, "evidence/ehcp_overview.html", context)


@login_required
def ehcp_target_create(request, student_pk):
    """Create a new EHCP target for a student."""
    student = get_object_or_404(Student, pk=student_pk)
    outcomes = EHCPOutcome.objects.all()
    areas = AssessmentArea.objects.select_related("subject", "framework").all()

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        outcome_id = request.POST.get("outcome") or None
        set_date = request.POST.get("set_date", "").strip()
        review_date = request.POST.get("review_date", "").strip() or None
        linked_area_ids = request.POST.getlist("linked_areas")

        if not title or not set_date:
            messages.error(request, "Title and set date are required.")
            return redirect("evidence:ehcp_target_create", student_pk=student.pk)

        target = EHCPTarget.objects.create(
            student=student,
            outcome_id=outcome_id,
            title=title,
            description=description,
            set_date=set_date,
            review_date=review_date,
            created_by=request.user,
        )
        if linked_area_ids:
            target.linked_areas.set(linked_area_ids)

        messages.success(request, f'Target "{title[:50]}" created.')
        return redirect("evidence:ehcp_overview", student_pk=student.pk)

    context = {
        "student": student,
        "outcomes": outcomes,
        "areas": areas,
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "evidence/ehcp_target_form.html", context)


@login_required
def ehcp_target_edit(request, pk):
    """Edit an EHCP target."""
    target = get_object_or_404(
        EHCPTarget.objects.select_related("student"), pk=pk
    )
    student = target.student
    outcomes = EHCPOutcome.objects.all()
    areas = AssessmentArea.objects.select_related("subject", "framework").all()

    if request.method == "POST":
        target.title = request.POST.get("title", "").strip()
        target.description = request.POST.get("description", "").strip()
        target.outcome_id = request.POST.get("outcome") or None
        target.status = request.POST.get("status", target.status)
        target.set_date = request.POST.get("set_date")
        target.review_date = request.POST.get("review_date") or None
        target.met_date = request.POST.get("met_date") or None

        if not target.title or not target.set_date:
            messages.error(request, "Title and set date are required.")
            return redirect("evidence:ehcp_target_edit", pk=pk)

        target.save()

        linked_area_ids = request.POST.getlist("linked_areas")
        target.linked_areas.set(linked_area_ids)

        messages.success(request, "Target updated.")
        return redirect("evidence:ehcp_overview", student_pk=student.pk)

    context = {
        "student": student,
        "target": target,
        "outcomes": outcomes,
        "areas": areas,
        "selected_areas": list(target.linked_areas.values_list("pk", flat=True)),
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "evidence/ehcp_target_form.html", context)


@login_required
def ehcp_target_review(request, pk):
    """Add a review to an EHCP target (HTMX or full page)."""
    target = get_object_or_404(
        EHCPTarget.objects.select_related("student"), pk=pk
    )

    if request.method == "POST":
        status = request.POST.get("status", "")
        notes = request.POST.get("notes", "").strip()
        review_date = request.POST.get("review_date", "").strip()

        if not status or not review_date:
            messages.error(request, "Status and review date are required.")
            return redirect("evidence:ehcp_overview", student_pk=target.student.pk)

        EHCPTargetReview.objects.create(
            target=target,
            status=status,
            notes=notes,
            reviewed_by=request.user,
            review_date=review_date,
        )

        # Update target status
        target.status = status
        if status in ("MET", "EXCEEDED") and not target.met_date:
            target.met_date = review_date
        target.save(update_fields=["status", "met_date", "updated_at"])

        messages.success(request, "Review recorded.")
        return redirect("evidence:ehcp_overview", student_pk=target.student.pk)

    context = {
        "target": target,
        "status_choices": EHCPTarget.STATUS_CHOICES,
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "evidence/ehcp_review_form.html", context)


@login_required
def ehcp_target_detail(request, pk):
    """Detail view for an EHCP target — unified progress timeline."""
    target = get_object_or_404(
        EHCPTarget.objects.select_related("student", "outcome", "created_by"),
        pk=pk,
    )
    reviews = target.reviews.select_related("reviewed_by").all()
    evidence_items = target.evidence_items.order_by("-captured_date")
    linked_areas = target.linked_areas.select_related("subject", "framework").all()

    # ── Build unified timeline ──────────────────────────────────────
    timeline = []

    # Target created event
    timeline.append({
        "date": target.set_date,
        "type": "created",
        "icon": "bi-flag",
        "colour": "secondary",
        "title": "Target set",
        "detail": f"Created by {target.created_by.get_full_name() or target.created_by.username}"
                  if target.created_by else "Target created",
    })

    # Reviews
    for r in reviews:
        colour_map = {
            "MET": "success", "EXCEEDED": "success",
            "IN_PROGRESS": "primary", "PARTIALLY_MET": "warning",
            "NOT_STARTED": "secondary",
        }
        timeline.append({
            "date": r.review_date,
            "type": "review",
            "icon": "bi-chat-left-text",
            "colour": colour_map.get(r.status, "secondary"),
            "title": f"Reviewed — {r.get_status_display()}",
            "detail": r.notes[:200] if r.notes else "",
            "user": r.reviewed_by.get_full_name() or r.reviewed_by.username
                    if r.reviewed_by else "",
        })

    # Evidence items
    for item in evidence_items:
        icon_map = {"PHOTO": "bi-camera", "VIDEO": "bi-camera-video", "DOCUMENT": "bi-file-earmark"}
        timeline.append({
            "date": item.captured_date,
            "type": "evidence",
            "icon": icon_map.get(item.evidence_type, "bi-paperclip"),
            "colour": "info",
            "title": item.title or item.get_evidence_type_display(),
            "detail": item.description[:200] if item.description else "",
            "pk": item.pk,
        })

    # Met event
    if target.met_date:
        timeline.append({
            "date": target.met_date,
            "type": "met",
            "icon": "bi-trophy",
            "colour": "success",
            "title": "Target met",
            "detail": "",
        })

    # Sort timeline chronologically
    timeline.sort(key=lambda e: e["date"])

    # ── Assessment progress for linked areas ────────────────────────
    area_progress = []
    for area in linked_areas:
        statements = area.statements.all()
        total = statements.count()
        if total == 0:
            continue
        # Count latest status per statement for this student
        counts = {"SEC": 0, "DEV": 0, "EME": 0, "NYA": 0}
        for stmt in statements:
            latest = (
                AssessmentRecord.objects
                .filter(student=target.student, statement=stmt)
                .order_by("-assessed_date", "-created_at")
                .values_list("status", flat=True)
                .first()
            )
            counts[latest if latest else "NYA"] += 1
        area_progress.append({
            "area": area,
            "total": total,
            "secure": counts["SEC"],
            "developing": counts["DEV"],
            "emerging": counts["EME"],
            "not_assessed": counts["NYA"],
            "pct_secure": round(counts["SEC"] / total * 100) if total else 0,
        })

    context = {
        "target": target,
        "student": target.student,
        "reviews": reviews,
        "evidence_items": evidence_items,
        "linked_areas": linked_areas,
        "timeline": timeline,
        "area_progress": area_progress,
    }
    return render(request, "evidence/ehcp_target_detail.html", context)


# ── Evidence ────────────────────────────────────────────────────────

@login_required
def evidence_gallery(request, student_pk):
    """Gallery view of all evidence for a student."""
    student = get_object_or_404(Student, pk=student_pk)
    items = Evidence.objects.filter(
        student_links__student=student
    ).select_related("subject", "uploaded_by").distinct()

    # Filters
    etype = request.GET.get("type", "")
    if etype:
        items = items.filter(evidence_type=etype)
    subject_id = request.GET.get("subject", "")
    if subject_id:
        items = items.filter(subject_id=subject_id)
    target_id = request.GET.get("target", "")
    if target_id:
        items = items.filter(student_links__ehcp_target_id=target_id)

    subjects = Subject.objects.filter(is_active=True)
    targets = student.ehcp_targets.all()

    context = {
        "student": student,
        "items": items[:60],
        "subjects": subjects,
        "targets": targets,
        "current_type": etype,
        "current_subject": subject_id,
        "current_target": target_id,
    }
    return render(request, "evidence/evidence_gallery.html", context)


@login_required
def evidence_upload(request, student_pk):
    """Upload evidence for a student (file upload or camera capture)."""
    student = get_object_or_404(Student, pk=student_pk)
    subjects = Subject.objects.filter(is_active=True)
    targets = student.ehcp_targets.exclude(status__in=["MET", "EXCEEDED"])

    if request.method == "POST":
        file = request.FILES.get("file")
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        evidence_type = request.POST.get("evidence_type", "PHOTO")
        subject_id = request.POST.get("subject") or None
        target_id = request.POST.get("ehcp_target") or None
        captured_date = request.POST.get("captured_date", "").strip()

        if not file:
            messages.error(request, "Please select a file or take a photo.")
            return redirect("evidence:evidence_upload", student_pk=student.pk)

        if not captured_date:
            captured_date = timezone.now().date()

        # Validate file size (max 50MB)
        if file.size > 50 * 1024 * 1024:
            messages.error(request, "File too large. Maximum size is 50 MB.")
            return redirect("evidence:evidence_upload", student_pk=student.pk)

        item = Evidence.objects.create(
            student=student,
            evidence_type=evidence_type,
            title=title or file.name,
            description=description,
            file=file,
            subject_id=subject_id,
            ehcp_target_id=target_id,
            captured_date=captured_date,
            uploaded_by=request.user,
        )

        # Create the M2M link
        EvidenceStudentLink.objects.create(
            evidence=item,
            student=student,
            ehcp_target_id=target_id,
        )

        # Auto-orient and convert HEIC→JPEG for photos
        if item.is_image or item.file_extension in (".heic", ".heif"):
            _normalise_image(item)

        # Generate thumbnail for photos
        if item.is_image:
            _regenerate_thumbnail(item)
            item.save(update_fields=["thumbnail"])

        # Generate thumbnail for videos (first frame)
        if item.is_video:
            _generate_video_thumbnail(item)
            item.save(update_fields=["thumbnail"])

        # For photos, check for faces and redirect to blur page
        if item.is_image:
            faces = detect_faces(item.file.path)
            if faces:
                request.session[f"faces_{item.pk}"] = faces
                messages.info(
                    request,
                    f"{len(faces)} face(s) detected. Select which face is the student to auto-blur others.",
                )
                return redirect("evidence:evidence_blur", pk=item.pk)

        messages.success(request, "Evidence uploaded.")
        return redirect("evidence:evidence_gallery", student_pk=student.pk)

    context = {
        "student": student,
        "subjects": subjects,
        "targets": targets,
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "evidence/evidence_upload.html", context)


@login_required
def evidence_detail(request, pk):
    """Detail view for a single evidence item."""
    item = get_object_or_404(
        Evidence.objects.select_related(
            "subject", "uploaded_by", "shared_by"
        ).prefetch_related("student_links__student", "student_links__ehcp_target"),
        pk=pk,
    )
    links = item.student_links.select_related("student", "ehcp_target")
    first_student = links[0].student if links else None
    context = {"item": item, "student": first_student, "student_links": links}
    return render(request, "evidence/evidence_detail.html", context)


@login_required
def evidence_toggle_share(request, pk):
    """Toggle family sharing on/off for an evidence item."""
    item = get_object_or_404(Evidence, pk=pk)

    if item.is_shared_with_family:
        item.is_shared_with_family = False
        item.shared_at = None
        item.shared_by = None
        item.save(update_fields=["is_shared_with_family", "shared_at", "shared_by"])
        label = "unshared"
    else:
        item.is_shared_with_family = True
        item.shared_at = timezone.now()
        item.shared_by = request.user
        item.save(update_fields=["is_shared_with_family", "shared_at", "shared_by"])
        label = "shared with family"

    if request.htmx:
        badge = (
            '<span class="badge bg-success"><i class="bi bi-people-fill me-1"></i>Shared</span>'
            if item.is_shared_with_family
            else '<span class="badge bg-secondary"><i class="bi bi-lock-fill me-1"></i>Private</span>'
        )
        return HttpResponse(badge)

    messages.success(request, f"Evidence {label}.")
    return redirect("evidence:evidence_detail", pk=pk)


@login_required
def evidence_delete(request, pk):
    """Delete an evidence item."""
    item = get_object_or_404(Evidence, pk=pk)
    first_link = item.student_links.select_related("student").first()

    if request.method == "POST":
        item.file.delete(save=False)
        if item.thumbnail:
            item.thumbnail.delete(save=False)
        item.delete()
        messages.success(request, "Evidence deleted.")
        if first_link:
            return redirect("evidence:evidence_gallery", student_pk=first_link.student.pk)
        return redirect("evidence:evidence_gallery_all")

    context = {"item": item, "student": first_link.student if first_link else None}
    return render(request, "evidence/evidence_confirm_delete.html", context)


# ── Face Blur ───────────────────────────────────────────────────────

@login_required
def evidence_blur(request, pk):
    """Face blur selection page — shows detected faces, lets staff choose which to keep."""
    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_image:
        return redirect("evidence:evidence_detail", pk=pk)

    # Get faces from session (set during upload) or detect fresh
    session_key = f"faces_{item.pk}"
    faces = request.session.get(session_key)
    if not faces:
        faces = detect_faces(item.file.path)
        if not faces:
            messages.info(request, "No faces detected in this image.")
            return redirect("evidence:evidence_detail", pk=pk)

    first_link = item.student_links.select_related("student").first()
    context = {
        "item": item,
        "student": first_link.student if first_link else None,
        "faces": json.dumps(faces),
        "face_count": len(faces),
    }
    return render(request, "evidence/evidence_blur.html", context)


@login_required
@require_POST
def evidence_apply_blur(request, pk):
    """Apply blur to non-kept faces and save the image.

    Accepts faces_json (user-modified coordinates with keep flags)
    or falls back to the legacy keep_faces index approach.
    """
    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_image:
        return redirect("evidence:evidence_detail", pk=pk)

    faces_json_raw = request.POST.get("faces_json", "").strip()

    if faces_json_raw:
        # New interactive UI sends full face list with keep flags
        all_faces = json.loads(faces_json_raw)
        blur_faces = [
            {"x": f["x"], "y": f["y"], "w": f["w"], "h": f["h"]}
            for f in all_faces if not f.get("keep", False)
        ]
        if blur_faces:
            blurred_img = apply_blur_to_faces(
                item.file.path, blur_faces, keep_indices=set()
            )
            blurred_img.save(item.file.path, quality=90)
            _regenerate_thumbnail(item)
            item.save(update_fields=["updated_at"])
    else:
        # Legacy fallback: keep_faces as comma-separated indices
        session_key = f"faces_{item.pk}"
        faces = request.session.get(session_key)
        if not faces:
            faces = detect_faces(item.file.path)

        keep_raw = request.POST.get("keep_faces", "")
        keep_indices = set()
        for idx in keep_raw.split(","):
            idx = idx.strip()
            if idx.isdigit():
                keep_indices.add(int(idx))

        if faces:
            blurred_img = apply_blur_to_faces(item.file.path, faces, keep_indices)
            blurred_img.save(item.file.path, quality=90)
            _regenerate_thumbnail(item)
            item.save(update_fields=["updated_at"])

        request.session.pop(session_key, None)

    messages.success(request, "Face blur applied successfully.")
    return redirect("evidence:evidence_detail", pk=pk)


@login_required
def evidence_detect_faces_api(request, pk):
    """API endpoint: detect faces in an evidence image. Returns JSON."""
    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_image:
        return JsonResponse({"faces": []})
    faces = detect_faces(item.file.path)
    return JsonResponse({"faces": faces})


# ── Manual Blur Brush ───────────────────────────────────────────────

@login_required
def evidence_manual_blur(request, pk):
    """Manual blur brush page — HTML5 Canvas-based drawing tool."""
    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_image:
        return redirect("evidence:evidence_detail", pk=pk)

    context = {"item": item, "student": None}
    return render(request, "evidence/evidence_manual_blur.html", context)


@login_required
@require_POST
def evidence_apply_manual_blur(request, pk):
    """Apply manual blur strokes and save the image."""
    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_image:
        return redirect("evidence:evidence_detail", pk=pk)

    strokes_json = request.POST.get("blur_mask", "")
    if not strokes_json or strokes_json == "[]":
        messages.info(request, "No blur areas selected.")
        return redirect("evidence:evidence_detail", pk=pk)

    try:
        strokes = json.loads(strokes_json)
    except (json.JSONDecodeError, ValueError):
        messages.error(request, "Invalid blur data.")
        return redirect("evidence:evidence_detail", pk=pk)

    # Apply strokes to image using OpenCV
    img_cv = cv2.imread(item.file.path)
    if img_cv is None:
        messages.error(request, "Could not open image file.")
        return redirect("evidence:evidence_detail", pk=pk)

    # Create blur mask
    mask = np.zeros(img_cv.shape[:2], dtype=np.uint8)

    for stroke in strokes:
        pts = []
        for point in stroke:
            x = int(point.get("x", 0))
            y = int(point.get("y", 0))
            size = int(point.get("size", 20))
            radius = max(size // 2, 5)
            cv2.circle(mask, (x, y), radius, 255, -1)
            pts.append((x, y))
        # Also draw thick lines connecting points for smooth coverage
        if len(pts) > 1:
            for i in range(len(pts) - 1):
                thickness = int(stroke[i].get("size", 20))
                cv2.line(mask, pts[i], pts[i + 1], 255, max(thickness, 10))

    # Strong Gaussian blur — apply iteratively for heavy effect
    blurred = cv2.GaussianBlur(img_cv, (99, 99), 30)
    blurred = cv2.GaussianBlur(blurred, (99, 99), 30)

    # Composite: original where mask is 0, blurred where mask is 255
    mask_3ch = cv2.merge([mask, mask, mask])
    result = np.where(mask_3ch > 0, blurred, img_cv)

    # Save back using OpenCV (preserves format correctly)
    cv2.imwrite(item.file.path, result)

    # Regenerate thumbnail from the blurred image
    _regenerate_thumbnail(item)

    # Touch the model to update cache-bust timestamp
    item.save(update_fields=["updated_at"])

    messages.success(request, "Manual blur applied successfully.")
    return redirect("evidence:evidence_detail", pk=pk)


# ── Video Face Tracking & Blur ─────────────────────────────────────

def _detect_faces_on_frame(frame, detector, det_w, det_h, scale):
    """Detect faces on a single OpenCV frame. Returns list of (x, y, w, h)."""
    if detector is not None:
        if scale != 1.0:
            small = cv2.resize(frame, (det_w, det_h), interpolation=cv2.INTER_AREA)
        else:
            small = frame
        _, detections = detector.detect(small)
        if detections is not None:
            inv = 1.0 / scale
            return [
                (int(d[0] * inv), int(d[1] * inv), int(d[2] * inv), int(d[3] * inv))
                for d in detections
            ]
        return []
    # Haar fallback
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if scale != 1.0:
        gray = cv2.resize(gray, (det_w, det_h), interpolation=cv2.INTER_AREA)
    gray = cv2.equalizeHist(gray)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
    )
    rects = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
    )
    inv = 1.0 / scale
    return [(int(x * inv), int(y * inv), int(w * inv), int(h * inv)) for (x, y, w, h) in rects]


def _face_histogram(frame, x, y, w, h, frame_h, frame_w):
    """Compute a normalised HSV colour histogram for a face crop."""
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(frame_w, x + w)
    y2 = min(frame_h, y + h)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def _cluster_faces(face_entries, threshold=0.55):
    """Cluster face entries by histogram similarity.

    Each entry: {"hist": np.array, "crop_b64": str, "rect": (x,y,w,h), "frame_idx": int}
    Returns list of clusters, each cluster = list of entries.
    """
    clusters = []
    for entry in face_entries:
        best_score = -1
        best_idx = -1
        for ci, cluster in enumerate(clusters):
            score = cv2.compareHist(entry["hist"], cluster[0]["hist"], cv2.HISTCMP_CORREL)
            if score > best_score:
                best_score = score
                best_idx = ci
        if best_score >= threshold and best_idx >= 0:
            clusters[best_idx].append(entry)
        else:
            clusters.append([entry])
    return clusters


@login_required
def video_face_blur(request, pk):
    """Detect faces across video, cluster unique individuals, show selection page."""
    import base64

    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_video:
        return redirect("evidence:evidence_detail", pk=pk)

    from .blur import _YUNET_MODEL

    src_path = item.file.path
    cap = cv2.VideoCapture(src_path)
    if not cap.isOpened():
        messages.error(request, "Could not open video file.")
        return redirect("evidence:evidence_detail", pk=pk)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        messages.error(request, "Could not read video frames.")
        return redirect("evidence:evidence_detail", pk=pk)

    # Prepare detector
    max_dim = 640
    scale = 1.0
    if max(frame_h, frame_w) > max_dim:
        scale = max_dim / max(frame_h, frame_w)
    det_w = int(frame_w * scale)
    det_h = int(frame_h * scale)

    has_yunet = os.path.isfile(_YUNET_MODEL)
    detector = None
    if has_yunet:
        detector = cv2.FaceDetectorYN.create(_YUNET_MODEL, "", (det_w, det_h))
        detector.setScoreThreshold(0.6)

    # Sample ~2 fps, but cap at 30 samples for speed
    sample_interval = max(1, int(fps / 2))
    max_samples = 30
    sample_count = 0

    face_entries = []  # each: {hist, crop_b64, rect, frame_idx}
    frame_num = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_num % sample_interval == 0 and sample_count < max_samples:
            sample_count += 1
            faces = _detect_faces_on_frame(frame, detector, det_w, det_h, scale)
            for (fx, fy, fw, fh) in faces:
                hist = _face_histogram(frame, fx, fy, fw, fh, frame_h, frame_w)
                if hist is None:
                    continue
                # Crop face for thumbnail (limit size)
                x1, y1 = max(0, fx), max(0, fy)
                x2, y2 = min(frame_w, fx + fw), min(frame_h, fy + fh)
                crop_bgr = frame[y1:y2, x1:x2]
                if crop_bgr.size == 0:
                    continue
                thumb = cv2.resize(crop_bgr, (80, 80), interpolation=cv2.INTER_AREA)
                _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
                b64 = base64.b64encode(buf).decode("ascii")
                face_entries.append({
                    "hist": hist,
                    "crop_b64": b64,
                    "rect": (fx, fy, fw, fh),
                    "frame_idx": frame_num,
                })
        frame_num += 1

    cap.release()

    if not face_entries:
        messages.info(request, "No faces detected in the video.")
        return redirect("evidence:evidence_detail", pk=pk)

    # Cluster into unique individuals
    clusters = _cluster_faces(face_entries, threshold=0.55)

    # Build cluster summaries for the template & session
    cluster_data = []  # sent to template
    session_clusters = []  # stored in session for processing

    for ci, cluster in enumerate(clusters):
        # Pick the crop from the middle of the cluster (likely best quality)
        rep_entry = cluster[len(cluster) // 2]
        # Compute mean histogram for this cluster
        mean_hist = np.zeros_like(cluster[0]["hist"])
        for entry in cluster:
            mean_hist += entry["hist"]
        mean_hist /= len(cluster)
        cv2.normalize(mean_hist, mean_hist)

        cluster_data.append({
            "id": ci,
            "crop_b64": rep_entry["crop_b64"],
            "appearances": len(cluster),
        })
        # Session: store mean histogram as list + sample rects
        session_clusters.append({
            "mean_hist": mean_hist.flatten().tolist(),
            "rects": [(e["rect"][0], e["rect"][1], e["rect"][2], e["rect"][3])
                      for e in cluster],
        })

    # Store cluster histograms in session so the apply view can use them
    request.session[f"vfb_clusters_{pk}"] = session_clusters

    context = {
        "item": item,
        "clusters": cluster_data,
        "total_faces": len(face_entries),
    }
    return render(request, "evidence/video_face_blur.html", context)


@login_required
@require_POST
def video_apply_face_blur(request, pk):
    """Process video blurring only the faces the user selected.

    Receives keep_ids — the cluster indices to leave UN-blurred.
    For every frame, detects faces, matches each to the nearest cluster
    by histogram, and blurs only non-kept faces.
    """
    import subprocess
    import tempfile
    import shutil

    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_video:
        return redirect("evidence:evidence_detail", pk=pk)

    # Parse kept cluster IDs from form
    keep_raw = request.POST.get("keep_ids", "")
    keep_ids = set()
    for tok in keep_raw.split(","):
        tok = tok.strip()
        if tok.isdigit():
            keep_ids.add(int(tok))

    # Retrieve cluster histograms from session
    session_key = f"vfb_clusters_{pk}"
    session_clusters = request.session.pop(session_key, None)
    if not session_clusters:
        messages.error(request, "Face detection data expired. Please try again.")
        return redirect("evidence:video_face_blur", pk=pk)

    # Rebuild mean histograms as numpy arrays
    cluster_hists = []
    for sc in session_clusters:
        h = np.array(sc["mean_hist"], dtype=np.float32).reshape(32, 32)
        cluster_hists.append(h)

    from .blur import _YUNET_MODEL

    src_path = item.file.path
    cap = cv2.VideoCapture(src_path)
    if not cap.isOpened():
        messages.error(request, "Could not open video file.")
        return redirect("evidence:evidence_detail", pk=pk)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Prepare detector
    max_dim = 640
    scale = 1.0
    if max(frame_h, frame_w) > max_dim:
        scale = max_dim / max(frame_h, frame_w)
    det_w = int(frame_w * scale)
    det_h = int(frame_h * scale)

    has_yunet = os.path.isfile(_YUNET_MODEL)
    detector = None
    if has_yunet:
        detector = cv2.FaceDetectorYN.create(_YUNET_MODEL, "", (det_w, det_h))
        detector.setScoreThreshold(0.6)

    # We detect on every Nth frame for speed, but blur using the last known rects
    detect_interval = max(1, int(fps / 4))  # ~4 detections per second
    current_blur_rects = []  # faces to blur on the current frame

    tmp_raw = tempfile.NamedTemporaryFile(suffix=".avi", delete=False)
    tmp_raw_path = tmp_raw.name
    tmp_raw.close()

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    out = cv2.VideoWriter(tmp_raw_path, fourcc, fps, (frame_w, frame_h))
    thumbnail_frame = None
    thumb_at = int(fps)

    frame_num = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Periodically re-detect faces
        if frame_num % detect_interval == 0:
            faces = _detect_faces_on_frame(frame, detector, det_w, det_h, scale)
            current_blur_rects = []
            for (fx, fy, fw, fh) in faces:
                hist = _face_histogram(frame, fx, fy, fw, fh, frame_h, frame_w)
                if hist is None:
                    # Can't compute histogram — blur to be safe
                    current_blur_rects.append((fx, fy, fw, fh))
                    continue
                # Match to nearest cluster
                best_score = -1
                best_ci = -1
                for ci, ch in enumerate(cluster_hists):
                    score = cv2.compareHist(hist, ch, cv2.HISTCMP_CORREL)
                    if score > best_score:
                        best_score = score
                        best_ci = ci
                # If match is good and cluster is kept → don't blur
                if best_score >= 0.4 and best_ci in keep_ids:
                    continue
                current_blur_rects.append((fx, fy, fw, fh))

        # Apply blur to current rects
        pad_pct = 0.15
        for (fx, fy, fw, fh) in current_blur_rects:
            px, py = int(fw * pad_pct), int(fh * pad_pct)
            rx1 = max(0, fx - px)
            ry1 = max(0, fy - py)
            rx2 = min(frame_w, fx + fw + px)
            ry2 = min(frame_h, fy + fh + py)
            roi = frame[ry1:ry2, rx1:rx2]
            if roi.size > 0:
                blurred = cv2.GaussianBlur(roi, (99, 99), 30)
                frame[ry1:ry2, rx1:rx2] = blurred

        if frame_num == thumb_at:
            thumbnail_frame = frame.copy()
        out.write(frame)
        frame_num += 1

    cap.release()
    out.release()

    # ffmpeg re-encode
    tmp_final = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_final_path = tmp_final.name
    tmp_final.close()

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", tmp_raw_path,
        "-i", src_path,
        "-map", "0:v:0",
        "-map", "1:a?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-vf", "format=yuv420p",
        "-color_range", "tv",
        "-c:a", "aac",
        "-movflags", "+faststart",
        tmp_final_path,
    ]

    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        for p in (tmp_raw_path, tmp_final_path):
            try:
                os.remove(p)
            except OSError:
                pass
        detail = ""
        if hasattr(exc, "stderr") and exc.stderr:
            detail = exc.stderr.decode(errors="replace")[:200]
        messages.error(request, f"Video encoding failed. {detail}")
        return redirect("evidence:evidence_detail", pk=pk)
    finally:
        try:
            os.remove(tmp_raw_path)
        except OSError:
            pass

    # Replace source file
    base, ext = os.path.splitext(src_path)
    if ext.lower() != ".mp4":
        new_path = base + ".mp4"
        shutil.move(tmp_final_path, new_path)
        os.chmod(new_path, 0o644)
        old_name = item.file.name
        item.file.name = os.path.splitext(old_name)[0] + ".mp4"
        if os.path.isfile(src_path):
            os.remove(src_path)
    else:
        shutil.move(tmp_final_path, src_path)
        os.chmod(src_path, 0o644)

    if thumbnail_frame is not None:
        thumb_path = f"evidence/thumbnails/{item.pk}_thumb.jpg"
        full_thumb_path = os.path.join(django_settings.MEDIA_ROOT, thumb_path)
        os.makedirs(os.path.dirname(full_thumb_path), exist_ok=True)
        cv2.imwrite(full_thumb_path, thumbnail_frame)
        item.thumbnail = thumb_path

    item.save(update_fields=["file", "thumbnail", "updated_at"])
    messages.success(request, "Face blur applied to selected faces.")
    return redirect("evidence:evidence_detail", pk=pk)


# ── Video Blur Region ──────────────────────────────────────────────

@login_required
def video_blur_region(request, pk):
    """Page for selecting a rectangle region to blur in a video."""
    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_video:
        return redirect("evidence:evidence_detail", pk=pk)

    context = {"item": item, "student": None}
    return render(request, "evidence/video_blur_region.html", context)


@login_required
@require_POST
def video_apply_blur_region(request, pk):
    """Apply fixed-region blur to a video and re-encode as browser-playable
    H.264 MP4, preserving the audio track."""
    item = get_object_or_404(Evidence, pk=pk)
    if not item.is_video:
        return redirect("evidence:evidence_detail", pk=pk)

    region_json = request.POST.get("blur_region", "")
    thumbnail_time = float(request.POST.get("thumbnail_time", 0))

    if not region_json:
        messages.info(request, "No blur region selected.")
        return redirect("evidence:evidence_detail", pk=pk)

    try:
        region = json.loads(region_json)
    except (json.JSONDecodeError, ValueError):
        messages.error(request, "Invalid blur region data.")
        return redirect("evidence:evidence_detail", pk=pk)

    x = int(region.get("x", 0))
    y = int(region.get("y", 0))
    w = int(region.get("w", 0))
    h = int(region.get("h", 0))

    if w <= 0 or h <= 0:
        messages.info(request, "No blur region drawn.")
        return redirect("evidence:evidence_detail", pk=pk)

    import subprocess
    import tempfile
    import shutil

    src_path = item.file.path

    cap = cv2.VideoCapture(src_path)
    if not cap.isOpened():
        messages.error(request, "Could not open video file.")
        return redirect("evidence:evidence_detail", pk=pk)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Step 1: OpenCV writes blurred frames to a raw AVI
    tmp_raw = tempfile.NamedTemporaryFile(suffix=".avi", delete=False)
    tmp_raw_path = tmp_raw.name
    tmp_raw.close()

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    out = cv2.VideoWriter(tmp_raw_path, fourcc, fps, (frame_w, frame_h))
    thumbnail_frame = None
    thumbnail_frame_num = int(thumbnail_time * fps)
    frame_num = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(frame_w, x + w), min(frame_h, y + h)
        if x2 > x1 and y2 > y1:
            roi = frame[y1:y2, x1:x2]
            blurred_roi = cv2.GaussianBlur(roi, (99, 99), 30)
            frame[y1:y2, x1:x2] = blurred_roi

        if frame_num == thumbnail_frame_num:
            thumbnail_frame = frame.copy()

        out.write(frame)
        frame_num += 1

    cap.release()
    out.release()

    # Step 2: ffmpeg re-encodes to H.264 MP4 and copies audio from original
    tmp_final = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_final_path = tmp_final.name
    tmp_final.close()

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", tmp_raw_path,     # blurred video frames
        "-i", src_path,         # original file (for audio)
        "-map", "0:v:0",        # video from blurred
        "-map", "1:a?",         # audio from original (if present)
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-vf", "format=yuv420p",  # force standard color range
        "-color_range", "tv",     # broadcast/limited range
        "-c:a", "aac",
        "-movflags", "+faststart",  # web-friendly: moov atom at start
        tmp_final_path,
    ]

    try:
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=300)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Clean up temp files
        for p in (tmp_raw_path, tmp_final_path):
            try:
                os.remove(p)
            except OSError:
                pass
        detail = ""
        if hasattr(exc, "stderr") and exc.stderr:
            detail = exc.stderr.decode(errors="replace")[:200]
        messages.error(request, f"Video encoding failed. {detail}")
        return redirect("evidence:evidence_detail", pk=pk)
    finally:
        try:
            os.remove(tmp_raw_path)
        except OSError:
            pass

    # Replace original — rename to .mp4 if needed for browser compatibility
    base, ext = os.path.splitext(src_path)
    if ext.lower() != ".mp4":
        new_path = base + ".mp4"
        shutil.move(tmp_final_path, new_path)
        os.chmod(new_path, 0o644)
        # Update the Django FileField to point to the new filename
        old_name = item.file.name
        item.file.name = os.path.splitext(old_name)[0] + ".mp4"
        # Remove the old file if it still exists
        if os.path.isfile(src_path):
            os.remove(src_path)
    else:
        shutil.move(tmp_final_path, src_path)
        os.chmod(src_path, 0o644)

    # Save thumbnail if captured
    if thumbnail_frame is not None:
        thumb_path = f"evidence/thumbnails/{item.pk}_thumb.jpg"
        full_thumb_path = os.path.join(django_settings.MEDIA_ROOT, thumb_path)
        os.makedirs(os.path.dirname(full_thumb_path), exist_ok=True)
        cv2.imwrite(full_thumb_path, thumbnail_frame)
        item.thumbnail = thumb_path

    item.save(update_fields=["file", "thumbnail", "updated_at"])
    messages.success(request, "Video blur applied successfully.")
    return redirect("evidence:evidence_detail", pk=pk)


# ── Quick Evidence Capture (no student pre-selected) ────────────────

@login_required
def quick_evidence_upload(request):
    """Quick capture: upload/take evidence without pre-selecting a student.

    After capture, redirect to the linking step where staff choose
    students, subject, and EHCP targets.
    """
    if request.method == "POST":
        file = request.FILES.get("file")
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        evidence_type = request.POST.get("evidence_type", "PHOTO")
        captured_date = request.POST.get("captured_date", "").strip()

        if not file:
            messages.error(request, "Please select a file or take a photo/video.")
            return redirect("evidence:quick_evidence_upload")

        if not captured_date:
            captured_date = timezone.now().date()

        if file.size > 50 * 1024 * 1024:
            messages.error(request, "File too large. Maximum size is 50 MB.")
            return redirect("evidence:quick_evidence_upload")

        item = Evidence.objects.create(
            evidence_type=evidence_type,
            title=title or file.name,
            description=description,
            file=file,
            captured_date=captured_date,
            uploaded_by=request.user,
        )

        # Auto-orient and convert HEIC→JPEG for photos
        if item.is_image or item.file_extension in (".heic", ".heif"):
            _normalise_image(item)

        # Generate thumbnail
        if item.is_image:
            _regenerate_thumbnail(item)
            item.save(update_fields=["thumbnail"])
        if item.is_video:
            _generate_video_thumbnail(item)
            item.save(update_fields=["thumbnail"])

        # For photos, check for faces and redirect to blur first
        if item.is_image:
            faces = detect_faces(item.file.path)
            if faces:
                request.session[f"faces_{item.pk}"] = faces
                # After blur, they'll go to detail, which shows the link prompt
                messages.info(
                    request,
                    f"{len(faces)} face(s) detected — blur faces first, then link to students.",
                )
                return redirect("evidence:evidence_blur", pk=item.pk)

        # Go straight to linking step
        return redirect("evidence:evidence_link_students", pk=item.pk)

    context = {
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "evidence/quick_evidence_upload.html", context)


@login_required
def evidence_link_students(request, pk):
    """Step 2: Link evidence to students, a subject, and EHCP targets."""
    item = get_object_or_404(Evidence, pk=pk)
    all_students = Student.objects.filter(is_active=True).select_related("class_group")
    subjects = Subject.objects.filter(is_active=True)

    if request.method == "POST":
        student_ids = request.POST.getlist("students")
        subject_id = request.POST.get("subject") or None

        if not student_ids:
            messages.error(request, "Please select at least one student.")
            return redirect("evidence:evidence_link_students", pk=pk)

        # Update subject on Evidence
        item.subject_id = subject_id
        item.save(update_fields=["subject", "updated_at"])

        # Clear old links and create new ones
        item.student_links.all().delete()
        for sid in student_ids:
            target_id = request.POST.get(f"ehcp_target_{sid}") or None
            EvidenceStudentLink.objects.create(
                evidence=item,
                student_id=sid,
                ehcp_target_id=target_id,
            )

        # Also set legacy FK to first student for backward compat
        item.student_id = student_ids[0]
        item.save(update_fields=["student", "updated_at"])

        messages.success(request, f"Evidence linked to {len(student_ids)} student(s).")
        return redirect("evidence:evidence_detail", pk=pk)

    # Pre-select existing links
    existing_links = {
        link.student_id: link.ehcp_target_id
        for link in item.student_links.all()
    }

    # Group students: assigned/covered class first, then the rest
    user = request.user
    today = timezone.now().date()
    my_class_ids = set(
        ClassGroup.objects.filter(assignments__user=user)
        .values_list("id", flat=True)
    )
    covered_ids = set(
        ClassGroup.objects.filter(
            covers__user=user,
            covers__start_date__lte=today,
            covers__end_date__gte=today,
        ).values_list("id", flat=True)
    )
    priority_ids = my_class_ids | covered_ids
    my_students = []
    other_students = []
    for s in all_students.order_by("last_name", "first_name"):
        if s.class_group_id and s.class_group_id in priority_ids:
            my_students.append(s)
        else:
            other_students.append(s)

    context = {
        "item": item,
        "my_students": my_students,
        "other_students": other_students,
        "all_students": list(all_students),
        "subjects": subjects,
        "existing_links": existing_links,
        "existing_subject": item.subject_id,
        "today": timezone.now().date().isoformat(),
        "has_priority_class": bool(priority_ids),
    }
    return render(request, "evidence/evidence_link_students.html", context)


@login_required
def student_ehcp_targets_api(request, student_pk):
    """HTMX endpoint: return EHCP target <option> elements for a student."""
    targets = EHCPTarget.objects.filter(
        student_id=student_pk
    ).exclude(status__in=["MET", "EXCEEDED"])

    html = '<option value="">— None —</option>'
    for t in targets:
        html += f'<option value="{t.pk}">{t.title[:60]}</option>'
    return HttpResponse(html)


# ── General Evidence Gallery ────────────────────────────────────────

@login_required
def evidence_gallery_all(request):
    """Browse all evidence across all students, with filters."""
    items = Evidence.objects.select_related(
        "subject", "uploaded_by"
    ).prefetch_related("student_links__student")

    # Filters
    etype = request.GET.get("type", "")
    if etype:
        items = items.filter(evidence_type=etype)

    student_id = request.GET.get("student", "")
    if student_id:
        items = items.filter(student_links__student_id=student_id)

    subject_id = request.GET.get("subject", "")
    if subject_id:
        items = items.filter(subject_id=subject_id)

    linked = request.GET.get("linked", "")
    if linked == "yes":
        items = items.filter(student_links__isnull=False)
    elif linked == "no":
        items = items.filter(student_links__isnull=True)

    items = items.distinct()

    all_students = Student.objects.filter(is_active=True)
    subjects = Subject.objects.filter(is_active=True)

    context = {
        "items": items[:100],
        "all_students": all_students,
        "subjects": subjects,
        "current_type": etype,
        "current_student": student_id,
        "current_subject": subject_id,
        "current_linked": linked,
    }
    return render(request, "evidence/evidence_gallery_all.html", context)


# ── EHCP Document Upload & OCR ──────────────────────────────────────

def _extract_pdf_text(pdf_path):
    """Extract text from a PDF. Try native text first, fall back to OCR."""
    import subprocess

    # Try pdftotext (native text layer) first
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()
            # If we got substantial text, it's a searchable PDF
            if len(text) > 100:
                return text, "native"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fall back to OCR via Tesseract
    try:
        import pytesseract
        from pdf2image import convert_from_path

        images = convert_from_path(pdf_path, dpi=300)
        pages = []
        for i, img in enumerate(images, 1):
            page_text = pytesseract.image_to_string(img, lang="eng")
            pages.append(f"--- Page {i} ---\n{page_text.strip()}")
        return "\n\n".join(pages), "ocr"
    except Exception as exc:
        raise RuntimeError(f"OCR failed: {exc}") from exc


def _generate_page_images(doc):
    """Convert PDF pages to JPEG images for the document viewer."""
    from pdf2image import convert_from_path

    pages_dir = os.path.join(
        django_settings.MEDIA_ROOT, "ehcp_pages", str(doc.pk)
    )
    os.makedirs(pages_dir, exist_ok=True)
    images = convert_from_path(doc.file.path, dpi=200)
    for i, img in enumerate(images, 1):
        img.save(
            os.path.join(pages_dir, f"page_{i:03d}.jpg"),
            "JPEG", quality=85,
        )


@login_required
def ehcp_document_upload(request, student_pk):
    """Upload an EHCP PDF for a student."""
    student = get_object_or_404(Student, pk=student_pk)

    if request.method == "POST":
        file = request.FILES.get("file")
        title = request.POST.get("title", "").strip()

        if not file:
            messages.error(request, "Please select a PDF file.")
            return redirect("evidence:ehcp_document_upload", student_pk=student.pk)

        if not file.name.lower().endswith(".pdf"):
            messages.error(request, "Only PDF files are accepted.")
            return redirect("evidence:ehcp_document_upload", student_pk=student.pk)

        if file.size > 30 * 1024 * 1024:
            messages.error(request, "File too large. Maximum size is 30 MB.")
            return redirect("evidence:ehcp_document_upload", student_pk=student.pk)

        doc = EHCPDocument.objects.create(
            student=student,
            file=file,
            original_filename=file.name,
            title=title or file.name,
            uploaded_by=request.user,
        )
        return redirect("evidence:ehcp_document_process", pk=doc.pk)

    context = {"student": student}
    return render(request, "evidence/ehcp_document_upload.html", context)


@login_required
def ehcp_document_process(request, pk):
    """Run OCR/text extraction on an uploaded EHCP PDF."""
    doc = get_object_or_404(EHCPDocument.objects.select_related("student"), pk=pk)

    if doc.processing_status == "COMPLETED":
        return redirect("evidence:ehcp_document_view", pk=pk)

    doc.processing_status = "PROCESSING"
    doc.save(update_fields=["processing_status"])

    try:
        text, method = _extract_pdf_text(doc.file.path)

        # Count pages
        try:
            from pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(doc.file.path)
            doc.page_count = info.get("Pages", 0)
        except Exception:
            doc.page_count = text.count("--- Page ")

        doc.ocr_text = text
        doc.edited_text = text  # start with OCR output for editing
        doc.processing_status = "COMPLETED"
        doc.save(update_fields=[
            "ocr_text", "edited_text", "processing_status", "page_count",
        ])
        messages.success(
            request,
            f"Text extracted ({method}) — {doc.page_count} page(s). "
            "You can now review and edit the text.",
        )

        # Generate page images for the document viewer
        try:
            _generate_page_images(doc)
        except Exception:
            pass  # Non-critical — falls back to iframe PDF viewer

    except Exception as exc:
        doc.processing_status = "FAILED"
        doc.save(update_fields=["processing_status"])
        messages.error(request, f"Text extraction failed: {exc}")

    return redirect("evidence:ehcp_document_view", pk=pk)


@login_required
def ehcp_document_view(request, pk):
    """View/edit extracted EHCP text side-by-side with the original PDF."""
    doc = get_object_or_404(EHCPDocument.objects.select_related("student"), pk=pk)
    student = doc.student

    if request.method == "POST":
        doc.edited_text = request.POST.get("edited_text", "")
        doc.title = request.POST.get("title", doc.title).strip()
        doc.save(update_fields=["edited_text", "title", "updated_at"])
        messages.success(request, "Changes saved.")
        return redirect("evidence:ehcp_document_view", pk=pk)

    context = {
        "doc": doc,
        "student": student,
        "page_images": doc.get_page_image_urls(),
    }
    return render(request, "evidence/ehcp_document_view.html", context)


# ── Annotation API ──────────────────────────────────────────────────

@login_required
def ehcp_annotations_api(request, pk):
    """GET: list annotations for a document. POST: create a new annotation."""
    doc = get_object_or_404(EHCPDocument, pk=pk)

    if request.method == "GET":
        annotations = doc.annotations.all().values(
            "id", "annotation_type", "page", "x", "y",
            "width", "height", "color", "text",
        )
        return JsonResponse(list(annotations), safe=False)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        annotation = EHCPAnnotation.objects.create(
            document=doc,
            annotation_type=data.get("type", "highlight"),
            page=int(data.get("page", 1)),
            x=float(data.get("x", 0)),
            y=float(data.get("y", 0)),
            width=float(data.get("width", 0)),
            height=float(data.get("height", 0)),
            color=data.get("color", "#ffeb3b"),
            text=data.get("text", ""),
            created_by=request.user,
        )
        return JsonResponse({
            "id": annotation.id,
            "type": annotation.annotation_type,
            "page": annotation.page,
            "x": annotation.x, "y": annotation.y,
            "width": annotation.width, "height": annotation.height,
            "color": annotation.color, "text": annotation.text,
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
@require_POST
def ehcp_annotation_delete(request, pk):
    """Delete a single annotation."""
    annotation = get_object_or_404(EHCPAnnotation, pk=pk)
    annotation.delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def ehcp_annotation_update(request, pk):
    """Update an annotation (text, color, position)."""
    annotation = get_object_or_404(EHCPAnnotation, pk=pk)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    for field in ("x", "y", "width", "height"):
        if field in data:
            setattr(annotation, field, float(data[field]))
    if "color" in data:
        annotation.color = data["color"]
    if "text" in data:
        annotation.text = data["text"]
    if "type" in data:
        annotation.annotation_type = data["type"]
    annotation.save()
    return JsonResponse({"ok": True})


@login_required
def ehcp_document_export_pdf(request, pk):
    """Export the EHCP PDF with annotations burned in."""
    doc = get_object_or_404(EHCPDocument, pk=pk)
    annotations = list(doc.annotations.all())

    if not annotations:
        # No annotations — just serve the original PDF
        with open(doc.file.path, "rb") as f:
            resp = HttpResponse(f.read(), content_type="application/pdf")
            resp["Content-Disposition"] = f'attachment; filename="annotated_{doc.original_filename}"'
            return resp

    # Use ReportLab to overlay annotations on the original PDF
    from io import BytesIO

    from PIL import Image as PILImage
    from reportlab.lib.colors import Color
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    # Render each page as image, draw annotations, combine into PDF
    pages_dir = os.path.join(
        django_settings.MEDIA_ROOT, "ehcp_pages", str(doc.pk)
    )

    page_files = sorted(
        f for f in os.listdir(pages_dir) if f.endswith(".jpg")
    ) if os.path.isdir(pages_dir) else []

    if not page_files:
        # Fall back to original PDF if no page images
        with open(doc.file.path, "rb") as f:
            resp = HttpResponse(f.read(), content_type="application/pdf")
            resp["Content-Disposition"] = f'attachment; filename="annotated_{doc.original_filename}"'
            return resp

    buf = BytesIO()

    # Group annotations by page
    ann_by_page = {}
    for ann in annotations:
        ann_by_page.setdefault(ann.page, []).append(ann)

    c = None
    for i, page_file in enumerate(page_files, start=1):
        img_path = os.path.join(pages_dir, page_file)
        img = PILImage.open(img_path)
        img_w, img_h = img.size

        if c is None:
            c = rl_canvas.Canvas(buf, pagesize=(img_w, img_h))
        else:
            c.showPage()
            c.setPageSize((img_w, img_h))

        # Draw page image
        c.drawImage(ImageReader(img), 0, 0, width=img_w, height=img_h)

        # Draw annotations for this page
        for ann in ann_by_page.get(i, []):
            ax = ann.x / 100.0 * img_w
            ay = ann.y / 100.0 * img_h
            aw = ann.width / 100.0 * img_w
            ah = ann.height / 100.0 * img_h
            # ReportLab origin is bottom-left; convert
            rl_y = img_h - ay - ah

            r = int(ann.color[1:3], 16) / 255.0
            g = int(ann.color[3:5], 16) / 255.0
            b = int(ann.color[5:7], 16) / 255.0

            if ann.annotation_type == "highlight":
                c.setFillColor(Color(r, g, b, alpha=0.35))
                c.setStrokeColor(Color(r, g, b, alpha=0))
                c.rect(ax, rl_y, aw, ah, fill=True, stroke=False)

            elif ann.annotation_type == "strikethrough":
                c.setStrokeColor(Color(r, g, b, alpha=0.8))
                c.setLineWidth(2)
                mid_y = rl_y + ah / 2
                c.line(ax, mid_y, ax + aw, mid_y)

            elif ann.annotation_type in ("textbox", "note"):
                # Draw background
                c.setFillColor(Color(r, g, b, alpha=0.15))
                c.setStrokeColor(Color(r, g, b, alpha=0.8))
                c.setLineWidth(1)
                c.rect(ax, rl_y, aw, ah, fill=True, stroke=True)
                # Draw text
                if ann.text:
                    c.setFillColor(Color(0, 0, 0, alpha=1))
                    font_size = max(8, min(14, ah * 0.6))
                    c.setFont("Helvetica", font_size)
                    text_y = rl_y + ah - font_size - 2
                    c.drawString(ax + 3, text_y, ann.text[:100])

    if c:
        c.save()

    buf.seek(0)
    resp = HttpResponse(buf.read(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="annotated_{doc.original_filename}"'
    return resp


@login_required
def ehcp_document_list(request, student_pk):
    """List all EHCP documents for a student."""
    student = get_object_or_404(Student, pk=student_pk)
    docs = student.ehcp_documents.all()
    context = {"student": student, "docs": docs}
    return render(request, "evidence/ehcp_document_list.html", context)


@login_required
@require_POST
def ehcp_document_delete(request, pk):
    """Delete an EHCP document."""
    doc = get_object_or_404(EHCPDocument.objects.select_related("student"), pk=pk)
    student_pk = doc.student.pk
    # Remove file from disk
    if doc.file and os.path.isfile(doc.file.path):
        os.remove(doc.file.path)
    doc.delete()
    messages.success(request, "EHCP document deleted.")
    return redirect("evidence:ehcp_document_list", student_pk=student_pk)


@login_required
def ehcp_document_extract_targets(request, pk):
    """Use AI to extract EHCP targets from the document text."""
    from core.models import AISettings

    doc = get_object_or_404(EHCPDocument.objects.select_related("student"), pk=pk)
    student = doc.student
    ai = AISettings.load()

    # Use edited text if available, otherwise OCR text
    source_text = doc.edited_text or doc.ocr_text

    if not source_text:
        messages.error(request, "No text available. Please run OCR first.")
        return redirect("evidence:ehcp_document_view", pk=pk)

    extracted_targets = []
    ai_error = None

    if request.method == "POST" and "import" in request.POST:
        # Import selected targets — auto-create outcome areas if needed
        # Build fuzzy lookup: normalise punctuation for matching
        def _norm(name):
            """Normalise outcome name for fuzzy matching."""
            n = name.lower().strip()
            n = n.replace(",", "").replace("&/or", "&").replace(" and ", " & ")
            return " ".join(n.split())

        all_outcomes = list(EHCPOutcome.objects.all())
        outcome_map = {}           # norm_name -> EHCPOutcome
        for o in all_outcomes:
            outcome_map[_norm(o.name)] = o
        max_order = max((o.order for o in all_outcomes), default=0)

        imported = 0
        target_titles = request.POST.getlist("target_title")
        target_descriptions = request.POST.getlist("target_description")
        target_outcomes = request.POST.getlist("target_outcome")

        for title, desc, outcome_name in zip(
            target_titles, target_descriptions, target_outcomes
        ):
            title = title.strip()
            if not title:
                continue
            outcome_name = outcome_name.strip()
            outcome = None
            if outcome_name:
                outcome = outcome_map.get(_norm(outcome_name))
                if outcome is None:
                    # Auto-create the outcome area
                    max_order += 1
                    outcome = EHCPOutcome.objects.create(
                        name=outcome_name, order=max_order,
                    )
                    outcome_map[_norm(outcome_name)] = outcome
            EHCPTarget.objects.create(
                student=student,
                outcome=outcome,
                title=title,
                description=desc.strip(),
                status="NOT_STARTED",
                set_date=timezone.now().date(),
                created_by=request.user,
            )
            imported += 1

        messages.success(request, f"{imported} target(s) imported.")
        return redirect("evidence:ehcp_overview", student_pk=student.pk)

    # Extract targets via AI
    if not ai.enabled or ai.provider == "none":
        ai_error = (
            "AI is not configured. Go to Setup → AI Settings to connect a provider. "
            "You can still manually create targets from the EHCP overview page."
        )
    else:
        from core.ai import ai_chat

        prompt = (
            "You are a UK SEN education specialist. Extract all EHCP outcomes and their "
            "associated targets from the following EHCP document text.\n\n"
            "An EHCP has broad outcome areas (e.g. Communication & Interaction, "
            "Cognition & Learning, Social Emotional & Mental Health, "
            "Sensory & Physical, Independence). Each outcome area contains "
            "specific targets that the child is working towards.\n\n"
            "For each target you find, provide:\n"
            "- title: a short name for the target\n"
            "- description: the full target description text from the EHCP\n"
            "- outcome: the EHCP outcome area this target falls under\n\n"
            "Return ONLY a JSON array of objects with keys: title, description, outcome.\n"
            "Do not include any other text.\n\n"
            f"--- EHCP DOCUMENT ---\n{source_text[:8000]}"
        )

        reply, err = ai_chat(prompt, max_tokens=4000, timeout=60)
        if err:
            ai_error = f"AI request failed: {err}"
        else:
            # Extract JSON from the reply (handle markdown code blocks)
            reply = reply.strip()
            if reply.startswith("```"):
                lines = reply.split("\n")
                reply = "\n".join(lines[1:])
                if reply.endswith("```"):
                    reply = reply[:-3]
            reply = reply.strip()

            try:
                extracted_targets = json.loads(reply)
                if not isinstance(extracted_targets, list):
                    extracted_targets = []
            except json.JSONDecodeError:
                ai_error = "AI returned invalid JSON. The extracted text may need editing for better results."

    outcomes = EHCPOutcome.objects.all()

    context = {
        "doc": doc,
        "student": student,
        "extracted_targets": extracted_targets,
        "ai_error": ai_error,
        "outcomes": outcomes,
    }
    return render(request, "evidence/ehcp_document_extract.html", context)


# ── Small Steps ─────────────────────────────────────────────────────

@login_required
def small_steps_manage(request, target_pk):
    """Manage small steps for an EHCP target — list, create, reorder."""
    target = get_object_or_404(
        EHCPTarget.objects.select_related("student", "outcome"), pk=target_pk
    )
    student = target.student
    steps = target.small_steps.all()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            letter = request.POST.get("letter", "").strip().upper()
            description = request.POST.get("description", "").strip()
            if letter and description:
                order = steps.count()
                SmallStep.objects.create(
                    target=target, letter=letter, description=description, order=order,
                )
                messages.success(request, f"Small Step {letter} added.")
            else:
                messages.error(request, "Letter and description are required.")

        elif action == "delete":
            step_pk = request.POST.get("step_pk")
            SmallStep.objects.filter(pk=step_pk, target=target).delete()
            messages.success(request, "Small step deleted.")

        return redirect("evidence:small_steps_manage", target_pk=target.pk)

    context = {
        "target": target,
        "student": student,
        "steps": steps,
        "achieved_count": steps.filter(status="ACHIEVED").count(),
    }
    return render(request, "evidence/small_steps_manage.html", context)


@login_required
@require_POST
def small_step_update_status(request, pk):
    """HTMX endpoint: update a small step's status."""
    step = get_object_or_404(SmallStep.objects.select_related("target__student", "target__outcome"), pk=pk)
    new_status = request.POST.get("status", "")
    if new_status in dict(SmallStep.STATUS_CHOICES):
        step.status = new_status
        step.status_date = timezone.now().date()
        step.notes = request.POST.get("notes", step.notes)
        step.save(update_fields=["status", "status_date", "notes", "updated_at"])

    target = step.target
    hx_target = request.headers.get("HX-Target", "")
    if hx_target.startswith("steps-panel-"):
        # Called from inline panel — return full panel
        steps = target.small_steps.all()
        return render(request, "evidence/_small_steps_panel.html", {
            "target": target, "steps": steps,
            "achieved_count": steps.filter(status="ACHIEVED").count(),
        })
    # Called from standalone manage page — return single row
    return render(request, "evidence/_small_step_row.html", {"step": step, "target": target})


@login_required
def small_steps_panel(request, target_pk):
    """HTMX endpoint: return the inline small-steps panel for a target."""
    target = get_object_or_404(
        EHCPTarget.objects.select_related("student", "outcome"), pk=target_pk
    )
    steps = target.small_steps.all()
    return render(request, "evidence/_small_steps_panel.html", {
        "target": target,
        "steps": steps,
        "achieved_count": steps.filter(status="ACHIEVED").count(),
    })


@login_required
@require_POST
def small_step_add_inline(request, target_pk):
    """HTMX endpoint: add a small step and return the updated panel."""
    target = get_object_or_404(
        EHCPTarget.objects.select_related("student", "outcome"), pk=target_pk
    )
    letter = request.POST.get("letter", "").strip().upper()
    description = request.POST.get("description", "").strip()
    if letter and description:
        if not target.small_steps.filter(letter=letter).exists():
            order = target.small_steps.count()
            SmallStep.objects.create(
                target=target, letter=letter, description=description, order=order,
            )
    steps = target.small_steps.all()
    return render(request, "evidence/_small_steps_panel.html", {
        "target": target,
        "steps": steps,
        "achieved_count": steps.filter(status="ACHIEVED").count(),
    })


@login_required
@require_POST
def small_step_delete_inline(request, pk):
    """HTMX endpoint: delete a small step and return the updated panel."""
    step = get_object_or_404(SmallStep.objects.select_related("target__student", "target__outcome"), pk=pk)
    target = step.target
    step.delete()
    steps = target.small_steps.all()
    return render(request, "evidence/_small_steps_panel.html", {
        "target": target,
        "steps": steps,
        "achieved_count": steps.filter(status="ACHIEVED").count(),
    })


@login_required
@require_POST
def small_step_edit_inline(request, pk):
    """HTMX endpoint: edit a small step's description and return updated panel."""
    step = get_object_or_404(SmallStep.objects.select_related("target__student", "target__outcome"), pk=pk)
    description = request.POST.get("description", "").strip()
    if description:
        step.description = description
        step.save(update_fields=["description", "updated_at"])
    target = step.target
    steps = target.small_steps.all()
    return render(request, "evidence/_small_steps_panel.html", {
        "target": target,
        "steps": steps,
        "achieved_count": steps.filter(status="ACHIEVED").count(),
    })


# ── MAPP ────────────────────────────────────────────────────────────

@login_required
def mapp_overview(request, student_pk):
    """MAPP overview for a student — all learning priorities grouped by EHCP target."""
    student = get_object_or_404(Student, pk=student_pk)
    priorities = (
        student.mapp_priorities
        .select_related("ehcp_target", "ehcp_target__outcome")
        .prefetch_related("dimensions")
        .all()
    )

    # Group by EHCP target
    grouped = {}
    for p in priorities:
        key = p.ehcp_target_id or 0
        if key not in grouped:
            grouped[key] = {
                "target": p.ehcp_target,
                "priorities": [],
            }
        grouped[key]["priorities"].append(p)

    context = {
        "student": student,
        "grouped": list(grouped.values()),
    }
    return render(request, "evidence/mapp_overview.html", context)


@login_required
def mapp_priority_create(request, student_pk):
    """Create a new MAPP learning priority."""
    student = get_object_or_404(Student, pk=student_pk)
    targets = student.ehcp_targets.select_related("outcome").all()
    mapp_config = MAPPConfig.get_active()

    # Get dimensions from config or use legacy defaults
    if mapp_config:
        dim_configs = list(mapp_config.dimension_configs.all())
        dimensions_for_template = [(dc.code, dc.name) for dc in dim_configs]
        scale_min = mapp_config.scale_min
        scale_max = mapp_config.scale_max
    else:
        dim_configs = None
        dimensions_for_template = MAPPDimensionScore.DIMENSION_CHOICES
        scale_min = 1
        scale_max = 10

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        target_id = request.POST.get("ehcp_target") or None
        academic_year = request.POST.get("academic_year", "").strip()
        term = request.POST.get("term", "").strip()
        ehcp_year = request.POST.get("ehcp_year", "").strip()

        if not title:
            messages.error(request, "Learning priority description is required.")
            return redirect("evidence:mapp_priority_create", student_pk=student.pk)

        priority = MAPPLearningPriority.objects.create(
            student=student,
            ehcp_target_id=target_id,
            title=title,
            academic_year=academic_year,
            term=term,
            ehcp_year=ehcp_year,
            order=student.mapp_priorities.count(),
        )

        # Create dimension rows from config or legacy
        if dim_configs:
            for dc in dim_configs:
                baseline = request.POST.get(f"baseline_{dc.code}", str(scale_min))
                try:
                    baseline_val = max(scale_min, min(scale_max, int(baseline)))
                except (ValueError, TypeError):
                    baseline_val = scale_min
                MAPPDimensionScore.objects.create(
                    priority=priority, dimension=dc.code,
                    dimension_config=dc, baseline_csd=baseline_val,
                )
        else:
            for dim_code in ["IND", "FLU", "MAI", "GEN"]:
                baseline = request.POST.get(f"baseline_{dim_code}", "1")
                try:
                    baseline_val = max(1, min(10, int(baseline)))
                except (ValueError, TypeError):
                    baseline_val = 1
                MAPPDimensionScore.objects.create(
                    priority=priority, dimension=dim_code, baseline_csd=baseline_val,
                )

        messages.success(request, "MAPP learning priority created.")
        return redirect("evidence:mapp_overview", student_pk=student.pk)

    context = {
        "student": student,
        "targets": targets,
        "dimensions": dimensions_for_template,
        "scale_min": scale_min,
        "scale_max": scale_max,
        "mapp_config": mapp_config,
    }
    return render(request, "evidence/mapp_priority_form.html", context)


@login_required
def mapp_priority_detail(request, pk):
    """View/edit a single MAPP learning priority — the CSD grid."""
    priority = get_object_or_404(
        MAPPLearningPriority.objects.select_related("student", "ehcp_target", "ehcp_target__outcome"),
        pk=pk,
    )
    dimensions = priority.dimensions.select_related("dimension_config").all()
    mapp_config = MAPPConfig.get_active()
    scale_min = mapp_config.scale_min if mapp_config else 1
    scale_max = mapp_config.scale_max if mapp_config else 10

    if request.method == "POST":
        # Update dimension scores
        for dim in dimensions:
            score_key = f"score_{dim.dimension}"
            if score_key in request.POST:
                max_possible = scale_max - dim.baseline_csd
                try:
                    new_score = max(0, min(max_possible, int(request.POST[score_key])))
                except (ValueError, TypeError):
                    continue
                dim.current_score = new_score
                dim.save(update_fields=["current_score"])

        # Update priority metadata
        priority.academic_year = request.POST.get("academic_year", priority.academic_year)
        priority.term = request.POST.get("term", priority.term)
        final_date = request.POST.get("final_assessment_date") or None
        priority.final_assessment_date = final_date
        priority.save(update_fields=["academic_year", "term", "final_assessment_date", "updated_at"])

        messages.success(request, "MAPP scores updated.")
        return redirect("evidence:mapp_priority_detail", pk=pk)

    # Build grid data for template
    grid = []
    for dim in dimensions:
        cells = []
        for csd in range(scale_min, scale_max + 1):
            cell = {"csd": csd, "marker": ""}
            if csd == dim.baseline_csd:
                cell["marker"] = "b"
            elif csd > dim.baseline_csd and csd <= dim.current_csd:
                cell["marker"] = str(csd - dim.baseline_csd)
            cells.append(cell)
        grid.append({
            "dim": dim,
            "cells": cells,
            "final_score": dim.current_score,
            "pct": dim.progress_pct,
            "max_score": scale_max - dim.baseline_csd,
        })

    context = {
        "priority": priority,
        "student": priority.student,
        "dimensions": dimensions,
        "grid": grid,
        "csd_range": range(scale_min, scale_max + 1),
        "mapp_config": mapp_config,
    }
    return render(request, "evidence/mapp_priority_detail.html", context)


@login_required
@require_POST
def mapp_priority_delete(request, pk):
    """Delete a MAPP learning priority."""
    priority = get_object_or_404(
        MAPPLearningPriority.objects.select_related("student"), pk=pk,
    )
    student_pk = priority.student.pk
    priority.delete()
    messages.success(request, "MAPP learning priority deleted.")
    return redirect("evidence:mapp_overview", student_pk=student_pk)


# ── Intervention Tracker ────────────────────────────────────────────


@login_required
def intervention_list(request, student_pk):
    """List all interventions for a student."""
    student = get_object_or_404(Student, pk=student_pk)
    status_filter = request.GET.get("status", "")
    enrolments = student.interventions.select_related(
        "program", "delivered_by", "ehcp_target",
    ).prefetch_related("sessions", "reviews").all()
    if status_filter:
        enrolments = enrolments.filter(status=status_filter)
    context = {
        "student": student,
        "enrolments": enrolments,
        "status_filter": status_filter,
        "status_choices": InterventionEnrolment.STATUS_CHOICES,
        "active_count": student.interventions.filter(status="ACTIVE").count(),
        "total_count": student.interventions.count(),
    }
    return render(request, "evidence/intervention_list.html", context)


@login_required
def intervention_enrol(request, student_pk):
    """Enrol a student in an intervention program."""
    student = get_object_or_404(Student, pk=student_pk)
    programs = InterventionProgram.objects.filter(is_active=True)
    targets = student.ehcp_targets.select_related("outcome").all()

    if request.method == "POST":
        program_id = request.POST.get("program")
        if not program_id:
            messages.error(request, "Please select an intervention program.")
            return redirect("evidence:intervention_enrol", student_pk=student.pk)

        program = get_object_or_404(InterventionProgram, pk=program_id)
        start_date = request.POST.get("start_date") or timezone.now().date()
        end_date = request.POST.get("end_date") or None
        target_id = request.POST.get("ehcp_target") or None

        enrolment = InterventionEnrolment.objects.create(
            student=student,
            program=program,
            delivered_by_id=request.POST.get("delivered_by") or None,
            frequency=request.POST.get("frequency", program.default_frequency or ""),
            duration_mins=request.POST.get("duration_mins") or program.default_duration_mins,
            goals=request.POST.get("goals", ""),
            start_date=start_date,
            end_date=end_date,
            ehcp_target_id=target_id,
            notes=request.POST.get("notes", ""),
        )
        messages.success(request, f"Enrolled in {program.name}.")
        return redirect("evidence:intervention_detail", pk=enrolment.pk)

    from django.contrib.auth import get_user_model
    User = get_user_model()
    staff = User.objects.filter(is_active=True, staffprofile__isnull=False).order_by("first_name", "last_name")

    context = {
        "student": student,
        "programs": programs,
        "targets": targets,
        "staff": staff,
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "evidence/intervention_enrol.html", context)


@login_required
def intervention_detail(request, pk):
    """View an intervention enrolment — sessions, reviews, and log new session."""
    enrolment = get_object_or_404(
        InterventionEnrolment.objects.select_related(
            "student", "program", "delivered_by", "ehcp_target",
        ),
        pk=pk,
    )
    sessions = enrolment.sessions.order_by("-session_date")[:20]
    reviews = enrolment.reviews.order_by("-review_date")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "log_session":
            session_date = request.POST.get("session_date")
            attended = request.POST.get("attended") == "true"
            InterventionSession.objects.create(
                enrolment=enrolment,
                session_date=session_date or timezone.now().date(),
                attended=attended,
                duration_mins=request.POST.get("duration_mins") or enrolment.duration_mins,
                notes=request.POST.get("session_notes", ""),
                recorded_by=request.user,
            )
            messages.success(request, "Session logged.")

        elif action == "add_review":
            InterventionReview.objects.create(
                enrolment=enrolment,
                review_date=request.POST.get("review_date") or timezone.now().date(),
                impact=request.POST.get("impact", "SOME"),
                progress_notes=request.POST.get("progress_notes", ""),
                next_steps=request.POST.get("next_steps", ""),
                continue_intervention=request.POST.get("continue_intervention") == "true",
                reviewed_by=request.user,
            )
            messages.success(request, "Review added.")

        elif action == "update_status":
            new_status = request.POST.get("status")
            if new_status in dict(InterventionEnrolment.STATUS_CHOICES):
                enrolment.status = new_status
                if new_status == "COMPLETED" and not enrolment.end_date:
                    enrolment.end_date = timezone.now().date()
                enrolment.save(update_fields=["status", "end_date", "updated_at"])
                messages.success(request, f"Status updated to {enrolment.get_status_display()}.")

        return redirect("evidence:intervention_detail", pk=pk)

    context = {
        "enrolment": enrolment,
        "student": enrolment.student,
        "sessions": sessions,
        "reviews": reviews,
        "impact_choices": InterventionReview.IMPACT_CHOICES,
        "status_choices": InterventionEnrolment.STATUS_CHOICES,
        "today": timezone.now().date().isoformat(),
    }
    return render(request, "evidence/intervention_detail.html", context)


@login_required
@require_POST
def intervention_delete(request, pk):
    """Delete an intervention enrolment."""
    enrolment = get_object_or_404(
        InterventionEnrolment.objects.select_related("student"), pk=pk,
    )
    student_pk = enrolment.student.pk
    enrolment.delete()
    messages.success(request, "Intervention enrolment deleted.")
    return redirect("evidence:intervention_list", student_pk=student_pk)
