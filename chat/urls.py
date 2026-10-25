from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/conversations/", views.conversations, name="conversations"),
    path("api/conversations/<uuid:conv_id>/", views.conversation_detail, name="conversation_detail"),
    path("api/conversations/<uuid:conv_id>/chat/", views.chat_stream, name="chat_stream"),
    path("webhooks/meta/", views.meta_webhook, name="meta_webhook"),
]
