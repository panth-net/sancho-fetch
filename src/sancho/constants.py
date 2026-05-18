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

PROTECTED_PATH_PREFIXES = [
    "custom/",
    "playbooks/",
    "fetched-data/",
    "analysis-data/",
    "outputs/",
    "logs/",
    "update-backups/",
    "AI_INSTRUCTIONS.md",
    "DATASET_CATALOG.md",
    ".env",
]

MANAGED_PATH_PREFIX = "source/"

SUPPORTED_MODULE_TYPES = {"fetch", "process", "analyze", "dashboard"}

CLIENT_NAMES = {"claude-desktop", "chatgpt-desktop", "chatgpt-web", "cursor", "vscode"}

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = PACKAGE_ROOT / "templates"
MODULE_TEMPLATES_ROOT = TEMPLATES_ROOT / "modules"
RUNTIME_TEMPLATES_ROOT = TEMPLATES_ROOT / "runtime"
WORKSPACE_TEMPLATES_ROOT = TEMPLATES_ROOT / "workspace"
RUNTIME_ROOT_TEMPLATE_FILES = {"AI_INSTRUCTIONS.md", "DATASET_CATALOG.md"}
