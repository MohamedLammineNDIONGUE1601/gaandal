from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0002_message_attachments"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialContact",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[("whatsapp", "WhatsApp"), ("messenger", "Facebook Messenger")],
                        max_length=12,
                    ),
                ),
                ("external_id", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "conversation",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_contact",
                        to="chat.conversation",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SocialInbound",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[("whatsapp", "WhatsApp"), ("messenger", "Facebook Messenger")],
                        max_length=12,
                    ),
                ),
                ("external_message_id", models.CharField(max_length=255)),
                ("external_contact_id", models.CharField(max_length=255)),
                ("text", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En attente"),
                            ("processing", "En traitement"),
                            ("failed", "Échec"),
                            ("sent", "Répondu"),
                        ],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("error", models.CharField(blank=True, max_length=500)),
                ("response_text", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assistant_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="social_inbound_assistant",
                        to="chat.message",
                    ),
                ),
                (
                    "conversation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="chat.conversation",
                    ),
                ),
                (
                    "user_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="social_inbound_user",
                        to="chat.message",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="socialcontact",
            constraint=models.UniqueConstraint(
                fields=("channel", "external_id"),
                name="unique_social_channel_contact",
            ),
        ),
        migrations.AddConstraint(
            model_name="socialinbound",
            constraint=models.UniqueConstraint(
                fields=("channel", "external_message_id"),
                name="unique_social_inbound_event",
            ),
        ),
    ]
