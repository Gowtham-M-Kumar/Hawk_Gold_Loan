from django.urls import path
from . import views

app_name = "goldrate"

urlpatterns = [
    path("", views.gold_rate_dashboard, name="gold_rate_dashboard"),
    path("api/live/", views.api_live_rate, name="api_live_rate"),
    path("api/history/", views.api_history, name="api_history"),
]
