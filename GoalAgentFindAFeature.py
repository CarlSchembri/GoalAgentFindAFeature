"""
Entry point for the goal-oriented coding agent.

Problem this solves: parse_gdd.py, scan_project.py, and detect_gaps.py are each independently
debuggable, but the actual workflow is "run all three, then look at gap_report.json" — never
three separate manual steps. This script chains them in one process, exiting once gap_report.json
exists. It always regenerates every output from scratch (no caching): the GDD is assumed to have
changed since the last run, so every run does a fresh parse -> scan -> detect pass.

What happens after this script exits (presenting candidate features, proposing a build plan,
executing it, writing the README) is deliberately not implemented here — that reasoning is done
by Claude Code reading gap_report.json directly, not by more stdlib code. See
.claude/commands/goal-agent-find-a-feature.md for how those stages continue the same run.
"""

from pathlib import Path

import detect_gaps
import parse_gdd
import scan_project

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
GDD_PATH = PROJECT_ROOT / "Docs" / "GDD.md"


def main() -> None:
    print("=== Stage 1/3: Parsing GDD ===")
    parse_gdd.run(GDD_PATH, TOOLS_DIR)

    print("\n=== Stage 2/3: Scanning codebase ===")
    scan_project.run(PROJECT_ROOT, TOOLS_DIR)

    print("\n=== Stage 3/3: Detecting gaps ===")
    detect_gaps.run(TOOLS_DIR / "features.json", TOOLS_DIR / "manifest.json", TOOLS_DIR)

    print(f"\n[GoalAgentFindAFeature] Done. See {(TOOLS_DIR / 'gap_report.json').relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
