from datetime import timedelta

from jose import JWTError
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPassword:
    def test_hash_is_not_plain(self):
        assert hash_password("secret") != "secret"

    def test_verify_correct(self):
        hashed = hash_password("my_password")
        assert verify_password("my_password", hashed) is True

    def test_verify_wrong(self):
        hashed = hash_password("my_password")
        assert verify_password("wrong", hashed) is False

    def test_same_password_different_hash(self):
        h1 = hash_password("pw")
        h2 = hash_password("pw")
        assert h1 != h2  # bcrypt salt


class TestAccessToken:
    def test_create_and_decode(self):
        token = create_access_token(subject=42)
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["type"] == "access"

    def test_string_subject(self):
        token = create_access_token(subject="user-uuid")
        payload = decode_token(token)
        assert payload["sub"] == "user-uuid"

    def test_custom_expiry(self):
        token = create_access_token(subject=1, expires_delta=timedelta(minutes=5))
        payload = decode_token(token)
        assert payload["sub"] == "1"

    def test_provider_is_optional_claim(self):
        token = create_access_token(subject=1, provider="email")
        payload = decode_token(token)
        assert payload["provider"] == "email"

    def test_jti_is_created(self):
        token = create_access_token(subject=1)
        payload = decode_token(token)
        assert isinstance(payload["jti"], str)

    def test_numeric_date_claims_are_integers(self):
        token = create_access_token(subject=1)
        payload = decode_token(token)
        assert isinstance(payload["iat"], int)
        assert isinstance(payload["exp"], int)

    def test_expired_token_raises(self):
        token = create_access_token(subject=1, expires_delta=timedelta(seconds=-1))
        with pytest.raises(JWTError):
            decode_token(token)


class TestRefreshToken:
    def test_create_and_decode(self):
        token = create_refresh_token(subject=42)
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["type"] == "refresh"

    def test_access_and_refresh_are_different(self):
        access = create_access_token(subject=1)
        refresh = create_refresh_token(subject=1)
        assert access != refresh

    def test_provider_is_optional_claim(self):
        token = create_refresh_token(subject=1, provider="email")
        payload = decode_token(token)
        assert payload["provider"] == "email"

    def test_jti_is_created(self):
        token = create_refresh_token(subject=1)
        payload = decode_token(token)
        assert isinstance(payload["jti"], str)

    def test_numeric_date_claims_are_integers(self):
        token = create_refresh_token(subject=1)
        payload = decode_token(token)
        assert isinstance(payload["iat"], int)
        assert isinstance(payload["exp"], int)

    def test_expired_token_raises(self):
        token = create_refresh_token(subject=1, expires_delta=timedelta(seconds=-1))
        with pytest.raises(JWTError):
            decode_token(token)
