"""
Stage 2 of the goal-oriented coding agent: scans the Unreal project for evidence of what exists.

Problem this solves: GetOnDaBus is Blueprint-only, so there's no source tree to grep for
symbols. The only evidence available from outside the Editor is the asset catalog itself —
every .uasset/.umap under Content/, named according to the project's prefix convention
(BP_, WBP_, DT_, DA_, IMC_, ...). This script walks that catalog and writes it to manifest.json,
which detect_gaps.py then fuzzy-matches GDD evidence tokens against. Also captures recent git
log as supplementary context. Runnable standalone for debugging.
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent
ASSET_EXTENSIONS = (".uasset", ".umap")


def find_content_dir(project_root: Path) -> Path:
    """Locate Content/ next to the project's .uproject file."""
    if not list(project_root.glob("*.uproject")):
        raise FileNotFoundError(f"No .uproject file found under {project_root}")
    content_dir = project_root / "Content"
    if not content_dir.is_dir():
        raise FileNotFoundError(f"No Content/ directory found at {content_dir}")
    return content_dir


def scan_assets(content_dir: Path) -> list[dict]:
    """Walk Content/ and collect every .uasset/.umap by filename (extension stripped) and relative path."""
    assets = []
    for path in content_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS:
            assets.append({
                "name": path.stem,
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "ext": path.suffix.lower(),
            })
    assets.sort(key=lambda a: a["path"])
    return assets


def get_git_log(project_root: Path, count: int = 20) -> list[str] | None:
    """Return the last `count` commit summaries, or None if this isn't a git repo / git isn't available."""
    if not (project_root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{count}"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def run(project_root: Path = PROJECT_ROOT, output_dir: Path = OUTPUT_DIR) -> dict:
    """Scan the project's Content/ folder and write manifest.json."""
    content_dir = find_content_dir(project_root)
    assets = scan_assets(content_dir)
    git_log = get_git_log(project_root)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project_root": str(project_root),
        "asset_count": len(assets),
        "assets": assets,
        "git_log": git_log,
    }

    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[scan_project] {len(assets)} assets found under {content_dir.relative_to(project_root)}.")
    if git_log is None:
        print("[scan_project] No .git directory found — git_log omitted.")
    else:
        print(f"[scan_project] Captured last {len(git_log)} commits as supplementary context.")

    return manifest


def _cli_main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT, help="Path to the .uproject's directory")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR, help="Directory to write manifest.json")
    args = parser.parse_args()
    run(args.project_root, args.out)


if __name__ == "__main__":
    _cli_main()
