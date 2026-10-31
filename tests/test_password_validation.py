"""Test password validation for admin views."""

import pytest

from fastapi_blog.admin.passwords import get_password_hasher
from fastapi_blog.admin.views import (
  BCRYPT_MAX_BYTES,
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  validate_and_prepare_password,
)


def test_password_min_length():
  """Test password minimum length validation."""
  # Too short
  with pytest.raises(ValueError, match='Password is too short'):
    validate_and_prepare_password('short')

  # Error should include current and minimum length
  with pytest.raises(ValueError, match='Minimum length: 8'):
    validate_and_prepare_password('abc')

  with pytest.raises(ValueError, match='Current length: 3'):
    validate_and_prepare_password('abc')

  # Exactly min length - should work
  password = 'a' * MIN_PASSWORD_LENGTH
  assert validate_and_prepare_password(password) == password


def test_password_max_length():
  """Test password maximum length validation."""
  # Too long
  with pytest.raises(ValueError, match='Password is too long'):
    validate_and_prepare_password('x' * (MAX_PASSWORD_LENGTH + 1))

  # Error should include current and maximum length
  with pytest.raises(ValueError, match='Maximum length: 128'):
    validate_and_prepare_password('x' * 200)

  with pytest.raises(ValueError, match='Current length: 200'):
    validate_and_prepare_password('x' * 200)


def test_password_valid_range():
  """Test passwords within valid range."""
  # Short valid password
  assert validate_and_prepare_password('Password1') == 'Password1'

  # Medium password
  password = 'MySecurePassword123!'
  assert validate_and_prepare_password(password) == password

  # Long but valid password
  password = 'a' * 50
  assert validate_and_prepare_password(password) == password


def test_password_bcrypt_byte_limit():
  """Test that passwords exceeding 72 bytes are rejected."""
  # Password exactly at bcrypt limit (72 ASCII chars = 72 bytes)
  password_72 = 'a' * BCRYPT_MAX_BYTES
  result = validate_and_prepare_password(password_72)
  assert result == password_72

  # Password over bcrypt limit should be rejected
  password_100 = 'a' * 100  # 100 bytes
  with pytest.raises(ValueError, match='exceeds bcrypt limit'):
    validate_and_prepare_password(password_100)

  # Error should mention byte size
  with pytest.raises(ValueError, match='72 bytes'):
    validate_and_prepare_password('a' * 100)

  with pytest.raises(ValueError, match='Current size: 100 bytes'):
    validate_and_prepare_password('a' * 100)


def test_password_unicode_handling():
  """Test password with unicode characters."""
  # Unicode password within limits
  password = 'Пароль123!'  # Russian + numbers
  result = validate_and_prepare_password(password)
  assert result == password

  # Unicode password that fits in 72 bytes
  password = 'й' * 30  # 30 chars * 2 bytes = 60 bytes
  result = validate_and_prepare_password(password)
  assert result == password

  # Unicode password exceeding 72 bytes should be rejected
  password = 'й' * 50  # 50 chars * 2 bytes = 100 bytes
  with pytest.raises(ValueError, match='exceeds bcrypt limit'):
    validate_and_prepare_password(password)

  # Error should include helpful tip
  with pytest.raises(
    ValueError, match='Unicode characters take multiple bytes'
  ):
    validate_and_prepare_password('й' * 50)


def test_password_empty():
  """Test empty password validation."""
  with pytest.raises(ValueError, match='Password is too short'):
    validate_and_prepare_password('')


def test_password_error_messages():
  """Test that error messages are helpful and specific."""
  # Too short - should explain the issue clearly
  try:
    validate_and_prepare_password('abc')
    assert False, 'Should have raised ValueError'
  except ValueError as e:
    error_msg = str(e)
    assert 'too short' in error_msg.lower()
    assert '8' in error_msg
    assert '3' in error_msg

  # Too long - should explain the issue clearly
  try:
    validate_and_prepare_password('x' * 150)
    assert False, 'Should have raised ValueError'
  except ValueError as e:
    error_msg = str(e)
    assert 'too long' in error_msg.lower()
    assert '128' in error_msg
    assert '150' in error_msg

  # Byte limit - should explain Unicode issue
  try:
    validate_and_prepare_password('ф' * 50)  # 100 bytes
    assert False, 'Should have raised ValueError'
  except ValueError as e:
    error_msg = str(e)
    assert 'bcrypt' in error_msg.lower()
    assert '72 bytes' in error_msg
    assert 'unicode' in error_msg.lower()


def test_password_constants():
  """Verify password constants are reasonable."""
  assert MIN_PASSWORD_LENGTH == 8
  assert MAX_PASSWORD_LENGTH == 128
  assert BCRYPT_MAX_BYTES == 72
  assert MIN_PASSWORD_LENGTH < BCRYPT_MAX_BYTES < MAX_PASSWORD_LENGTH


# --- PasswordHasher (TODO 7.5: `passlib` replaced by direct `bcrypt`) ---------


def test_password_hasher_round_trip():
  hasher = get_password_hasher()
  hashed = hasher.hash('correct horse battery staple')
  assert hashed.startswith('$2b$')
  assert hasher.verify('correct horse battery staple', hashed)
  assert not hasher.verify('wrong password', hashed)


def test_password_hasher_accepts_legacy_passlib_hashes():
  """Passlib produced plain `$2b$` bcrypt hashes; they stay valid (7.5)."""
  legacy = '$2b$12$SWoHzbu1rn0TItH36PNIRetjtCNdibSp59o/E/tJV4FD4ANg535ey'
  assert get_password_hasher().verify('legacy-password', legacy)
  assert not get_password_hasher().verify('other-password', legacy)


def test_password_hasher_never_matches_bad_input():
  hasher = get_password_hasher()
  hashed = hasher.hash('short-password')
  # More than 72 bytes never matches (bcrypt 5 raises; we answer False).
  assert not hasher.verify('x' * 100, hashed)
  # Malformed hashes never match either.
  assert not hasher.verify('short-password', 'not-a-bcrypt-hash')
