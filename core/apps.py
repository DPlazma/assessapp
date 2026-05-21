from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Extend django-allauth's Microsoft Graph $select so that the
        # Entra `employeeId` attribute (e.g. "Stf_520") is returned in
        # the user's extra_data. Without this, our social adapter can
        # never match an SSO user to the StaffProfile imported from
        # Arbor, and allauth ends up creating a duplicate shadow user.
        # See core/adapters.py::_extract_arbor_staff_id.
        try:
            from allauth.socialaccount.providers.microsoft.views import (
                MicrosoftGraphOAuth2Adapter,
            )
        except ImportError:  # allauth not installed (e.g. some mgmt cmds)
            return

        extra_fields = ("employeeId",)
        current = MicrosoftGraphOAuth2Adapter.user_properties
        if any(f not in current for f in extra_fields):
            MicrosoftGraphOAuth2Adapter.user_properties = tuple(current) + tuple(
                f for f in extra_fields if f not in current
            )
            MicrosoftGraphOAuth2Adapter.profile_url_params = {
                "$select": ",".join(MicrosoftGraphOAuth2Adapter.user_properties)
            }
