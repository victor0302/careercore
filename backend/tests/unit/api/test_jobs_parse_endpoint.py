import pytest
from fastapi import HTTPException

from app.ai.exceptions import BudgetExceededError
from app.api.v1.endpoints.jobs import parse_job


async def test_parse_job_maps_budget_exceeded_to_429(db, mock_user, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise_budget(self, user_id, job_id):
        raise BudgetExceededError(str(user_id), budget=50_000, used=50_000)

    monkeypatch.setattr("app.api.v1.endpoints.jobs.JobService.parse", _raise_budget)

    with pytest.raises(HTTPException) as exc_info:
        await parse_job(job_id="00000000-0000-0000-0000-000000000001", current_user=mock_user, db=db, ai=None)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "Daily AI token budget exceeded."
