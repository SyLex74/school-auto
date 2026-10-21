"""Private HTTP API consumed by the VK bot."""

from ..legacy_views import (
    api_cities,
    api_mark_notified,
    api_pending_changes,
    api_regions,
    api_schools,
    api_schedules_by_school,
    api_subscribers,
    api_vk_user_detail,
)

__all__ = [
    'api_cities', 'api_mark_notified', 'api_pending_changes', 'api_regions',
    'api_schools', 'api_schedules_by_school', 'api_subscribers',
    'api_vk_user_detail',
]
