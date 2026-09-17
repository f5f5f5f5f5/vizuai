from models.schemas import Job
from services.redis_client import LocalRuntimeStateClient


def test_local_runtime_state_client_tracks_jobs_debug_and_update_dedupe() -> None:
    client = LocalRuntimeStateClient()
    job = Job(job_id="job-1", chat_id=0, status="queued")

    client.store_job(job)
    client.store_debug(job.job_id, {"stage": "test"})

    assert client.get_job(job.job_id) == job
    assert client.get_debug(job.job_id) == {"stage": "test"}
    assert client.mark_update_seen(123) is True
    assert client.mark_update_seen(123) is False


def test_local_runtime_state_client_enforces_process_local_job_limit() -> None:
    client = LocalRuntimeStateClient()

    assert client.try_acquire_global_job_slot("job-1", limit=1, lease_seconds=60) is True
    assert client.try_acquire_global_job_slot("job-2", limit=1, lease_seconds=60) is False
    assert client.get_global_active_job_count() == 1

    client.release_global_job_slot("job-1")

    assert client.try_acquire_global_job_slot("job-2", limit=1, lease_seconds=60) is True
