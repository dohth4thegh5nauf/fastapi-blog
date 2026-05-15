"""Role management models for admin panel."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base


# Association table for many-to-many relationship between users and roles
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users_with_roles.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class Role(Base):
    """Role model for role-based access control.

    Attributes:
      id: Primary key
      name: Role name (e.g. 'admin', 'editor', 'viewer')
      description: Role description
      is_active: Whether role is active
      created_at: Creation timestamp
      updated_at: Last update timestamp
      users: Users with this role

    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=datetime.utcnow, nullable=True
    )

    # Relationship to users (many-to-many)
    users: Mapped[list["UserWithRoles"]] = relationship(
        "UserWithRoles",
        secondary=user_roles,
        back_populates="roles",
    )

    def __repr__(self) -> str:
        return f'<Role(id={self.id}, name="{self.name}")>'


# Extended User model with roles support
class UserWithRoles(Base):
    """Extended User model with role-based access control.

    This is an alternative to the basic User model that includes role management.

    Attributes:
      id: Primary key
      email: User email (unique)
      hashed_password: Bcrypt hashed password
      is_active: Whether user is active
      created_at: Creation timestamp
      updated_at: Last update timestamp
      roles: List of roles assigned to user

    """

    __tablename__ = "users_with_roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=datetime.utcnow, nullable=True
    )

    # Relationship to roles (many-to-many)
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
    )

    def __repr__(self) -> str:
        role_names = [role.name for role in self.roles]
        return (
            f'<UserWithRoles(id={self.id}, email="{self.email}", roles={role_names})>'
        )

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role.

        Args:
          role_name: Name of the role to check

        Returns:
          True if user has the role, False otherwise

        """
        return any(role.name == role_name for role in self.roles)

    def has_any_role(self, *role_names: str) -> bool:
        """Check if user has any of the specified roles.

        Args:
          *role_names: Names of roles to check

        Returns:
          True if user has at least one of the roles, False otherwise

        """
        return any(self.has_role(name) for name in role_names)


# Convenience function to create default roles
async def create_default_roles(session) -> None:
    """Create default roles if they don't exist.

    Creates three default roles:
    - admin: Full access to all features
    - editor: Can create and edit content
    - viewer: Read-only access

    Args:
      session: SQLAlchemy async session

    """
    from sqlalchemy import select

    # Check if roles already exist
    result = await session.execute(select(Role))
    existing_roles = result.scalars().all()

    if existing_roles:
        return  # Roles already exist

    # Create default roles
    admin_role = Role(
        name="admin",
        description="Administrator with full access",
        is_active=True,
    )
    editor_role = Role(
        name="editor",
        description="Editor who can create and edit content",
        is_active=True,
    )
    viewer_role = Role(
        name="viewer",
        description="Viewer with read-only access",
        is_active=True,
    )

    session.add_all([admin_role, editor_role, viewer_role])
    await session.commit()
