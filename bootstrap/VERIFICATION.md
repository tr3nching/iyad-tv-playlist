# Programme-guide verification — November 6, 2026

Generated **2026-11-06 15:26:57 UTC** (07:26:57 Pacific Standard Time).

**33 of 246 channels** have real, current programme schedules, totalling **3,456 programme entries**.
**213 remain unmapped:** 183 have no unambiguous regional mapping; 30 mapped identities have no
current real programmes in this source. Placeholder “No Data” and station-name-only schedules
are excluded. Channel IDs match the cleaned playlist names exactly.

Source: https://m3u-edit.com/epg-source.php?file=PH2.xml.gz, as listed at https://m3u-edit.com/epg.
The live response was retrieved successfully on November 6; it does not supply a Last-Modified
header. Feed freshness is therefore established from retrieval time and programme date ranges,
not an invented provider generation timestamp. SHA-256 and per-channel ranges are recorded
in `epg-status.json`. Overall retained coverage ends November 9, 06:20 UTC; individual channels
end earlier. **No overlapping programme entries** were found. All accepted timestamps have
explicit UTC offsets and positive durations. Gaps are reported per channel.

## Independent alignment evidence

The separate `independent-alignment.json` records broadcaster checks, examples, and title differences.

- **NHK World Japan:** 49 exact normalized programme-title and start-instant matches against
  https://masterpl.hls.nhkworld.jp/epg/w/20261106.json. Four same-start title differences reflect
  abbreviated episode labels or a generic “NHK WORLD Selection” umbrella label. The primary feed
  also contains 77 short items without a matching start in the regional guide; these mostly fit
  inside its larger programme blocks. This is not a claim that every short filler is represented.
- **Arirang:** 41 exact normalized title/start-instant matches against Arirang's public schedule
  API, selecting **WORLD (`CH_W`)**, not KOREA (`CH_K`). Twelve same-start title differences include
  live/repeat markers, year suffixes, and “Premium Collection B” versus “Premium Collection”.
  The timestamps agree; no regional time shift was applied. The source's stray JSON suffix in
  several titles was removed. Public schedule page: https://www.arirang.com/schedule.
- **NBA TV Philippines:** Its regional entry lists Miami Heat–Golden State Warriors at
  **November 6, 03:00 UTC = 11:00 Manila = November 5, 19:00 Pacific**. The Miami Heat's official
  game notes list that game's November 5 start at 22:00 Eastern, the same absolute time:
  https://www.nba.com/gamenotes/heat.pdf. This confirms that game's time conversion, **not** the
  entire NBA TV Philippines daily broadcast lineup. The channel has 85 retained entries, 56
  upcoming, with no overlaps or gaps, through **November 8, 14:30 UTC**.
- **NBA TV** is intentionally unmapped. It is a different playlist entry, and the Philippines
  schedule must not be copied to it merely because the names resemble one another.

Examples from the broadcaster comparison:

| Channel | Programme | UTC | Manila |
|---|---|---|---|
| NHK World Japan | Today's Close-Up | Nov 5 15:30 | Nov 5 23:30 |
| NHK World Japan | Backstage Japan | Nov 5 16:30 | Nov 6 00:30 |
| NHK World Japan | Core Kyoto | Nov 5 17:30 | Nov 6 01:30 |
| Arirang World | Trip In Korea | Nov 5 15:30 | Nov 5 23:30 |
| Arirang World | Re: Space | Nov 5 16:30 | Nov 6 00:30 |
| Arirang World | The Living Sea Of Jeju | Nov 5 19:50 | Nov 6 03:50 |

## Rejected source and playback limits

The Philippines mirror at https://free-epg.de/api/epg/ph.xml.gz carries the same numeric-source
wall-clock entries with **+0800**, while the tested PH2 source uses **+0000**. Comparisons against
the broadcaster schedules establish that using the mirror without correcting its own source
metadata would produce an **eight-hour error**. It was not used. It also contains many “No Data”
placeholder channels. No global time shift is needed for the chosen PH2 feed.

These checks confirm matching identities, timestamp integrity, and specific broadcaster-schedule
examples. They **do not confirm that every stream's actual picture is synchronized** with its guide.
No live stream was decoded during this EPG task, and universal schedule accuracy is not claimed.
All other mapped channels remain source-derived schedules without independent broadcaster confirmation.

Set the player's EPG time offset to **0** and its timezone to the TV's actual location.
