"""
Stage 3 of the goal-oriented coding agent: cross-references the GDD's feature ledger against
the actual project manifest to find real gaps.

Problem this solves: the GDD's inline status tags (Completed/To do/...) are hand-written and
can go stale in either direction — a feature marked "Completed" might reference an asset that
was renamed or never actually created, and a feature marked "To do" might already have partial
evidence sitting in Content/ from earlier exploratory work. This script doesn't trust the tag by
itself; it fuzzy-matches each feature's evidence tokens against the real asset manifest and
classifies the result, so Stage 4 (candidate selection) works from verified gaps rather than
GDD claims. Runnable standalone for debugging.
"""

import argparse
import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent

DONE_LIKE = {"DONE", "IN_PROGRESS"}
TODO_LIKE = {"TODO"}
SKIP_LIKE = {"NOT_V1", "CUT_FOR_V1"}


def _asset_matches_token(token: str, asset_name: str) -> bool:
    """Case-insensitive substring match in either direction (handles partial/renamed evidence)."""
    t, a = token.lower(), asset_name.lower()
    return t in a or a in t


def classify_feature(feature: dict, asset_names: list[str]) -> dict:
    """
    Classify one feature's evidence against the manifest.

    - SKIP: status is NOT_V1 or CUT_FOR_V1 — out of scope, not a real gap.
    - UNVERIFIABLE: no evidence tokens to check (common for freeform "To do" notes with no
      named assets yet).
    - For DONE/IN_PROGRESS-tagged features: CONFIRMED_DONE if every evidence token matches an
      asset, else CONTRADICTED (the GDD claims done/in-progress but the evidence doesn't back
      it up — flagged loudly since the tag may be stale).
    - For TODO-tagged features: CONFIRMED_MISSING if no evidence token matches anything (the
      GDD's "to do" claim holds up), else CONTRADICTED (an extension beyond the spec's example:
      evidence already exists despite the "to do" tag, so the GDD may be stale in the *other*
      direction — same label, opposite cause).
    """
    status = feature["status"]
    evidence = feature["evidence"]

    if status in SKIP_LIKE:
        return {**feature, "matched_evidence": [], "unmatched_evidence": evidence, "classification": "SKIP"}

    if not evidence:
        return {**feature, "matched_evidence": [], "unmatched_evidence": [], "classification": "UNVERIFIABLE"}

    matched = [tok for tok in evidence if any(_asset_matches_token(tok, name) for name in asset_names)]
    unmatched = [tok for tok in evidence if tok not in matched]
    all_found = len(matched) == len(evidence)
    none_found = len(matched) == 0

    if status in DONE_LIKE:
        classification = "CONFIRMED_DONE" if all_found else "CONTRADICTED"
    elif status in TODO_LIKE:
        classification = "CONFIRMED_MISSING" if none_found else "CONTRADICTED"
    else:
        classification = "UNVERIFIABLE"

    return {**feature, "matched_evidence": matched, "unmatched_evidence": unmatched, "classification": classification}


def detect_gaps(features: list[dict], asset_names: list[str]) -> list[dict]:
    return [classify_feature(f, asset_names) for f in features]


def print_summary(results: list[dict]) -> None:
    counts: dict[str, int] = {}
    for r in results:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1

    print("[detect_gaps] Summary:")
    for classification in ["CONFIRMED_DONE", "CONTRADICTED", "CONFIRMED_MISSING", "UNVERIFIABLE", "SKIP"]:
        if classification in counts:
            print(f"  {classification:<18} {counts[classification]}")

    contradicted = [r for r in results if r["classification"] == "CONTRADICTED"]
    if contradicted:
        print("[detect_gaps] CONTRADICTED (GDD tag may be stale):")
        for r in contradicted:
            print(f"    {r['id']} — {r['name']} — GDD says {r['status']}, "
                  f"matched {r['matched_evidence']} / evidence {r['evidence']}")

    missing = [r for r in results if r["classification"] == "CONFIRMED_MISSING"]
    if missing:
        print(f"[detect_gaps] {len(missing)} CONFIRMED_MISSING feature(s) available as build candidates.")


def run(features_path: Path, manifest_path: Path, output_dir: Path = OUTPUT_DIR) -> dict:
    """Load features.json and manifest.json, classify every feature, write gap_report.json."""
    features_payload = json.loads(features_path.read_text(encoding="utf-8"))
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    asset_names = [a["name"] for a in manifest_payload["assets"]]
    results = detect_gaps(features_payload["features"], asset_names)

    report = {
        "gdd_generated_at": features_payload.get("generated_at"),
        "manifest_generated_at": manifest_payload.get("generated_at"),
        "asset_count": manifest_payload.get("asset_count"),
        "results": results,
    }
    (output_dir / "gap_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print_summary(results)
    return report


def _cli_main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=OUTPUT_DIR / "features.json")
    parser.add_argument("--manifest", type=Path, default=OUTPUT_DIR / "manifest.json")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="Directory to write gap_report.json")
    args = parser.parse_args()
    run(args.features, args.manifest, args.out)


if __name__ == "__main__":
    _cli_main()
