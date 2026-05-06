from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from .models import Notification


@login_required
def notification_list(request):
    """Return notifications as an HTML fragment (for HTMX dropdown)."""
    notifications = (
        Notification.objects.filter(
            recipient=request.user, is_dismissed=False
        )
        .order_by("-created_at")[:20]
    )
    html = render_to_string(
        "notifications/notification_list.html",
        {"notifications": notifications},
        request=request,
    )
    return HttpResponse(html)


@login_required
def mark_read(request, pk):
    """Mark a single notification as read."""
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.is_read = True
    notif.save(update_fields=["is_read"])
    if notif.link:
        return HttpResponse(
            status=200,
            headers={"HX-Redirect": notif.link},
        )
    return HttpResponse(status=204)


@login_required
def mark_all_read(request):
    """Mark all notifications as read for the current user."""
    Notification.objects.filter(
        recipient=request.user, is_read=False
    ).update(is_read=True)
    return HttpResponse(status=204, headers={"HX-Trigger": "notificationsUpdated"})


@login_required
def dismiss(request, pk):
    """Dismiss a single notification."""
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.is_dismissed = True
    notif.save(update_fields=["is_dismissed"])
    return HttpResponse(status=200, headers={"HX-Trigger": "notificationsUpdated"})


@login_required
def unread_count(request):
    """Return the unread count as a small HTML badge (for HTMX polling)."""
    count = Notification.objects.filter(
        recipient=request.user, is_read=False, is_dismissed=False
    ).count()
    if count > 0:
        badge = (
            f'<span class="position-absolute top-0 start-100 translate-middle badge '
            f'rounded-pill bg-danger" style="font-size:0.65rem;">'
            f'{count if count < 100 else "99+"}</span>'
        )
    else:
        badge = ""
    return HttpResponse(badge)
