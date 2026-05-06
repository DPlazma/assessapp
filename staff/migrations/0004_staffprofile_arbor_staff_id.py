from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("staff", "0003_staffprofile_pathway_lead"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="arbor_staff_id",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Arbor Staff ID (matches Entra Employee ID without the 'Stf_' prefix).",
                null=True,
                unique=True,
            ),
        ),
    ]
