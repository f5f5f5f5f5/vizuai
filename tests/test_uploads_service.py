from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app_services.uploads.service import UploadsService
from models.account_model import Account
from models.base import Base
from models.upload_intent_model import UploadIntent
from models.uploaded_file_model import UploadedFile
from utils.time import utcnow


def _build_session_factory(tmp_path):
    db_path = tmp_path / "uploads.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    @contextmanager
    def _session():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    return _session


class _FakeStorage:
    def __init__(self, metadata: dict | None):
        self._metadata = metadata

    def get_object_metadata(self, key: str) -> dict | None:
        return self._metadata

    def get_object_url(self, key: str) -> str:
        return f"https://cdn.example/{key}"


def _build_service(storage: _FakeStorage) -> UploadsService:
    service = object.__new__(UploadsService)
    service._storage = storage
    return service


def _seed_intent(session_factory):
    account_id = uuid4()
    upload_id = uuid4()
    with session_factory() as session:
        session.add(
            Account(
                id=account_id,
                status="active",
                primary_email="test@example.com",
                locale="ru",
            )
        )
        session.add(
            UploadIntent(
                id=upload_id,
                account_id=account_id,
                purpose="room_photo",
                filename="room.jpg",
                content_type="image/jpeg",
                size_bytes=123,
                storage_key="uploads/test/room.jpg",
                status="pending",
                expires_at=utcnow().replace(year=utcnow().year + 1),
            )
        )
        session.commit()
    return str(account_id), str(upload_id)


def test_complete_intent_rejects_missing_storage_object(tmp_path, monkeypatch):
    session_factory = _build_session_factory(tmp_path)
    monkeypatch.setattr("app_services.uploads.service.get_db_session", session_factory)
    account_id, upload_id = _seed_intent(session_factory)
    service = _build_service(_FakeStorage(metadata=None))

    result = service._complete_intent_sync(account_id, upload_id, "uploads/test/room.jpg")

    assert result["status"] == "storage_object_missing"
    with session_factory() as session:
        assert session.query(UploadedFile).count() == 0


def test_complete_intent_rejects_storage_size_mismatch(tmp_path, monkeypatch):
    session_factory = _build_session_factory(tmp_path)
    monkeypatch.setattr("app_services.uploads.service.get_db_session", session_factory)
    account_id, upload_id = _seed_intent(session_factory)
    service = _build_service(_FakeStorage(metadata={"size_bytes": 999, "content_type": "image/jpeg"}))

    result = service._complete_intent_sync(account_id, upload_id, "uploads/test/room.jpg")

    assert result["status"] == "storage_size_mismatch"
    with session_factory() as session:
        assert session.query(UploadedFile).count() == 0


def test_complete_intent_accepts_existing_matching_object(tmp_path, monkeypatch):
    session_factory = _build_session_factory(tmp_path)
    monkeypatch.setattr("app_services.uploads.service.get_db_session", session_factory)
    account_id, upload_id = _seed_intent(session_factory)
    service = _build_service(_FakeStorage(metadata={"size_bytes": 123, "content_type": "image/jpeg"}))

    result = service._complete_intent_sync(account_id, upload_id, "uploads/test/room.jpg")

    assert result["status"] == "ok"
    with session_factory() as session:
        assert session.query(UploadedFile).count() == 1
