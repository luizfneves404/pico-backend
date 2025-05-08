import asyncio
import os
import time
from datetime import timedelta

import quiz.challenge_service as challenge_service
import requests
from api.services.misc_service import generate_transcription
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from ninja.files import UploadedFile
from quiz.models import QuestionSelectionMethod

from app.config import settings

User = get_user_model()

# Usar configurações do settings
BRANCH_KEY = settings.branch_api_key
BRANCH_KEY_TEST = settings.branch_api_key_test


class Command(BaseCommand):
    help = "Generate challenges from PDFs in a specified directory"

    def add_arguments(self, parser):
        parser.add_argument(
            "directory", type=str, help="Directory containing PDF files"
        )
        parser.add_argument(
            "--user",
            type=str,
            help="Username of the user to associate with the challenges",
            required=True,
        )

    def handle(self, *args, **options):
        directory = options["directory"]
        username = options["user"]

        # Validate directory
        if not os.path.isdir(directory):
            self.stderr.write(self.style.ERROR(f"Directory {directory} does not exist"))
            return

        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"User {username} does not exist"))
            return

        # Process subdirectories
        subdirs = [
            d
            for d in os.listdir(directory)
            if os.path.isdir(os.path.join(directory, d))
        ]

        if not subdirs:
            self.stderr.write(
                self.style.ERROR(f"No subdirectories found in {directory}")
            )
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(subdirs)} subdirectories"))

        # Lista para armazenar todos os resultados
        all_results = []

        # Process each subdirectory
        for subdir in subdirs:
            subdir_path = os.path.join(directory, subdir)

            # Determine subject based on subdirectory name
            if subdir.startswith("Matemática"):
                subject = "Matemática"
            elif subdir.startswith("Física"):
                subject = "Física"
            elif subdir.startswith("Química"):
                subject = "Química"
            else:
                subject = "História"

            self.stdout.write(f"Processing subdirectory: {subdir} (Subject: {subject})")

            # Get PDF files in this subdirectory
            pdf_files = []
            for filename in os.listdir(subdir_path):
                if filename.lower().endswith((".pdf", ".PDF")):
                    file_path = os.path.join(subdir_path, filename)
                    pdf_files.append(file_path)

            if not pdf_files:
                self.stderr.write(
                    self.style.ERROR(f"No PDF files found in {subdir_path}")
                )
                continue

            self.stdout.write(
                self.style.SUCCESS(f"Found {len(pdf_files)} PDF files in {subdir}")
            )

            # Process each PDF file
            results = asyncio.run(self.process_pdfs(pdf_files, user, subject))
            all_results.extend(results)

        # Imprimir todos os resultados de forma organizada ao final
        self.stdout.write("\nAll Processing Results:")
        self.stdout.write("-" * 50)
        for result in all_results:
            if "error" in result:
                self.stdout.write(
                    self.style.ERROR(
                        f"PDF: {result['pdf_name']}\nError: {result['error']}\n"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"PDF: {result['pdf_name']}\n"
                        f"Challenge ID: {result['challenge_id']}\n"
                        f"Challenge Code: {result['challenge_code']}\n"
                        f"Challenge Title: {result['challenge_title']}\n"
                        f"Share Link: {result['branch_link']}\n"
                    )
                )
            self.stdout.write("-" * 50)

    def generate_branch_link(
        self, challenge_code, battle_type, creator_id, creator_username
    ):
        """
        Generate a Branch.io deep link for a challenge or duel
        """
        try:
            unique_alias = (
                f"{battle_type}_{challenge_code}_t={int(time.time())}_uId={creator_id}"
            )

            url = "https://api2.branch.io/v1/url"
            data = {
                "branch_key": BRANCH_KEY,
                "alias": unique_alias,
                "data": {
                    "itemType": "battle",
                    "battleCode": challenge_code,
                    "battleType": battle_type,
                    "creatorId": str(creator_id),
                    "creatorUsername": creator_username,
                    "referrerId": str(creator_id),
                    "referrerUsername": creator_username,
                    "timestamp": str(int(time.time())),
                },
                "title": f"Entre no meu {battle_type}!",
                "description": "Junte-se a mim no Pico!",
                "feature": "backend_invite",
                "channel": "backend_autogenerated",
                "campaign": "paula_resumos_test",
                "$desktop_url": "https://www.usepico.com.br/",
            }

            response = requests.post(url, json=data)
            response.raise_for_status()

            return response.json().get("url")
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"Error generating Branch link: {str(e)}")
            )
            return None

    async def process_pdfs(self, pdf_files, user, subject):
        results = []  # Lista para armazenar os resultados

        for pdf_path in pdf_files:
            try:
                pdf_name = os.path.basename(pdf_path)
                self.stdout.write(f"Processing {pdf_name}...")

                # Generate transcription
                try:
                    # Abrir o arquivo PDF diretamente
                    with open(pdf_path, "rb") as f:
                        # Criar UploadedFile com o arquivo aberto
                        uploaded_file = UploadedFile(
                            file=f,
                            name=pdf_name,
                            content_type="application/pdf",
                            size=os.path.getsize(pdf_path),
                        )

                        # Gerar transcrição
                        transcription_blocks = await generate_transcription(
                            [uploaded_file]
                        )

                    num_blocks = len(transcription_blocks)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Transcription generated with {num_blocks} blocks"
                        )
                    )

                    if num_blocks == 0:
                        self.stderr.write(
                            self.style.ERROR(
                                f"No transcription blocks generated for {pdf_path}"
                            )
                        )
                        continue

                    # Definir período do desafio
                    start_time = timezone.now()
                    end_time = start_time + timedelta(days=700)

                    # Criar desafio
                    challenge_result = await challenge_service.acreate_challenge(
                        by_user_id=user.id,
                        to_user_ids=[],  # Sem usuários adicionais
                        start_time=start_time,
                        end_time=end_time,
                        is_fast=True,
                        selection_method=QuestionSelectionMethod.USER_GENERATED,
                        query="",
                        question_blocks=transcription_blocks,
                        topic="",  # Usar nome do PDF como tópico
                        subject=subject,
                        area="",
                        difficulty="",
                        source_filter="",
                    )

                    battle_type = "Desafio"
                    challenge_code = (
                        challenge_result.code
                    )  # Usando o campo code em vez de id

                    branch_link = self.generate_branch_link(
                        challenge_code=challenge_code,
                        battle_type=battle_type,
                        creator_id=user.id,
                        creator_username=user.username,
                    )

                    # Exibir link imediatamente para verificação
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"\n--- Challenge Created ---\n"
                            f"PDF: {pdf_name}\n"
                            f"Challenge Code: {challenge_code}\n"
                            f"Share Link: {branch_link}\n"
                            f"------------------------\n"
                        )
                    )

                    # Armazenar resultado com referência ao PDF
                    results.append(
                        {
                            "pdf_name": pdf_name,
                            "pdf_path": pdf_path,
                            "challenge_id": challenge_result.id,
                            "challenge_code": challenge_code,
                            "challenge_title": challenge_result.title,
                            "branch_link": branch_link,
                        }
                    )

                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Error in transcription/challenge creation: {str(e)}"
                        )
                    )
                    results.append(
                        {"pdf_name": pdf_name, "pdf_path": pdf_path, "error": str(e)}
                    )

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f"Error processing {pdf_path}: {str(e)}")
                )
                results.append(
                    {"pdf_name": pdf_name, "pdf_path": pdf_path, "error": str(e)}
                )

        return results
