"""Pydantic schemas for User endpoints."""

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(ch.islower() for ch in value):
            raise ValueError("Password must include at least one lowercase letter.")
        if not any(ch.isupper() for ch in value):
            raise ValueError("Password must include at least one uppercase letter.")
        if not any(ch.isdigit() for ch in value):
            raise ValueError("Password must include at least one number.")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
