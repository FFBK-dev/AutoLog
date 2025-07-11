#!/usr/bin/env python3
"""Central FileMaker Data-API helpers."""

import os, requests, warnings, urllib3
warnings.filterwarnings("ignore")
urllib3.disable_warnings()

# ── connection details (override with env-vars if you like) ────────────────
SERVER   = os.getenv("FILEMAKER_SERVER",  "10.0.222.144")
DB_NAME  = "Emancipation to Exodus"
USERNAME = os.getenv("FILEMAKER_USERNAME", "Background")
PASSWORD = os.getenv("FILEMAKER_PASSWORD", "july1776")
# ───────────────────────────────────────────────────────────────────────────

def url(path: str) -> str:
    db_enc = DB_NAME.replace(" ", "%20")
    return f"https://{SERVER}/fmi/data/vLatest/databases/{db_enc}/{path}"

def get_token() -> str:
    r = requests.post(
        url("sessions"),
        auth=(USERNAME, PASSWORD),
        headers={"Content-Type": "application/json"},
        data="{}",
        verify=False,
    )
    r.raise_for_status()
    return r.json()["response"]["token"]

def api_headers(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

def find_record_id(tok: str, layout: str, query: dict) -> str:
    r = requests.post(
        url(f"layouts/{layout}/_find"),
        headers=api_headers(tok),
        json={"query": [query], "limit": 1},
        verify=False,
    )
    r.raise_for_status()
    data = r.json()["response"]["data"]
    if not data:
        raise RuntimeError(f"No match on {layout} for {query}")
    return data[0]["recordId"]

def update_record(tok: str, layout: str, rec_id: str, field_data: dict):
    r = requests.patch(
        url(f"layouts/{layout}/records/{rec_id}"),
        headers=api_headers(tok),
        json={"fieldData": field_data},
        verify=False,
    )
    return r          # ← return it; caller decides what to do