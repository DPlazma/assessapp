"""
Management command to import assessment statements from CSV.

Expected CSV columns:
    framework, subject, area, statement, year_group (optional), phase (optional)

Usage:
    python manage.py import_statements path/to/statements.csv
"""
import csv

from django.core.management.base import BaseCommand, CommandError

from assessments.models import AssessmentFramework, AssessmentArea, AssessmentStatement
from students.models import Subject


class Command(BaseCommand):
    help = "Import assessment statements from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file")

    def handle(self, *args, **options):
        csv_path = options["csv_file"]

        try:
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                created = 0
                skipped = 0
                errors = 0

                for i, row in enumerate(reader, start=2):
                    try:
                        framework_name = row.get("framework", "").strip()
                        subject_name = row.get("subject", "").strip()
                        area_name = row.get("area", "").strip()
                        statement_text = row.get("statement", "").strip()
                        year_group = row.get("year_group", "").strip()
                        phase = row.get("phase", "").strip()

                        if not all([framework_name, subject_name, area_name, statement_text]):
                            self.stderr.write(f"Row {i}: Missing required fields, skipping.")
                            skipped += 1
                            continue

                        framework, _ = AssessmentFramework.objects.get_or_create(
                            name=framework_name
                        )
                        subject, _ = Subject.objects.get_or_create(name=subject_name)
                        area, _ = AssessmentArea.objects.get_or_create(
                            framework=framework,
                            subject=subject,
                            name=area_name,
                            defaults={
                                "year_group": int(year_group) if year_group else None,
                                "phase": int(phase) if phase else None,
                            },
                        )
                        _, was_created = AssessmentStatement.objects.get_or_create(
                            area=area,
                            statement_text=statement_text,
                            defaults={"order": created},
                        )
                        if was_created:
                            created += 1
                        else:
                            skipped += 1

                    except Exception as e:
                        self.stderr.write(f"Row {i}: {e}")
                        errors += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Import complete: {created} created, {skipped} skipped, {errors} errors."
                    )
                )

        except FileNotFoundError:
            raise CommandError(f"File not found: {csv_path}")
