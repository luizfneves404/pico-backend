FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

RUN apt -y update && apt install --no-install-recommends -y postgresql-client libmagic1 tesseract-ocr && rm -rf /var/lib/apt/lists/*

COPY Pipfile Pipfile.lock ./
RUN pip install pipenv && pipenv install --system --deploy --ignore-pipfile

COPY . .

RUN chmod +x ./docker-entrypoint.sh ./docker-celery-entrypoint.sh ./docker-celery-flower-entrypoint.sh
