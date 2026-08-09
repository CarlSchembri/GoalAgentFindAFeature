# Goal-Oriented Coding Agent — GetOnDaBus

A stdlib-only Python pipeline that regenerates a feature ledger from `Docs/GDD.md`, scans
`Content/` for real evidence of what's built, cross-references the two to find gaps, and
(with Claude Code driving the reasoning stages) picks one missing feature, plans it, and
builds it.

```
py Tools/GoalAgent/GoalAgentFindAFeature.py
```

or, in Claude Code: `/goal-agent-find-a-feature`

No API key, no LLM provider, no third-party packages in Stages 1–3 — just the stdlib
(`pathlib`, `re`, `json`, `argparse`, `subprocess`). Every run re-derives everything from
scratch: there is no hand-maintained ledger file, and no caching between runs. Stages 4–7
(presenting candidates, planning, executing, writing this section) are done by Claude Code
reading the stdlib stages' output directly, not by more generated code.

## Pipeline

| Stage | File | What it does |
|---|---|---|
| 1. Parse GDD | `parse_gdd.py` | Regex-parses `Docs/GDD.md`'s inline convention — a feature heading immediately followed by a parenthetical status tag, e.g. `Passenger Inventory (Completed BP_Vehicle, BP_PassengerCycler)` or `Spawn Manager (To do)`. Splits into 14 numbered sections via a sequential-number heuristic (so Section 10's internal "1. Data & Progression Agent" ... "8. Audio Agent" sub-list doesn't get mistaken for new top-level sections). Writes `feature_ledger.md` + `features.json`, prints a diff against the previous run. |
| 2. Scan codebase | `scan_project.py` | Walks `Content/` for every `.uasset`/`.umap`, since there's no `Source/` tree to grep in a Blueprint-only project — the asset catalog itself is the only evidence available from outside the Editor. Also captures `git log --oneline -20`. Writes `manifest.json`. |
| 3. Detect gaps | `detect_gaps.py` | Fuzzy-matches each feature's evidence tokens (`BP_`, `WBP_`, `DT_`, `DA_`, `IMC_`, ... prefixed names pulled from the GDD's status tags) against the manifest. Classifies each feature `CONFIRMED_DONE` / `CONTRADICTED` / `CONFIRMED_MISSING` / `UNVERIFIABLE` / `SKIP`. Writes `gap_report.json` + a printed summary table. |
| 4–7 | (Claude Code, live) | Presents 2–4 candidates with reasoning, proposes a build plan for the one picked, executes it (direct MCP / copy-paste prompt / guided walkthrough), and writes this file's build record. |

`GoalAgentFindAFeature.py` chains Stages 1–3 as direct function calls in one process — they
are never run as three separate manual steps from the user's side.

## A real wrinkle Stage 3 surfaced

On the first real run against the (now-tagged) GDD, **zero** features landed in
`CONFIRMED_MISSING` or `CONTRADICTED` — every `To do`-tagged feature in this GDD is written
as freeform prose with no asset name in it (only `Completed` tags name assets), so they all
fell into `UNVERIFIABLE` rather than `CONFIRMED_MISSING`. The slash command's Stage 4
instructions account for this: when the primary pool is empty, `TODO`-status `UNVERIFIABLE`
features are the practical equivalent for this GDD's convention (confirmed-missing via
absence of a checkable name, rather than via a failed token match).

Stage 3 also caught one true contradiction that wasn't in the evidence-token match at all:
`DT_DriverRewards` and `Struct_DriverReward` already exist in `Content/BP/Data/` (from an
earlier build), but the GDD still tags "Driver Rewards" as `To do` — the note names
follow-up UI work (a Transit Ladder widget), not the data layer, so the tag isn't fully
stale, just imprecise. Surfaced during Stage 4 reasoning, not by the automated classifier.

## What feature did it build, and why

**Drop-Off Scoring Zones** — `FEAT-drop-off-scoring-zones` (GDD Section 4, cross-referenced
with Section 8's exact tier table).

Picked over three other `TODO` candidates (Passenger Quota HUD, City Destruction price
table, Driver Rewards' Transit Ladder widget) because it's the single biggest lever in the
gap report: five *other* separately-tagged `TODO` features — Fare Balance, Passenger Fares,
Currency Values, Target Scoring, and End-of-Shift Report & Grade — all depend on a tiered
scoring result existing before they can do anything. It's also fully specified (GDD Section
8 already gives exact values: Awful +0s/+$0 through Perfect +18s/+$15) and the sprint plan
(Section 14, Week 2) names it as the top outstanding scoring priority. Cleanly schema-able
as a DataTable — Data & Progression Agent territory per Section 10 — rather than something
that needs new design decisions to generate.

## What got built

- **`Struct_ScoringTier`** (`Content/BP/Data/`) — the one manual step, created by hand in
  the Editor's struct editor (same constraint as the earlier Driver Rewards build:
  `FStructureEditorUtils` has no Python/Blueprint binding, and this project's `unreal-mcp`
  toolset exposes no struct-creation tool either — confirmed by checking `AssetTools`,
  `ObjectTools`, `DataTableTools`, and `BlueprintTools` directly). Fields: `TierName` (Name),
  `DisplayLabel` (Text), `TimeBonusSeconds` (Integer), `MoneyBonus` (Integer).
- **`DT_DropOffScoringTiers`** (`Content/BP/Data/`) — created live via `unreal-mcp`'s
  `DataTableTools.create` against `Struct_ScoringTier`, then populated with 5 rows
  (`Awful`/`Bad`/`OK`/`Good`/`Perfect`) transcribed exactly from the GDD's Section 8 table.
  Verified post-write via `get_rows` — all 5 rows confirmed correct, including `Perfect`'s
  `DisplayLabel` of `"Perfect!"` with the exclamation point from the GDD text.
- **`BP_Destination`** (existing actor, extended not replaced) — two new variables added via
  `BlueprintTools.add_object_variable`/`add_variable`: `ScoringTiersTable` (DataTable
  reference, defaulted to `DT_DropOffScoringTiers`) and `LastScoredTier` (Name). Blueprint
  compiled and all three assets saved.
- **`generated/FEAT-drop-off-scoring-zones.py`** — standalone Unreal Editor Python Scripting
  fallback that reproduces the same build without depending on `unreal-mcp` being connected,
  per the assignment's requirement to always produce this regardless of which execution path
  was actually used.

## Explicitly out of scope (real Blueprint-only boundary)

- The event-graph logic that measures a landed NPC's distance from `BP_Destination`'s
  center and looks up which tier it falls into. The GDD gives tier *payouts* but never
  specifies the physical boundary radii between tiers — it says outright that these values
  need playtest verification — so there's nothing to generate there even in principle;
  that's tuning work to be done by hand.
- The dancing/reaction animations, the money-popup widget, and the "Red X" bad-drop widget
  described in Section 4 — animation Blueprint and UI/HUD event-graph wiring, not data.
- Hooking `LastScoredTier` into Fare Balance / clock-extension logic — the downstream
  systems (still separately `TODO`) that would read this new table, not part of this
  feature's scaffold.

## Was I able to run this in the game?

**Execution path used: Direct MCP execution**, live against the running Editor via the
`unreal-mcp` connection (not the copy-paste-prompt or guided-walkthrough paths).

_(Placeholder — fill in after testing in the Editor / PIE.)_
