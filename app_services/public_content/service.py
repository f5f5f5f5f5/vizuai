"""Public content service scaffold."""
from __future__ import annotations


class PublicContentService:
    async def get_examples(self) -> list[dict]:
        raise NotImplementedError

    async def get_pricing(self) -> list[dict]:
        raise NotImplementedError

    async def get_faq(self) -> list[dict]:
        raise NotImplementedError
