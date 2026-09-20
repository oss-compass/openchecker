"""
OpenChecker request body validation.

The ``/opencheck`` endpoint is the only place where untrusted HTTP input turns
into work for the agents, and two problems motivated this module:

* a request with a missing or misspelled field used to fail with an unhandled
  ``KeyError``/``TypeError`` that was reported to the caller as a generic HTTP
  500 (the ``#TODO`` that used to sit in ``main.OpenCheck.post``), which makes
  it impossible for a client to tell a bad request from a server fault;
* values that used to be accepted as-is are interpolated into the bash scripts
  defined in ``constans.py`` and executed by ``agent.py``: ``project_url`` is
  passed to ``git clone`` unquoted and ``task_metadata.version_number`` becomes
  a git tag, so a payload such as
  ``{"project_url": "https://example.com/x; rm -rf /"}`` would have been
  executed by the agent.

The checks below are therefore more than type checks: they reject values that
cannot be represented safely in the generated scripts, and they report *every*
problem of a request at once so a client can fix the whole payload in one round
trip.

Flask and the queue client are deliberately not imported here, which keeps the
rules testable on their own and lets the message consumer reuse them if the same
schema ever has to be validated a second time.
"""

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit


class RequestValidationError(ValueError):
    """Raised when an /opencheck request body does not match the schema.

    Attributes:
        errors: One human readable message per invalid field. The messages are
            returned to the caller with the HTTP 400 response, so they describe
            what is wrong without echoing the offending value back.
    """

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# Checker names the agent knows how to execute. Keep this list in sync with the
# command_switch of agent._execute_commands: an unknown command only produces a
# log warning there while the message is still acknowledged, so a typo used to
# end up as a successful response with an empty report.
SUPPORTED_COMMANDS = frozenset([
    "binary-checker",
    "release-checker",
    "url-checker",
    "sonar-scanner",
    "osv-scanner",
    "scancode",
    "dependency-checker",
    "readme-checker",
    "maintainers-checker",
    "languages-detector",
    "oat-scanner",
    "license-detector",
    "api-doc-checker",
    "build-doc-checker",
    "readme-opensource-checker",
    "bestpractices-checker",
    "dangerous-workflow-checker",
    "dependency-update-tool-checker",
    "fuzzing-checker",
    "packaging-checker",
    "pinned-dependencies-checker",
    "sast-checker",
    "security-policy-checker",
    "token-permissions-checker",
    "webhooks-checker",
    "changed-files-since-commit-detector",
    "criticality-score",
    "scorecard-score",
    "code-count",
    "package-info",
    "ohpm-info",
    "repo-country-organizations",
    "eol-checker",
])

# Fields the endpoint documents, used for the error message of a body that is
# not a JSON object at all.
REQUIRED_FIELDS = ("commands", "project_url", "callback_url")
OPTIONAL_FIELDS = ("commit_hash", "access_token", "task_metadata")

ALLOWED_URL_SCHEMES = ("http", "https")

# Limits: they stop a single request from filling the queue with a payload that
# no checker can use.
MAX_COMMANDS = 50
MAX_COMMAND_LENGTH = 64
MAX_URL_LENGTH = 2048
MAX_ACCESS_TOKEN_LENGTH = 512
MAX_TASK_METADATA_LENGTH = 4096
MAX_TASK_METADATA_DEPTH = 3
MAX_VERSION_NUMBER_LENGTH = 128

_BODY_ERROR = (
    "Request body must be a JSON object with the required fields %s and the "
    "optional fields %s." % (", ".join(REQUIRED_FIELDS), ", ".join(OPTIONAL_FIELDS))
)

# Characters that must never show up in a URL or in the git revision taken from
# task_metadata: constans.py interpolates both values into bash scripts without
# quoting, so whitespace (which splits an argument) and the shell metacharacters
# that start a command or expand a variable would allow command injection
# through a request body.
_UNSAFE_SHELL_CHARACTERS = re.compile(r"""[ \t\r\n`$;|&<>(){}\[\]\\'"!*]""")

# git revisions are hexadecimal, nothing else.
_COMMIT_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{4,64}$")

