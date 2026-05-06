"""
Seed the default MAPP configuration (IFMG — Independence, Fluency,
Maintenance, Generalisation) with a 1-10 scale.

Usage:
  python manage.py seed_mapp_config
"""

from django.core.management.base import BaseCommand

from evidence.models import MAPPConfig, MAPPDimensionConfig


DIMENSIONS = [
    ("I", "Independence", 1),
    ("F", "Fluency", 2),
    ("M", "Maintenance", 3),
    ("G", "Generalisation", 4),
]


class Command(BaseCommand):
    help = "Create the default MAPP configuration (IFMG, 1-10 scale)."

    def handle(self, *args, **options):
        if MAPPConfig.objects.exists():
            self.stdout.write("MAPP config already exists — skipping.")
            return

        config = MAPPConfig.objects.create(
            name="Standard IFMG",
            scale_min=1,
            scale_max=10,
            is_active=True,
        )
        for code, name, order in DIMENSIONS:
            MAPPDimensionConfig.objects.create(
                config=config,
                code=code,
                name=name,
                order=order,
            )
        self.stdout.write(self.style.SUCCESS(
            f"  ✓ Created MAPP config '{config.name}' with {len(DIMENSIONS)} dimensions"
        ))
