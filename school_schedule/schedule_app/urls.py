from django.urls import path

from .views import auth, bot_api, pages, schedule

app_name = 'schedule_app'

urlpatterns = [
    path('healthz/', pages.healthz, name='healthz'),
    path('', pages.index, name='index'),
    path('choice/', pages.choice_view, name='choice'),
    path('schedule/', pages.schedule_view, name='schedule'),
    path('auto/', pages.auto_schedule_view, name='auto_schedule'),
    path('auth/', auth.auth_view, name='auth'),
    path('verify/', auth.verify_email_view, name='verify_email'),
    path('resend-code/', auth.resend_verification_code, name='resend_code'),
    path('logout/', auth.logout_view, name='logout'),
    path('profile/', pages.profile_view, name='profile'),
    path('profile/edit/', pages.profile_edit_view, name='profile_edit'),
    path('upload/', pages.upload_schedule_view, name='upload_schedule'),
    path('upload/process/', schedule.process_upload, name='process_upload'),
    path('api/save/', schedule.save_schedule, name='save_schedule'),
    path('api/load/<str:day>/', schedule.load_schedule, name='load_schedule'),
    path('api/delete_schedule/<int:schedule_id>/', schedule.delete_schedule, name='delete_schedule'),
    path('api/cities/', schedule.get_cities, name='get_cities'),
    path('api/schools/', schedule.get_schools, name='get_schools'),
    path('bot-api/regions/', bot_api.api_regions, name='api_regions'),
    path('bot-api/cities/', bot_api.api_cities, name='api_cities'),
    path('bot-api/schools/', bot_api.api_schools, name='api_schools'),
    path('bot-api/vk-users/<int:vk_id>/', bot_api.api_vk_user_detail, name='api_vk_user_detail'),
    path('bot-api/schedules/by-school/', bot_api.api_schedules_by_school, name='api_schedules_by_school'),
    path('bot-api/schedule-changes/pending/', bot_api.api_pending_changes, name='api_pending_changes'),
    path('bot-api/schedule-changes/mark-notified/', bot_api.api_mark_notified, name='api_mark_notified'),
    path('bot-api/subscribers/', bot_api.api_subscribers, name='api_subscribers'),
]
