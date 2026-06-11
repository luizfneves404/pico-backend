class UserNotFoundError(Exception):
    pass


class UsernameAlreadyExists(Exception):
    pass


class PhoneNumberAlreadyExists(Exception):
    pass


class EmailAlreadyExists(Exception):
    pass


class ReferredByNotFoundError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class SocialAuthError(Exception):
    """Base exception for social authentication errors."""

    pass


class InvalidTokenError(SocialAuthError):
    """Raised when social ID token is invalid."""

    pass


class AccountExistsError(SocialAuthError):
    """Raised when an account already exists with different auth method."""

    pass


class InvalidCountryCodeError(Exception):
    """Raised when an invalid country code is provided."""

    pass


class InvalidLevelIdError(Exception):
    pass


class InvalidInstitutionIdError(Exception):
    pass


class InvalidCourseIdError(Exception):
    pass


class InvalidStageIdError(Exception):
    pass


class InvalidResetTokenError(Exception):
    pass


class MissingNameError(Exception):
    pass
