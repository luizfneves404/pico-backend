import csv
import logging
import os
import re

import shared.openai_utils as openai_utils
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from quiz.models import Question
from quiz.quiz_service import SUBJECTS

logger = logging.getLogger(__name__)


def clean_text(text: str):
    """
    Limpa o texto removendo quebras de linha excessivas, espaços duplicados,
    bytes NUL e caracteres de controle indesejados.
    """
    if not isinstance(text, str):
        text = str(text)
    # Remove bytes NUL
    text = text.replace("\x00", "")
    # Substitui caracteres de controle (exceto newline e tab) por espaço
    text = re.sub(r"[\x01-\x1F\x7F]", " ", text)
    # Substitui sequências de três ou mais quebras de linha por duas
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    # Substitui sequências de dois ou mais espaços por um espaço
    text = re.sub(r" {2,}", " ", text)
    return text


class Command(BaseCommand):
    help = "Importa questões discursivas (sem opções) de um arquivo CSV"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Caminho para o arquivo CSV")
        parser.add_argument(
            "image_base_path",
            type=str,
            help="Caminho base para o diretório de imagens",
            nargs="?",
            default="",
        )

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs["csv_file"]
        image_base_path = kwargs.get("image_base_path", "")

        try:
            with open(csv_file_path, "r", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)
                headers = reader.fieldnames
                logger.debug(f"Cabeçalhos do CSV: {headers}")

                # Verificar se 'caderno_number' ou '\ufeffcaderno_number' está presente
                if "caderno_number" in headers:
                    caderno_key = "caderno_number"
                elif "\ufeffcaderno_number" in headers:
                    caderno_key = "\ufeffcaderno_number"
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            "A coluna 'caderno_number' ou '\ufeffcaderno_number' não foi encontrada no CSV. Verifique os cabeçalhos."
                        )
                    )
                    return

                rows = [row for row in reader]
                logger.debug(f"Foram encontradas {len(rows)} linhas no arquivo CSV")

                # Preparar os textos para embeddings
                extra_embedding_texts = [clean_text(row["text"]) for row in rows]
                # Filtrar textos vazios e garantir que são strings
                extra_embedding_texts = [text for text in extra_embedding_texts if text]

                if not extra_embedding_texts:
                    self.stdout.write(
                        self.style.ERROR(
                            "Nenhum texto válido encontrado para computar embeddings."
                        )
                    )
                    return

                embeddings = openai_utils.compute_embedding(extra_embedding_texts)

                if len(embeddings) != len(extra_embedding_texts):
                    self.stdout.write(
                        self.style.ERROR(
                            "O número de embeddings retornados não corresponde ao número de textos enviados."
                        )
                    )
                    return

                for index, (row, embedding) in enumerate(
                    zip(rows, embeddings), start=1
                ):
                    try:
                        extra_embedding_text = clean_text(row["text"])

                        # Validação do assunto
                        subject_raw = row.get("subject", "").strip()
                        subject = clean_text(subject_raw)
                        if subject not in set(SUBJECTS):
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Assunto '{subject}' inválido para a questão na linha {index}. Pulando..."
                                )
                            )
                            continue

                        # Processamento da imagem
                        image_path = row.get("image_path", "").strip()
                        image_file = None

                        if image_path and image_base_path:
                            full_image_path = os.path.join(image_base_path, image_path)
                            if os.path.exists(full_image_path):
                                with open(full_image_path, "rb") as img_file:
                                    image_file = ContentFile(
                                        img_file.read(),
                                        name=os.path.basename(full_image_path),
                                    )
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"Imagem '{full_image_path}' não encontrada na linha {index}. Pulando imagem..."
                                    )
                                )

                        # Processar caderno_number removendo zeros à esquerda
                        caderno_number_raw = row.get(caderno_key, "").strip()
                        logger.debug(
                            f"Valor bruto de '{caderno_key}' na linha {index}: '{caderno_number_raw}'"
                        )

                        # Remover zeros à esquerda
                        caderno_number_clean = caderno_number_raw.lstrip("0")
                        logger.debug(
                            f"Valor limpo de '{caderno_key}' na linha {index}: '{caderno_number_clean}'"
                        )

                        # Verificar se o valor está vazio após remover zeros
                        if not caderno_number_clean:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"caderno_number está vazio após remover zeros na linha {index}. Pulando questão..."
                                )
                            )
                            continue

                        # Converter para inteiro
                        if caderno_number_clean.isdigit():
                            caderno_number = int(caderno_number_clean)
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"caderno_number '{caderno_number_clean}' inválido na linha {index}. Pulando questão..."
                                )
                            )
                            continue

                        # Para cada item A, B, C, D, criar uma questão separada se existir
                        for choice_letter in ["A", "B", "C", "D"]:
                            choice_text_raw = row.get(choice_letter, "").strip()
                            if not choice_text_raw:
                                continue  # Pular se o item estiver vazio

                            choice_text = clean_text(choice_text_raw)

                            # Limpar o campo source
                            source_raw = row.get("source", "").strip()
                            source = clean_text(source_raw).upper()

                            # Verificar se ainda existem bytes NUL
                            if "\x00" in choice_text or "\x00" in source:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"Questão '{choice_letter}' na linha {index} contém bytes NUL após a limpeza. Pulando..."
                                    )
                                )
                                continue

                            question = Question(
                                text=choice_text,
                                extra_embedding_text=extra_embedding_text,
                                subject=subject,
                                source=source,
                                caderno=caderno_number,
                                embedding=embedding,
                            )

                            if image_file:
                                question.image.save(image_file.name, image_file)
                                question.is_active = (
                                    True  # Ativar presumindo que irá funcionar
                                )

                            question.save()
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Questão '{choice_letter}' criada com sucesso na linha {index}"
                                )
                            )
                    except Exception as e:
                        logger.error(f"Erro ao processar a linha {index}: {e}")
                        self.stdout.write(
                            self.style.ERROR(
                                f"Ocorreu um erro ao processar a linha {index}: {e}"
                            )
                        )

        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f"Arquivo CSV '{csv_file_path}' não encontrado.")
            )
        except Exception as e:
            logger.error(f"Erro ao importar questões: {e}")
            self.stdout.write(
                self.style.ERROR(f"Ocorreu um erro durante a importação: {e}")
            )
