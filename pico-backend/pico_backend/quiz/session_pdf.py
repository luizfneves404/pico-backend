import io
import string
import unicodedata

from asgiref.sync import sync_to_async
from django.core.files import File as DjangoFile
from django.core.files.base import ContentFile
from django.db.models import Prefetch
from django.utils.text import slugify
from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase.pdfmetrics import registerFont, registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from quiz.models import Choice, Question, Session, open_field_file_as_temp

from .constants import LINK_COLOR, MARGIN

registerFont(TTFont("SourceSans3", "SourceSans3-Regular.ttf"))
registerFont(TTFont("SourceSans3-Bold", "SourceSans3-Bold.ttf"))
registerFont(TTFont("SourceSans3-Italic", "SourceSans3-Italic.ttf"))

registerFontFamily(
    "SourceSans3",
    normal="SourceSans3",
    bold="SourceSans3-Bold",
    italic="SourceSans3-Italic",
)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="NormalTTF", fontName="SourceSans3"))
styles.add(
    ParagraphStyle(
        name="Centered",
        parent=styles["NormalTTF"],
        alignment=1,  # 0=left, 1=center, 2=right, 3=justify
    )
)


class SessionNotFound(Exception):
    pass


def get_session_pdf(session_id: int) -> DjangoFile:
    choices_prefetch = Prefetch("questions__choices", queryset=Choice.objects.all())
    session = Session.objects.prefetch_related("questions", choices_prefetch).get(
        id=session_id
    )

    buffer = io.BytesIO()

    # Get document title
    if session.session_type == "quiz":
        doc_title = f"Quiz: {session.title}" if session.title else "Quiz"
    elif session.session_type == "duel":
        doc_title = f"Duelo: {session.title}" if session.title else "Duelo"
    elif session.session_type == "challenge":
        doc_title = f"Desafio: {session.title}" if session.title else "Desafio"
    else:
        doc_title = session.session_type.title()

    doc_subject = session.title

    # Create the PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=doc_title,
        author="Pico",
        subject=doc_subject,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    elements: list[Flowable] = []

    header_text = (
        "Esse PDF foi gerado pelo Pico, a inteligência artificial pro vestibular.<br/>"
        'Para conhecer, baixe <a href="https://onelink.to/gw59yg" color="'
        + LINK_COLOR
        + '">pico.app</a> na sua app store e '
        'nos siga no Instagram <a href="https://www.instagram.com/use_pico" color="'
        + LINK_COLOR
        + '">usepico.com.br</a><br/><br/>'
    )
    header = Paragraph(header_text, styles["Centered"])
    elements.append(header)

    elements.append(
        Paragraph(
            f"Questões do {session.session_type.title()} {session.title}"
            if session.title
            else f"Questões do {session.session_type.title()}",
            styles["Heading1"],
        )
    )

    context_managers = []
    questions: list[Question] = [question for question in session.questions.all()]
    for i, question in enumerate(questions):
        elements.append(Paragraph(f"Questão {i + 1}", styles["Heading2"]))

        elements.append(Spacer(1, 12))

        if question.image:
            context_managers.append(open_field_file_as_temp(question.image))
            img_path = context_managers[-1].__enter__()

            elements.append(
                Image(img_path, kind="percentage", width=35, height=35, hAlign="LEFT")
            )

            elements.append(Spacer(1, 12))

        elements.append(
            Paragraph(
                unicodedata.normalize(
                    "NFC",
                    f"{convert_linebreaks_to_br(question.text_with_source_and_subject)}",
                ),
                styles["NormalTTF"],
            )
        )

        elements.append(Spacer(1, 12))

        for j, choice in enumerate(question.choices.all()):
            if choice.text:
                elements.append(
                    Paragraph(
                        unicodedata.normalize(
                            "NFC",
                            f"{string.ascii_uppercase[j]}) {choice.text}",
                        ),
                        styles["NormalTTF"],
                    )
                )

        elements.append(Spacer(1, 12))
        elements.append(HorizontalLine(doc.width - 2 * MARGIN, black))
        elements.append(Spacer(1, 12))

    elements.append(PageBreak())
    elements.append(Paragraph("Gabarito", styles["Heading1"]))

    for i, question in enumerate(questions):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"Questão {i + 1}", styles["Heading2"]))
        elements.append(Spacer(1, 12))
        if question.answer_text:
            elements.append(
                Paragraph(
                    unicodedata.normalize(
                        "NFC", f"{convert_linebreaks_to_br(question.answer_text)}"
                    ),
                    styles["NormalTTF"],
                )
            )
        elif question.answer_image:
            context_managers.append(open_field_file_as_temp(question.answer_image))
            img_path = context_managers[-1].__enter__()
            elements.append(
                Image(img_path, hAlign="LEFT", kind="percentage", width=35, height=35)
            )
        else:
            for j, choice in enumerate(question.choices.all()):
                if choice.is_correct and choice.text:
                    (
                        elements.append(
                            Paragraph(
                                unicodedata.normalize(
                                    "NFC",
                                    f"{string.ascii_uppercase[j]}) {choice.text}",
                                ),
                                styles["NormalTTF"],
                            )
                        )
                    )

        elements.append(Spacer(1, 12))
        elements.append(HorizontalLine(doc.width - 2 * MARGIN, black))

    doc.build(elements)

    buffer.seek(0)

    django_file_content = ContentFile(buffer.getvalue())
    django_file_name = (
        f"{session.session_type}-{slugify(session.title)}.pdf"
        if session.title
        else f"{session.session_type}.pdf"
    )
    django_file = DjangoFile(django_file_content, name=django_file_name)

    for context_manager in context_managers:
        context_manager.__exit__(None, None, None)

    return django_file


async def get_session_pdf_url(session_id: int) -> str:
    session = await Session.objects.filter(id=session_id).afirst()
    if not session:
        raise SessionNotFound
    session.file = await sync_to_async(get_session_pdf)(session_id)
    await session.asave()
    return session.file.url


def convert_linebreaks_to_br(text: str) -> str:
    """Converts newline characters to <br/> for use in ReportLab Paragraphs."""
    return text.replace("\n", "<br/>")


class HorizontalLine(Flowable):
    """A custom flowable that draws a horizontal line."""

    def __init__(self, width: float, color: Color) -> None:
        Flowable.__init__(self)
        self.width = width
        self.color = color

    def draw(self):
        """Draw the line."""
        self.canv.setLineWidth(0.5)
        self.canv.setStrokeColor(self.color)
        self.canv.line(0, 0, self.width, 0)
