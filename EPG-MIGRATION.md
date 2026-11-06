# EPG consolidation

The source configuration and channel identities from tr3nching/ph-epg have been incorporated here. `scripts/update_epg.py` is the only EPG builder and `scripts/refresh.mjs` is the only M3U builder. The EPG builder reads the local catalog directly and downloads source feeds; it does not depend on another playlist or generated guide.

Prior counts of 185 represented source matches, including expired-only programmes and some wrong identities. Current and total matches are reported separately. Existing source offsets are preserved; listings are normalized to UTC. Known station mismatches have explicit strict mappings; later feeds may recover stale or invalid first choices.
