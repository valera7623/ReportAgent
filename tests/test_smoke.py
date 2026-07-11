"""Pytest smoke tests for ReportAgent improvements."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DOMAIN", "localhost")
    monkeypatch.setenv("DISABLE_AUTH", "false")
    monkeypatch.setenv("BILLING_ENABLED", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-32chars-min")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key-32-characters-long")


def test_startup_guards_allow_localhost():
    from app.startup_guards import validate_production_config

    validate_production_config()


def test_startup_guards_block_disable_auth_on_public_domain(monkeypatch):
    from app.startup_guards import validate_production_config

    monkeypatch.setenv("DOMAIN", "reportagent.example.com")
    monkeypatch.setenv("DISABLE_AUTH", "true")
    with pytest.raises(RuntimeError, match="DISABLE_AUTH"):
        validate_production_config()


def test_refund_report_slot_no_user():
    from app.payments.usage_tracker import refund_report_slot

    assert refund_report_slot(user_id=None) is False


def test_yookassa_should_not_cancel_on_abandoned_checkout():
    from app.webhooks.yookassa_webhook import _should_cancel_on_payment_canceled

    assert _should_cancel_on_payment_canceled({"id": "pay-1"}, {}) is False
    assert (
        _should_cancel_on_payment_canceled(
            {"id": "pay-1"},
            {"cancel_subscription": "true"},
        )
        is True
    )


def test_stripe_event_dedup_claim(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from app.db.init_db import run_migrations
    from app.webhooks.stripe_webhook import _claim_stripe_event

    run_migrations()
    assert _claim_stripe_event("evt_123", "checkout.session.completed") is True
    assert _claim_stripe_event("evt_123", "checkout.session.completed") is False


def test_scheduled_next_run_daily():
    from app.routers.scheduled_reports import _compute_next_run

    result = _compute_next_run("@daily")
    assert "T" in result and result.endswith("Z")
