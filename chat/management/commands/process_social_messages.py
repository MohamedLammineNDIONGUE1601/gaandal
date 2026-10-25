import time

from django.db import close_old_connections
from django.core.management.base import BaseCommand, CommandError

from chat.social import process_social_inbound


class Command(BaseCommand):
    help = "Traite les messages entrants WhatsApp et Facebook mis en file d’attente."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=3)
        parser.add_argument("--retry-failed", action="store_true")

    def handle(self, *args, **options):
        if options["poll_seconds"] < 0.5:
            raise CommandError("--poll-seconds doit être supérieur ou égal à 0.5.")

        retry_failed = options["retry_failed"]
        try:
            while True:
                close_old_connections()
                processed = process_social_inbound(retry_failed=retry_failed)
                retry_failed = False
                if processed:
                    self.stdout.write(f"{processed} message(s) traité(s).")
                elif options["once"]:
                    self.stdout.write("Aucun message en attente.")
                if options["once"]:
                    break
                time.sleep(options["poll_seconds"])
        except KeyboardInterrupt:
            self.stdout.write("Arrêt du traitement des messages sociaux.")
