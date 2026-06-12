from typing import List, Optional

from pydantic import BaseModel


# ── auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class PermissionItem(BaseModel):
    menu_id: int
    sub_id: Optional[int] = None


class PharmacyBrief(BaseModel):
    id: int
    name: str
    code: Optional[str] = None


class UserInfo(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    role: str
    pharmacy: Optional[PharmacyBrief] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
    permissions: List[PermissionItem] = []


class MeResponse(BaseModel):
    user: UserInfo
    permissions: List[PermissionItem] = []


class LogAccessRequest(BaseModel):
    menu_id: int
    sub_id: Optional[int] = None


# ── admin: pharmacies ───────────────────────────────────────────────────────────

class PharmacyCreate(BaseModel):
    name: str
    code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None


class PharmacyUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class PharmacyResponse(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool
    user_count: int = 0

    class Config:
        from_attributes = True


# ── admin: users ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    permissions: List[PermissionItem] = []


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    pharmacy_id: Optional[int] = None
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class PermissionsUpdate(BaseModel):
    permissions: List[PermissionItem] = []
