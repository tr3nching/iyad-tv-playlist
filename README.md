# PH TV

TV channels, backups and a program guide in one playlist.

**[Playlist URL](https://tr3nching.github.io/ph-tv-playlist/playlist.m3u)**

Add this URL to your IPTV app. The program guide is included automatically; if your app asks for a guide time offset, use **0**.

Additional channels appear in their own group. Alternate streams appear in the **Backup** group with `[Backup]` after the channel name. Select a backup when needed; switching is manual.

Playlist and guide updates are scheduled every 30 minutes. Failed backup entries are checked again at the next update. Some channels need a player with DRM support.

## Development

Requires Node.js 22+ and Python 3.10+.

```
npm test
python scripts/test_update_epg.py
npm run refresh
python scripts/update_epg.py
```

One builder generates the playlist; one builds the guide. Channel and guide settings are in `catalog.json` and `epg-config.json`. Generated files go to `site/`; `bootstrap/` contains fallback files.
