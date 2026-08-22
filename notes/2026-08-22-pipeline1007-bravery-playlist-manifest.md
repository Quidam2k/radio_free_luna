# Pipeline #1007 — Themed Playlist Manifest: BRAVERY / COURAGE / DANGER

**Status:** DRAFT for Jarvis + Karen curation review. **Nothing aired.**
**Assignment:** #3157 · suggestion #1007 · target label `playlist-bravery`
**Author:** worker-rfl-playlist-bravery--20260822-172918-ffc8
**Date:** 2026-08-22

## Seed
**"What's Up Danger"** — Blackway & Black Caviar (*Spider-Man: Into the Spider-Verse* OST, 2018).
Present in RFL DB (id lookup: title/artist fields are scrambled — stored as artist
`What's Up Danger(Movie Version Edit)`, title `Spider-Man Into the Spider-Verse Soundtrack | ...`).
Also on disk: `E:\Stacked Deck\Music\VA - Spider-Man Into the Spider-Verse OST (2018)\1 What's Up Danger.mp3`.
The thematic thesis of the whole set: the leap-of-faith — courage answering danger.

## Methodology
- **Sources mined:** RFL catalog (3,197 tracks, 3,174 from Stacked Deck) across
  title / artist / album / file_path / AI `track_analysis.themes` + `summary`;
  PLUS the `Todd Walker - music` disk folder (see gap note).
- **Vocabulary:** word-boundary matched. Courage cluster (brave, valor, hero,
  fearless, daring, bold, warrior, invincible, fight, rise, survive, stand,
  strength…), Danger cluster (danger, risk, peril, threat, war, kill, death,
  blood, storm, fire, dark, shadow, devil, beast, edge, chase…), and a Fear /
  cowardice antonym cluster (coward, afraid, scared, run, hide, flee, surrender…)
  used as the narrative *foil*.
- **Field weighting:** title×3, themes×2, path×1.2, album×1.5, artist×1, summary×0.6.
- **#1006 weighting applied:** `Todd Walker - music` ×2.0 boost; Cirque du Soleil ×1.6 boost.
- **Freshness (session_manager.calculate_freshness):** computed per track
  (1.0 − min(0.5, play_count/50) − same-day repeat penalty). Whole catalog is
  currently fresh=1.0 (no recent play history), so freshness did not separate
  candidates this round — flagged for the curators as a live-rotation factor, not
  a pruning factor here.
- Raw mine returned **411 candidates**; hand-curated below (raw score has known
  metaphor noise — e.g. fire-as-passion, shadow ballads — pushed to Stretch).

