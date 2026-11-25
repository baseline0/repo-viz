"""Repository root and path constants for repo-viz.

This is the SINGLE SOURCE OF TRUTH for all path resolution in this repo.
All other modules should import REPO_ROOT and derived paths from here.

Never use .parent calls outside of this file.
"""

from pathlib import Path

# Repo root: src/repo_viz/constants.py → go up 3 levels to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Common paths relative to repo root
SRC_DIR = REPO_ROOT / "src"
TESTS_DIR = REPO_ROOT / "tests"
SCRIPTS_DIR = REPO_ROOT / "scripts"
DOCS_DIR = REPO_ROOT / "docs"
CONFIG_DIR = REPO_ROOT / "config"
FLEET_DATA_DIR = REPO_ROOT / ".fleet"

# Example usage in other modules:
#
# from repo_viz.constants import REPO_ROOT
# config_file = REPO_ROOT / "config" / "settings.yaml"
#
# Instead of:
#
# from pathlib import Path
# config_file = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
