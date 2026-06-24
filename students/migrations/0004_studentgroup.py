from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("students", "0003_classgroup_pathway_phase"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("is_shared", models.BooleanField(default=False, help_text="If on, all staff can view this group.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="student_groups",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "students",
                    models.ManyToManyField(
                        blank=True,
                        related_name="custom_groups",
                        to="students.student",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
    ]
