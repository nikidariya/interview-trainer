"""Хеширование паролей Argon2id и правила локальных учётных записей."""
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def normalize_username(username: str) -> str:
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username):
        raise ValueError("Логин: от 3 до 32 символов — латинские буквы, цифры, _, . или -.")
    return username


def hash_password(password: str) -> str:
    if not 8 <= len(password) <= 128:
        raise ValueError("Пароль должен содержать от 8 до 128 символов.")
    return hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not 1 <= len(password) <= 128:
        return False
    try:
        return hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False
