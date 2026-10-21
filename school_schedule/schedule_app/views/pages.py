"""Page and health-check views."""

from ..legacy_views import (
    auto_schedule_view,
    choice_view,
    custom_403,
    custom_404,
    custom_500,
    healthz,
    index,
    profile_edit_view,
    profile_view,
    schedule_view,
    upload_schedule_view,
)

__all__ = [
    'auto_schedule_view', 'choice_view', 'custom_403', 'custom_404',
    'custom_500', 'healthz', 'index', 'profile_edit_view', 'profile_view',
    'schedule_view', 'upload_schedule_view',
]
