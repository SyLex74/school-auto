from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('schedule_app.urls')),
    path('captcha/', include('captcha.urls')),   # обязательно для работы капчи
]