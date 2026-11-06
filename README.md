# Automatically refreshed TV playlist

Playlist URL: **https://tr3nching.github.io/iyad-tv-playlist/playlist.m3u**

In TiviMate on Google TV, choose **Add playlist → M3U playlist → Enter URL** and paste the URL above. Enable playlist updates on app startup, and periodic updates if available. This displays channels inside TiviMate; it does not add them to Google TV Freeplay.

## Updates

GitHub Actions retrieves the enabled channel catalog and resolves each channel's primary source using the same public endpoints as https://iyad.click. It requests the site's normal playback tokens where required, then publishes an M3U file through GitHub Pages. No video is hosted or relayed. No DRM keys are published. Alternate sources and program schedules are not included.

The schedule runs every 30 minutes at minutes 17 and 47 (UTC). GitHub may delay scheduled jobs. The source's tokens can expire before the next update; this interval is provisional, not a guarantee of uninterrupted playback. Some channels require DRM, browser headers, or the original player and will not play in TiviMate. Successful URL extraction does not verify video playback.

If the catalog fails or fewer than 90% of enabled channels resolve, publishing stops and the previous deployment remains available. It may still contain expired links. Check **Actions** for failures and **status.json** on the published site for the last successful update.

GitHub disables scheduled workflows in public repositories after 60 days without repository activity. If that happens, re-enable the workflow in Actions. The workflow can also be run manually through **Actions → Refresh and publish playlist → Run workflow**.

## Setup in a new repository

1. Upload these files to a public GitHub repository with `main` as its default branch, including `.github/workflows/refresh.yml`.
2. In **Settings → Pages**, select **GitHub Actions** as the source.
3. Run the workflow from the Actions tab.
4. Replace the account/repository in the URL above if you use a different repository.

The playlist and its signed stream URLs are public. Generated playlists are deployed as Pages artifacts rather than committed to source history. Use sources you are authorized to access; GitHub hosting does not provide additional viewing rights.

## Local checks

Requires Node.js 22 or newer, with no additional packages.

```
npm test
npm run refresh
```

Output is written to `site/playlist.m3u` and `site/status.json`. The source API can reject requests from particular networks, including GitHub runners; inspect the workflow logs if local retrieval succeeds but hosted updates fail.
