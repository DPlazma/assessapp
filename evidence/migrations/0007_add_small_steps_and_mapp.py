"""Add SmallStep, MAPPLearningPriority, and MAPPDimensionScore models."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0006_add_ehcp_annotation"),
        ("students", "0002_add_explorers_pathway"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Small Steps ──────────────────────────────────────────
        migrations.CreateModel(
            name="SmallStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("letter", models.CharField(help_text="Step letter, e.g. A, B, C", max_length=2)),
                ("description", models.TextField()),
                ("status", models.CharField(
                    choices=[("NOT_STARTED", "Not Started"), ("WORKING_ON", "Working On"), ("ACHIEVED", "Achieved")],
                    default="NOT_STARTED", max_length=12,
                )),
                ("status_date", models.DateField(blank=True, null=True, help_text="Date status last changed")),
                ("notes", models.TextField(blank=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("target", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="small_steps",
                    to="evidence.ehcptarget",
                )),
            ],
            options={
                "ordering": ["target", "order", "letter"],
                "unique_together": {("target", "letter")},
            },
        ),
        # ── MAPP ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="MAPPLearningPriority",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.TextField(help_text="Learning priority description")),
                ("academic_year", models.CharField(blank=True, help_text="e.g. 23/24", max_length=10)),
                ("term", models.CharField(blank=True, help_text="e.g. Spring, Summer", max_length=20)),
                ("ehcp_year", models.CharField(blank=True, help_text="EHCP year this was taken from", max_length=10)),
                ("baseline_date", models.DateField(blank=True, null=True)),
                ("final_assessment_date", models.DateField(blank=True, null=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("student", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="mapp_priorities",
                    to="students.student",
                )),
                ("ehcp_target", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="mapp_priorities",
                    to="evidence.ehcptarget",
                )),
            ],
            options={
                "ordering": ["student", "ehcp_target", "order"],
                "verbose_name": "MAPP learning priority",
                "verbose_name_plural": "MAPP learning priorities",
            },
        ),
        migrations.CreateModel(
            name="MAPPDimensionScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dimension", models.CharField(
                    choices=[("IND", "Independence"), ("FLU", "Fluency"), ("MAI", "Maintenance"), ("GEN", "Generalisation")],
                    max_length=3,
                )),
                ("baseline_csd", models.PositiveSmallIntegerField(help_text="Baseline position on 1-10 CSD scale")),
                ("current_score", models.PositiveSmallIntegerField(default=0, help_text="Steps progressed from baseline (0-10)")),
                ("priority", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="dimensions",
                    to="evidence.mapplearningpriority",
                )),
            ],
            options={
                "ordering": ["priority", "dimension"],
                "verbose_name": "MAPP dimension score",
                "unique_together": {("priority", "dimension")},
            },
        ),
    ]
