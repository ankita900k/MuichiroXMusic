# Muichiro Music — Hep.gg library + personal favourites

## Environment

Set `HEP_MUSIC_API_KEY` in Render Environment. `HEP_MUSIC_BASE_URL` is optional and defaults to `https://music.jakeypri.me`. You no longer need a YouTube Data API key.

## Search and audio

- `/play song name` and `/audio song name` resolve song names directly through Hep.gg's music library.
- Supported public media URLs are handled by Hep.gg `/media`.
- Audio is delivered/played as MP3 through the existing voice and Telegram audio paths.
- Track artwork and metadata are used when Hep.gg provides them.

## Personal favourite songs

- Tap `♡ FAVOURITE` on the current player card to save that track to your personal favourites database. Each Telegram user has a separate list. Repeated taps do not create duplicates.
- `/fav` lists saved tracks and their numbers.
- `/playfav 3` plays or queues favourite number 3.
- `/playfav all` plays/queues the first 50 saved favourites in order. If a track is already playing, saved favourites are added to the end of the existing queue.
- Favourite data uses the project's existing SQLite/PostgreSQL database, depending on `DATABASE_URL`.

## Other commands

- `/queue`, `/now`, `/skip`, `/pause`, `/resume`, and `/stop` keep the existing queue/player controls.
- The favourite button is only on the voice player card; `/audio` remains a straightforward audio-delivery command.

Keep API keys private and do not commit real keys to GitHub. FFmpeg remains installed for the existing seeking/media handling.


### Favourite songs limit
Each Telegram user can save up to 10 favourite songs. `/fav` lists those saved tracks, and `/playfav all` plays/queues at most those 10 songs.
