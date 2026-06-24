from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("students", "0001_initial"),
        ("core", "0006_remove_arbor_graphql_url"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassInsight",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.TextField(blank=True, help_text="Sanitised HTML produced by the AI provider.")),
                ("created_at", models.DateTimeField(auto_now=True)),
                (
                    "class_group",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ai_insight",
                        to="students.classgroup",
                    ),
                ),
                (
                    "generated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="class_insights",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
