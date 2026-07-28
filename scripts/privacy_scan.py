"""Check commit candidates and release archives without printing matched values.

Credential files and personal workspaces are rejected by name, never opened.
Optional private identifier patterns belong in ignored local storage, not tests
or encoded constants in the public repository. This is a release guard, not a
guarantee that arbitrary unknown secrets can be recognized.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIRS = {
    ".audit", ".git", ".codex", ".vscode", ".idea", "sancho-workspace",
    "sancho-fetched-data", "sancho-downloads", "fetched-data", "analysis-data",
    "update-backups", "logs", "__pycache__", ".pytest_cache", ".venv",
}
INTERNAL_DOCS = {
    "anthropic-directory-eligibility-request.md", "openai-plugin-watch.md",
    "manual_validation.md", "release_checklist.md", "gameplan.md", "temp_update_doc.md",
}
WORKING_DOC = re.compile(r"^(?:audit|plan|todo|tasks|checklist)(?:[_.-].*)?\.(?:md|txt|json|xml)$", re.I)
PUBLIC_PROJECT_DOCS = {
    "DATASOURCE_IMPLEMENTATION_STANDARD.md", "MCP_SERVER_SETUP_CLAUDE_CHATGPT_WEB.md",
    "MODULE_CREATION_GUIDE.md", "SUPPORT_MATRIX.md",
}
SECRET_FILE = re.compile(
    r"(?:^|/)(?:id_rsa|id_ed25519|(?:credentials|secrets)\.(?:json|yaml|yml|toml|ini)|[^/]*(?:service[-_]?account|keypair|wallet[-_]?secret|credential[-_]?export)[^/]*|client_secret[^/]*\.json)$"
    r"|\.(?:pem|key|p12|pfx|keystore)$", re.I,
)
QUERY_CREDENTIAL = re.compile(r"[?&](?:api_key|apikey|key|token|access_token|email)=([^&\s\x22\x27<>]{6,256})", re.I)
PERSONAL_EMAIL = re.compile(r"[\w.+%\\-]{1,64}(?:@|%40|\\@)(?:gmail|hotmail|outlook|yahoo|icloud)\.[A-Za-z]{2,10}", re.I)
HOME_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+|(?<![\w:/])/(?:Users|home)/)"
    r"(?P<owner>[^\s\\/\x22\x27<>]{1,64})(?=[\\/])"
)
HOSTNAME = re.compile(r"\b(?:DESKTOP|LAPTOP)-[A-Z0-9]{5,}\b", re.I)
TOKEN_PREFIX = re.compile(
    r"\b(?:AKIA[A-Z0-9]{16}|AIza[0-9A-Za-z_-]{35}|gh[pousr]_[A-Za-z0-9]{30,255}"
    r"|github_pat_[A-Za-z0-9_]{40,255}|xox[baprs]-[A-Za-z0-9-]{20,255})\b"
)
LITERAL_CREDENTIAL = re.compile(
    r"\b(?:[A-Za-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)"
    r"[\x22\x27]?\s*[=:]\s*[\x22\x27]?([A-Za-z0-9+/_.%=-]{24,256})(?=[\x22\x27\s,}]|$)", re.I,
)
EXAMPLE_OWNER = {"you", "user", "username", "example", "test", "tester", "alice", "bob", "public", "default"}
PLACEHOLDER = re.compile(r"^(?:REDACTED|YOUR|demo|None|test|synthetic|example|placeholder|fake|secret|\{|%7B|\$|<)", re.I)


def forbidden_path(name: str) -> str | None:
    path = PurePosixPath(name.replace("\\", "/"))
    parts = {part.lower() for part in path.parts}
    if ".." in parts or path.is_absolute() or re.match(r"^[A-Za-z]:", name):
        return "unsafe_archive_path"
    if parts & PRIVATE_DIRS:
        return "private_or_generated_path"
    lower = path.name.lower()
    if "project-docs" in path.parts:
        remaining = path.parts[path.parts.index("project-docs") + 1:]
        if not (len(remaining) == 1 and remaining[0] in PUBLIC_PROJECT_DOCS) and not (remaining and remaining[0] == "assets"):
            return "internal_working_document"
    if (lower == ".env" or lower.startswith(".env.") or lower.endswith(".env")) and lower != ".env.example":
        return "credential_file_not_opened"
    if SECRET_FILE.search(path.as_posix()):
        return "credential_file_not_opened"
    if lower in INTERNAL_DOCS or WORKING_DOC.fullmatch(lower) or {"docs", "audits"} <= parts or {"docs", "release"} <= parts:
        return "internal_working_document"
    return None


def private_patterns(terms: list[str]) -> list[re.Pattern]:
    literals, encoded_values = [], []
    for term in terms:
        if not isinstance(term, str) or not term:
            continue
        # Short names need word boundaries to avoid matching ordinary words.
        literal = re.escape(term)
        literals.append(r"\b" + literal + r"\b" if len(term) < 5 else literal)
        encoded = base64.b64encode(term.encode()).decode().rstrip("=")
        encoded_values.append(re.escape(encoded))
        escaped = quote(term, safe="")
        if escaped != term:
            literals.append(re.escape(escaped))
    return [re.compile("|".join(literals), re.I), re.compile("|".join(encoded_values))] if literals else []


def scan_content(name: str, data: bytes, patterns: list[re.Pattern] | None = None) -> list[dict]:
    text = data.decode("utf-8", errors="replace")
    lower_text = text.lower()
    findings: set[tuple[str, int]] = set()

    def note(category: str, offset: int) -> None:
        findings.add((category, text.count("\n", 0, offset) + 1))

    for pattern in patterns or []:
        for match in pattern.finditer(text):
            note("private_identifier", match.start())
    if any(domain in lower_text for domain in ("gmail.", "hotmail.", "outlook.", "yahoo.", "icloud.")):
        for match in PERSONAL_EMAIL.finditer(text):
            note("personal_email", match.start())
    if "Users" in text or "/home/" in text or "Documents and Settings" in text:
        for match in HOME_PATH.finditer(text):
            if match["owner"].lower() not in EXAMPLE_OWNER:
                note("personal_computer_path", match.start())
    if "desktop-" in lower_text or "laptop-" in lower_text:
        for match in HOSTNAME.finditer(text):
            note("personal_computer_name", match.start())
    if "?" in text or "&" in text:
        for match in QUERY_CREDENTIAL.finditer(text):
            if not PLACEHOLDER.match(unquote(match[1])):
                note("credential_in_url", match.start())
    if any(prefix in text for prefix in ("AKIA", "AIza", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_", "xox")):
        for match in TOKEN_PREFIX.finditer(text):
            note("credential_token_pattern", match.start())
    if any(word in lower_text for word in ("api_key", "apikey", "api-key", "token", "secret", "password")):
        for match in LITERAL_CREDENTIAL.finditer(text):
            value = match[1]
            if not PLACEHOLDER.match(value) and any(c.isdigit() for c in value) and any(c.isalpha() for c in value):
                note("literal_credential", match.start())
    for match in re.finditer(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
        note("private_key_marker", match.start())
    # UTF-16 metadata in binary artifacts must not hide local identifiers.
    if b"\0" in data and patterns:
        for encoding in ("utf-16-le", "utf-16-be"):
            decoded = data.decode(encoding, errors="ignore")
            if any(p.search(decoded) for p in patterns):
                findings.add(("private_identifier_binary_metadata", 0))
    return [{"path": name, "category": category, "line": line} for category, line in sorted(findings)]


def archive_findings(label: str, data: bytes, patterns: list[re.Pattern] | None = None) -> tuple[int, list[dict]]:
    count, findings = 0, []
    findings.extend(scan_content("archive_filename", label.encode(), patterns))

    def member(name: str, size: int, read, *, is_link: bool = False) -> None:
        nonlocal count
        findings.extend(scan_content(f"{label}!member_name", name.encode(), patterns))
        issue = forbidden_path(name)
        if issue or is_link or size > 128 * 1024 * 1024:
            findings.append({"path": f"{label}!{name}", "category": issue or ("archive_link" if is_link else "oversized_archive_member")})
            return
        count += 1
        content = read()
        findings.extend(scan_content(f"{label}!{name}", content, patterns))
        if name.endswith((".zip", ".mcpb", ".whl", ".tar.gz")):
            # Release artifacts do not need nested arbitrary archives.
            findings.append({"path": f"{label}!{name}", "category": "nested_archive_requires_review"})

    stream = io.BytesIO(data)
    if zipfile.is_zipfile(stream):
        with zipfile.ZipFile(stream) as archive:
            findings.extend(scan_content(f"{label}!archive_comment", archive.comment, patterns))
            for item in archive.infolist():
                findings.extend(scan_content(f"{label}!member_metadata", item.comment + item.extra, patterns))
                if not item.is_dir():
                    member(item.filename, item.file_size, lambda item=item: archive.read(item),
                           is_link=((item.external_attr >> 16) & 0o170000) == 0o120000)
    else:
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:*") as archive:
            findings.extend(scan_content(f"{label}!archive_metadata", json.dumps(archive.pax_headers).encode(), patterns))
            for item in archive:
                metadata = {"owner": item.uname, "group": item.gname, "pax": item.pax_headers}
                findings.extend(scan_content(f"{label}!member_metadata", json.dumps(metadata).encode(), patterns))
                if item.isfile() or item.issym() or item.islnk():
                    member(item.name, item.size, lambda item=item: archive.extractfile(item).read(),
                           is_link=item.issym() or item.islnk())
    return count, findings


def repository_files(root: Path) -> list[str]:
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=root, capture_output=True, check=True)
    return sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})


def scan_repository(root: Path, patterns: list[re.Pattern] | None = None) -> dict:
    findings, count, members = [], 0, 0
    for name in repository_files(root):
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue  # A pending deletion is absent from the proposed working tree.
        findings.extend(scan_content("repository_filename", name.encode(), patterns))
        issue = forbidden_path(name)
        if issue or path.is_symlink():
            findings.append({"path": name, "category": issue or "symlink_not_followed"})
            continue
        if not path.is_file():
            continue
        data = path.read_bytes()
        count += 1
        if path.suffix in {".mcpb", ".zip", ".whl"} or name.endswith(".tar.gz"):
            total, issues = archive_findings(name, data, patterns)
            members += total
            findings.extend(issues)
        else:
            findings.extend(scan_content(name, data, patterns))
    return {"files_scanned": count, "archive_members_scanned": members, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="store_true", help="Scan tracked and eligible untracked working files")
    parser.add_argument("--artifact", type=Path, action="append", default=[], help="Scan a built wheel, sdist or MCPB")
    parser.add_argument("--private-patterns", type=Path, help="Ignored local JSON with personal_terms; never a credential file")
    parser.add_argument("--report", type=Path, help="Optional local report; contains locations and categories, never matches")
    args = parser.parse_args()
    terms = json.loads(args.private_patterns.read_text(encoding="utf-8"))["personal_terms"] if args.private_patterns else []
    patterns = private_patterns(terms)
    report = {"files_scanned": 0, "archive_members_scanned": 0, "findings": []}
    if args.repo or not args.artifact:
        report = scan_repository(ROOT, patterns)
    for path in args.artifact:
        count, issues = archive_findings(path.name, path.read_bytes(), patterns)
        report["archive_members_scanned"] += count
        report["findings"].extend(issues)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(bool(report["findings"]))


if __name__ == "__main__":
    raise SystemExit(main())
