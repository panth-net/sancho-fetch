from __future__ import annotations

from pathlib import Path

WORKSPACE_DIRNAME = "sancho-workspace"

REQUIRED_DIRECTORIES = [
    "source/fetch",
    "source/process",
    "source/analyze",
    "source/dashboard",
    "source/_runtime",
    "custom/fetch",
    "custom/process",
    "custom/analyze",
    "custom/dashboard",
    "playbooks",
    "fetched-data",
    "analysis-data",
    "outputs",
    "logs",
    "update-backups",
]

REQUIRED_FILES = [
    ".env.example",
    ".env",
    "AI_INSTRUCTIONS.md",
    "DATASET_CATALOG.md",
    "sancho.yaml",
    "modules.yaml",
    "modules.lock.yaml",
]

MANAGED_PATH_PREFIX = "source/"

SUPPORTED_MODULE_TYPES = {"fetch", "process", "analyze", "dashboard"}

CLIENT_NAMES = {"claude-desktop", "codex", "chatgpt-desktop", "chatgpt-web", "cursor", "vscode"}

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = PACKAGE_ROOT / "templates"
MODULE_TEMPLATES_ROOT = TEMPLATES_ROOT / "modules"
RUNTIME_TEMPLATES_ROOT = TEMPLATES_ROOT / "runtime"
WORKSPACE_TEMPLATES_ROOT = TEMPLATES_ROOT / "workspace"
# The .env.example that ships inside the package. Unlike a repo-root path,
# this exists in both a source checkout and an installed wheel.
BUNDLED_ENV_EXAMPLE = WORKSPACE_TEMPLATES_ROOT / ".env.example"
RUNTIME_ROOT_TEMPLATE_FILES = {"AI_INSTRUCTIONS.md", "DATASET_CATALOG.md"}
