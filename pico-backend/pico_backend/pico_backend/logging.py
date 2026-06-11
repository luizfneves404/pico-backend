from django.core.cache import cache
from django.utils.log import AdminEmailHandler

PERIOD_LENGTH_IN_SECONDS = 300
MAX_EMAILS_IN_PERIOD = 30
COUNTER_CACHE_KEY = "email_admins_counter"


class ThrottledAdminEmailHandler(AdminEmailHandler):
    def increment_counter(self):
        try:
            cache.incr(COUNTER_CACHE_KEY)
        except ValueError:
            cache.set(COUNTER_CACHE_KEY, 1, PERIOD_LENGTH_IN_SECONDS)
        return cache.get(COUNTER_CACHE_KEY)

    def emit(self, record):
        try:
            counter = self.increment_counter()
        except Exception:
            pass
        else:
            if counter > MAX_EMAILS_IN_PERIOD:
                return
        super(ThrottledAdminEmailHandler, self).emit(record)
