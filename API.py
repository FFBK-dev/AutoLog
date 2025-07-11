#!/usr/bin/env python3
from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Body
from importlib import util as iutil
from pathlib import Path
import subprocess, os, shlex, types, logging

API_KEY = os.getenv("FM_AUTOMATION_KEY", "supersecret")
PYTHON  = "/Library/Developer/CommandLineTools/usr/bin/python3"

BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = BASE_DIR / "jobs"

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

def load_job(path: Path) -> types.ModuleType:
    spec = iutil.spec_from_file_location(path.stem, path)
    mod  = iutil.module_from_spec(spec)
    spec.loader.exec_module(mod)            # type: ignore
    return mod

SCRIPTS = {}
for f in JOBS_DIR.glob("*.py"):
    m      = load_job(f)
    arg_ls = getattr(m, "__ARGS__", [])
    if not isinstance(arg_ls, list):
        raise RuntimeError(f"{f.name}: __ARGS__ must be a list")
    SCRIPTS[f.stem] = {"path": str(f), "args": arg_ls}

def check_key(h: str = Header(..., alias="x-api-key")):
    if h != API_KEY:
        raise HTTPException(status_code=401, detail="bad key")

app = FastAPI(title="FM Automation API")

@app.post("/run/{job}", dependencies=[Depends(check_key)])
def run_job(
    job: str,
    background_tasks: BackgroundTasks,      # injected by FastAPI
    payload: dict = Body({})                # default stays last
):
    cfg = SCRIPTS.get(job)
    if not cfg:
        raise HTTPException(status_code=404, detail="unknown job")

    try:
        argv = [payload[k] for k in cfg["args"]]
    except KeyError as miss:
        raise HTTPException(status_code=400, detail=f"missing key: {miss}")

    cmd = [PYTHON, cfg["path"], *map(str, argv)]
    background_tasks.add_task(subprocess.run, cmd)
    return {"queued": True}