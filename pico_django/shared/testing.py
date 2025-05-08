from unittest.mock import patch

from django.test import TestCase
from redis import ConnectionPool, Redis
from shared.mock import mock_external_apis

from app.config import settings


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

        # Flush Redis for clean test state
        redis_connection_pool = ConnectionPool.from_url(settings.redis_url)
        redis = Redis.from_pool(redis_connection_pool)
        redis.flushall()
        redis.close()
