from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import SecretStr

from app.core.config import settings


def create_mail_client() -> FastMail:
    if not settings.MAIL_SERVER or not settings.MAIL_FROM:
        raise RuntimeError("이메일 설정이 구성되지 않았습니다. (MAIL_SERVER, MAIL_FROM 확인)")

    config = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=SecretStr(settings.MAIL_PASSWORD),
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_STARTTLS=settings.MAIL_STARTTLS,
        MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )
    return FastMail(config)


async def send_verification_email(email: str, code: str) -> None:
    message = MessageSchema(
        subject="[GEMBTI] 이메일 인증번호를 확인해 주세요",
        recipients=[email],
        body=f"인증번호는 {code}입니다. 5분 이내에 입력해 주세요.",
        subtype=MessageType.plain,
    )
    await create_mail_client().send_message(message)
