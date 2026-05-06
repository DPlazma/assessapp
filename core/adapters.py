import re

from django.db import transaction

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from staff.models import StaffProfile


def _extract_arbor_staff_id(extra_data):
    """
    Pull Arbor Staff ID from Entra/Microsoft Graph extra_data.

    School convention (synced from Arbor → Entra via SalamanderSoft):
      - Staff: Entra Employee ID = "Stf_520" → Arbor Staff ID 520
      - Students: Entra Employee ID = "520" (no prefix) → not matched here
    """
    if not extra_data:
        return None
    raw = (
        extra_data.get("employeeId")
        or extra_data.get("employee_id")
        or extra_data.get("employeeID")
        or ""
    )
    if not raw:
        return None
    m = re.match(r"^\s*[Ss][Tt][Ff]_(\d+)\s*$", str(raw))
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


class AssessAppSocialAdapter(DefaultSocialAccountAdapter):
    """Ensure every SSO user gets a StaffProfile on first login.

    If the Entra account carries an Arbor Staff ID (employeeId like
    "Stf_520") and we already have a local user (created by the
    Arbor import) with that arbor_staff_id, adopt that user — connect
    the SocialAccount to it instead of creating a new one. This keeps
    class assignments, marking history, etc. attached to one record.
    """

    def pre_social_login(self, request, sociallogin):
        # Adopt an existing local user keyed by Arbor Staff ID, before
        # allauth creates a brand-new shadow user.
        if sociallogin.is_existing:
            return
        arbor_id = _extract_arbor_staff_id(sociallogin.account.extra_data)
        if not arbor_id:
            return
        try:
            profile = StaffProfile.objects.select_related("user").get(
                arbor_staff_id=arbor_id
            )
        except StaffProfile.DoesNotExist:
            return
        sociallogin.connect(request, profile.user)

    def save_user(self, request, sociallogin, form=None):
        with transaction.atomic():
            user = super().save_user(request, sociallogin, form)
            arbor_id = _extract_arbor_staff_id(sociallogin.account.extra_data)
            defaults = {"role": "teacher"}
            if arbor_id:
                defaults["arbor_staff_id"] = arbor_id
            StaffProfile.objects.get_or_create(user=user, defaults=defaults)
            # If a profile already existed without an Arbor ID, stamp it now.
            if arbor_id:
                StaffProfile.objects.filter(
                    user=user, arbor_staff_id__isnull=True
                ).update(arbor_staff_id=arbor_id)
        return user
