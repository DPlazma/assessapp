from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST

from students.models import ClassGroup
from .models import ClassCover, ClassAssignment


@login_required
def cover_class(request):
    """Self-service class cover — one-tap to start covering a class."""
    today = timezone.now().date()
    user = request.user

    # Current active covers
    active_covers = ClassCover.objects.filter(
        user=user, start_date__lte=today, end_date__gte=today
    )

    # Classes not already assigned or covered
    assigned_ids = ClassAssignment.objects.filter(user=user).values_list(
        "class_group_id", flat=True
    )
    covered_ids = active_covers.values_list("class_group_id", flat=True)
    available_classes = ClassGroup.objects.exclude(
        pk__in=list(assigned_ids) + list(covered_ids)
    )

    if request.method == "POST":
        class_id = request.POST.get("class_id")
        end_date = request.POST.get("end_date", "")

        if class_id:
            class_group = get_object_or_404(ClassGroup, pk=class_id)
            cover_end = today  # Default: expires end of today
            if end_date:
                from datetime import date as date_type
                try:
                    parts = end_date.split("-")
                    cover_end = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
                except (ValueError, IndexError):
                    cover_end = today

            ClassCover.objects.create(
                user=user,
                class_group=class_group,
                start_date=today,
                end_date=cover_end,
            )
            messages.success(request, f"You are now covering {class_group.name}.")
            return redirect("staff:cover_class")

    context = {
        "active_covers": active_covers,
        "available_classes": available_classes,
    }
    return render(request, "staff/cover_class.html", context)


@login_required
@require_POST
def end_cover(request, cover_id):
    """End a cover early."""
    cover = get_object_or_404(ClassCover, pk=cover_id, user=request.user)
    today = timezone.now().date()
    cover.end_date = today
    cover.save()
    messages.success(request, f"Cover for {cover.class_group.name} ended.")
    return redirect("staff:cover_class")
