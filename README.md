# Gaandal — agent IA (Django)

Interface de chat avec Gemini : conversations multiples, réponses en streaming, rendu Markdown, formules LaTeX, graphiques SVG nettoyés, copie du code, thème clair/sombre, responsive.

## Installation

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env                 # puis renseigner GEMINI_API_KEY
python manage.py migrate
python manage.py runserver
```

Ouvrir http://127.0.0.1:8000

Créez une clé Gemini dans Google AI Studio. Ne la partagez pas et ne la publiez pas. Le modèle par défaut est `gemini-3.8-flash`. Vous pouvez choisir un autre modèle accessible en modifiant `INTELLECTO_MODEL` dans `.env`.

## Configuration (.env)

| Variable | Rôle |
|---|---|
| `GEMINI_API_KEY` | Clé API Gemini (jamais côté navigateur) |
| `INTELLECTO_MODEL` | Modèle Gemini utilisé (par défaut : `gemini-3.8-flash`) |
| `INTELLECTO_MAX_TOKENS` | Longueur maximale des réponses (4096 par défaut) |

La personnalité de l'agent se modifie dans `config/settings.py` (`INTELLECTO_SYSTEM_PROMPT`).

## Assistance en pulaar

Gaandal recherche les entrées pertinentes dans `chat/data/lexique-pulaar-francais.pdf` et les transmet à Gemini comme contexte. Son instruction est de répondre exclusivement en pulaar, quelle que soit la langue de la question, et de ne pas recopier les définitions françaises du lexique. Cette recherche documentaire n'entraîne pas et ne modifie pas le modèle Gemini ; le respect de la langue dépend des capacités du modèle.

## Pièces jointes et voix

Le chat accepte les PDF, images PNG/JPEG/WebP/GIF, fichiers texte TXT/Markdown/CSV/JSON, fichiers audio courants et vidéos MP4/WebM/MOV. Un message vocal peut être enregistré depuis le navigateur si le microphone est autorisé. Les pièces jointes sont transmises à Gemini pour analyse ; Gaandal n’en conserve que les noms, types et tailles. Limites : 5 fichiers, 15 Mo maximum chacun et 25 Mo au total. Les fichiers texte doivent être en UTF-8 et sont limités à 50 000 caractères chacun et 100 000 caractères cumulés par envoi.

## Réseaux sociaux

Le webhook Meta reçoit les messages texte WhatsApp Business et Facebook Messenger puis les met en file d’attente. Le worker `python manage.py process_social_messages` génère une réponse en pulaar et l’envoie sur le canal d’origine. Pour traiter une fois les messages en attente, lancez `python manage.py process_social_messages --once`; pour réessayer les échecs, utilisez `python manage.py process_social_messages --once --retry-failed`.

Configurez dans `.env` l’application Meta Developer (secret et jeton de vérification), la version Graph API, le jeton WhatsApp Business et l’identifiant du numéro, ainsi que le jeton de page et l’identifiant de page Facebook. Dans Meta, abonnez l’application au webhook HTTPS `https://<votre-domaine>/webhooks/meta/` pour les événements de messages. Le serveur doit être accessible depuis Internet en HTTPS et le worker doit fonctionner en continu. Les pièces jointes et messages vocaux reçus directement sur les réseaux sociaux ne sont pas encore traités.

Les jetons, secrets et identifiants restent côté serveur et ne doivent jamais être publiés. Les identifiants des utilisateurs Meta et le texte des messages sont enregistrés dans la base de Gaandal pour conserver les conversations et reprendre les traitements. Prévoyez des règles de conservation et informez les utilisateurs avant d’activer ces canaux.

## Structure

- `chat/views.py` : API (liste/création/suppression de conversations, streaming NDJSON)
- `chat/lexicon.py` et `chat/data/lexique-pulaar-francais.pdf` : recherche locale dans le lexique pulaar-français
- `chat/models.py` : `Conversation`, `Message`
- `chat/templates/chat/index.html`, `chat/static/chat/{css,js}` : interface

## Notes

- Les conversations sont rattachées à la session du navigateur (sans compte). Pour un déploiement multi-utilisateurs, ajoutez l'authentification Django.
- En production : `DJANGO_DEBUG=0`, vraie `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `collectstatic`, et un serveur ASGI/WSGI (gunicorn) avec le buffering proxy désactivé pour le streaming.
