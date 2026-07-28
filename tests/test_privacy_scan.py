from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from scripts import privacy_scan as scan


@pytest.mark.parametrize("name", [
    ".env", "nested/.env.local", "production.env", "nested/credentials.json", "nested/service-account.json",
    "private.pem", "sancho-fetched-data/run/data.json", ".audit/results.json",
    "docs/release/MANUAL_VALIDATION.md", "project-docs/RELEASE_CHECKLIST.md", "PLAN.md",
    "project-docs/UNREVIEWED_NOTES.md",
])
def test_private_files_are_rejected_without_reading(name):
    assert scan.forbidden_path(name)


def test_credential_file_is_not_opened(tmp_path, monkeypatch):
    (tmp_path / ".env").touch()
    monkeypatch.setattr(scan, "repository_files", lambda _: [".env"])
    monkeypatch.setattr(Path, "read_bytes", lambda _: pytest.fail("Credential file opened"))
    result = scan.scan_repository(tmp_path)
    assert result["files_scanned"] == 0
    assert result["findings"][0]["category"] == "credential_file_not_opened"


def test_archive_blocks_private_member_before_decompression(monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("package/.env", "synthetic private-file sentinel")
        archive.writestr("package/README.md", "public documentation")
    original = zipfile.ZipFile.read

    def read(self, name, *args, **kwargs):
        assert (name.filename if hasattr(name, "filename") else name) != "package/.env"
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", read)
    count, issues = scan.archive_findings("sample.whl", buffer.getvalue())
    assert count == 1 and len(issues) == 1
    assert issues[0]["category"] == "credential_file_not_opened"


def test_personal_paths_and_email_are_reported_without_values():
    email = "private-fixture" + "@" + "gmail.com"
    owner = "fictional-person"
    text = "C:" + "\\Users\\" + owner + "\\Documents\\file.txt\n" + email
    issues = scan.scan_content("example.txt", text.encode())
    assert {row["category"] for row in issues} == {"personal_computer_path", "personal_email"}
    assert email not in json.dumps(issues) and owner not in json.dumps(issues)


def test_provider_urls_and_placeholder_home_paths_are_not_personal():
    text = 'https://agency.example/home/data https://api.example/users/10 C:/Users/you/project'
    assert scan.scan_content("public.md", text.encode()) == []


def test_private_patterns_cover_literal_encoded_and_binary_metadata():
    import base64

    name = "fictional-contributor"
    patterns = scan.private_patterns([name])
    for value in [name.encode(), base64.b64encode(name.encode()), name.encode("utf-16-le")]:
        issues = scan.scan_content("example.bin", value, patterns)
        assert issues and name not in json.dumps(issues)


def test_credential_detection_never_echoes_token():
    value = "gh" + "p_" + "aB7" * 12
    issues = scan.scan_content("public.py", value.encode())
    assert issues and issues[0]["category"] == "credential_token_pattern"
    assert value not in json.dumps(issues)


@pytest.mark.parametrize("template", ['{{"access_token": "{value}"}}', 'PROVIDER_API_KEY={value}', "password='{value}'"])
def test_json_and_environment_assignments_are_checked(template):
    value = "aB7" * 12
    issues = scan.scan_content("sample.txt", template.format(value=value).encode())
    assert any(row["category"] == "literal_credential" for row in issues)
    assert value not in json.dumps(issues)


def test_archive_comments_and_owner_metadata_are_scanned():
    import tarfile

    name = "fictional-contributor"
    patterns = scan.private_patterns([name])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.comment = name.encode()
        archive.writestr("README.md", "public")
    _, issues = scan.archive_findings("sample.whl", buffer.getvalue(), patterns)
    assert any(row["category"] == "private_identifier" for row in issues)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("README.md")
        info.uname = name
        info.size = 6
        archive.addfile(info, io.BytesIO(b"public"))
    _, issues = scan.archive_findings("sample.tar.gz", buffer.getvalue(), patterns)
    assert any(row["category"] == "private_identifier" for row in issues)


def test_templates_and_public_reference_docs_are_allowed():
    for path in ["src/sancho/templates/workspace/.env.example", "project-docs/MODULE_CREATION_GUIDE.md",
                 "project-docs/DATASOURCE_IMPLEMENTATION_STANDARD.md", "docs/PRIVACY.md"]:
        assert scan.forbidden_path(path) is None
