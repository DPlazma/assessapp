from functools import wraps
from django.http import HttpResponseForbidden


def slt_required(view_func):
    """Restrict access to SLT users only (must also be @login_required)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        profile = getattr(request.user, "staffprofile", None)
        if not profile or not profile.is_slt:
            return HttpResponseForbidden("Only SLT members can access this page.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def slt_or_subject_lead_required(view_func):
    """Restrict access to SLT or Subject Lead users."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        profile = getattr(request.user, "staffprofile", None)
        if not profile or not (profile.is_slt or profile.is_subject_lead):
            return HttpResponseForbidden(
                "Only SLT members or subject leads can access this page."
            )
        return view_func(request, *args, **kwargs)

    return _wrapped
