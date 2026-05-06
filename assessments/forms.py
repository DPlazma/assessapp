from django import forms
from .models import AssessmentRecord, AssessmentStatement


class AssessmentRecordForm(forms.ModelForm):
    class Meta:
        model = AssessmentRecord
        fields = ["status", "notes"]
        widgets = {
            "status": forms.RadioSelect,
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Optional note..."}),
        }