# version_number is rendered into the download-checkout script both as
# ``git checkout "<version>"`` and as ``[ <version> != "None" ]``, so only
# characters that are valid in a git tag or branch name are allowed.
_VERSION_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")

# Access tokens are forwarded to the platform APIs in HTTP headers, so
# whitespace and control characters have to be rejected.
_UNSAFE_TOKEN_CHARACTERS = re.compile(r"[\s\x00-\x1f\x7f]")


def _field_type(value: Any) -> str:
    """Return the JSON type name of ``value``, used in error messages."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _validate_commands(value: Any, errors: List[str]) -> List[str]:
    """Validate ``commands`` and return it de-duplicated, keeping the order."""
    if value is None:
        errors.append("'commands' is required and must be a non-empty list of checker names.")
        return []
    if not isinstance(value, list):
        errors.append("'commands' must be an array of checker names, got %s." % _field_type(value))
        return []
    if not value:
        errors.append("'commands' must contain at least one checker name.")
        return []
    if len(value) > MAX_COMMANDS:
        errors.append("'commands' must not contain more than %d checker names." % MAX_COMMANDS)
        return []

    commands: List[str] = []
    for index, command in enumerate(value):
        if not isinstance(command, str):
            errors.append("'commands[%d]' must be a string, got %s." % (index, _field_type(command)))
            continue
        name = command.strip()
        if not name:
            errors.append("'commands[%d]' must not be empty." % index)
            continue
        if len(name) > MAX_COMMAND_LENGTH:
            errors.append("'commands[%d]' must not be longer than %d characters." % (index, MAX_COMMAND_LENGTH))
            continue
        if name not in SUPPORTED_COMMANDS:
            errors.append("'commands[%d]' is not a supported checker: %r." % (index, name))
            continue
        if name in commands:
            # Running a checker twice doubles the work for the agent and the
            # second run overwrites the result of the first one.
            continue
        commands.append(name)
    return commands


def _validate_url(field: str, value: Any, errors: List[str]) -> Optional[str]:
    """Validate a required http(s) URL and return it stripped."""
    if value is None:
        errors.append("'%s' is required and must be an http(s) URL." % field)
        return None
    if not isinstance(value, str):
        errors.append("'%s' must be a string URL, got %s." % (field, _field_type(value)))
        return None

    url = value.strip()
    if not url:
        errors.append("'%s' must not be empty." % field)
        return None
    if len(url) > MAX_URL_LENGTH:
        errors.append("'%s' must not be longer than %d characters." % (field, MAX_URL_LENGTH))
        return None
    if _UNSAFE_SHELL_CHARACTERS.search(url):
        errors.append("'%s' contains whitespace or shell metacharacters that are not allowed in a URL." % field)
        return None

    parsed = urlsplit(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        errors.append("'%s' must use the %s scheme." % (field, " or ".join(ALLOWED_URL_SCHEMES)))
        return None
    if not parsed.netloc:
        errors.append("'%s' must contain a host name." % field)
        return None
    return url


def _validate_commit_hash(value: Any, errors: List[str]) -> Optional[str]:
    """Validate the optional ``commit_hash`` field and return it stripped."""
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append("'commit_hash' must be a string, got %s." % _field_type(value))
        return None
    commit_hash = value.strip()
    if not commit_hash:
        # An explicitly empty value means "use the default branch"; treating it
        # as missing keeps the agent from passing an empty revision to git.
        return None
    if not _COMMIT_HASH_PATTERN.match(commit_hash):
        errors.append("'commit_hash' must be a 4 to 64 character hexadecimal git revision.")
        return None
    return commit_hash


def _validate_access_token(value: Any, errors: List[str]) -> Optional[str]:
    """Validate the optional ``access_token`` field and return it stripped."""
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append("'access_token' must be a string, got %s." % _field_type(value))
        return None
    token = value.strip()
    if not token:
        return None
    if len(token) > MAX_ACCESS_TOKEN_LENGTH:
        errors.append("'access_token' must not be longer than %d characters." % MAX_ACCESS_TOKEN_LENGTH)
        return None
    if _UNSAFE_TOKEN_CHARACTERS.search(token):
        errors.append("'access_token' must not contain whitespace or control characters.")
        return None
    return token


def _json_depth(value: Any, current_depth: int = 1) -> int:
    """Return the nesting depth of a JSON value (1 for a scalar)."""
    if isinstance(value, dict):
        children = list(value.values())
    elif isinstance(value, list):
        children = list(value)
    else:
        return current_depth
    if not children:
        return current_depth
    return max(_json_depth(child, current_depth + 1) for child in children)


def _validate_task_metadata(value: Any, errors: List[str]) -> Dict[str, Any]:
    """Validate the optional ``task_metadata`` object and return a copy.

    ``version_number`` gets special attention because
    ``agent._download_project_source`` renders it into the ``download-checkout``
    bash script, so it has to look like a git tag or branch name and nothing
    else.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        errors.append("'task_metadata' must be a JSON object, got %s." % _field_type(value))
        return {}
    if any(not isinstance(key, str) for key in value):
        errors.append("'task_metadata' keys must be strings.")
        return {}

    try:
        serialized = json.dumps(value)
    except (TypeError, ValueError):
        errors.append("'task_metadata' must only contain JSON serializable values.")
        return {}
    if len(serialized) > MAX_TASK_METADATA_LENGTH:
        errors.append("'task_metadata' must not be larger than %d characters when serialized." % MAX_TASK_METADATA_LENGTH)
        return {}
    if _json_depth(value) > MAX_TASK_METADATA_DEPTH:
        errors.append("'task_metadata' must not be nested deeper than %d levels." % MAX_TASK_METADATA_DEPTH)
        return {}

    metadata = dict(value)
    version_number = metadata.get("version_number")
    if version_number is not None:
        if not isinstance(version_number, str):
            errors.append("'task_metadata.version_number' must be a string.")
            return metadata
        version_number = version_number.strip()
        if not version_number:
            # An empty value means "no tag or branch"; dropping the key lets the
            # agent fall back to the default branch instead of rendering an
            # empty comparison into the checkout script.
            metadata.pop("version_number", None)
            return metadata
        if (len(version_number) > MAX_VERSION_NUMBER_LENGTH
                or not _VERSION_NUMBER_PATTERN.match(version_number)):
            errors.append(
                "'task_metadata.version_number' must be a tag or branch name of at most %d characters "
                "using only letters, digits, '.', '_', '+' and '-'." % MAX_VERSION_NUMBER_LENGTH
            )
            return metadata
        metadata["version_number"] = version_number
    return metadata


