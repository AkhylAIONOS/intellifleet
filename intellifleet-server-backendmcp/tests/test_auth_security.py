from datetime import timedelta
import json

import jwt
import pytest

from backend.core.security import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_password_hash,
    verify_password,
)
from backend.models.userSchema import LoginRequest, UserCreate
from backend.routes import auth


def test_password_is_hashed_and_verifiable():
    password = "temporary-test-value"
    stored = get_password_hash(password)
    assert stored != password
    assert verify_password(password, stored)
    assert not verify_password("incorrect-value", stored)


def test_access_token_expiration_is_enforced():
    token = create_access_token({"user_id": 987654}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


@pytest.mark.asyncio
async def test_first_time_signup_verification_and_login(monkeypatch):
    sent = {}
    created = {}
    monkeypatch.setattr(auth, "get_user_by_email", lambda _email: None)
    async def capture_email(**kwargs):
        sent.update(kwargs)
    monkeypatch.setattr(auth, "send_email", capture_email)

    signup = await auth.create_user_endpoint(UserCreate(
        first_name="New", last_name="User", email="new.user@example.com",
        password="temporary-test-value",
    ))
    assert json.loads(signup.body)["success"] is True
    verification_token = sent["body"].split("token=", 1)[1].splitlines()[0]
    monkeypatch.setattr(auth, "create_user", lambda data: created.update(data))
    await auth.verify_email(verification_token)
    assert created["password"] != "temporary-test-value"
    assert verify_password("temporary-test-value", created["password"])

    user = {"id": 999, **created}
    monkeypatch.setattr(auth, "get_user_by_email", lambda _email: user)
    login = await auth.login_for_access_token(LoginRequest(
        email="new.user@example.com", password="temporary-test-value"
    ))
    body = json.loads(login.body)
    assert body["success"] is True
    assert body["data"]["first_name"] == "New"
    jwt.decode(body["data"]["token"], SECRET_KEY, algorithms=[ALGORITHM])
