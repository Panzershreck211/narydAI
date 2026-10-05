from pydantic import BaseModel, Field

from app.schemas.user import UserOut


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class PinLoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=50)
    pin: str = Field(pattern=r"^\d{4,6}$")


class RefreshRequest(BaseModel):
    refresh_token: str


class SetPinRequest(BaseModel):
    pin: str = Field(pattern=r"^\d{4,6}$")
    password: str = Field(description="Текущий пароль для подтверждения")


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
