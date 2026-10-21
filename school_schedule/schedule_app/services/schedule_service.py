"""Business operations related to schedule changes and cache invalidation."""

from django.core.cache import cache
from django.utils import timezone

from ..models import ScheduleChange


def log_schedule_change(user, day, change_type, class_name=''):
    profile = getattr(user, 'profile', None)
    if not profile or not profile.school_id:
        return

    threshold = timezone.now() - timezone.timedelta(minutes=5)
    duplicate = ScheduleChange.objects.filter(
        school=profile.school,
        class_name=class_name or '',
        day=day,
        change_type=change_type,
        notified=False,
        created_at__gte=threshold,
    ).exists()
    if not duplicate:
        ScheduleChange.objects.create(
            school=profile.school,
            class_name=class_name or '',
            day=day,
            change_type=change_type,
        )


def invalidate_school_cache(user):
    profile = getattr(user, 'profile', None)
    if profile and profile.school_id:
        cache.delete(f'schedule_school_{profile.school_id}')


def diff_changed_classes(old_data, new_data):
    def index_by_class(data):
        return {
            (item.get('name') or '').strip().upper(): item.get('lessons') or []
            for item in (data or [])
            if (item.get('name') or '').strip()
        }

    def normalize(lessons):
        result = []
        for lesson in lessons:
            subject = (lesson.get('subject') or '').strip()
            if not subject or subject == '--|--':
                result.append(None)
                continue
            rooms = tuple(sorted(
                (room.get('classroom') or '').strip()
                for room in (lesson.get('classrooms') or [])
                if room.get('classroom')
            ))
            result.append((subject, rooms))
        return result

    old_map = index_by_class(old_data)
    new_map = index_by_class(new_data)
    return sorted(
        name for name in set(old_map) | set(new_map)
        if normalize(old_map.get(name, [])) != normalize(new_map.get(name, []))
    )


def class_names_from_data(data):
    return [
        (item.get('name') or '').strip().upper()
        for item in (data or [])
        if (item.get('name') or '').strip()
    ]
