"""
engine/setup_phase1.py
Public Conversation Analysis Engine — Phase 1 One-Shot Setup Script

Idempotent. Safe to run multiple times.

What it does:
    1. Creates virtual environment (if not already created)
    2. Initializes data store directories
    3. Runs the Phase 1 exit criteria validator

Usage:
    python engine/setup_phase1.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).parent
ROOT_DIR = ENGINE_DIR.parent
VENV_DIR = ROOT_DIR / ".venv"


def step(msg: str) -> None:
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def create_venv() -> None:
    step("Step 1 — Virtual Environment")
    if VENV_DIR.exists():
        print(f"  ✓ Virtual environment already exists at {VENV_DIR}")
        return
    print(f"  Creating virtual environment at {VENV_DIR} ...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    print("  ✓ Virtual environment created.")
    print(
        f"\n  Activate with:\n"
        f"    Windows:  {VENV_DIR}\\Scripts\\activate\n"
        f"    Mac/Linux: source {VENV_DIR}/bin/activate\n"
        f"\n  Then install dependencies:\n"
        f"    pip install -r engine/requirements.txt\n"
    )


def init_store() -> None:
    step("Step 2 — Data Store Directories")
    sys.path.insert(0, str(ROOT_DIR))
    from engine.data_store import init_data_store
    init_data_store()
    print("  ✓ Data store directories ready.")


def run_validator() -> bool:
    step("Step 3 — Phase 1 Exit Criteria Validation")
    from engine.validate_phase1 import run_all_checks
    return run_all_checks()


if __name__ == "__main__":
    create_venv()
    init_store()
    success = run_validator()
    print("\n")
    if success:
        print("  ✅  PHASE 1 SETUP COMPLETE — proceed to Phase 2.")
    else:
        print("  ❌  PHASE 1 SETUP INCOMPLETE — review errors above.")
    sys.exit(0 if success else 1)
