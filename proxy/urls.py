from django.urls import path

from . import views

urlpatterns = [
    path("healthz", views.health, name="health"),
    path("readyz", views.readiness, name="readiness"),
    path("v1/models", views.models_endpoint, name="proxy-models"),
    path("v1/chat/completions", views.chat_completions, name="proxy-chat-completions"),
    path("logs/", views.request_log_list, name="request-log-list"),
    path("logs/<uuid:request_id>/", views.request_log_detail, name="request-log-detail"),
]
