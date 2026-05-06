"""Add pathway_lead role and lead_pathway field to StaffProfile."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("staff", "0002_subjectlead"),
    ]

    operations = [
        migrations.AlterField(
            model_name="staffprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("teacher", "Teacher"),
                    ("ta", "Teaching Assistant"),
                    ("hlta", "HLTA"),
                    ("subject_lead", "Subject Lead"),
                    ("pathway_lead", "Pathway Lead"),
                    ("slt", "Senior Leadership Team"),
                ],
                default="teacher",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="staffprofile",
            name="lead_pathway",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PREP", "Preparations"),
                    ("EXP", "Explorers"),
                    ("FUT", "Futures"),
                    ("HOR", "Horizons"),
                ],
                help_text="For Pathway Leads: which pathway they oversee.",
                max_length=4,
            ),
        ),
    ]
