from celery import shared_task

from api.services import fcm_service


@shared_task
def task_send_notification(user_ids: list[int], title: str, body: str) -> None:
    fcm_service.send_notification(user_ids, title, body)
