"""Add Explorers (EXP) pathway choice to Student.pathway."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="pathway",
            field=models.CharField(
                choices=[
                    ("PREP", "Preparations"),
                    ("EXP", "Explorers"),
                    ("FUT", "Futures"),
                    ("HOR", "Horizons"),
                ],
                default="PREP",
                max_length=4,
            ),
        ),
    ]
