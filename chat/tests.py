import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from google.genai import errors

from .lexicon import retrieve_lexicon
from .models import Conversation, Message, SocialInbound
from .social import _post_graph_message, process_social_inbound
from .views import chat_stream, meta_webhook


class PulaarLexiconTests(TestCase):
    def test_retrieves_entry_by_pulaar_word_or_french_meaning(self):
        self.assertIn("Adjarama", retrieve_lexicon("merci"))
        self.assertIn("Adjarama", retrieve_lexicon("Que signifie Adjarama ?"))

    def test_returns_no_entries_for_an_unmatched_query(self):
        self.assertEqual(retrieve_lexicon("xylophone intergalactique"), "")


class MetaWebhookTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(META_VERIFY_TOKEN="verify-me")
    def test_verifies_meta_webhook_subscription(self):
        request = self.factory.get(
            "/webhooks/meta/?hub.mode=subscribe"
            "&hub.verify_token=verify-me&hub.challenge=12345"
        )

        response = meta_webhook(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"12345")

    @override_settings(META_APP_SECRET="test-app-secret")
    def test_rejects_webhook_with_invalid_signature(self):
        request = self.factory.post(
            "/webhooks/meta/",
            data=b'{"object":"whatsapp_business_account"}',
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
        )

        response = meta_webhook(request)

        self.assertEqual(response.status_code, 403)

    @override_settings(META_APP_SECRET="test-app-secret")
    def test_queues_signed_text_events_and_deduplicates_retries(self):
        body = json.dumps(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "id": "wamid.test",
                                            "from": "221700000000",
                                            "type": "text",
                                            "text": {"body": "Jam tan"},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        ).encode()
        signature = hmac.new(
            b"test-app-secret", body, hashlib.sha256
        ).hexdigest()

        def send_webhook():
            request = self.factory.post(
                "/webhooks/meta/",
                data=body,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
            )
            return meta_webhook(request)

        first = send_webhook()
        duplicate = send_webhook()

        self.assertEqual(json.loads(first.content)["queued"], 1)
        self.assertEqual(json.loads(duplicate.content)["queued"], 0)
        inbound = SocialInbound.objects.get(external_message_id="wamid.test")
        self.assertEqual(inbound.text, "Jam tan")


class SocialMessageWorkerTests(TestCase):
    @override_settings(GEMINI_API_KEY="test-key")
    @patch("chat.social._send_social_reply")
    @patch("chat.social._generate_social_reply", return_value="Jam tan.")
    def test_generates_and_sends_one_reply_for_an_inbound_event(
        self, generate_reply, send_reply
    ):
        inbound = SocialInbound.objects.create(
            channel="messenger",
            external_message_id="mid.test",
            external_contact_id="psid.test",
            text="A jaaraama",
        )

        processed = process_social_inbound()

        inbound.refresh_from_db()
        self.assertEqual(processed, 1)
        self.assertEqual(inbound.status, "sent")
        self.assertEqual(inbound.response_text, "Jam tan.")
        self.assertEqual(inbound.conversation.messages.count(), 2)
        generate_reply.assert_called_once_with(inbound.conversation)
        send_reply.assert_called_once_with("messenger", "psid.test", "Jam tan.")

    @override_settings(
        META_GRAPH_API_VERSION="v25.0",
        WHATSAPP_ACCESS_TOKEN="test-whatsapp-token",
        WHATSAPP_PHONE_NUMBER_ID="phone.test",
    )
    @patch("chat.social.urllib.request.urlopen")
    def test_sends_whatsapp_reply_through_the_configured_graph_api(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 200

        _post_graph_message("whatsapp", "221700000000", "Jam tan.")

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://graph.facebook.com/v25.0/phone.test/messages",
        )
        self.assertEqual(
            request.get_header("Authorization"), "Bearer test-whatsapp-token"
        )
        self.assertEqual(
            json.loads(request.data)["text"]["body"],
            "Jam tan.",
        )

    @override_settings(
        META_GRAPH_API_VERSION="v25.0",
        FACEBOOK_PAGE_ACCESS_TOKEN="test-page-token",
        FACEBOOK_PAGE_ID="page.test",
    )
    @patch("chat.social.urllib.request.urlopen")
    def test_sends_messenger_reply_through_the_configured_graph_api(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 200

        _post_graph_message("messenger", "psid.test", "Jam tan.")

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://graph.facebook.com/v25.0/page.test/messages",
        )
        self.assertEqual(
            request.get_header("Authorization"), "Bearer test-page-token"
        )
        self.assertEqual(
            json.loads(request.data)["recipient"]["id"],
            "psid.test",
        )


class ChatStreamTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.session = SessionStore()
        self.session.create()
        self.conversation = Conversation.objects.create(
            session_key=self.session.session_key
        )

    @override_settings(GEMINI_API_KEY="test-key")
    @patch("chat.views.genai.Client")
    def test_streams_gemini_response_and_persists_it(self, client_class):
        previous_user_message = Message.objects.create(
            conversation=self.conversation, role="user", content="Question précédente"
        )
        previous_assistant_message = Message.objects.create(
            conversation=self.conversation,
            role="assistant",
            content="Réponse précédente",
        )
        now = timezone.now()
        Message.objects.filter(pk=previous_user_message.pk).update(
            created_at=now - timedelta(minutes=2)
        )
        Message.objects.filter(pk=previous_assistant_message.pk).update(
            created_at=now - timedelta(minutes=1)
        )

        client = client_class.return_value
        client.interactions.create.return_value = [
            SimpleNamespace(
                event_type="step.delta",
                delta=SimpleNamespace(type="text", text="Bonjour"),
            ),
            SimpleNamespace(
                event_type="step.delta",
                delta=SimpleNamespace(type="text", text=" !"),
            ),
        ]
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data=json.dumps({"message": "Salut"}),
            content_type="application/json",
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)
        events = [
            json.loads(line)
            for line in b"".join(response.streaming_content).decode().splitlines()
        ]

        self.assertEqual(
            [event["type"] for event in events], ["delta", "delta", "done"]
        )
        self.assertEqual(
            [event["text"] for event in events[:2]], ["Bonjour", " !"]
        )
        client.interactions.create.assert_called_once()
        call = client.interactions.create.call_args.kwargs
        self.assertEqual(
            call["input"],
            [
                {
                    "type": "user_input",
                    "content": [{"type": "text", "text": "Question précédente"}],
                },
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": "Réponse précédente"}],
                },
                {
                    "type": "user_input",
                    "content": [{"type": "text", "text": "Salut"}],
                }
            ],
        )
        self.assertEqual(call["model"], settings.INTELLECTO_MODEL)
        self.assertTrue(call["stream"])
        self.assertEqual(call["generation_config"]["thinking_level"], "low")
        self.assertEqual(
            call["generation_config"]["max_output_tokens"],
            settings.INTELLECTO_MAX_TOKENS,
        )
        self.assertIn(
            "exactement une illustration pertinente",
            call["system_instruction"],
        )
        self.assertEqual(
            list(
                self.conversation.messages.order_by("created_at").values_list(
                    "role", "content"
                )
            )[-2:],
            [("user", "Salut"), ("assistant", "Bonjour !")],
        )

    @override_settings(GEMINI_API_KEY="test-key")
    @patch("chat.views.genai.Client")
    def test_ignores_non_text_step_delta_events(self, client_class):
        client = client_class.return_value
        client.interactions.create.return_value = [
            SimpleNamespace(event_type="step.delta", delta=None),
            SimpleNamespace(
                event_type="step.delta",
                delta=SimpleNamespace(type="thought_signature", text="ignored"),
            ),
            SimpleNamespace(
                event_type="step.delta",
                delta=SimpleNamespace(type="text", text="Njarama"),
            ),
        ]
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data=json.dumps({"message": "Salut"}),
            content_type="application/json",
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)
        events = [
            json.loads(line)
            for line in b"".join(response.streaming_content).decode().splitlines()
        ]

        self.assertEqual(
            [event["type"] for event in events], ["delta", "done"]
        )
        self.assertEqual(events[0]["text"], "Njarama")

    @override_settings(GEMINI_API_KEY="")
    def test_returns_clear_error_when_gemini_key_is_missing(self):
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data=json.dumps({"message": "Salut"}),
            content_type="application/json",
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            json.loads(response.content)["error"],
            "GEMINI_API_KEY manquante : configurez le fichier .env",
        )
        self.assertFalse(self.conversation.messages.exists())

    @override_settings(GEMINI_API_KEY="test-key")
    @patch("chat.views.genai.Client")
    def test_includes_relevant_lexicon_entries_in_gemini_prompt(self, client_class):
        client_class.return_value.interactions.create.return_value = []
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data=json.dumps({"message": "Que signifie Adjarama ?"}),
            content_type="application/json",
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)
        list(response.streaming_content)

        system_instruction = (
            client_class.return_value.interactions.create.call_args.kwargs[
                "system_instruction"
            ]
        )
        self.assertIn("Adjarama", system_instruction)
        self.assertIn("merci", system_instruction)
        self.assertIn("réponds exclusivement en pulaar", system_instruction)
        self.assertIn("même si l'utilisateur le demande", system_instruction)
        self.assertNotIn("Tu réponds dans la langue de l'utilisateur", system_instruction)

    @override_settings(GEMINI_API_KEY="test-key")
    @patch("chat.views.genai.Client")
    def test_attaches_pdf_to_gemini_and_persists_only_its_metadata(self, client_class):
        client = client_class.return_value
        client.files.upload.return_value = SimpleNamespace(
            name="files/test-pdf",
            uri="https://files.example/test-pdf",
            mime_type="application/pdf",
        )
        client.interactions.create.return_value = []
        pdf = SimpleUploadedFile(
            "cours.pdf", b"%PDF-1.4\nfake test content", content_type="application/pdf"
        )
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data={"message": "Fais un résumé en pulaar", "files": pdf},
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)
        events = [
            json.loads(line)
            for line in b"".join(response.streaming_content).decode().splitlines()
        ]

        self.assertEqual(events[-1]["type"], "done")
        client.files.upload.assert_called_once()
        content = client.interactions.create.call_args.kwargs["input"][-1]["content"]
        self.assertEqual(content[-1]["type"], "document")
        self.assertEqual(content[-1]["uri"], "https://files.example/test-pdf")
        client.files.delete.assert_called_once_with(name="files/test-pdf")
        saved = self.conversation.messages.get(role="user")
        self.assertEqual(saved.attachments[0]["name"], "cours.pdf")
        self.assertEqual(saved.attachments[0]["mime_type"], "application/pdf")

    @override_settings(GEMINI_API_KEY="test-key")
    @patch("chat.views.genai.Client")
    def test_includes_utf8_text_attachment_in_gemini_input(self, client_class):
        client_class.return_value.interactions.create.return_value = []
        text_file = SimpleUploadedFile(
            "notes.txt", "Jam tan, miɗo janngina.".encode(), content_type="text/plain"
        )
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data={"message": "Résume ce document", "files": text_file},
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)
        list(response.streaming_content)

        client = client_class.return_value
        client.files.upload.assert_not_called()
        content = client.interactions.create.call_args.kwargs["input"][-1]["content"]
        self.assertIn("Jam tan, miɗo janngina.", content[-1]["text"])

    @override_settings(GEMINI_API_KEY="test-key")
    @patch("chat.views.genai.Client")
    def test_treats_recorded_webm_voice_note_as_audio(self, client_class):
        client = client_class.return_value
        client.files.upload.return_value = SimpleNamespace(
            name="files/test-audio",
            uri="https://files.example/test-audio",
            mime_type="audio/webm",
        )
        client.interactions.create.return_value = []
        audio = SimpleUploadedFile(
            "message-vocal.webm",
            b"test audio",
            content_type="audio/webm;codecs=opus",
        )
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data={"files": audio},
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)
        list(response.streaming_content)

        upload_config = client.files.upload.call_args.kwargs["config"]
        self.assertEqual(upload_config["mime_type"], "audio/webm")
        content = client.interactions.create.call_args.kwargs["input"][-1]["content"]
        self.assertEqual(content[-1]["type"], "audio")

    @override_settings(GEMINI_API_KEY="test-key")
    def test_rejects_unsupported_attachment_types(self):
        executable = SimpleUploadedFile("app.exe", b"not allowed")
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data={"message": "Analyse ce fichier", "files": executable},
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Type de fichier non pris en charge",
            json.loads(response.content)["error"],
        )
        self.assertFalse(self.conversation.messages.exists())

    @override_settings(GEMINI_API_KEY="test-key")
    @patch("chat.views.genai.Client")
    def test_reports_gemini_client_error_status(self, client_class):
        client_class.return_value.interactions.create.side_effect = (
            errors.ClientError(
                400,
                {"error": {"message": "Invalid model", "status": "INVALID_ARGUMENT"}},
            )
        )
        request = self.factory.post(
            f"/api/conversations/{self.conversation.id}/chat/",
            data=json.dumps({"message": "Salut"}),
            content_type="application/json",
        )
        request.session = self.session

        response = chat_stream(request, self.conversation.id)
        events = [
            json.loads(line)
            for line in b"".join(response.streaming_content).decode().splitlines()
        ]

        self.assertEqual(events[0]["type"], "error")
        self.assertIn("HTTP 400", events[0]["text"])
