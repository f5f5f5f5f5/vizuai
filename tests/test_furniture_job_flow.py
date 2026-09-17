from types import SimpleNamespace
from uuid import uuid4

from app_services.history.service import _is_retry_eligible
from app_services.jobs.service import _design_record_draft_id
from models.job_model import Job


def test_design_record_draft_id_skips_furniture_jobs():
    job = Job(
        account_id=uuid4(),
        job_type="furniture_search",
        draft_id=uuid4(),
        draft_type="furniture_search",
        status="processing",
    )

    assert _design_record_draft_id(job) is None


def test_history_retry_eligible_uses_furniture_job_draft_link():
    design = SimpleNamespace(
        mode="furniture_search",
        draft=None,
        job=SimpleNamespace(draft_type="furniture_search", draft_id=uuid4()),
    )

    assert _is_retry_eligible(design) is True
