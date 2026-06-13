# Exclude Indian/Bollywood Content Filter (+ correctness sweep)

Date: 2026-06-13
Status: approved, Phase 1 in progress

## Goal

Add an `exclude_indian` toggle (default **ON**) that removes Indian/Bollywood
content from recommendations, mirroring the existing `exclude_anime` pattern.
Fold in correctness fixes surfaced by a 3-agent review (Opus + Qwen committee,
Codex adversarial).

## Decisions (user-confirmed)

- **Scope:** all Indian content, not just Hindi.
- **Detection:** `original_language in {hi, ta, te, ml, kn, bn, pa, mr}` OR
  `"IN" in origin_country`. **Fail open** when language is missing (do not
  over-filter).
- **Default:** ON.
- **Placement:** post-filter in `score_and_rank` (option a). Option b (TMDB
  discover push-down) is structurally impossible — discover has
  `with_original_language` (include one) but no exclusion, and ~70% of
  candidates come from `/recommendations` + `/similar` which take no language
  params.
- **Seeds/profile:** also drop Indian items from the taste-profile sample and
  resolved seeds, to stop the candidate generator chasing Bollywood for an
  Indian-heavy user (removes the empty-row cause, not just the symptom).
- **Empty rows:** stay hidden. Never backfill with filtered content.

## Review findings that shaped the design

1. **BUG-1 (HIGH) — hard prerequisite.** The recs cache key
   `user:{auth}:recs:{media_type}` (recommendations.py:583/591) omits all config
   flags. Without a config fingerprint, toggling `exclude_indian` (or
   `exclude_anime`) is inert until cache TTL (up to 4h). MUST fix or the feature
   looks broken.
2. **Second stale layer: `taste:v3`.** If `exclude_indian` filters the taste
   sample, `user:{auth}:taste:v3` (recommendations.py:363) feeds both dynamic
   and curated rows and would stay stale. Must be config-scoped / version-bumped.
   The `discover:*` keys in tmdb.py cache **raw pre-filter** candidates and must
   NOT get the config hash (verified by Codex).
3. **"Language is free in seeds/profile" is FALSE.** `_fetch_per_seed` and
   `_build_taste_profile` fetch `details_map` but read only `genre_ids` from it;
   `_attach_external_ids` does not copy `original_language`/`origin_country`. So
   `_is_indian` for seeds/profile must read language from the item OR fall back
   to `details_map` (already in hand).
4. **`register_config` bug (background.py:29)** dedupes by auth key and never
   updates stored `(config, token)`, so config changes are ignored by periodic
   warming. Fix alongside the cache key.

## Phase 1 (this change)

Wiring points for `exclude_indian` (mirror `exclude_anime` exactly):
- `app/models/config.py` — `UserConfig.exclude_indian: bool = Field(True, ...)`
- `app/api/endpoints/configure.py` — `ConfigRequest`, `UserConfig(...)`
  construction, form checkbox + JS field + `__EXCLUDE_INDIAN_CHECKED__`
  placeholder + default resolution.
- `app/services/recommendations.py` — `_is_indian` detector; filter loop
  refactored to a `(flag, predicate)` list shared by anime + indian; taste
  profile + resolved-seed filtering with details fallback.

Cache correctness:
- Add `UserConfig.cache_fingerprint()` — stable short hash over output-affecting
  fields (`min_rating`, `exclude_anime`, `exclude_indian`, `include_movies`,
  `include_series`).
- Append it to the recs key: `user:{auth}:recs:{media_type}:{fp}`.
- Version/scope the taste key with the taste-relevant flag
  (`exclude_indian`): `user:{auth}:taste:v4:{taste_fp}`.
- Leave `discover:*` keys untouched.
- Fix `register_config` to overwrite stored `(config, token)`.

Behavior invariants (no accidental change):
- Watched-set check stays FIRST.
- `min_rating` gate stays separate (not in the predicate list).
- Items without IMDB ID keep current behavior (pass scoring, dropped later in
  catalog conversion).

TDD assertions:
- `_is_indian` true for hi/ta/te/.../IN-origin; false for en/missing-language.
- Recs SWR key differs when only `exclude_indian` changes; identical otherwise.
- Taste key differs when `exclude_indian` changes.
- `discover_*` keys identical across `exclude_indian` changes.
- Seed/profile filter drops an Indian item whose base lacks `original_language`
  but whose `details` has it.
- `register_config` overwrites stored config for the same auth key.

## Phase 2 (after Phase 1, separated by risk)

**2a — genuinely safe cleanup:** delete empty `demo_niche_recs.py`; remove dead
`batch_recommendations`/`batch_similar`/`get_similar`; log swallowed `gather`
exception counts; hold `create_task` refs (with pruning); drop the dead
`cache_key` assignment at recommendations.py:583.

**2b — ranking BEHAVIOR changes (bring back to user as explicit decisions, NOT
cleanup):** `_is_anime` OR→AND; taste-affinity denominator (matching genres vs
total); rating-weight fold. Each changes existing users' recommendations.

## Phase 3 — security

HTML-escape the **string** placeholder substitutions in configure.py
(`__TMDB_DEFAULT__`, `__STREMIO_AUTH_DEFAULT__`, `__STREMIO_LOVED_DEFAULT__`).
Numeric/`checked` placeholders are not injectable.

## Deferred (Phase 4-5, separate session)

- BUG-C "Because you watched X" rows are offset-slices of one pooled list →
  serve true per-seed rows (user chose this fix).
- BUG-B watch-progress parse (needs live-Stremio verification).
- God-class decomposition, central `cache_keys.py`, config immutability.
- Latent: manifest warmer writes `catalog:{token}:...` (never read) and
  regenerates all catalog types with `generate_recommendations`.

## Baseline

40 passed / 7 pre-existing failures (manifest count drift, stremio method
rename in tests, background event-loop harness). Target: no NEW failures.
