SYSTEM_MESSAGE_GENERATE_TRANSCRIPTION_FROM_IMAGE = """Você recebeu a tarefa de transcrever o conteúdo acadêmico presente em uma imagem de um caderno ou material escolar.

Regras importantes:
1. Transcreva TODO o conteúdo acadêmico de forma clara e completa
2. Ignore informações pessoais, rabiscos ou anotações não relacionadas
3. Não mencione a imagem ou faça referência a ela
4. Não adicione comentários ou observações próprias

Forneça apenas o conteúdo acadêmico transcrito."""


PEN_TO_PRINT_RAPIDAPI_URL = (
    "https://pen-to-print-handwriting-ocr.p.rapidapi.com/recognize/"
)
PEN_TO_PRINT_RAPIDAPI_SESSION = "extract_text_pen_to_print for essay"
PEN_TO_PRINT_RAPIDAPI_HOST = "pen-to-print-handwriting-ocr.p.rapidapi.com"

EXTRACT_OPENAI_MODEL = "gpt-4o"
EXTRACT_OPENAI_SYSTEM_MESSAGE = """A imagem a seguir é uma foto ou escaneamento de uma redação do ENEM. Por favor, extraia o texto da imagem e responda com o texto extraído da imagem. Se a imagem não for uma redação, responda com 'Não aplicável.'"""
EXTRACT_OPENAI_TIMEOUT = 60

TEXTRACT_EXTRACTION_METHOD = "Amazon Textract"

PEN_TO_PRINT_EXTRACTION_METHOD = "Pen to Print"

EXTRACT_OPENAI_EXTRACTION_METHOD = "OpenAI"
