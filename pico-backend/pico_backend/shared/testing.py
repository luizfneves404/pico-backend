from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from redis import ConnectionPool, Redis

from shared.mock import mock_external_apis

REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT


class PatchingAndRedisTestCase(TestCase):
    def setUp(self):
        self.patcher = mock_external_apis()
        self.mocks = self.patcher.__enter__()
        self.addCleanup(self.patcher.__exit__, None, None, None)

        patcher = patch(
            "quiz.session_service._task_mark_question_timed_out.apply_async",
            return_value=None,
        )
        self.mock_timeout_task = patcher.start()
        self.addCleanup(patcher.stop)

        redis_connection_pool = ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
        )
        redis = Redis.from_pool(redis_connection_pool)
        redis.flushall()
        redis.close()
