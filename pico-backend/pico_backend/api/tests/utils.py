from django.core.files.uploadedfile import SimpleUploadedFile


def create_simple_uploaded_file(file_path: str, file_name: str, content_type: str):
    with open(file_path, "rb") as file:
        file = SimpleUploadedFile(file_name, file.read(), content_type=content_type)
    return file
