"""Persistent global music provider selection."""
from database import db, cursor

VALID_PROVIDERS = {"annie", "hep"}


def get_music_provider() -> str:
    cursor.execute("SELECT provider FROM music_provider_settings WHERE id = 1")
    row = cursor.fetchone()
    value = (row[0] if row else "hep") or "hep"
    return value if value in VALID_PROVIDERS else "hep"


def set_music_provider(provider: str) -> None:
    provider = provider.lower().strip()
    if provider not in VALID_PROVIDERS:
        raise ValueError("Provider must be 'annie' or 'hep'")
    cursor.execute(
        """
        INSERT INTO music_provider_settings (id, provider, updated_at)
        VALUES (1, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO UPDATE
        SET provider = EXCLUDED.provider, updated_at = CURRENT_TIMESTAMP
        """,
        (provider,),
    )
    db.commit()
