import hashlib
import hmac

from prd_engine.api.middleware import webhook_auth


def test_valid_webhook_signature(monkeypatch):
    secret = "test-webhook-secret"
    payload = b'{"event":"workflow.completed"}'
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    monkeypatch.setattr(webhook_auth.settings, "webhook_secret", secret)

    assert webhook_auth.verify_webhook_signature(payload, signature)


def test_invalid_webhook_signature_rejected(monkeypatch):
    monkeypatch.setattr(webhook_auth.settings, "webhook_secret", "test-webhook-secret")

    assert not webhook_auth.verify_webhook_signature(
        b'{"event":"workflow.completed"}',
        "invalid-signature",
    )


def test_signature_for_changed_payload_rejected(monkeypatch):
    secret = "test-webhook-secret"
    original = b'{"event":"workflow.completed"}'
    altered = b'{"event":"workflow.failed"}'
    signature = hmac.new(secret.encode(), original, hashlib.sha256).hexdigest()
    monkeypatch.setattr(webhook_auth.settings, "webhook_secret", secret)

    assert not webhook_auth.verify_webhook_signature(altered, signature)
