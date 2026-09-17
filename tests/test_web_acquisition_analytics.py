from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app_services.analytics.acquisition_service import (
    AcquisitionService,
    bind_web_acquisition_to_account,
    upsert_web_acquisition_touch,
)
from app_services.analytics.service import AnalyticsService
from models.account_flow_event_model import AccountFlowEvent
from models.account_model import Account
from models.base import Base
from models.web_acquisition_attribution_model import WebAcquisitionAttribution


def _build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Account.__table__,
            AccountFlowEvent.__table__,
            WebAcquisitionAttribution.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def test_upsert_web_acquisition_touch_persists_first_touch(monkeypatch):
    session = _build_session()
    first_now = datetime(2026, 3, 30, 12, 0, 0)
    second_now = first_now + timedelta(minutes=10)

    monkeypatch.setattr("app_services.analytics.acquisition_service.utcnow", lambda: first_now)
    row = upsert_web_acquisition_touch(
        session,
        anon_id="anon-1",
        path="/?utm_source=yandex",
        referrer="https://yandex.ru/",
        host="api.vizuai.example",
        acquisition={
            "utm_source": "yandex",
            "utm_medium": "cpc",
            "utm_campaign": "spring_sale",
            "landing_host": "vizuai.example",
        },
    )
    session.commit()

    monkeypatch.setattr("app_services.analytics.acquisition_service.utcnow", lambda: second_now)
    row_again = upsert_web_acquisition_touch(
        session,
        anon_id="anon-1",
        path="/legal",
        referrer="https://google.com/",
        host="api.vizuai.example",
        acquisition={"utm_source": "google"},
    )
    session.commit()

    assert row.id == row_again.id
    assert row_again.first_utm_source == "yandex"
    assert row_again.first_utm_medium == "cpc"
    assert row_again.first_utm_campaign == "spring_sale"
    assert row_again.first_landing_host == "vizuai.example"
    assert row_again.first_landing_path == "/?utm_source=yandex"
    assert row_again.first_referrer == "https://yandex.ru/"
    assert row_again.last_seen_at == second_now


def test_bind_web_acquisition_to_account_links_existing_row(monkeypatch):
    session = _build_session()
    now = datetime(2026, 3, 30, 12, 0, 0)
    monkeypatch.setattr("app_services.analytics.acquisition_service.utcnow", lambda: now)
    account = Account(id=uuid4(), status="active", primary_email="owner@vizuai.example")
    session.add(account)
    session.commit()

    upsert_web_acquisition_touch(
        session,
        anon_id="anon-2",
        path="/",
        referrer="https://t.co/example",
        host="vizuai.example",
        acquisition={"utm_source": "telegram"},
    )
    session.commit()

    row = bind_web_acquisition_to_account(
        session,
        account_id=account.id,
        anon_id="anon-2",
        acquisition={"utm_source": "telegram"},
    )
    session.commit()

    assert row is not None
    assert row.account_id == account.id
    assert row.linked_at == now


def test_acquisition_report_groups_linked_accounts(monkeypatch):
    session = _build_session()
    now = datetime(2026, 3, 30, 18, 0, 0)
    monkeypatch.setattr("app_services.analytics.acquisition_service.utcnow", lambda: now)

    account = Account(id=uuid4(), status="active", primary_email="paid@vizuai.example")
    session.add(account)
    session.commit()

    bind_web_acquisition_to_account(
        session,
        account_id=account.id,
        anon_id="anon-report",
        acquisition={
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "brand_ru",
            "landing_host": "vizuai.example",
            "landing_path": "/?utm_source=google",
        },
    )
    session.add(
        AccountFlowEvent(
            account_id=account.id,
            event_type="auth_verified",
            screen_key="auth",
            action_key="magic_link_verify",
            source="web_api",
            created_at=now,
        )
    )
    session.add(
        AccountFlowEvent(
            account_id=account.id,
            event_type="checkout_created",
            screen_key="billing",
            action_key="create_checkout",
            source="web_api",
            created_at=now,
        )
    )
    session.add(
        AccountFlowEvent(
            account_id=account.id,
            event_type="checkout_paid",
            screen_key="billing",
            action_key="provider_webhook",
            source="web_api",
            created_at=now,
        )
    )
    session.add(
        AccountFlowEvent(
            account_id=account.id,
            event_type="design_job_created",
            screen_key="workspace",
            action_key="create_job",
            source="web_api",
            created_at=now,
        )
    )
    session.commit()

    @contextmanager
    def _fake_db_session():
        yield session

    monkeypatch.setattr("app_services.analytics.acquisition_service.get_db_session", _fake_db_session)

    report = AcquisitionService()._build_report_sync(days=30)

    assert report["totals"]["visitors"] == 1
    assert report["totals"]["logins"] == 1
    assert report["totals"]["checkout_started"] == 1
    assert report["totals"]["checkout_paid"] == 1
    assert report["totals"]["jobs_launched"] == 1
    assert report["sources"][0]["utm_source"] == "google"
    assert report["sources"][0]["checkout_paid"] == 1


def test_account_event_binds_anon_id_to_account(monkeypatch):
    session = _build_session()
    now = datetime(2026, 3, 31, 12, 0, 0)
    monkeypatch.setattr("app_services.analytics.acquisition_service.utcnow", lambda: now)

    account = Account(id=uuid4(), status="active", primary_email="owner@vizuai.example")
    session.add(account)
    session.commit()

    upsert_web_acquisition_touch(
        session,
        anon_id="anon-existing-session",
        path="/",
        referrer="https://facebook.com/",
        host="api.vizuai.example",
        acquisition={
            "landing_host": "vizuai.example",
            "landing_path": "/?fbclid=test",
            "referrer": "https://facebook.com/",
        },
    )
    session.commit()

    @contextmanager
    def _fake_db_session():
        yield session

    monkeypatch.setattr("app_services.analytics.service.get_db_session", _fake_db_session)

    AnalyticsService()._record_event_sync(
        str(account.id),
        event_type="client_page_view",
        screen_key="home",
        source="frontend_app",
        meta={
            "anon_id": "anon-existing-session",
            "acquisition": {
                "landing_host": "vizuai.example",
                "landing_path": "/?fbclid=test",
            },
        },
    )

    session.expire_all()
    row = session.query(WebAcquisitionAttribution).filter_by(anon_id="anon-existing-session").first()
    assert row is not None
    assert row.account_id == account.id
    assert row.linked_at == now
