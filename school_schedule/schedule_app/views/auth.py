"""Authentication and account views."""

from ..legacy_views import (
    auth_view,
    logout_view,
    resend_verification_code,
    verify_email_view,
)

__all__ = [
    'auth_view', 'logout_view', 'resend_verification_code',
    'verify_email_view',
]
