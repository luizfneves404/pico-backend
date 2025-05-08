# shared/gemini_utils.py
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from api.services.constants import SYSTEM_MESSAGE_TRANSCRIBE_PDF
from google import genai
from google.genai import types
from ninja.files import UploadedFile

from app.config import settings

logger = logging.getLogger(__name__)

client = genai.Client(api_key=settings.gemini_api_key)

PDF_MEMORY_LIMIT = 20 * 1024 * 1024  # 20 MB


def transcribe_uploaded_pdf(uploaded: UploadedFile) -> str:
    # Correct variable reference
    prompt = SYSTEM_MESSAGE_TRANSCRIBE_PDF
    model = "gemini-2.5-flash-preview-04-17"

    logger.info(f"Transcribing PDF with size {uploaded.size} bytes using model {model}")

    if uploaded.size < PDF_MEMORY_LIMIT:
        # ------------- caminho inline (≤ 20 MB) -------------
        data = uploaded.read()  # synchronous read
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=data, mime_type="application/pdf"),
                "Esse é meu documento.",
            ],
            config=types.GenerateContentConfig(
                temperature=0.5, system_instruction=prompt
            ),
        )
        if response.text:
            return response.text.strip()
        else:
            raise ValueError("Unable to transcribe PDF.")

    # ------------- caminho File API (> 20 MB) -------------
    if hasattr(uploaded, "temporary_file_path"):
        file_path = Path(uploaded.temporary_file_path())  # type: ignore
    else:  # é InMemory mas grande porque limiar foi alterado
        tmp = NamedTemporaryFile(delete=False, suffix=".pdf")
        for chunk in uploaded.chunks():
            tmp.write(chunk)
        tmp.close()
        file_path = Path(tmp.name)

    gfile = client.files.upload(file=file_path, config={"mime_type": "application/pdf"})
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash-preview-04-17",
            contents=[gfile, "Esse é meu documento."],  # Using same text as inline path
            config=types.GenerateContentConfig(
                temperature=0.5, system_instruction=prompt
            ),
        )
        if resp.text:
            return resp.text.strip()
        else:
            raise ValueError("Unable to transcribe PDF.")
    finally:
        if file_path.exists():
            file_path.unlink(missing_ok=True)
