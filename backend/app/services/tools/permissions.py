from typing import Sequence
from app.core.logging import logger


ROLE_HIERARCHY = {
    "VIEWER": 1,
    "MEMBER": 2,
    "MANAGER": 3,
    "ADMIN": 4,
    "OWNER": 5,
}


class ToolPermissionError(Exception):
    """Raised when a user role is not authorized to execute a tool."""
    pass


class ToolPermissionChecker:
    """Evaluates whether an authenticated user role satisfies tool authorization constraints."""

    @staticmethod
    def is_authorized(user_role: str, required_roles: Sequence[str]) -> bool:
        normalized_role = user_role.upper().strip()
        normalized_required = [r.upper().strip() for r in required_roles]

        # Explicit inclusion check
        if normalized_role in normalized_required:
            return True

        # Fallback role hierarchy check (if user has higher role than minimum required)
        min_required_level = min(
            (ROLE_HIERARCHY.get(r, 99) for r in normalized_required),
            default=99,
        )
        user_level = ROLE_HIERARCHY.get(normalized_role, 0)
        return user_level >= min_required_level

    @classmethod
    def verify_permission(cls, tool_name: str, user_role: str, required_roles: Sequence[str]) -> None:
        if not cls.is_authorized(user_role, required_roles):
            logger.warning(
                f"Tool authorization denied: tool='{tool_name}', user_role='{user_role}', required={required_roles}"
            )
            raise ToolPermissionError(
                f"Role '{user_role}' is not authorized to execute tool '{tool_name}'. Required roles: {list(required_roles)}"
            )
