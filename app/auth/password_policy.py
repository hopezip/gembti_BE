import re


def join_korean_words(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)

    conjunction = "과" if has_final_consonant(words[-2]) else "와"
    return f"{', '.join(words[:-1])}{conjunction} {words[-1]}"


def has_final_consonant(word: str) -> bool:
    last_char_code = ord(word[-1])
    return 0xAC00 <= last_char_code <= 0xD7A3 and (last_char_code - 0xAC00) % 28 != 0


def get_missing_password_policy_parts(password: str) -> list[str]:
    missing_parts = []

    if not re.search(r"[A-Za-z]", password):
        missing_parts.append("영문")
    if not re.search(r"\d", password):
        missing_parts.append("숫자")
    if not re.search(r"[^A-Za-z0-9]", password):
        missing_parts.append("특수문자")

    return missing_parts


def validate_password_policy(password: str) -> None:
    missing_parts = get_missing_password_policy_parts(password)

    if missing_parts:
        raise ValueError(f"비밀번호에는 {join_korean_words(missing_parts)}가 포함되어야 합니다.")
