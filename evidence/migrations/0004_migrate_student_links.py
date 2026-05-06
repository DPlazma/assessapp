"""Data migration: copy legacy Evidence.student FK → EvidenceStudentLink rows."""
from django.db import migrations


def forwards(apps, schema_editor):
    Evidence = apps.get_model("evidence", "Evidence")
    EvidenceStudentLink = apps.get_model("evidence", "EvidenceStudentLink")

    links = []
    for ev in Evidence.objects.filter(student__isnull=False).select_related():
        links.append(
            EvidenceStudentLink(
                evidence=ev,
                student_id=ev.student_id,
                ehcp_target_id=ev.ehcp_target_id,
            )
        )
    if links:
        EvidenceStudentLink.objects.bulk_create(links, ignore_conflicts=True)


def backwards(apps, schema_editor):
    # No reverse needed — the FK columns are still present
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("evidence", "0003_add_evidence_student_link"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
