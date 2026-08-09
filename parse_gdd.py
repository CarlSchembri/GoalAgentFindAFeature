"""
Stage 1 of the goal-oriented coding agent: regenerates the feature ledger from Docs/GDD.md.

Problem this solves: the GDD is the single source of truth for what's built vs. not, using
an inline convention — a feature heading immediately followed by a parenthetical status tag,
e.g. "Passenger Inventory (Completed BP_Vehicle, BP_PassengerCycler)" or "Spawn Manager (To do)".
There is deliberately no hand-maintained ledger file: this script re-derives feature_ledger.md
and features.json from the GDD text on every run, so the ledger can never drift from the design
doc. Runnable standalone for debugging the regex against real GDD text.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GDD_PATH = PROJECT_ROOT / "Docs" / "GDD.md"
OUTPUT_DIR = Path(__file__).resolve().parent

# Ordered longest-first so "cut for v1" is preferred over a shorter accidental
# prefix match; all are matched case-insensitively at the start of a parenthetical.
STATUS_KEYWORDS = ["cut for v1", "not v1", "in progress", "completed", "to do"]
STATUS_MAP = {
    "completed": "DONE",
    "to do": "TODO",
    "in progress": "IN_PROGRESS",
    "not v1": "NOT_V1",
    "cut for v1": "CUT_FOR_V1",
}
STATUS_RE = re.compile(
    r"^(?P<kw>" + "|".join(re.escape(k) for k in sorted(STATUS_KEYWORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Numbered top-level section headers, e.g. "1.Overview" or "3. Driving & Controls (Completed IMC_MyGame)".
SECTION_HEADER_RE = re.compile(r"^(\d+)\.\s*(.+)$")

# One or more trailing "(...)" groups at the end of a line, e.g. a heading followed by
# "(Completed BP_X) (To do: more work)". No nested parens appear in this GDD's convention.
PARENS_TAIL_RE = re.compile(r"^(?P<heading>.*?)\s*(?P<parens>(?:\([^()]*\)\s*)+)$")

# Unreal asset-naming convention: BP_, WBP_, DT_, DA_, UDA_, IMC_, STT_, BT_, AIC_, S_, etc.
EVIDENCE_TOKEN_RE = re.compile(r"[A-Z]{1,4}_\w+")


def slugify(text: str) -> str:
    """Turn a feature name into a stable id fragment, e.g. 'Driving & Controls' -> 'driving-and-controls'."""
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def split_heading_and_parens(text: str) -> tuple[str, list[str]]:
    """Split a line into its heading text and the raw contents of any trailing '(...)' groups."""
    match = PARENS_TAIL_RE.match(text)
    if not match:
        return text.strip(), []
    heading = match.group("heading").strip()
    paren_groups = re.findall(r"\(([^()]*)\)", match.group("parens"))
    return heading, paren_groups


def extract_feature_from_line(line: str) -> dict | None:
    """
    Return a feature dict if `line` is a status-tagged heading, else None.

    A line qualifies if, after stripping an optional leading "N. " section-number
    prefix, it ends in one or more "(...)" groups and the FIRST such group starts
    with a recognized status keyword. Only the first parenthetical determines status;
    any later ones are folded into the note as extra context (real GDD headings like
    "Fairweather PSA (Completed WBP_FairweatherPSA) (To do: need background image...)"
    carry two).
    """
    section_match = SECTION_HEADER_RE.match(line)
    text_for_heading = section_match.group(2) if section_match else line

    heading, paren_groups = split_heading_and_parens(text_for_heading)
    if not heading or not paren_groups:
        return None

    first = paren_groups[0].strip()
    status_match = STATUS_RE.match(first)
    if not status_match:
        return None

    status_raw = status_match.group("kw")
    status = STATUS_MAP[status_raw.lower()]
    remainder = first[status_match.end():].strip(" :,-")

    extra_parens = paren_groups[1:]
    note = remainder
    if extra_parens:
        extra_text = " ".join(f"({p.strip()})" for p in extra_parens)
        note = f"{note} | also: {extra_text}" if note else f"also: {extra_text}"

    evidence_source = " ".join([first] + extra_parens)
    evidence = list(dict.fromkeys(EVIDENCE_TOKEN_RE.findall(evidence_source)))

    return {
        "id": f"FEAT-{slugify(heading)}",
        "name": heading,
        "status": status,
        "status_raw": status_raw,
        "evidence": evidence,
        "note": note,
    }


def parse_gdd(gdd_path: Path) -> dict:
    """Parse the GDD into numbered sections and status-tagged features."""
    lines = gdd_path.read_text(encoding="utf-8").splitlines()

    sections: list[dict] = []
    features: list[dict] = []

    current_section_number = 0
    current_section_name = "(preamble)"
    expected_next = 1

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        section_match = SECTION_HEADER_RE.match(line)
        if section_match:
            num = int(section_match.group(1))
            if num == expected_next:
                heading_text, _ = split_heading_and_parens(section_match.group(2))
                current_section_number = num
                current_section_name = heading_text
                sections.append({"number": num, "name": current_section_name, "line": line_no})
                expected_next += 1

        feature = extract_feature_from_line(line)
        if feature:
            feature["section_number"] = current_section_number
            feature["section_name"] = current_section_name
            feature["line_number"] = line_no
            features.append(feature)

    return {"sections": sections, "features": features}


def diff_features(old_features: list[dict], new_features: list[dict]) -> dict:
    """Compare two features.json feature lists by id and summarize what changed."""
    old_by_id = {f["id"]: f for f in old_features}
    new_by_id = {f["id"]: f for f in new_features}

    added = [fid for fid in new_by_id if fid not in old_by_id]
    removed = [fid for fid in old_by_id if fid not in new_by_id]
    status_changed = [
        (fid, old_by_id[fid]["status"], new_by_id[fid]["status"])
        for fid in new_by_id
        if fid in old_by_id and old_by_id[fid]["status"] != new_by_id[fid]["status"]
    ]
    return {"added": added, "removed": removed, "status_changed": status_changed}


def write_ledger_markdown(parsed: dict, gdd_path: Path, out_path: Path) -> None:
    lines = [
        "# Feature Ledger",
        "",
        "Auto-generated by `parse_gdd.py` — do not hand-edit, it is overwritten every run.",
        f"",
        f"Source: `{gdd_path.relative_to(PROJECT_ROOT)}`  ",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
    ]
    features_by_section: dict[int, list[dict]] = {}
    for f in parsed["features"]:
        features_by_section.setdefault(f["section_number"], []).append(f)

    for section in parsed["sections"]:
        section_features = features_by_section.get(section["number"], [])
        if not section_features:
            continue
        lines.append(f"## {section['number']}. {section['name']}")
        lines.append("")
        for f in section_features:
            evidence = ", ".join(f["evidence"]) if f["evidence"] else "(none)"
            note = f" — {f['note']}" if f["note"] else ""
            lines.append(f"- **{f['id']}** — {f['name']} — `{f['status']}` — evidence: {evidence}{note}")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def run(gdd_path: Path = DEFAULT_GDD_PATH, output_dir: Path = OUTPUT_DIR) -> dict:
    """Parse the GDD, regenerate the ledger, print a diff against the previous run, return the result."""
    parsed = parse_gdd(gdd_path)

    features_json_path = output_dir / "features.json"
    old_features: list[dict] = []
    if features_json_path.exists():
        try:
            old_features = json.loads(features_json_path.read_text(encoding="utf-8")).get("features", [])
        except (json.JSONDecodeError, OSError):
            old_features = []

    diff = diff_features(old_features, parsed["features"])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gdd_path": str(gdd_path.relative_to(PROJECT_ROOT)),
        "sections": parsed["sections"],
        "features": parsed["features"],
    }
    features_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_ledger_markdown(parsed, gdd_path, output_dir / "feature_ledger.md")

    print(f"[parse_gdd] {len(parsed['sections'])} sections, {len(parsed['features'])} status-tagged features found.")
    if not old_features:
        print("[parse_gdd] No previous features.json — this is the first run (or it was missing/unreadable).")
    else:
        if diff["added"]:
            print(f"[parse_gdd] New features: {', '.join(diff['added'])}")
        if diff["removed"]:
            print(f"[parse_gdd] Features no longer in GDD: {', '.join(diff['removed'])}")
        if diff["status_changed"]:
            for fid, old_status, new_status in diff["status_changed"]:
                print(f"[parse_gdd] Status changed: {fid} {old_status} -> {new_status}")
        if not (diff["added"] or diff["removed"] or diff["status_changed"]):
            print("[parse_gdd] No changes since last run.")

    return {"parsed": parsed, "diff": diff}


def _cli_main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gdd", type=Path, default=DEFAULT_GDD_PATH, help="Path to GDD.md")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="Directory to write feature_ledger.md/features.json")
    args = parser.parse_args()
    run(args.gdd, args.out)


if __name__ == "__main__":
    _cli_main()
