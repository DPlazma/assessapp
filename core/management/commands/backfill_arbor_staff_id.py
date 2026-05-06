"""
Backfill StaffProfile.arbor_staff_id for existing local users
by matching against Arbor's staff list (by full name).

Usage:
  python manage.py backfill_arbor_staff_id            # dry-run
  python manage.py backfill_arbor_staff_id --commit
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.arbor import get_arbor_client
from staff.models import StaffProfile

User = get_user_model()


class Command(BaseCommand):
    help = "Match local users to Arbor staff by name and stamp arbor_staff_id."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Persist changes (default is dry-run).",
        )

    def handle(self, *args, **opts):
        commit = opts["commit"]

        client, err = get_arbor_client()
        if err:
            raise CommandError(err)
        arbor_staff = client.fetch_staff()

        # Build name → arbor_id map
        arbor_by_name = {}
        for st in arbor_staff:
            person = st.get("person") or {}
            first = (person.get("legalFirstName") or "").strip()
            last = (person.get("legalLastName") or "").strip()
            full = f"{first} {last}".strip().lower()
            if not full:
                continue
            try:
                arbor_id = int(st["id"])
            except (TypeError, ValueError, KeyError):
                continue
            arbor_by_name.setdefault(full, arbor_id)

        matched = 0
        already = 0
        unmatched = []
        ambiguous = []

        for user in User.objects.filter(is_active=True).select_related("staffprofile"):
            full = f"{user.first_name} {user.last_name}".strip().lower()
            if not full:
                continue
            profile = getattr(user, "staffprofile", None)
            if profile and profile.arbor_staff_id:
                already += 1
                continue
            arbor_id = arbor_by_name.get(full)
            if not arbor_id:
                unmatched.append(user.get_full_name() or user.username)
                continue
            # Guard against another profile already claiming this id
            clash = StaffProfile.objects.filter(arbor_staff_id=arbor_id).exclude(
                user=user
            ).first()
            if clash:
                ambiguous.append(
                    f"{user.get_full_name()} → arbor_id {arbor_id} already on "
                    f"{clash.user.get_full_name() or clash.user.username}"
                )
                continue
            if commit:
                if profile is None:
                    StaffProfile.objects.create(
                        user=user, role="teacher", arbor_staff_id=arbor_id
                    )
                else:
                    profile.arbor_staff_id = arbor_id
                    profile.save(update_fields=["arbor_staff_id"])
            matched += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n{'COMMITTED' if commit else 'DRY-RUN'} — "
            f"matched: {matched}, already-set: {already}, "
            f"unmatched: {len(unmatched)}, ambiguous: {len(ambiguous)}"
        ))
        if unmatched:
            self.stdout.write("\nUnmatched local users:")
            for n in unmatched:
                self.stdout.write(f"  - {n}")
        if ambiguous:
            self.stdout.write("\nAmbiguous (skipped):")
            for n in ambiguous:
                self.stdout.write(f"  - {n}")
        if not commit:
            self.stdout.write("\nRe-run with --commit to apply.")
