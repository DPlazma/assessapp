def staff_role(request):
    """Add staff role flags to every template context."""
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        profile = getattr(user, "staffprofile", None)
        return {
            "is_slt": profile.is_slt if profile else False,
            "is_subject_lead": profile.is_subject_lead if profile else False,
        }
    return {"is_slt": False, "is_subject_lead": False}
