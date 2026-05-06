"""
Mark local users as inactive when their linked Arbor staff record is no
longer active in school.

Match is by StaffProfile.arbor_staff_id. A user is deactivated when:
  - their arbor_staff_id appears in Arbor with isActiveInSchool=False, OR
  - their arbor_staff_id appears in Arbor with a non-null leavingDate.

Conversely, a user previously deactivated by this script will be
re-activated if their Arbor record is active again.

Usage:
  python manage.py deactivate_arbor_leavers
  python manage.py deactivate_arbor_leavers --commit
  python manage.py deactivate_arbor_leavers --commit --keep-superusers
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.arbor import get_arbor_client
from staff.models import StaffProfile

User = get_user_model()


class Command(BaseCommand):
    help = "Deactivate local users whose linked Arbor staff record is inactive."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true",
                            help="Persist changes (default is dry-run).")
        parser.add_argument("--keep-superusers", action="store_true",
                            default=True,
                            help="Never deactivate superusers (default).")
        parser.add_argument("--include-superusers", action="store_true",
                            help="Allow deactivating superusers too.")

    def handle(self, *args, **opts):
        commit = opts["commit"]
        keep_super = not opts.get("include_superusers", False)

        client, err = get_arbor_client()
        if err:
            raise CommandError(err)

        arbor_staff = client.fetch_staff(include_inactive=True)

        # Build {arbor_id: is_active}
        status = {}
        for st in arbor_staff:
            try:
                aid = int(st["id"])
            except (TypeError, ValueError, KeyError):
                continue
            active = bool(st.get("isActiveInSchool")) and not st.get("leavingDate")
            status[aid] = active

        to_deactivate = []
        to_reactivate = []
        unknown = []

        profiles = StaffProfile.objects.select_related("user").exclude(
            arbor_staff_id__isnull=True
        )
        for p in profiles:
            u = p.user
            arbor_active = status.get(p.arbor_staff_id)
            if arbor_active is None:
                unknown.append((u, p.arbor_staff_id))
                continue
            if arbor_active and not u.is_active:
                to_reactivate.append(u)
            elif (not arbor_active) and u.is_active:
                if keep_super and (u.is_superuser or u.is_staff):
                    continue
                to_deactivate.append(u)

        self.stdout.write(self.style.SUCCESS(
            f"\n{'COMMITTED' if commit else 'DRY-RUN'} — "
            f"to deactivate: {len(to_deactivate)}, "
            f"to reactivate: {len(to_reactivate)}, "
            f"unknown-in-arbor: {len(unknown)}"
        ))

        if to_deactivate:
            self.stdout.write("\nWill deactivate (still marked active locally, "
                              "but inactive in Arbor):")
            for u in to_deactivate[:50]:
                self.stdout.write(f"  - {u.get_full_name() or u.username} "
                                  f"(id {u.id})")
            if len(to_deactivate) > 50:
                self.stdout.write(f"  …and {len(to_deactivate) - 50} more")

        if to_reactivate:
            self.stdout.write("\nWill reactivate (active in Arbor, "
                              "currently disabled locally):")
            for u in to_reactivate:
                self.stdout.write(f"  - {u.get_full_name() or u.username}")

        if unknown:
            self.stdout.write("\nLocal arbor_staff_ids not present in Arbor "
                              "response (skipped):")
            for u, aid in unknown[:20]:
                self.stdout.write(f"  - {u.get_full_name() or u.username} "
                                  f"(arbor_staff_id={aid})")
            if len(unknown) > 20:
                self.stdout.write(f"  …and {len(unknown) - 20} more")

        if commit:
            if to_deactivate:
                User.objects.filter(id__in=[u.id for u in to_deactivate]).update(
                    is_active=False
                )
            if to_reactivate:
                User.objects.filter(id__in=[u.id for u in to_reactivate]).update(
                    is_active=True
                )
        else:
            self.stdout.write("\nRe-run with --commit to apply.")
