import hashlib
import hmac
from typing import Any

GITHUB_SIGNATURE_PREFIX = "sha256="
MAX_WEBHOOK_BODY_BYTES = 1_048_576


def build_github_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return f"{GITHUB_SIGNATURE_PREFIX}{digest}"


def verify_github_signature(
    body: bytes,
    signature: str,
    secret: str,
) -> bool:
    if not signature.startswith(GITHUB_SIGNATURE_PREFIX):
        return False

    expected = build_github_signature(body, secret)
    return hmac.compare_digest(expected, signature)


def _optional_text(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:max_length]


def extract_github_metadata(
    payload: dict[str, Any],
) -> tuple[str, str | None, str | None]:
    repository = payload.get("repository")
    repository_full_name = "unknown"
    if isinstance(repository, dict):
        repository_full_name = (
            _optional_text(repository.get("full_name"), 200) or "unknown"
        )

    git_ref = _optional_text(payload.get("ref"), 500)
    commit_sha = _optional_text(payload.get("after"), 40)
    if commit_sha is not None and (
        len(commit_sha) != 40
        or any(character not in "0123456789abcdefABCDEF" for character in commit_sha)
    ):
        commit_sha = None

    return repository_full_name, git_ref, commit_sha
