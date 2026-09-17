from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_

from models.design_model import Design
from utils.time import utcnow


class DesignRepository:
    def __init__(self, session) -> None:
        self.session = session

    def create_design(
        self,
        user_id: int | None,
        original_image_url: str,
        user_request: str,
        status: str = "pending",
        mode: str = "full",
        units_spent: int | None = None,
        account_id: UUID | None = None,
        job_id: UUID | None = None,
        draft_id: UUID | None = None,
        style_reference_image_url: str | None = None,
        style_reference_used: bool | None = None,
        style_reference_status: str | None = None,
    ) -> Design:
        design = Design(
            user_id=user_id,
            account_id=account_id,
            original_image_url=original_image_url,
            user_request=user_request,
            status=status,
            mode=mode,
            units_spent=units_spent,
            job_id=job_id,
            draft_id=draft_id,
            style_reference_image_url=style_reference_image_url,
            style_reference_used=bool(style_reference_used) if style_reference_used is not None else False,
            style_reference_status=style_reference_status,
        )
        self.session.add(design)
        self.session.commit()
        self.session.refresh(design)
        return design

    def set_result(
        self,
        design_id: UUID,
        final_image_url: str | None = None,
        status: str = "completed",
        duration_seconds: int | None = None,
        cost_usd: Decimal | float | None = None,
        error_message: str | None = None,
        selected_image: str | None = None,
        score_render: int | None = None,
        score_fix: int | None = None,
        providers_json: dict | None = None,
        debug_json: dict | None = None,
        metadata_json: dict | None = None,
        prepared_image_url: str | None = None,
        render_image_url: str | None = None,
        fix_image_url: str | None = None,
        style_reference_image_url: str | None = None,
        style_reference_used: bool | None = None,
        style_reference_status: str | None = None,
        error_stage: str | None = None,
        pipeline_version: str | None = None,
    ) -> Design | None:
        design = self.get_design(design_id)
        if design:
            if final_image_url is not None:
                design.final_image_url = final_image_url
            if prepared_image_url is not None:
                design.prepared_image_url = prepared_image_url
            if render_image_url is not None:
                design.render_image_url = render_image_url
            if fix_image_url is not None:
                design.fix_image_url = fix_image_url
            if style_reference_image_url is not None:
                design.style_reference_image_url = style_reference_image_url
            if style_reference_used is not None:
                design.style_reference_used = bool(style_reference_used)
            if style_reference_status is not None:
                design.style_reference_status = style_reference_status
            if selected_image is not None:
                design.selected_image = selected_image
            design.status = status
            design.ended_at = utcnow()
            if duration_seconds is not None:
                design.duration_seconds = duration_seconds
            if cost_usd is not None:
                design.cost_usd = cost_usd
            if error_message is not None:
                design.error_message = error_message
            if score_render is not None:
                design.score_render = score_render
            if score_fix is not None:
                design.score_fix = score_fix
            if providers_json is not None:
                design.providers_json = providers_json
            if debug_json is not None:
                design.debug_json = debug_json
            if metadata_json is not None:
                design.metadata_json = metadata_json
            if error_stage is not None:
                design.error_stage = error_stage
            if pipeline_version is not None:
                design.pipeline_version = pipeline_version
            self.session.commit()
            self.session.refresh(design)
        return design

    def get_design(self, design_id: UUID) -> Design | None:
        return self.session.query(Design).filter(Design.id == design_id).first()

    def get_by_job_id(self, job_id: UUID) -> Design | None:
        return self.session.query(Design).filter(Design.job_id == job_id).first()

    def get_account_design(self, account_id: UUID, design_id: UUID) -> Design | None:
        return (
            self.session.query(Design)
            .filter(Design.account_id == account_id, Design.id == design_id)
            .first()
        )

    def get_account_designs(self, account_id: UUID, limit: int = 50) -> list[Design]:
        return (
            self.session.query(Design)
            .filter(Design.account_id == account_id)
            .order_by(Design.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_account_designs_paginated(
        self,
        account_id: UUID,
        *,
        mode: str | None = None,
        status: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Design], int]:
        base_query = self.session.query(Design).filter(Design.account_id == account_id)

        if mode:
            base_query = base_query.filter(Design.mode == mode)
        if status:
            base_query = base_query.filter(Design.status == status)
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            base_query = base_query.filter(
                or_(
                    Design.user_request.ilike(pattern),
                    Design.error_message.ilike(pattern),
                )
            )

        total_items = base_query.count()
        items = (
            base_query.order_by(Design.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total_items

    def get_user_designs(self, user_id: int, limit: int = 20) -> list[Design]:
        return (
            self.session.query(Design)
            .filter(Design.user_id == user_id)
            .order_by(Design.created_at.desc())
            .limit(limit)
            .all()
        )
