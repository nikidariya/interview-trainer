import pytest

from app.passwords import hash_password, normalize_username, verify_password


def test_argon_hashes_use_random_salt_and_verify_password_exactly():
    password = "  long password phrase  "
    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert first.startswith("$argon2id$")
    assert verify_password(first, password)
    assert not verify_password(first, password.strip())
    assert not verify_password(first, "wrong password phrase")
    assert not verify_password("corrupted", password)


@pytest.mark.parametrize("password", ["", "short", "a" * 129])
def test_registration_rejects_invalid_password_length(password):
    with pytest.raises(ValueError):
        hash_password(password)


def test_username_is_case_insensitive():
    assert normalize_username(" Alice_123 ") == "alice_123"


@pytest.mark.parametrize("username", ["ab", "a" * 33, "a b", "юзер", "';DROP TABLE users;"])
def test_invalid_usernames(username):
    with pytest.raises(ValueError):
        normalize_username(username)
