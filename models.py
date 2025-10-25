from enum import Enum
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class Role(str, Enum):
    recruiter = "recruiter"
    candidate = "candidate"

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: Optional[str] = None
    role: Role

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserPublic(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: Role
    is_active: bool = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    sub: EmailStr
    role: Role
    exp: int
