"""Password hashing for the admin users (bcrypt, used directly).

`passlib` (unmaintained since 2020) is replaced by calling `bcrypt`
directly, which lifts the `bcrypt<4.1` pin (TODO 7.5). Hashes made earlier
with `passlib` (`$2b$...`) stay valid: they are plain bcrypt hashes.
"""

import bcrypt


class PasswordHasher:
  """Hash and check passwords with bcrypt."""

  def hash(self, password: str) -> str:
    """Return the bcrypt hash of a password (up to 72 bytes)."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode(
      'ascii'
    )

  def verify(self, password: str, hashed: str) -> bool:
    """Return whether the password matches the hash.

    A password longer than 72 bytes or a malformed hash never matches.
    """
    try:
      return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('ascii'))
    except (ValueError, UnicodeError):
      return False


_hasher: PasswordHasher | None = None


def get_password_hasher() -> PasswordHasher:
  """Return the shared hasher."""
  global _hasher
  if _hasher is None:
    _hasher = PasswordHasher()
  return _hasher
