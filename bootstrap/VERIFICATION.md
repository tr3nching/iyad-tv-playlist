# Programme-guide verification — November 6, 2026

Generated **2026-11-06 16:14:18 UTC** (08:14:18 Pacific Standard Time).

**37 of 246 channels** have real, current programme schedules, totalling **3,755 programme entries**.
**209 remain unmapped:** 148 have no unambiguous regional mapping; 61 mapped identities have no
current eligible real programmes in the two sources. Placeholder “No Data” and station-name-only schedules
are excluded. Channel IDs match the cleaned playlist names exactly.

Sources: https://m3u-edit.com/epg-source.php?file=PH2.xml.gz and
https://m3u-edit.com/epg-source.php?file=PH1.xml.gz, as listed at https://m3u-edit.com/epg.
The live response was retrieved successfully on November 6; it does not supply a Last-Modified
header. Feed freshness is therefore established from retrieval time and programme date ranges,
not an invented provider generation timestamp. SHA-256 and per-channel ranges are recorded
in `epg-status.json`. Overall retained coverage ends November 9, 06:20 UTC; individual channels
end earlier. **No overlapping programme entries** were found. All accepted timestamps have
explicit UTC offsets and positive durations. Gaps are reported per channel.

## PH1 + PH2 source comparison

| Source | Channel definitions | Programme entries in source | Selected channels | Selected programmes |
|---|---:|---:|---:|---:|
| PH1 | 134 | **0** | 0 | 0 |
| PH2 | 111 | 5,960 | 37 | 3,755 |

Why 37 of the 111 PH2 definitions are used:

- 43 definitions contain zero programme entries.
- 19 contain only expired programme entries.
- 7 contain only station-name placeholder blocks.
- 37 match current primary playlist channels and contain usable schedules.
- 5 have current schedules for alternate or absent primary channels: DreamWorks (Tagalized),
  Kapatid Channel, One Sports+, Premier Sports 2, SPOTV 2. These are different feeds from the
  main entries in this 246-channel playlist; substituting them would display wrong programme guides.

The complete 111-definition categorization is in `ph2-coverage-breakdown.json`.
Four corrected regional matches expanded the guide from 33 to 37: Al Jazeera, CNN HD,
TVN, and TVN Movies. The catalog marks the news feeds as Cignal/local; TVN has explicit
Philippines/local tags and the provider identifier `cg_tvnpre`, while TVN Movies uses the
same provider's `cg_tvnmovie` and a source logo named `tvn_movies_267`.

PH1 was fetched successfully twice, not rejected due to a name or timezone assumption.
Its XML declares 134 channels but has **no `<programme>` elements and no timestamps to compare**.
Its SHA-256 is `e922619ba961d88eeb3c8e990d4dd2ce98cbc4c3820a1622d126210b1ed07c3e`.
PH2 SHA-256 is `78b63658427351c389912b0121d7e6e8e7facb6cb331f6d00cfa167cf67238ba`.
The source XML contains 5,883 +0000 entries and 77 +0800 entries; each explicit offset is honored.

The updater now fetches both sources independently and includes explicit PH1 HD/SD aliases.
When PH1 programme data returns, it requires at least three exact UTC/title matches across
at least two shared PH2 channels before using PH1 for uncovered channels. A coherent nonzero
shift is withheld for review; **no automatic time shift** is applied. It always prefers a
current PH2 schedule, then eligible PH1 HD/SD, selecting one source per channel. It never
interleaves overlapping source schedules. Candidates with overlapping programmes are rejected.
Four automated tests pass: PH1 empty, matching UTC instants, eight-hour shift rejection,
and clean PH2 preference/PH1 fallback without duplicate schedules.

## Independent alignment evidence

The separate `independent-alignment.json` records broadcaster checks, examples, and title differences.

- **NHK World Japan:** 47 exact normalized programme-title and start-instant matches against
  https://masterpl.hls.nhkworld.jp/epg/w/20261106.json. Four same-start title differences reflect
  abbreviated episode labels or a generic “NHK WORLD Selection” umbrella label. The primary feed
  also contains 79 items without a matching start in the retained guide window; these mostly fit
  inside its larger programme blocks. This is not a claim that every short filler is represented.
- **Arirang:** 39 exact normalized title/start-instant matches against Arirang's public schedule
  API, selecting **WORLD (`CH_W`)**, not KOREA (`CH_K`). Twelve same-start title differences include
  live/repeat markers, year suffixes, and “Premium Collection B” versus “Premium Collection”.
  The timestamps agree; no regional time shift was applied. The source's stray JSON suffix in
  several titles was removed. Public schedule page: https://www.arirang.com/schedule.
- **NBA TV Philippines:** Its regional entry lists Miami Heat–Golden State Warriors at
  **November 6, 03:00 UTC = 11:00 Manila = November 5, 19:00 Pacific**. The Miami Heat's official
  game notes list that game's November 5 start at 22:00 Eastern, the same absolute time:
  https://www.nba.com/gamenotes/heat.pdf. This confirms that game's time conversion, **not** the
  entire NBA TV Philippines daily broadcast lineup. The channel has 83 retained entries, 54
  upcoming, with no overlaps or gaps, through **November 8, 14:30 UTC**.
- **NBA TV** is intentionally unmapped. It is a different playlist entry, and the Philippines
  schedule must not be copied to it merely because the names resemble one another.

Examples from the broadcaster comparison:

| Channel | Programme | UTC | Manila |
|---|---|---|---|
| NHK World Japan | Backstage Japan | Nov 5 16:30 | Nov 6 00:30 |
| NHK World Japan | Core Kyoto | Nov 5 17:30 | Nov 6 01:30 |
| NHK World Japan | Hometown Stories | Nov 5 19:00 | Nov 6 03:00 |
| Arirang World | Re: Space | Nov 5 16:30 | Nov 6 00:30 |
| Arirang World | The Living Sea Of Jeju | Nov 5 19:50 | Nov 6 03:50 |
| Arirang World | Moo No Plan | Nov 5 20:00 | Nov 6 04:00 |

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
