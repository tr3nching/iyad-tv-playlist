# PH TV

TV channels, backups and a program guide in one playlist.

**[Playlist URL](https://tr3nching.github.io/ph-tv-playlist/playlist.m3u)**

Add this URL to your IPTV app. The program guide is included automatically; if your app asks for a guide time offset, use **0**.

Channels are grouped by type: Sports, Movies, News, Kids, Anime, Documentaries, Music, Lifestyle, Faith, Education, Entertainment and General. GMA, TFC Asia, Kapamilya Channel, TV5 and A2Z are in Entertainment.

Additional streams keep their original names and separate guide IDs. Similar names do not establish that they carry the same channel. All additional entries are retained. `*` marks an additional entry whose name or exact stream URL also occurs in the original list. These entries do not automatically replace a missing channel or inherit its guide.

Additional entries receive a guide only when an exact stream match or reviewed regional identity supports it. Entries without usable listings remain without a guide.

When a guide program has no genre, its channel category supplies a fallback using Android TV's supported genre names. Existing program genres are preserved. Channels without guide listings remain without listings; unknown categories stay unclassified. Genre filters depend on the TV app's support.

Playlist and guide updates are scheduled every 30 minutes. All saved channels remain listed, including entries that fail hosted checks. Some channels need a player with DRM support.

Reachability checks are informational and do not hide channels. The playlist entries and custom channel numbers follow category blocks: Entertainment 100–199, Movies 200–299, Sports 300–399, News 400–499, Kids 500–599, Anime 600–699, Documentaries 700–799, Music 800–899, Lifestyle 900–999, Faith 1000–1099, Education 1100–1199 and General 1200–1299. Within each category, channels are alphabetically ordered by display name. Custom numbers follow that order and may change when entries are added or removed. TV apps that enforce alphabetical sorting may display a different order.

Checks run from the hosting network and cover manifests plus media requests where supported. They do not guarantee decoding, DRM playback, or access from your TV. `stream-health.json` records the results without stream URLs or keys.

## Development

Requires Node.js 22+ and Python 3.10+.

```
npm test
python scripts/test_update_epg.py
python scripts/test_check_streams.py
npm run refresh
python scripts/check_streams.py
node scripts/refresh.mjs --finalize
python scripts/update_epg.py
```

One builder generates the playlist; one builds the guide. Settings are in `catalog.json`, `channel-groups.json` and `epg-config.json`. `channel-category-review.json` records category evidence and uncertainties; source-specific names are in `source-channel-overrides.json`. Additional guide identities are in `3rs-epg-mappings.json`, with live coverage recorded in `3rs-epg-audit.json`. Generated files go to `site/`; `bootstrap/` contains fallback files.
