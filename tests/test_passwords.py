import pytest

from app.passwords import hash_password, normalize_username, verify_password


def test_argon_hashes_use_random_salt_and_verify_password_exactly():
    password = "LongPassword123"
    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert first.startswith("$argon2id$")
    assert verify_password(first, password)
    assert not verify_password(first, " " + password)
    assert not verify_password(first, password.upper())
    assert not verify_password(first, "wrong password phrase")
    assert not verify_password("corrupted", password)


@pytest.mark.parametrize("password", ["", "short", "a" * 129, "Password.123", "Password_123", "Password-123", "Password 123", "Пароль123", "Password!123"])
def test_registration_rejects_invalid_password(password):
    with pytest.raises(ValueError):
        hash_password(password)


def test_username_is_case_sensitive():
    assert normalize_username(" Alice123 ") == "Alice123"
    assert normalize_username("Alice") != normalize_username("alice")


@pytest.mark.parametrize("username", ["ab", "a" * 33, "a b", "юзер", "';DROP TABLE users;", "Alice.123", "Alice_123", "Alice-123"])
def test_invalid_usernames(username):
    with pytest.raises(ValueError):
        normalize_username(username)
