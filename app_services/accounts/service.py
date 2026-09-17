"""Accounts application service."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func

from models.account_model import Account
from models.design_model import Design
from models.job_model import Job
from services.db_connection import get_db_session


def _serialize_account(account: Account) -> dict:
    return {
        "id": str(account.id),
        "email": account.primary_email,
        "display_name": account.display_name,
        "locale": account.locale,
        "timezone": account.timezone,
        "marketing_opt_in": bool(account.marketing_opt_in),
        "created_at": account.created_at,
        "last_seen_at": account.last_seen_at,
    }


class AccountsService:
    async def get_account(self, account_id: str) -> dict | None:
        with get_db_session() as session:
            account = session.query(Account).filter(Account.id == UUID(account_id)).first()
            if account is None:
                return None
            return _serialize_account(account)

    async def update_account(self, account_id: str, payload: dict) -> dict | None:
        with get_db_session() as session:
            account = session.query(Account).filter(Account.id == UUID(account_id)).first()
            if account is None:
                return None

            display_name = payload.get("display_name")
            if display_name is not None:
                normalized_name = str(display_name).strip()
                account.display_name = normalized_name[:128] or None

            locale = payload.get("locale")
            if locale is not None:
                normalized_locale = str(locale).strip().lower()
                account.locale = normalized_locale[:16] or None

            timezone = payload.get("timezone")
            if timezone is not None:
                normalized_timezone = str(timezone).strip()
                account.timezone = normalized_timezone[:64] or None

            session.commit()
            session.refresh(account)
            return _serialize_account(account)

    async def get_usage(self, account_id: str) -> dict:
        with get_db_session() as session:
            account_uuid = UUID(account_id)
            total_runs = (
                session.query(func.count(Job.id))
                .filter(Job.account_id == account_uuid)
                .scalar()
                or 0
            )
            completed_runs = (
                session.query(func.count(Job.id))
                .filter(
                    Job.account_id == account_uuid,
                    Job.status == "completed",
                )
                .scalar()
                or 0
            )
            failed_runs = (
                session.query(func.count(Job.id))
                .filter(
                    Job.account_id == account_uuid,
                    Job.status == "failed",
                )
                .scalar()
                or 0
            )
            design_runs = (
                session.query(func.count(Job.id))
                .filter(
                    Job.account_id == account_uuid,
                    Job.job_type == "design",
                )
                .scalar()
                or 0
            )
            furniture_runs = (
                session.query(func.count(Job.id))
                .filter(
                    Job.account_id == account_uuid,
                    Job.job_type == "furniture_search",
                )
                .scalar()
                or 0
            )
            credits_spent = (
                session.query(func.coalesce(func.sum(Design.units_spent), 0))
                .filter(Design.account_id == account_uuid)
                .scalar()
                or 0
            )

            return {
                "total_runs": int(total_runs),
                "completed_runs": int(completed_runs),
                "failed_runs": int(failed_runs),
                "design_runs": int(design_runs),
                "furniture_runs": int(furniture_runs),
                "credits_spent": int(credits_spent),
            }
