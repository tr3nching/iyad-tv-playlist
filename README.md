# PH TV

TV channels, backups and a program guide in one playlist.

**[Playlist URL](https://tr3nching.github.io/ph-tv-playlist/playlist.m3u)**

Add this URL to your IPTV app. The program guide is included automatically; if your app asks for a guide time offset, use **0**.

Channels are grouped by type: Sports, Movies, News, Kids, Anime, Documentaries, Music, Lifestyle, Faith, Education, Entertainment and General. Backups appear in the same category with `[Backup]` after the channel name. Duplicate stream addresses are removed. Select a backup when needed; switching is manual.

When a guide program has no genre, its channel category supplies a fallback using Android TV's supported genre names. Existing program genres are preserved. Channels without guide listings remain without listings; unknown categories stay unclassified. Genre filters depend on the TV app's support.

Playlist and guide updates are scheduled every 30 minutes. Failed backup entries are checked again at the next update. Some channels need a player with DRM support.

## Development

Requires Node.js 22+ and Python 3.10+.

```
npm test
python scripts/test_update_epg.py
npm run refresh
python scripts/update_epg.py
```

One builder generates the playlist; one builds the guide. Settings are in `catalog.json`, `channel-groups.json` and `epg-config.json`. Generated files go to `site/`; `bootstrap/` contains fallback files.
