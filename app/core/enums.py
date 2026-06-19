from enum import StrEnum


class RedisPurpose(StrEnum):
    AUTH = "auth"
    EMAIL = "email"
    STEAM = "steam"
    SUPPORT = "support"


class LoginProvider(StrEnum):
    EMAIL = "email"
    STEAM = "steam"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]
