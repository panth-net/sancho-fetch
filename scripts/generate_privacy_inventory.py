"""Generate a source-backed upstream domain/credential inventory without reading .env."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "src" / "sancho" / "templates" / "modules"
OUTPUT = ROOT / "docs" / "privacy" / "upstream-inventory.json"
URL_RE = re.compile(r"https?://[^\s'\"<>`)]+")
ENV_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:API_KEY|API_TOKEN|APP_TOKEN|ACCESS_TOKEN|AUTH_TOKEN|"
    r"CLIENT_ID|CLIENT_SECRET|SECRET_KEY|KEY_ID|KEY_SECRET|PASSWORD|CONTACT_EMAIL|USER_AGENT)\b"
)


def _authentication_methods(env_vars: list[str]) -> list[str]:
    methods: set[str] = set()
    for name in env_vars:
        if "EMAIL" in name or "USER_AGENT" in name:
            methods.add("provider-required-request-identity")
        if "CLIENT_ID" in name or "CLIENT_SECRET" in name:
            methods.add("oauth-client-credentials")
        if any(token in name for token in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            methods.add("api-key-or-token")
    return sorted(methods) or ["none-declared"]


def _source_text(module_dir: Path) -> str:
    chunks: list[str] = []
    for path in sorted(module_dir.iterdir()):
        if path.is_file() and path.suffix in {".py", ".yaml", ".yml", ".md"}:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def generate() -> dict:
    modules: list[dict] = []
    all_domains: set[str] = set()
    credentialed = 0
    for module_dir in sorted(MODULES.glob("fetch.*")):
        manifest_path = module_dir / "module.yaml"
        if not manifest_path.exists():
            continue
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        text = _source_text(module_dir)
        domains = sorted(
            {
                parsed.netloc.lower()
                for raw in URL_RE.findall(text)
                if (parsed := urlparse(raw.rstrip(".,;"))).netloc
            }
        )
        env_vars = sorted(set(ENV_RE.findall(text)))
        auth_methods = _authentication_methods(env_vars)
        all_domains.update(domains)
        if env_vars:
            credentialed += 1
        modules.append(
            {
                "module_id": manifest.get("id", module_dir.name),
                "description": str(manifest.get("description", "")).strip().split("\n", 1)[0],
                "upstream_domains": domains,
                "authentication": "credentialed-when-selected" if env_vars else "none-declared",
                "authentication_methods": auth_methods,
                "credential_environment_variables": env_vars,
                "credential_destination": domains if env_vars else [],
                "request_flow": "local workspace -> selected upstream domain",
                "response_flow": "selected upstream -> local canonical cache and working export",
            }
        )
    return {
        "scope": "static bundled fetch-module source; .env values are never read",
        "module_count": len(modules),
        "unique_upstream_domain_count": len(all_domains),
        "credentialed_module_count": credentialed,
        "upstream_domains": sorted(all_domains),
        "modules": modules,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = generate()
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {OUTPUT}: {payload['module_count']} modules, "
        f"{payload['unique_upstream_domain_count']} domains"
    )


if __name__ == "__main__":
    main()
