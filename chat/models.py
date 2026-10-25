import uuid

from django.db import models


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_key = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=120, default="Nouvelle conversation")
    dialect = models.CharField(max_length=20, default="pulaar_sn")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class Message(models.Model):
    ROLE_CHOICES = [("user", "Utilisateur"), ("assistant", "INTELLECTO")]

    conversation = models.ForeignKey(
        Conversation, related_name="messages", on_delete=models.CASCADE
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    attachments = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


class SocialContact(models.Model):
    CHANNEL_CHOICES = [("whatsapp", "WhatsApp"), ("messenger", "Facebook Messenger")]

    channel = models.CharField(max_length=12, choices=CHANNEL_CHOICES)
    external_id = models.CharField(max_length=255)
    conversation = models.OneToOneField(
        Conversation, related_name="social_contact", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "external_id"],
                name="unique_social_channel_contact",
            )
        ]

    def __str__(self):
        return f"{self.channel}: {self.external_id}"


class SocialInbound(models.Model):
    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("processing", "En traitement"),
        ("failed", "Échec"),
        ("sent", "Répondu"),
    ]

    channel = models.CharField(max_length=12, choices=SocialContact.CHANNEL_CHOICES)
    external_message_id = models.CharField(max_length=255)
    external_contact_id = models.CharField(max_length=255)
    text = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True)
    response_text = models.TextField(blank=True)
    conversation = models.ForeignKey(
        Conversation, null=True, blank=True, on_delete=models.SET_NULL
    )
    user_message = models.ForeignKey(
        Message,
        null=True,
        blank=True,
        related_name="social_inbound_user",
        on_delete=models.SET_NULL,
    )
    assistant_message = models.ForeignKey(
        Message,
        null=True,
        blank=True,
        related_name="social_inbound_assistant",
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "external_message_id"],
                name="unique_social_inbound_event",
            )
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.channel}: {self.external_message_id} ({self.status})"
