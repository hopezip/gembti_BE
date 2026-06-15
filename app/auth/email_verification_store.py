import hashlib
import hmac
from typing import Any, cast

from app.auth.models import EmailVerificationPurpose
from app.core.config import settings
from app.core.enums import RedisPurpose
from app.core.redis import get_redis

EMAIL_CODE_PREFIX = "auth:email:code"
EMAIL_PREVIOUS_CODE_PREFIX = "auth:email:code:previous"
EMAIL_VERIFIED_PREFIX = "auth:email:verified"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def code_key(email: str, purpose: EmailVerificationPurpose) -> str:
    return f"{EMAIL_CODE_PREFIX}:{purpose.value}:{normalize_email(email)}"


def previous_code_key(email: str, purpose: EmailVerificationPurpose) -> str:
    return f"{EMAIL_PREVIOUS_CODE_PREFIX}:{purpose.value}:{normalize_email(email)}"


def verified_key(email: str, purpose: EmailVerificationPurpose) -> str:
    return f"{EMAIL_VERIFIED_PREFIX}:{purpose.value}:{normalize_email(email)}"


def hash_verification_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


async def save_verification_code(
    email: str,
    purpose: EmailVerificationPurpose,
    code: str,
) -> None:
    redis = cast("Any", await get_redis(RedisPurpose.EMAIL))
    current_key = code_key(email, purpose)
    current_hash = await redis.get(current_key)
    if isinstance(current_hash, str):
        await redis.set(
            previous_code_key(email, purpose),
            current_hash,
            ex=settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS,
        )

    await redis.set(
        current_key,
        hash_verification_code(code),
        ex=settings.EMAIL_VERIFICATION_CODE_TTL_SECONDS,
    )


async def delete_verification_code(
    email: str,
    purpose: EmailVerificationPurpose,
) -> None:
    redis = cast("Any", await get_redis(RedisPurpose.EMAIL))
    await redis.delete(code_key(email, purpose), previous_code_key(email, purpose))


async def verify_email_code(
    email: str,
    purpose: EmailVerificationPurpose,
    code: str,
) -> bool:
    redis = cast("Any", await get_redis(RedisPurpose.EMAIL))
    saved_hash = await redis.get(code_key(email, purpose))
    previous_hash = await redis.get(previous_code_key(email, purpose))
    candidate_hashes = [
        hash_value for hash_value in (saved_hash, previous_hash) if isinstance(hash_value, str)
    ]
    if not candidate_hashes:
        return False

    code_hash = hash_verification_code(code)
    if not any(hmac.compare_digest(saved_hash, code_hash) for saved_hash in candidate_hashes):
        return False

    await redis.set(
        verified_key(email, purpose),
        "1",
        ex=settings.EMAIL_VERIFIED_TTL_SECONDS,
    )
    await redis.delete(code_key(email, purpose), previous_code_key(email, purpose))
    return True


async def consume_verified_email(
    email: str,
    purpose: EmailVerificationPurpose,
) -> bool:
    redis = cast("Any", await get_redis(RedisPurpose.EMAIL))
    return bool(await redis.getdel(verified_key(email, purpose)))
