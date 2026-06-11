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

    async def test_jsonl_manifest_validation(self):
        """Test JSONL manifest validation."""
        # Valid JSONL manifest
        jsonl_content = (
            '{"filename": "document.pdf", "original_name": "My Document.pdf"}\n'
            '{"filename": "image.jpg", "original_name": "Profile.jpg"}'
        )
        schema = FileImportSchema(jsonl_manifest=jsonl_content)
        records = schema.parse_jsonl_manifest()
        assert len(records) == 2
        assert records[0].filename == "document.pdf"
        assert records[0].original_name == "My Document.pdf"

        with pytest.raises(
            ValueError,
            match="Invalid JSON on line 1: Expecting property name enclosed in double quotes",
        ):
            FileImportSchema(jsonl_manifest='{filename": "test.pdf"}')

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
        with (
            zipfile.ZipFile(zip_buffer, "r") as test_zip,
            pytest.raises(ValueError, match="Unsafe file path"),
        ):
            admin.validate_zip_file(test_zip)

    async def test_process_direct_import(self):
        """Test direct file import processing."""
        admin = FileAdmin()

        # Mock upload files
        files = [
            UploadFile(file=io.BytesIO(b"Content 1"), filename="file1.txt", size=9),
            UploadFile(file=io.BytesIO(b"Content 2"), filename="file2.txt", size=9),
        ]

        await admin.process_direct_import(files)

    async def test_create_zip_with_manifest(self):
        """Test creating a zip file with JSONL manifest for import."""
        # Create test files
        files_content = {
            "document1.pdf": b"PDF content 1",
            "image.jpg": b"JPEG content",
            "document2.pdf": b"PDF content 2",
        }

        # Create JSONL manifest

        jsonl_content = """{"filename": "document1.pdf", "original_name": "First Document.pdf"}
{"filename": "image.jpg", "original_name": "Profile Image.jpg"}
{"filename": "document2.pdf", "original_name": "Second Document.pdf"}"""

        # Create zip file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            # Add files
            for filename, content in files_content.items():
                zip_file.writestr(filename, content)

        zip_buffer.seek(0)

        # Test that we can parse the manifest
        schema = FileImportSchema(jsonl_manifest=jsonl_content)
        records = schema.parse_jsonl_manifest()

        assert len(records) == 3
        assert records[0].filename == "document1.pdf"
        assert records[0].get_safe_filename() == "First Document.pdf"
