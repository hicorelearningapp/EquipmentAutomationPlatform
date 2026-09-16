"""Where the backend reads from and writes to.

Two folders, so the installed program never writes into its own folder (under Program Files
that folder is read-only):

  app_dir()   ships with the program and is only read: script templates, the embedding model,
              the MES templates we deliver
  data_dir()  everything written while running: projects, the user's MES templates, logs

BraceLink sets EAP_DATA_DIR when it starts the backend. When it isn't set - which is how
development and the tests run - both folders are the backend folder, exactly as before.

On first use the MES templates are copied from the app folder into the data folder, because
the backend adds to and edits them while running.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend


def app_dir() -> Path:
    """Files delivered with the program; treat as read-only."""
    configured = os.environ.get("EAP_APP_DIR")
    return Path(configured).resolve() if configured else BACKEND_DIR


def data_dir() -> Path:
    """Files written while running. Defaults to the backend folder in development."""
    configured = os.environ.get("EAP_DATA_DIR")
    return Path(configured).expanduser().resolve() if configured else BACKEND_DIR


def gem_templates_dir() -> Path:
    """Test script templates delivered with the program (read-only)."""
    return app_dir() / "GEMTestScriptTemplates"


def mes_templates_dir() -> Path:
    """MES templates. Written to while running, so they live in the data folder."""
    return data_dir() / "MESMapTemplates"


def logs_dir() -> Path:
    directory = data_dir() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_storage_root(storage_root: str | Path) -> Path:
    """Make a relative storage location mean 'inside the data folder', not 'wherever the
    program happened to be started from'."""
    root = Path(storage_root).expanduser()
    return root.resolve() if root.is_absolute() else (data_dir() / root).resolve()


def prepare_data_dir() -> None:
    """Create the data folder and, on first use, copy in the MES templates we deliver."""
    target = mes_templates_dir()
    if target.resolve() == (app_dir() / "MESMapTemplates").resolve():
        return  # development: the two folders are the same, nothing to copy

    shipped = app_dir() / "MESMapTemplates"
    if target.exists() or not shipped.is_dir():
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(shipped, target)
    logger.info("Copied the delivered MES templates to %s", target)
