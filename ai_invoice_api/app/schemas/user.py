from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# ── Register ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name:         str
    company_name: str
    email:        EmailStr
    password:     str


class UserDetails(BaseModel):
    name:         str
    company_name: str
    email:        str


class RegisterResponse(BaseModel):
    status:      int
    message:     str
    userdetails: UserDetails


# ── Login ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class LoginResponse(BaseModel):
    status:  int
    message: str
    token:   str


class LogoutResponse(BaseModel):
    status:  int
    message: str


# ── User Profile ──────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    id:            int
    name:          str
    email:         str
    company_name:  str
    gst_number:    Optional[str] = None
    address:       Optional[str] = None
    mobile_number: Optional[str] = None


class ProfileResponse(BaseModel):
    status:      int
    message:     str
    userdetails: UserProfile


class AllUsersResponse(BaseModel):
    status:  int
    message: str
    users:   List[UserProfile]


class UpdateProfileRequest(BaseModel):
    name:          Optional[str] = None
    email:         Optional[EmailStr] = None
    company_name:  Optional[str] = None
    gst_number:    Optional[str] = None
    address:       Optional[str] = None
    mobile_number: Optional[str] = None
