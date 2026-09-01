from pydantic import BaseModel, EmailStr
from typing import Any, Dict, List, Optional, Union

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str