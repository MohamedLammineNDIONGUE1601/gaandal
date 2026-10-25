from django.contrib import admin

from .models import Conversation, Message, SocialContact, SocialInbound


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "session_key", "updated_at")
    inlines = [MessageInline]


@admin.register(SocialContact)
class SocialContactAdmin(admin.ModelAdmin):
    list_display = ("channel", "external_id", "conversation", "created_at")
    search_fields = ("external_id",)


@admin.register(SocialInbound)
class SocialInboundAdmin(admin.ModelAdmin):
    list_display = ("channel", "external_message_id", "status", "attempts", "created_at")
    list_filter = ("channel", "status")
    search_fields = ("external_message_id", "external_contact_id")
    readonly_fields = ("created_at", "updated_at")
