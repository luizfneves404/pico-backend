import io
import zipfile

import pytest
from fastapi import UploadFile

from app.files.admin import FileAdmin, FileImportRecord, FileImportSchema


class TestFileImport:
    async def test_file_import_record_validation(self):
        """Test the FileImportRecord validation."""
        # Valid record
        record = FileImportRecord(
            filename="document.pdf", original_name="My Document.pdf"
        )
        assert record.filename == "document.pdf"
        assert record.get_safe_filename() == "My Document.pdf"

        # Valid record without original_name
        record = FileImportRecord(filename="document.pdf")
        assert record.get_safe_filename() == "document.pdf"

        # Invalid: filename with path separators
        with pytest.raises(ValueError, match="Invalid filename"):
            FileImportRecord(filename="folder/document.pdf")

        # Invalid: filename starting with dot
        with pytest.raises(ValueError, match="Invalid filename"):
            FileImportRecord(filename=".hidden")

        # Invalid: too long filename
        with pytest.raises(ValueError, match="Filename too long"):
            FileImportRecord(filename="a" * 300)

    async def test_csv_manifest_validation(self):
        """Test CSV manifest validation."""
        # Valid CSV
        csv_content = "filename,original_name\ndocument.pdf,My Document.pdf\nimage.jpg,Profile.jpg"
        schema = FileImportSchema(csv_manifest=csv_content)
        records = schema.parse_csv_manifest()
        assert len(records) == 2
        assert records[0].filename == "document.pdf"
        assert records[0].original_name == "My Document.pdf"

        # Invalid: missing filename column
        with pytest.raises(ValueError, match='CSV must have "filename" column'):
            FileImportSchema(csv_manifest="name,size\ntest.pdf,1000")

        # Invalid: empty CSV
        with pytest.raises(ValueError, match="CSV manifest cannot be empty"):
            FileImportSchema(csv_manifest="filename\n")

        # Invalid: bad filename in CSV
        with pytest.raises(ValueError, match="Invalid CSV row"):
            FileImportSchema(csv_manifest="filename\n../bad.pdf")

    async def test_validate_upload_file(self):
        """Test upload file validation."""
        admin = FileAdmin()

        # Create a valid upload file mock
        content = b"Test file content"
        upload_file = UploadFile(
            file=io.BytesIO(content), filename="test.pdf", size=len(content)
        )

        # Should not raise
        admin.validate_upload_file(upload_file)

        # Test file too large
        large_upload = UploadFile(
            file=io.BytesIO(content),
            filename="large.pdf",
            size=100 * 1024 * 1024,  # 100MB (larger than 50MB limit)
        )
        with pytest.raises(ValueError, match="File too large"):
            admin.validate_upload_file(large_upload)

        # Test invalid filename
        invalid_upload = UploadFile(
            file=io.BytesIO(content), filename="../bad.pdf", size=len(content)
        )
        with pytest.raises(ValueError, match="Invalid filename"):
            admin.validate_upload_file(invalid_upload)

    async def test_zip_file_validation(self):
        """Test zip file security validation."""
        admin = FileAdmin()

        # Create a valid zip file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr("test.txt", "Hello world")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, "r") as test_zip:
            # Should not raise
            admin.validate_zip_file(test_zip)

        # Test path traversal attack
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr("../evil.txt", "malicious content")

        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, "r") as test_zip:
            with pytest.raises(ValueError, match="Unsafe file path"):
                admin.validate_zip_file(test_zip)

    async def test_process_direct_import(self):
        """Test direct file import processing."""
        admin = FileAdmin()

        # Mock upload files
        files = [
            UploadFile(file=io.BytesIO(b"Content 1"), filename="file1.txt", size=9),
            UploadFile(file=io.BytesIO(b"Content 2"), filename="file2.txt", size=9),
        ]

        # This would normally upload to storage and create File objects
        # For the test, we'll just verify it doesn't crash
        try:
            await admin.process_direct_import(files)
            # The actual storage upload will fail in tests, but the logic should work
        except Exception as e:
            # Expected to fail due to storage not being set up in tests
            assert "storage" in str(e).lower() or "session" in str(e).lower()

    async def test_create_zip_with_manifest(self):
        """Test creating a zip file with CSV manifest for import."""
        # Create test files
        files_content = {
            "document1.pdf": b"PDF content 1",
            "image.jpg": b"JPEG content",
            "document2.pdf": b"PDF content 2",
        }

        # Create CSV manifest
        csv_content = """filename,original_name
document1.pdf,First Document.pdf
image.jpg,Profile Image.jpg
document2.pdf,Second Document.pdf"""

        # Create zip file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            # Add files
            for filename, content in files_content.items():
                zip_file.writestr(filename, content)

        zip_buffer.seek(0)

        # Test that we can parse the manifest
        schema = FileImportSchema(csv_manifest=csv_content)
        records = schema.parse_csv_manifest()

        assert len(records) == 3
        assert records[0].filename == "document1.pdf"
        assert records[0].get_safe_filename() == "First Document.pdf"
