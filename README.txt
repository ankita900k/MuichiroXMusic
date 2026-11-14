Muichiro HQ monitoring + Owner Command Center patch.
See MONITORING_SETUP.txt and OWNER_HQ_UPGRADE.txt before installing.
Owner dashboard URL: /owner (requires owner credentials).
This patch does not replace music/voice.py.


MUICHIRO MUSIC PROVIDER SWITCH
------------------------------
Set ANNIE_API_KEY in Render Environment if you want to use the Annie provider.
ANNIE_BASE_URL defaults to https://api.alonexraj.shop.
HEP_MUSIC_API_KEY / HEP_MUSIC_BASE_URL continue to configure the HEP provider.

The bot owner can switch the GLOBAL provider with:
/musicconnection annie
/musicconnection hep
/musicconnection

The selected provider is stored in PostgreSQL (music_provider_settings), so it
survives bot restarts. New requests use the selected provider; tracks already
queued keep the provider they were resolved with.

The /audio command continues to send a normal Telegram audio file. The
Muichiro-branded generated player artwork is used only for voice-chat playback.
Annie's supplied API documentation does not guarantee a metadata/thumbnail
endpoint; embedded tags and any metadata returned by the download response are
used when available, with Muichiro artwork as the thumbnail fallback.

MUICHIRO WELCOME ARTWORK
------------------------
New members receive the generated Muichiro welcome card by default when no
custom welcome message/media has been configured. The image displays Name,
Username, and User ID. Existing custom /setwelcome settings remain supported.
