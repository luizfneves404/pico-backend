import json
import logging
from datetime import datetime
from typing import Any

import shared.openai_utils as openai_utils
from celery import shared_task
from django.utils import timezone
from study_plans.models import StudyPlan

from pico_backend.celery import celery_async_workflow

logger = logging.getLogger(__name__)

CALENDAR_MODEL = "gpt-4o"

CALENDAR_TEMPERATURE = 0.33

CALENDAR_TIMEOUT = 60

CALENDAR_SYSTEM_MESSAGE = """Você é um especialista em planejar calendários de estudo para o ENEM 2024. Você irá receber os seguintes dados:

- Data de Hoje
- Área de Foco do Estudante (Exatas, Humanas, Biomédicas, Geral)

Com base nisso, você deve criar um JSON contendo um calendário com 28 dias, começando pelo dia de hoje, dizendo os temas a ser estudados pelo aluno. Siga algumas regras:

- Os temas não devem se repetir nesse período de 28 dias. A ideia é que o aluno reconfigure seu calendário após esse momento
- As quatro áreas do ENEM deverão ser abordadas ao longo desse período. No entanto, em proporções diferentes:
Se o aluno escolheu "Exatas" como Área de Foco, ele deve ter 3 dias de matemática, 2 dias de ciências de natureza, 1 dia de português e 1 dia de humanas a cada semana.
Se o aluno escolheu "Humanas", ele deve ter 3 dias de humanas, 2 dias de português, 1 dia de matemática e 1 dia de ciências da natureza a cada semana.
Se o aluno escolheu "Biomédicas", ele deve ter 4 dias de ciências da natureza (foco maior em química e biologia)s; 1 dia de matemática, 1 dia de português, 1 dia de humanas.
Se o aluno escolheu “Geral”, ele deve receber cada dia uma área diferente, sem repetir, focando nos tópicos mais recorrentes de cada área.
- Para cada dia, você deve atribuir ao aluno o tópico que ele estudará, dentro de cada categoria. Os tópicos não devem se repetir. Utilize os tópicos mais cobrados no ENEM para fazer essa atribuição.
- O json deve ter o seguinte formato:
  {"calendar": [
    {"date": "2024-05-30", "area": "Area", "query": "Topic"}, ...]}
Pule uma linha ao fim de cada semana a fim de facilitar a visualização.
Para Area, considere apenas as quatro opções: Matemática, Ciências Humanas, Ciências da Natureza, Linguagens.
Lembre-se de sempre escolher os tópicos mais cobrados dentro de cada área. Esse calendário de estudos é apenas para questões do ENEM, então não deve incluir redação. Considere os temas mais cobrados do ENEM de cada área para escolher os tópicos."""

CALENDAR_USER_MESSAGE = """Data de Hoje: {today}
Área de Foco do Estudante: {area}"""


def validate_calendar_json(calendar: dict[str, Any]) -> bool:
    try:
        # Check if the calendar key exists and is a list
        if (
            not isinstance(calendar, dict)
            or "calendar" not in calendar
            or not isinstance(calendar["calendar"], list)
        ):
            logger.error("Invalid calendar JSON: missing 'calendar' key or not a list")
            return False

        # Check if each entry in the calendar list has the required keys
        required_keys = {"date", "area", "query"}
        for entry in calendar["calendar"]:
            if not isinstance(entry, dict):
                logger.error("Invalid calendar JSON: entry is not a dictionary")
                return False
            if not required_keys.issubset(entry.keys()):
                logger.error("Invalid calendar JSON: missing required keys")
                return False
            # Validate the date format
            try:
                datetime.strptime(entry["date"], "%Y-%m-%d")
            except ValueError:
                logger.error("Invalid calendar JSON: invalid date format")
                return False
            # Validate the area
            if entry["area"] not in {
                "Matemática",
                "Ciências Humanas",
                "Ciências da Natureza",
                "Linguagens",
            }:
                logger.error("Invalid calendar JSON: invalid area")
                return False
            # Validate the query (just ensure it's a non-empty string)
            if not isinstance(entry["query"], str) or not entry["query"].strip():
                logger.error("Invalid calendar JSON: invalid query")
                return False

        return True
    except KeyError:
        return False


@shared_task(bind=True)
def add_calendar_json(self, study_plan_id: int, area: str, retry: bool = False):
    logger.debug(f"Adding calendar JSON to study plan {study_plan_id}... ")

    temperature = 0 if retry else CALENDAR_TEMPERATURE

    calendar_response = openai_utils.get_openai_completion(
        CALENDAR_MODEL,
        temperature,
        [
            {
                "role": "system",
                "content": CALENDAR_SYSTEM_MESSAGE,
            },
            {
                "role": "user",
                "content": CALENDAR_USER_MESSAGE.format(
                    today=timezone.localdate().strftime("%Y-%m-%d"), area=area
                ),
            },
        ],
        json_mode=True,
        timeout=CALENDAR_TIMEOUT,
    )

    try:
        calendar = json.loads(calendar_response)
    except json.JSONDecodeError as e:
        if not retry:
            logger.error(f"JSON decode error: {e}, retrying with temperature 0")
            self.retry(args=(study_plan_id, area), kwargs={"retry": True}, countdown=5)
            return
        else:
            logger.error(f"JSON decode error on retry with temperature 0: {e}")
            calendar = {"error": "Invalid Calendar JSON"}

    if validate_calendar_json(calendar):
        study_plan = StudyPlan.objects.get(id=study_plan_id)
        study_plan.calendar = calendar
        study_plan.save()
        logger.info(f"Calendar JSON added to study plan {study_plan_id}")
    else:
        if not retry:
            logger.warning(f"Invalid calendar JSON, retrying with temperature 0")
            self.retry(args=(study_plan_id, area), kwargs={"retry": True}, countdown=5)
        else:
            study_plan = StudyPlan.objects.get(id=study_plan_id)
            study_plan.calendar = {"error": "Invalid Calendar JSON"}
            study_plan.save()
            logger.info(f"Invalid calendar JSON added to study plan {study_plan_id}")


@celery_async_workflow
def add_calendar_json_async_workflow(id: int, area: str):
    add_calendar_json.si(id, area).delay().forget()