## ⚠️ GAP for orchestrator attention
The **`Todd Walker - music`** folder (a #1006 weighting favorite) has **0 tracks
in the RFL database** — it is NOT indexed. 364 files on disk (m4a/opus dupes).
I scanned it directly off disk to honor the weighting, but these tracks can't be
sequenced/aired by RFL until someone adds
`E:\Stacked Deck\Music\Todd Walker - music` to `MUSIC_DIRECTORIES` and lets the
file monitor + analyzer ingest them. **Recommend a follow-up ticket.** Cirque IS
indexed (84 rows).

---

## STRONG — direct, on-theme, high confidence

### Courage
- **Brave** — Sara Bareilles · "I wanna see you be brave" — the mission statement.
- **Fight Song** — Rachel Platten · scrappy-underdog defiance anthem.
- **Fight Like a Brave** — Red Hot Chili Peppers · title does the work; get-back-up funk.
- **I Will Survive** — Cake (cover) · survivor's creed with a deadpan swagger.
- **Stand And Deliver** — Adam & The Ants · highwayman bravado — danger *and* dash.
- **Fearless** — Attaboy · 🟢 TODD-WALKER · courage named outright.
- **Resilient** — Rising Appalachia · 🟢 TODD-WALKER · standing back up as chorus.
- **Bella Ciao** — 🟢 TODD-WALKER · partisan resistance anthem — courage under occupation.
- **Let Me Fall** — Cirque du Soleil (*Quidam*) · 🔵 CIRQUE · the leap-of-faith ballad; pairs with the seed.

### Danger
- **Running with the Devil** — Van Halen · reckless-danger swagger.
- **Threat** — Cirque du Soleil · 🔵 CIRQUE · pure menace, wordless.
- **Riders on the Storm** — The Doors · "there's a killer on the road."
- **War Pigs** — Black Sabbath · war as horror.
- **Sunday Bloody Sunday** — U2 · danger + defiance in one.
- **The Dogs of War** — 🟢 TODD-WALKER · Pink Floyd — mercenary menace.
- **OTYKEN — Storm** — 🟢 TODD-WALKER · primal, tribal danger.
- **Psycho Killer** — Talking Heads · 🟢 TODD-WALKER · twitchy dread.

## MEDIUM — solid theme, single strong signal or lightly metaphorical
- **Do Not Go Gentle Into That Night** — Dylan Thomas · rage against the dying — courage vs. death (spoken).
- **It Is a Good Day to Die** — Robbie Robertson · warrior's calm before battle.
- **Words of Fire, Deeds of Blood** — Robbie Robertson · war-drum intensity.
- **Get Up, Stand Up** — Peter Gabriel · stand-your-ground defiance.
- **Stand** — Sly & the Family Stone · take-your-stand soul.
- **Stand Together** — Beastie Boys · solidarity-as-courage.
- **Strong Enough** — Sheryl Crow · quieter nerve.
- **Market Square Heroes** — Marillion · everyman-hero prog.
- **Into the Fire** — Sarah McLachlan · walking into the trial.
- **Walk Through the Fire** — Peter Gabriel · trial-by-fire.
- **Crash and Burn** — Sheryl Crow · the risk and its cost.
- **Chain Lightning** — Rush · charged danger.
- **Witch Hunt** — Rush · 🟢 TODD-WALKER · fear & persecution (the mob as danger).
- **Double Edge** — Emika · 🟢 TODD-WALKER · living on the knife's edge.
- **Kill!** — The Raveonettes · 🟢 TODD-WALKER · noir menace.
- **Alegría** — Cirque du Soleil · 🔵 CIRQUE · defiant, triumphant joy.
- **Banquine** — Cirque du Soleil · 🔵 CIRQUE · high-flying acrobatic tension.

## STRETCH — metaphorical, atmospheric, or the FEAR/cowardice foil (narrative contrast)
*The shadow side — for arc/contrast; curators may keep a few as counterweight.*
- **Run Runaway** — Slade · the flight instinct (foil).
- **Hide and Seek** — Imogen Heap · 🟢 TODD-WALKER · hiding (foil).
- **Surrender** — Cheap Trick · 🟢 TODD-WALKER · ironic capitulation (foil).
- **Sweet Surrender** — Sarah McLachlan · giving in (foil).
- **Fear** — Sarah McLachlan · names the enemy directly (foil).
- **Take My Breath Away** — Berlin · 🟢 TODD-WALKER · Top Gun "danger zone" adjacency.
- **House of the Rising Sun** — cautionary danger tale.
- **Ring of Fire / Play With Fire / Kiss of Fire** — fire-as-passion (metaphor stretch).
- **Out of the Shadows / Chasing Shadows / Between the Shadows** — shadow ballads (atmosphere).
- **Flying / Journey of Man / Reach for Me Now** — Cirque · 🔵 CIRQUE · leap/quest atmosphere.

---

## Proposed mix names — Ren Faire binomial-pair house style (Todd picks)
House precedent in library: *Northern Ren Faire '05* mixes ("Wishin' & Hopin'").
1. **Valor & Venom** — the courage/danger duality, straight up.
2. **Mettle & Menace** — nerve tested against the thing that threatens it.
3. **Dare & Dread** — the leap and the fear it answers (tightest tie to the "What's Up Danger" seed).
*(Ren-faire-flavored alt: **Pluck & Peril**.)*

## Notes for curators
- 🟢 = `Todd Walker - music` (disk-only, needs indexing before it can air — see gap).
- 🔵 = Cirque du Soleil (indexed, #1006-boosted).
- Full raw 411-candidate dump preserved at scratchpad `candidates.json` if you want to widen.
- Suggested arc: open on the seed (**What's Up Danger**) → Strong-Danger to set stakes →
  Strong-Courage as the answer → dip a Fear-foil for contrast → close triumphant
  (**Let Me Fall** / **Alegría** / **I Will Survive**).
