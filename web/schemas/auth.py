"""Auth-related Pydantic schemas."""

from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: int  # user_id
    exp: int


class UserInfo(BaseModel):
    id: int
    x_username: str
    x_display_name: str | None = None
    email: str | None = None
    is_active: bool = True
