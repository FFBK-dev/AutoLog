#!/usr/bin/env python3
"""
Batch-convert non-JPEG images to JPEG (≤50 MB) using ImageMagick 7.
Keeps colours, copies metadata with ExifTool, deletes originals.
"""

import argparse, logging, shutil, subprocess, sys
from pathlib import Path

# ── Tunables ──────────────────────────────────────────────────────────
TARGET_MB      = 50
TARGET_BYTES   = TARGET_MB * 1024 * 1024
Q_START_SMALL  = 95         # used if original already ≤ TARGET_MB
Q_START_BIG    = 92         # first try when > TARGET_MB
Q_STEP         = 5
Q_MIN          = 70
IMG_SKIP       = {".jpg", ".jpeg"}          # never reconvert these
# ──────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

def run(cmd: list[str]) -> None:
    """Run a subprocess; raise on non-zero exit."""
    logging.debug("CMD: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)

def under_limit(p: Path) -> bool:
    return p.stat().st_size <= TARGET_BYTES

def convert(src: Path) -> None:
    """Convert one file -> JPEG, copy metadata, delete src."""
    dest = src.with_suffix(".jpg")
    size_mb = src.stat().st_size / 1e6
    logging.debug("    original size %.1f MB", size_mb)

    q = Q_START_SMALL if under_limit(src) else Q_START_BIG

    while True:
        run([
            "magick", str(src),
            "-quality", str(q),
            "-interlace", "JPEG",
            "-colorspace", "sRGB",
            str(dest),
        ])
        if under_limit(dest) or q <= Q_MIN:
            break
        q -= Q_STEP
        logging.debug("      > still >%d MB, retry q=%d", TARGET_MB, q)

    # ensure writable for exiftool
    dest.chmod(dest.stat().st_mode | 0o200)

    if shutil.which("exiftool"):
        try:
            run([
                "exiftool",
                "-overwrite_original_in_place",
                "-TagsFromFile", str(src),
                "-all:all",
                str(dest),
            ])
            logging.debug("      > metadata copied")
        except subprocess.CalledProcessError as e:
            logging.warning("      > metadata copy failed (%s) – continuing", e)

    logging.debug("      > final size %.1f MB, q=%d", dest.stat().st_size/1e6, q)

    src.unlink()                       # remove original
    logging.info("    ✅ %s → %.1f MB (q=%d)", dest.name, dest.stat().st_size/1e6, q)

def gather(path: Path) -> list[Path]:
    """Return list of targets (non-recursive)."""
    if path.is_file():
        return [path] if path.suffix.lower() not in IMG_SKIP else []
    return [p for p in path.iterdir() if p.is_file() and p.suffix.lower() not in IMG_SKIP]

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert non-JPEG images to JPEG (≤50 MB).")
    ap.add_argument("source", nargs="?", help="file or folder (prompt if blank)")
    args = ap.parse_args()

    raw = (args.source or input("Enter file or folder path: ").strip()).strip("'\"")
    src_path = Path(raw).expanduser()

    if not src_path.exists():
        logging.error("Path not found: %s", src_path)
        sys.exit(1)

    targets = gather(src_path)
    if not targets:
        logging.info("No convertible images found.")
        return

    failed = []
    total = len(targets)
    logging.info("Found %d files to process\n", total)

    for idx, f in enumerate(targets, 1):
        logging.info("[%d/%d] %s", idx, total, f.name)
        try:
            convert(f)
        except Exception as e:                     # broad on purpose
            logging.error("    ❌ %s (%s)", f.name, e)
            failed.append(f)

    # ── Summary ───────────────────────────────────────────────────────
    success = total - len(failed)
    logging.info("\nFinished: %d succeeded, %d failed", success, len(failed))
    if failed:
        logging.info("Failures:")
        for f in failed:
            logging.info("   • %s", f)

if __name__ == "__main__":
    main()