from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from staff.models import StaffProfile


class AssessAppSocialAdapter(DefaultSocialAccountAdapter):
    """Ensure every SSO user gets a StaffProfile on first login."""

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        StaffProfile.objects.get_or_create(
            user=user,
            defaults={"role": "teacher"},
        )
        return user
