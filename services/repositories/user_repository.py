from datetime import datetime

from utils.time import utcnow

from models.user_model import User


class UserRepository:
    def __init__(self, session) -> None:
        self.session = session

    def get_user(self, user_id: int) -> User | None:
        return self.session.query(User).filter(User.user_id == user_id).first()

    def get_or_create(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        user = self.get_user(user_id)
        if user:
            return user

        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def set_whitelist(self, user_id: int, is_active: bool) -> User | None:
        user = self.get_user(user_id)
        if user:
            user.is_active = is_active
            self.session.commit()
            self.session.refresh(user)
        return user

    def increment_usage(self, user_id: int) -> User | None:
        user = self.get_user(user_id)
        if user:
            user.usage_count += 1
            self.session.commit()
            self.session.refresh(user)
        return user

    def set_last_request(self, user_id: int, when: datetime | None = None) -> User | None:
        if when is None:
            when = utcnow()
        user = self.get_user(user_id)
        if user:
            user.last_request_at = when
            self.session.commit()
            self.session.refresh(user)
        return user

    def is_whitelisted(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        return user.is_active if user else False
