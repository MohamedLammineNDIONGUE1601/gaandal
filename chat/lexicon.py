import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache

from django.conf import settings
from pypdf import PdfReader


_FRENCH_STOP_WORDS = {
    "alors", "au", "aucun", "aussi", "autre", "avec", "avoir", "bon", "car",
    "ce", "cela", "ces", "cet", "cette", "ceux", "chaque", "ci", "comme",
    "comment", "dans", "de", "des", "donc", "du", "elle", "elles", "en",
    "encore", "est", "et", "eux", "faire", "fait", "fois", "font", "hors",
    "ici", "il", "ils", "je", "juste", "la", "le", "les", "leur", "lui",
    "ma", "mais", "me", "meme", "mes", "moi", "mon", "ne", "nos", "notre",
    "nous", "on", "ou", "par", "pas", "peu", "plus", "pour", "pourquoi",
    "quand", "que", "quel", "quelle", "quelles", "quels", "qui", "sa", "sans",
    "se", "ses", "si", "son", "sont", "sous", "sur", "ta", "te", "tes", "toi",
    "ton", "tous", "tout", "trop", "tu", "un", "une", "vos", "votre", "vous",
}
_MAX_CONTEXT_CHARS = 4000


@dataclass(frozen=True)
class LexiconEntry:
    page: int
    text: str


def _tokens(text):
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(
        char
        for char in normalized
        if not unicodedata.combining(char) and char != "\ufffd"
    )
    return set(re.findall(r"[a-z0-9]+", normalized))


@lru_cache(maxsize=2)
def _load_entries(pdf_path):
    entries = []
    for page_number, page in enumerate(PdfReader(pdf_path).pages, start=1):
        for line in (page.extract_text() or "").splitlines():
            line = " ".join(line.split())
            if ":" in line:
                entries.append(LexiconEntry(page=page_number, text=line))
    return tuple(entries)


def _match_score(query_tokens, entry_tokens, normalized_query, normalized_entry):
    score = 0
    for token in query_tokens:
        if token in entry_tokens:
            score += 3 if len(token) > 3 else 1
        elif len(token) >= 5 and any(
            SequenceMatcher(None, token, candidate).ratio() >= 0.84
            for candidate in entry_tokens
            if len(candidate) >= 5
        ):
            score += 1
    if normalized_query and normalized_query in normalized_entry:
        score += 4
    return score


def retrieve_lexicon(query, limit=5):
    """Return short, relevant Pulaar/French dictionary entries for a query."""
    query_tokens = _tokens(query) - _FRENCH_STOP_WORDS
    if not query_tokens:
        return ""

    normalized_query = " ".join(sorted(query_tokens))
    ranked_entries = []
    for entry in _load_entries(str(settings.PULAAR_LEXICON_PATH)):
        entry_tokens = _tokens(entry.text)
        score = _match_score(
            query_tokens,
            entry_tokens,
            normalized_query,
            " ".join(sorted(entry_tokens)),
        )
        if score:
            ranked_entries.append((score, entry))

    ranked_entries.sort(key=lambda result: result[0], reverse=True)
    excerpts = []
    total_chars = 0
    for _, entry in ranked_entries[:limit]:
        excerpt = f"[Page {entry.page}] {entry.text}"
        if total_chars + len(excerpt) > _MAX_CONTEXT_CHARS:
            break
        excerpts.append(excerpt)
        total_chars += len(excerpt)

    return "\n".join(excerpts)
