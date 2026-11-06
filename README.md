# Automatically refreshed TV playlist

Playlist URL: **https://tr3nching.github.io/iyad-tv-playlist/playlist.m3u**

DRM-capable playlist: **https://tr3nching.github.io/iyad-tv-playlist/playlist-drm.m3u**

OTT Navigator native format: **https://tr3nching.github.io/iyad-tv-playlist/playlist-drm.otc.json**

Program guide: **https://tr3nching.github.io/iyad-tv-playlist/epg.xml** (also available as `epg.xml.gz`). Both playlist formats reference the guide automatically. Set the player's guide time offset to **0**; timestamps are UTC and the player displays local time.

The separate DRM playlist includes ClearKey settings supplied by the source's normal player, in KODIPROP format. Use a player supporting that format, such as OTT Navigator. These settings are publicly hosted together with the stream URLs. The basic playlist omits them. A successful desktop decode does not guarantee Google TV app compatibility.

In TiviMate on Google TV, choose **Add playlist → M3U playlist → Enter URL** and paste the URL above. Enable playlist updates on app startup, and periodic updates if available. This displays channels inside TiviMate; it does not add them to Google TV Freeplay.

## Playback and guide verification

The initial clear-stream check decoded video on 137 channels. A separate fresh ClearKey test decoded 19 of 88 configured DASH channels, including NBA TV. NBA TV Philippines still returned HTTP 403 for media fragments even with fresh settings and the source player's no-referrer behavior. Supplying DRM settings cannot fix source access failures, and the new playlist does not imply every channel works. Results are short desktop samples, not a Google TV hardware test.

The revised guide covers **37 of 246 channels**, with **3,755 listings and zero overlaps** in its checked snapshot. The first pass missed four valid PH2 mappings: Al Jazeera, CNN HD, TVN, and TVN Movies; these are now included. It excludes placeholders, stale listings, and ambiguous regional identities. NBA TV Philippines is mapped; generic NBA TV remains unmapped. The 209 channels without a verified usable mapping retain no guide rather than an unrelated schedule.

Both `PH1.xml.gz` and `PH2.xml.gz` are checked on each guide update. The current PH1 download has 134 channel definitions and **zero programme entries**. PH2 has 111 definitions and 5,960 programme entries: 37 sources used, 43 with no entries, 19 with no current/future entries, seven placeholders, and five distinct alternate feeds. The updater prefers PH2 per channel, then considers PH1 when its real programmes return and its cross-feed timing checks pass. It does not mix overlapping schedules or silently shift times. Source counts and eligibility are published in `epg-status.json`.

`ALL_SOURCES1.txt` was used as a bounded discovery index. Its US2, PLEX1, and UK1 sections identify potential additional guides, but those are not confirmed regional or schedule matches and are not merged yet. The roughly 200 MB combined XML was not downloaded. See `INDEX-LOOKUP.md` for candidate sources and `ph2-coverage-breakdown.json` for all 111 PH2 definitions.

The latest independent recheck matched 47 NHK and 39 Arirang World titles/times; an NBA TV Philippines game time was also cross-checked. A mirror with an eight-hour timestamp error was rejected. These representative checks establish the chosen feed's time interpretation for those examples, not universal broadcaster or stream-picture synchronization. See the published `VERIFICATION.md`, `independent-alignment.json`, `mapping.csv`, and `epg-status.json` for sources, coverage and limitations.

## Updates

GitHub Actions retrieves the enabled channel catalog and resolves each channel's primary source using the same public endpoints as https://iyad.click. It requests the site's normal playback tokens where required, then publishes basic and DRM-capable M3U files through GitHub Pages. No video is hosted or relayed. The DRM variant preserves the source-supplied ClearKey settings; it does not obtain missing keys or licenses. Alternate sources are not included.

The schedule runs every 30 minutes at minutes 17 and 47 (UTC). GitHub may delay scheduled jobs. The source's tokens can expire before the next update; this interval is provisional, not a guarantee of uninterrupted playback. Some channels require DRM, browser headers, or the original player and will not play in TiviMate. Successful URL extraction does not verify video playback.

If the live catalog fails, the updater uses saved channel names from `catalog.json` and still requests fresh playback URLs. New or removed channels will only be picked up when the live catalog works again. If playback requests fail or fewer than 90% of enabled channels resolve, it retains previously published stream files (or the checked-in snapshot). Those links may expire. The EPG updater runs independently using its own public source, so stream-source errors do not stop guide updates. Check `refresh-status.json` for the outcome of each attempt, `status.json` for the age of stream links, and `epg-status.json` for guide freshness and coverage. A green Pages deployment alone does not prove a successful stream refresh.

GitHub disables scheduled workflows in public repositories after 60 days without repository activity. If that happens, re-enable the workflow in Actions. The workflow can also be run manually through **Actions → Refresh and publish playlist → Run workflow**.

## Setup in a new repository

1. Upload these files to a public GitHub repository with `main` as its default branch, including `.github/workflows/refresh.yml`.
2. In **Settings → Pages**, select **GitHub Actions** as the source.
3. Run the workflow from the Actions tab.
4. Replace the account/repository in the URL above if you use a different repository.

The playlist and its signed stream URLs are public. The initial successfully retrieved snapshot is included under `bootstrap/` so the URL can be tried while the upstream stream database is unavailable. It is deployed only for the initial setup commit; subsequent scheduled refreshes must retrieve fresh URLs successfully to replace it. Check `status.json` to distinguish that snapshot from a successful automatic refresh. Later generated playlists are deployed as Pages artifacts rather than committed to source history. Use sources you are authorized to access; GitHub hosting does not provide additional viewing rights.

## Local checks

Requires Node.js 22 or newer and Python 3.10 or newer, with no additional packages.

```
npm test
npm run refresh
python scripts/update_epg.py --catalog catalog.json --out site
```

Output is written to `site/playlist.m3u` and `site/status.json`. The source API can reject requests from particular networks, including GitHub runners; inspect the workflow logs if local retrieval succeeds but hosted updates fail.
