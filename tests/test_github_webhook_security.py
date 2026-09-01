from app.services.github_webhook import (
    build_github_signature,
    verify_github_signature,
)


def test_valid_github_signature_is_accepted() -> None:
    body = b'{"ref":"refs/heads/main"}'
    secret = "unit-test-webhook-secret"
    signature = build_github_signature(body, secret)

    assert verify_github_signature(body, signature, secret)


def test_modified_body_is_rejected() -> None:
    body = b"original"
    secret = "unit-test-webhook-secret"
    signature = build_github_signature(body, secret)

    assert not verify_github_signature(b"modified", signature, secret)


def test_non_sha256_signature_is_rejected() -> None:
    assert not verify_github_signature(
        b"payload",
        "sha1=invalid",
        "unit-test-webhook-secret",
    )
