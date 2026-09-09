from enum import IntEnum

from config import (
    DatabaseConnectionRetryableError,
    DatabaseSecretConfigurationError,
)


class RuntimeConfigurationError(ValueError):
    """Raised when local runtime configuration cannot start a valid crawl."""


class RuntimeExitCode(IntEnum):
    """v11-runtime-exit-1 application-to-worker process contract."""

    SUCCESS = 0
    SCHEMA_CONTRACT_ERROR = 65
    DETERMINISTIC_APPLICATION_ERROR = 70
    DB_CONNECTION_TRANSIENT = 75
    AUTHORIZATION_ERROR = 77
    INVALID_CONFIGURATION = 78


_AUTHORIZATION_SQLSTATES = {"42501"}
_SCHEMA_CONTRACT_SQLSTATES = {"3F000", "42P01", "42703", "42804", "42883"}
_TRANSIENT_SQLSTATES = {"53300", "57P01", "57P02", "57P03"}
_AWS_AUTHORIZATION_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "UnrecognizedClientException",
}
_AWS_CREDENTIAL_ERROR_NAMES = {
    "CredentialRetrievalError",
    "NoCredentialsError",
    "PartialCredentialsError",
}


def _error_chain(error):
    current = error
    seen = set()
    while isinstance(current, BaseException) and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _sqlstate(error):
    value = getattr(error, "sqlstate", None) or getattr(error, "pgcode", None)
    return value if isinstance(value, str) else ""


def _aws_error_code(error):
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return ""
    details = response.get("Error")
    if not isinstance(details, dict):
        return ""
    code = details.get("Code")
    return code if isinstance(code, str) else ""


def classify_runtime_error(error):
    """Map an exception chain to the stable v11 runtime process exit contract."""
    chain = tuple(_error_chain(error))

    for item in chain:
        sqlstate = _sqlstate(item)
        status_code = getattr(item, "status_code", None)
        if (
            sqlstate.startswith("28")
            or sqlstate in _AUTHORIZATION_SQLSTATES
            or _aws_error_code(item) in _AWS_AUTHORIZATION_CODES
            or type(item).__name__ in _AWS_CREDENTIAL_ERROR_NAMES
            or status_code in {401, 403}
        ):
            return RuntimeExitCode.AUTHORIZATION_ERROR

    if any(
        isinstance(item, (DatabaseSecretConfigurationError, RuntimeConfigurationError))
        for item in chain
    ):
        return RuntimeExitCode.INVALID_CONFIGURATION

    if any(_sqlstate(item) in _SCHEMA_CONTRACT_SQLSTATES for item in chain):
        return RuntimeExitCode.SCHEMA_CONTRACT_ERROR

    if any(
        isinstance(item, DatabaseConnectionRetryableError)
        or _sqlstate(item).startswith("08")
        or _sqlstate(item) in _TRANSIENT_SQLSTATES
        for item in chain
    ):
        return RuntimeExitCode.DB_CONNECTION_TRANSIENT

    return RuntimeExitCode.DETERMINISTIC_APPLICATION_ERROR
