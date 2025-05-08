import logging
import random
import string

from django.db import IntegrityError, models, transaction

CODE_GENERATION_MAX_RETRIES = 30

logger = logging.getLogger(__name__)


class InvalidCodeError(Exception):
    pass


class CodeManager(models.Manager):
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False):
        # Filter out instances that already have a code to avoid overwriting
        for obj in objs:
            if not obj.code:
                obj.code = generate_random_code()

        # Ensure uniqueness for the generated codes
        existing_codes = set(
            self.filter(code__in=[obj.code for obj in objs]).values_list(
                "code", flat=True
            )
        )
        generated_codes = set(obj.code for obj in objs)

        # Resolve collisions by regenerating codes for duplicates
        for obj in objs:
            while (
                obj.code in existing_codes or list(generated_codes).count(obj.code) > 1
            ):
                obj.code = generate_random_code()

        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts
        )

    def bulk_update(self, objs, fields, batch_size=None):
        if "code" in fields:
            # Filter out instances that already have a code to avoid overwriting
            for obj in objs:
                if not obj.code:
                    obj.code = generate_random_code()

            # Ensure uniqueness for the generated codes
            existing_codes = set(
                self.filter(code__in=[obj.code for obj in objs]).values_list(
                    "code", flat=True
                )
            )
            generated_codes = set(obj.code for obj in objs)

            # Resolve collisions by regenerating codes for duplicates
            for obj in objs:
                while (
                    obj.code in existing_codes
                    or list(generated_codes).count(obj.code) > 1
                ):
                    obj.code = generate_random_code()

        return super().bulk_update(objs, fields, batch_size=batch_size)


class CodeModel(models.Model):
    code = models.CharField(max_length=5, unique=True)

    objects = CodeManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.code:  # Only generate code if it hasn't been set
            for attempt in range(CODE_GENERATION_MAX_RETRIES):
                self.code = generate_random_code()  # Generate random code
                try:
                    with transaction.atomic():  # Start a savepoint
                        super().save(*args, **kwargs)
                    break  # If save is successful, exit the loop
                except IntegrityError as e:
                    if "code" in str(e):
                        if attempt == CODE_GENERATION_MAX_RETRIES - 1:
                            raise IntegrityError(
                                "Unable to generate a unique code after multiple attempts"
                            ) from e
                        else:
                            logger.warning(f"IntegrityError: {e}")
                    else:
                        raise e
        else:
            super().save(*args, **kwargs)


def generate_random_code(length=5):
    # Define the character set, excluding ambiguous characters
    chars = "".join(set(string.ascii_uppercase + string.digits) - set("IOQ01"))

    # Generate a random string of the desired length
    return "".join(random.choice(chars) for _ in range(length))


def validate_code_format(code: str):
    if not code.isalnum() or len(code) != 5:
        raise InvalidCodeError()
