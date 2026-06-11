from django import forms


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


class CSVUploadForm(forms.Form):
    csv_file = forms.FileField()
    source = forms.CharField(max_length=100, required=True)
    prova_codes = forms.CharField(
        max_length=100, required=True
    )  # Campo para múltiplos códigos de prova


class CSVUploadFormNumber(forms.Form):
    csv_file = forms.FileField()
    source = forms.CharField(max_length=100, required=True)


class ImageUploadForm(forms.Form):
    images = MultipleFileField()  # Use the MultipleFileField for multiple file upload
    source = forms.CharField(max_length=100, required=True)
    subject = forms.CharField(max_length=100, required=True)
    extra_instructions = forms.CharField(max_length=1000, required=False)
    questions_per_image = forms.IntegerField(initial=4, required=True)


class StudentQuestionsCSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV File",
        help_text="Upload a CSV file containing student questions",
    )


class DiscursiveQuestionsCSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV File", help_text="Upload a CSV file containing discursive questions"
    )
