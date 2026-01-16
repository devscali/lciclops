"""
Modelos de Usuario - Little Caesars Reports
Aurelia: "Pydantic para validar todo, no confíes en nada que venga del frontend"
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


class UserPreferences(BaseModel):
    currency: str = "MXN"
    date_format: str = "DD/MM/YYYY"
    default_report_type: str = "pnl"


class UserBase(BaseModel):
    email: EmailStr
    display_name: str = Field(..., min_length=2, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    franchise_id: Optional[str] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=2, max_length=100)
    preferences: Optional[UserPreferences] = None


class UserInDB(UserBase):
    id: str
    role: UserRole = UserRole.USER
    franchise_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    preferences: UserPreferences = UserPreferences()


class UserResponse(UserBase):
    id: str
    role: UserRole
    franchise_id: Optional[str]
    preferences: UserPreferences

    class Config:
        from_attributes = True
