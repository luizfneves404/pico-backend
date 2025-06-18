# stdlib
import logging
from typing import IO, Final

# third‑party
from google import genai
from google.genai import types, errors

from app.shared.constants import SYSTEM_MESSAGE_TRANSCRIBE_PDF
from app.config import settings

logger = logging.getLogger(__name__)

# ---------- constantes de negócio ----------
_GEMINI_MODEL: Final[str] = "gemini-2.5-flash-preview-05-20"
PDF_SIZE_LIMIT: Final[int] = 20 * 1024 * 1024  # 20 MB hard‑limit

# ---------- client único (reutilizável) ----------
client = genai.Client(api_key=settings.gemini_api_key)


async def transcribe_uploaded_pdf(file_like: IO[bytes]) -> str:
    """
    Recebe um objeto file-like (IO[bytes]) representando **uma página PDF** (<20 MB),
    envia como bytes _inline_ ao Gemini e devolve a transcrição limpa.

    ● 100 % assíncrona, sem bloqueios no event‑loop.
    ● Imune a consumo excessivo de memória, pois valida tamanho antes de `read()`.
    ● Propaga `errors.APIError` como ValueError com log apropriado.
    """
    # 1) ler conteúdo do file-like object ---------------------------------------
    data = file_like.read()  # lê o conteúdo do file-like
    size = len(data)

    if size > PDF_SIZE_LIMIT:
        raise ValueError(f"PDF tem {size/1_048_576:.1f} MB > limite de 20 MB.")

    # 2) chamar Gemini (API assíncrona nativa) ----------------------------------
    try:
        response = await client.aio.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=data, mime_type="application/pdf"),
                "Esse é meu documento.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_MESSAGE_TRANSCRIBE_PDF,
                temperature=0.5,
            ),
        )
    except errors.APIError as e:
        logger.error("Gemini APIError %s – %s", e.code, e.message)
        raise ValueError("Falha no OCR do PDF.") from e

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Modelo não retornou texto.")

    return text
