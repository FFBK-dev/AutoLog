#!/usr/bin/env python3
"""
import_ale.py
─────────────
Receives raw ALE text on the command-line, parses it, then updates the
Start / End *and* Duration time-codes in FileMaker.

Endpoint      : /run/import_ale
Required JSON : {"ale_text": "<full ALE file contents>"}
"""

__ARGS__ = ["ale_text"]           # fast-loader knows we expect 1 CLI arg

# ─────────────── imports & plumbing ───────────────
import re, csv, io, sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))   # project root
import config as cfg                                          # FM helpers
# ──────────────────────────────────────────────────

# ───── tweak these constants for your solution only ─────
LAYOUT         = "Footage"
MATCH_FIELD    = "INFO_Filename"

START_FIELD    = "SPECS_File_startTC"
END_FIELD      = "SPECS_File_endTC"
DUR_FIELD      = "SPECS_File_Duration_Timecode"      # ← NEW
FPS_FIELD      = "SPECS_File_Framerate"              # ← NEW
# ─────────────────────────────────────────────────────────

def parse_ale(text: str):
    """Return list[dict] of ALE rows (normalises line-endings & tabs)."""
    text = re.sub(r"\r\n?", "\n", text)
    m = re.search(r"(?ms)^Column\s*\n([^\n]+?)\n+Data\s*\n", text)
    if not m:
        sys.exit("❌  Column/Data section not found.")
    headers = [h.strip() or f"COL{i}"
               for i, h in enumerate(re.split(r"\t+", m.group(1)))]
    reader  = csv.DictReader(io.StringIO(text[m.end():]),
                             fieldnames=headers, delimiter="\t")
    return [row for row in reader if any(row.values())]

def main(raw_text: str):
    print("🚀  ALE → FileMaker sync …")
    rows = parse_ale(raw_text)

    # locate required columns (case-insensitive)
    def col(name): return next(k for k in rows[0] if k.lower() == name.lower())
    src_col   = col("Source File")
    st_col    = col("Start")
    end_col   = col("End")
    dur_col   = col("Duration")          # ← NEW
    fps_col   = col("FPS")               # ← NEW

    tok, done, missing = cfg.get_token(), 0, 0

    for r in rows:
        fname = r[src_col].strip()
        if not fname:
            continue                             # skip blank lines

        try:
            rec_id = cfg.find_record_id(tok, LAYOUT, {MATCH_FIELD: fname})
        except RuntimeError:
            missing += 1
            print(f"⚠️  No match for {fname}")
            continue

        field_data = {
            START_FIELD: r[st_col].strip(),
            END_FIELD  : r[end_col].strip(),
            DUR_FIELD  : r[dur_col].strip(),     # ← NEW
            FPS_FIELD  : r[fps_col].strip(),     # ← NEW
        }

        try:
            cfg.update_record(tok, LAYOUT, rec_id, field_data)
            done += 1
        except Exception as e:
            print(f"❌  Update failed for {fname} – {e}")

    print(f"\n✅  Updated {done} records — {missing} clips not found.")

# ────────────────────────── CLI entry ──────────────────────────
if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Need exactly one argument: <ale_text>")
    main(sys.argv[1])