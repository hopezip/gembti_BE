import hashlib
import hmac
from typing import Any, cast

from app.auth.models import EmailVerificationPurpose
from app.core.config import settings
from app.core.redis import get_redis

EMAIL_CODE_PREFIX = "auth:email:code"
EMAIL_VERIFIED_PREFIX = "auth:email:verified"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def code_key(email: str, purpose: EmailVerificationPurpose) -> str:
    return f"{EMAIL_CODE_PREFIX}:{purpose.value}:{normalize_email(email)}"


def verified_key(email: str, purpose: EmailVerificationPurpose) -> str:
    return f"{EMAIL_VERIFIED_PREFIX}:{purpose.value}:{normalize_email(email)}"


def hash_verification_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


async def save_verification_code(
    email: str,
    purpose: EmailVerificationPurpose,
    code: str,
) -> None:
    redis = cast("Any", await get_redis())
    await redis.set(
        code_key(email, purpose),
        hash_verification_code(code),
        ex=settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS,
    )


async def delete_verification_code(
    email: str,
    purpose: EmailVerificationPurpose,
) -> None:
    redis = cast("Any", await get_redis())
    await redis.delete(code_key(email, purpose))


async def verify_email_code(
    email: str,
    purpose: EmailVerificationPurpose,
    code: str,
) -> bool:
    redis = cast("Any", await get_redis())
    saved_hash = await redis.get(code_key(email, purpose))
    if not isinstance(saved_hash, str):
        return False

    if not hmac.compare_digest(saved_hash, hash_verification_code(code)):
        return False

    await redis.set(
        verified_key(email, purpose),
        "1",
        ex=settings.EMAIL_VERIFIED_TTL_SECONDS,
    )
    await redis.delete(code_key(email, purpose))
    return True


async def consume_verified_email(
    email: str,
    purpose: EmailVerificationPurpose,
) -> bool:
    redis = cast("Any", await get_redis())
    return bool(await redis.getdel(verified_key(email, purpose)))
