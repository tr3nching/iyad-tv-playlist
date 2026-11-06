# PH TV playlist

One repository with one M3U builder (`scripts/refresh.mjs`) and one EPG builder (`scripts/update_epg.py`). The source feed definitions and channel identities from `tr3nching/ph-epg` are consolidated in `epg-config.json`. Guide generation reads the local channel catalog directly and does not depend on the old generated guide or a remote M3U.

## Add to your TV

Combined primary + backup playlist: **https://tr3nching.github.io/ph-tv-playlist/playlist-combined.m3u**

Primary DRM playlist: https://tr3nching.github.io/ph-tv-playlist/playlist-drm.m3u

Backup playlist: https://tr3nching.github.io/ph-tv-playlist/playlist-backup.m3u

Basic primary playlist: https://tr3nching.github.io/ph-tv-playlist/playlist.m3u

OTT Navigator native primary playlist: https://tr3nching.github.io/ph-tv-playlist/playlist-drm.otc.json

EPG: **https://tr3nching.github.io/ph-tv-playlist/epg.xml.gz** (uncompressed `epg.xml` also available).

All playlists include the EPG URL automatically. Compatible TV apps can import both from the playlist; some require enabling automatic EPG refresh once. Set the guide offset to **0**. Combined playlists label alternate entries `[Backup]` in a Backup group; selecting another stream is manual, not automatic failover. Channels exclusive to the backup source may lack a guide.

The repository was renamed from its original name. GitHub repository links redirect, but old GitHub Pages playlist links must be replaced with the new URLs above. Operational source API addresses, logo URLs and required playback headers remain so source access keeps working.

## Guide coverage

The checked consolidated snapshot has **186 channel matches including unusable listings**, and **170 channels with usable current schedules**, with zero overlapping listings. Counts vary as feeds update. These are different measurements: the earlier 185 count included stale schedules and placeholder entries. `epg-status.json`, `mapping.json`, `mapping.csv` and `report.txt` show current coverage, selected source identities and unsuccessful attempts.

The single builder tries explicit per-source identities, then unique exact names. It preserves regional words and tries later sources if an earlier source has stale, placeholder, invalid or overlapping data. Strict mappings correct mismatches such as US NBA TV versus NBA TV Philippines, GMA versus GMA Pinoy TV, Philippine TV5 versus French-language TV5, Tap Action Flix versus Tap Movies, and TAP Edge versus TAP Sports. Exact timestamp offsets are normalized to UTC without shifting the broadcast instant. One source is selected per channel. Placeholder-only and stale-only schedules do not count as usable current guides.

Configuration preserves all imported source definitions; `activeSources` selects 25 relevant feeds for each build. Downloads and expanded XML sizes are bounded. Source failures are isolated, and an inadequate build leaves the previous published guide intact. Regional matches and every broadcast are not independently confirmed; zero overlaps does not prove stream-picture synchronization. Historical NHK, Arirang and NBA Philippines representative checks are retained in `independent-alignment.json` and `VERIFICATION.md`.

## Stream sources and updates

The M3U builder resolves the primary provider's public player API and extracts the backup site's public literal player configuration at https://3rstvportal.blogspot.com/. It never executes that page's scripts. Unsupported embeds and malformed ClearKey settings are excluded. Backup extraction runs independently before primary-source retrieval, so a primary outage does not prevent the backup playlist updating. `backup-status.json` describes the extraction, not proof of playback or source independence.

Primary DRM settings are the public source-supplied ClearKey metadata. Use a player that supports KODIPROP/ClearKey or the OTT Navigator native format. Stream URLs and these settings are publicly hosted. No video is hosted or relayed. URLs can expire; source access, headers and app support affect playback. The backup website may use some of the same underlying servers as the primary provider.

GitHub Actions runs every 30 minutes. It restores prior assets, runs the M3U builder and EPG builder independently, then publishes their outputs. `status.json` records primary stream age, `backup-status.json` records backup extraction age, `refresh-status.json` records attempted refresh outcomes, and `epg-status.json` records guide coverage. A successful Pages deployment alone does not establish successful stream refresh or playback.

The initial desktop clear-stream sample decoded video on 137 channels. A later primary ClearKey sample decoded 19 of 88 configured DASH channels, including NBA TV. NBA TV Philippines returned HTTP 403 for media fragments. These historical short samples do not guarantee current or Google TV playback. The new backup entries have not all been video-decoded.

## Local use

Requires Node.js 22+ and Python 3.10+, with no additional packages.

```
npm test
python scripts/test_update_epg.py
npm run refresh
python scripts/update_epg.py --catalog catalog.json --out site
```

`node scripts/refresh.mjs --backup-only` updates backups and the combined playlist using the existing primary file. `python scripts/update_epg.py --offline` rebuilds from previously downloaded source caches. Generated artifacts are published from `site/`; checked fallback files are in `bootstrap/`.
