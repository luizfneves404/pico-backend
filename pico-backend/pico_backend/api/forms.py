from django import forms
from django.core.exceptions import ValidationError
from essays.models import EssayTopic
from quiz.models import Session

from api.models import FileGroup


class BulkEmailForm(forms.Form):
    html_file = forms.FileField(label="HTML file for template")
    subject = forms.CharField(label="Subject")


class VariableBulkMessageForm(forms.Form):
    csv_file = forms.FileField()
    attachment = forms.FileField(required=False)
    essay_topic = forms.ModelChoiceField(
        queryset=EssayTopic.objects.all(), required=False
    )
    session = forms.ModelChoiceField(queryset=Session.objects.all(), required=False)


class BulkMessageForm(forms.Form):
    content = forms.CharField(widget=forms.Textarea)
    attachment = forms.FileField(required=False)
    essay_topic_id = forms.IntegerField(required=False)
    session_id = forms.IntegerField(required=False)

    def clean_essay_topic_id(self):
        essay_topic_id = self.cleaned_data.get("essay_topic_id")
        if essay_topic_id:
            try:
                essay_topic = EssayTopic.objects.get(id=essay_topic_id)
            except EssayTopic.DoesNotExist:
                raise ValidationError("Invalid Essay Topic ID.")
            return essay_topic  # Return the object instead of the ID if needed
        return None

    def clean_session_id(self):
        session_id = self.cleaned_data.get("session_id")
        if session_id:
            try:
                session = Session.objects.get(id=session_id)
            except Session.DoesNotExist:
                raise ValidationError("Invalid Session ID.")
            return session  # Return the object instead of the ID if needed
        return None


class EmbeddingCSVUploadForm(forms.Form):
    csv_file = forms.FileField()
    file_group = forms.ModelChoiceField(queryset=FileGroup.objects.all())


class NotificationForm(forms.Form):
    """Form for the bulk notification action."""

    title = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={"placeholder": "Notification title"}),
    )
    body = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"placeholder": "Notification body", "rows": 4}),
    )
