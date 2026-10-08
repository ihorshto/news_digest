"""Supported digest/query languages and their Google News locale parameters."""

SUPPORTED_LANGUAGES: dict[str, str] = {
    "uk": "Українська",
    "en": "English",
    "pl": "Polski",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
}

# language -> (hl, gl, ceid)
GOOGLE_NEWS_LOCALES: dict[str, tuple[str, str, str]] = {
    "uk": ("uk", "UA", "UA:uk"),
    "en": ("en-US", "US", "US:en"),
    "pl": ("pl", "PL", "PL:pl"),
    "de": ("de", "DE", "DE:de"),
    "fr": ("fr", "FR", "FR:fr"),
    "es": ("es", "ES", "ES:es"),
    "it": ("it", "IT", "IT:it"),
}

LANGUAGE_NAMES_EN: dict[str, str] = {
    "uk": "Ukrainian",
    "en": "English",
    "pl": "Polish",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
}
