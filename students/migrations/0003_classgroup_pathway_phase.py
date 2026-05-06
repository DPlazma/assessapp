"""Add pathway + phase to ClassGroup; auto-fill known classes."""

from django.db import migrations, models


def fill_known_pathways(apps, schema_editor):
    """Map West Gate's known class naming convention to pathways.

    Explorers 1-4    → Explorers
    Class 1-6        → Horizons
    Class 7-12       → Futures
    Class 13-20      → Preparations  (phase left blank for SLT to set)
    Anything else    → blank
    """
    import re

    ClassGroup = apps.get_model("students", "ClassGroup")
    for cg in ClassGroup.objects.all():
        name = (cg.name or "").strip()
        lower = name.lower()
        pathway = ""

        if lower.startswith("explorers"):
            pathway = "EXP"
        else:
            m = re.match(r"class\s+(\d+)$", lower)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 6:
                    pathway = "HOR"
                elif 7 <= n <= 12:
                    pathway = "FUT"
                elif 13 <= n <= 20:
                    pathway = "PREP"

        if pathway:
            cg.pathway = pathway
            cg.save(update_fields=["pathway"])

    # Propagate to existing students
    Student = apps.get_model("students", "Student")
    for s in Student.objects.select_related("class_group").all():
        cg = s.class_group
        if cg and cg.pathway and s.pathway != cg.pathway:
            s.pathway = cg.pathway
            s.save(update_fields=["pathway"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0002_add_explorers_pathway"),
    ]

    operations = [
        migrations.AddField(
            model_name="classgroup",
            name="pathway",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PREP", "Preparations"),
                    ("EXP", "Explorers"),
                    ("FUT", "Futures"),
                    ("HOR", "Horizons"),
                ],
                help_text="West Gate pathway / house this class belongs to.",
                max_length=4,
            ),
        ),
        migrations.AddField(
            model_name="classgroup",
            name="phase",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                choices=[(1, "Phase 1"), (2, "Phase 2")],
                help_text="Only used for the Preparations pathway (Phase 1 or 2).",
            ),
        ),
        migrations.RunPython(fill_known_pathways, noop),
    ]
