from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from services.repositories.design_repository import DesignRepository
from services.repositories.user_repository import UserRepository
from utils.time import utcnow


def _build_session_factory(tmp_path):
    db_path = tmp_path / "repo.db"
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


def test_user_repository_crud(tmp_path):
    session_factory = _build_session_factory(tmp_path)
    with session_factory() as session:
        repo = UserRepository(session)
        user = repo.get_or_create(1001, username="tester", first_name="Test")
        assert user.user_id == 1001

        fetched = repo.get_user(1001)
        assert fetched.username == "tester"

        repo.set_whitelist(1001, True)
        assert repo.is_whitelisted(1001) is True

        repo.increment_usage(1001)
        repo.set_last_request(1001, utcnow())
        updated = repo.get_user(1001)
        assert updated.usage_count == 1


def test_design_repository_crud(tmp_path):
    session_factory = _build_session_factory(tmp_path)
    with session_factory() as session:
        design_repo = DesignRepository(session)
        user_repo = UserRepository(session)
        user_repo.get_or_create(2001, username="testuser")

        design = design_repo.create_design(
            user_id=2001,
            original_image_url="https://example.com/original.jpg",
            user_request="test request",
        )
        assert design.user_id == 2001

        fetched = design_repo.get_design(design.id)
        assert fetched is not None
        assert fetched.user_request == "test request"

        updated = design_repo.set_result(
            design_id=design.id,
            final_image_url="https://example.com/design.jpg",
            selected_image="render",
            score_render=87,
            score_fix=76,
            providers_json={"planner": "gpt-5.2"},
            debug_json={"note": "ok"},
            duration_seconds=12,
            cost_usd=1.5,
        )
        assert updated.status == "completed"
        assert updated.duration_seconds == 12

        designs = design_repo.get_user_designs(2001)
        assert len(designs) == 1