def validate_opencheck_payload(payload: Any) -> Dict[str, Any]:
    """Validate and normalize the JSON body of a ``POST /opencheck`` request.

    Args:
        payload: The decoded request body as returned by
            ``request.get_json(silent=True)``. ``None`` is what Flask returns
            for a missing body, a wrong content type or malformed JSON.

    Returns:
        A dict with the normalized ``commands``, ``project_url``,
        ``commit_hash``, ``access_token``, ``callback_url`` and
        ``task_metadata`` fields. The optional fields are always present so the
        caller does not need its own defaults, unknown fields are ignored so the
        endpoint stays forward compatible, and ``commands`` is de-duplicated
        while keeping the order of the request.

    Raises:
        RequestValidationError: If the body is not a JSON object, or a field is
            missing, of the wrong type or outside the documented limits. Every
            problem is reported at once.
    """
    # ``None`` covers a missing body, a non JSON content type and malformed
    # JSON; any other non dict value is a JSON array/string/number body.
    if payload is None or not isinstance(payload, dict):
        raise RequestValidationError([_BODY_ERROR])

    errors: List[str] = []
    commands = _validate_commands(payload.get("commands"), errors)
    project_url = _validate_url("project_url", payload.get("project_url"), errors)
    callback_url = _validate_url("callback_url", payload.get("callback_url"), errors)
    commit_hash = _validate_commit_hash(payload.get("commit_hash"), errors)
    access_token = _validate_access_token(payload.get("access_token"), errors)
    task_metadata = _validate_task_metadata(payload.get("task_metadata"), errors)

    if errors:
        raise RequestValidationError(errors)

    return {
        "commands": commands,
        "project_url": project_url,
        "commit_hash": commit_hash,
        "access_token": access_token,
        "callback_url": callback_url,
        "task_metadata": task_metadata,
    }
