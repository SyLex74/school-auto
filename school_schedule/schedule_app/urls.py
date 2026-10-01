from django.urls import path
from . import views

app_name = 'schedule_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('choice/', views.choice_view, name='choice'),
    path('schedule/', views.schedule_view, name='schedule'),
    path('auto/', views.auto_schedule_view, name='auto_schedule'),
    path('auth/', views.auth_view, name='auth'),
    path('verify/', views.verify_email_view, name='verify_email'),
    path('resend-code/', views.resend_verification_code, name='resend_code'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('api/save/', views.save_schedule, name='save_schedule'),
    path('api/load/<str:day>/', views.load_schedule, name='load_schedule'),
    path('api/delete_schedule/<int:schedule_id>/', views.delete_schedule, name='delete_schedule'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('upload/', views.upload_schedule_view, name='upload_schedule'),
    path('upload/process/', views.process_upload, name='process_upload'),
    path('api/cities/', views.get_cities, name='get_cities'),
    path('api/schools/', views.get_schools, name='get_schools'),

]