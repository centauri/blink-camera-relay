"""Prevent credentials entering Docker layers through a local build context."""
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("context", [ROOT,ROOT/"vendor/onvif"])
def test_docker_context_excludes_nested_private_files(context):
    rules=(context/".dockerignore").read_text().splitlines()
    assert rules[0]=="**"  # Explicit allowlist, not only Git ignore rules.
    for pattern in ("**/.env","**/.env.*","**/auth.json","**/credentials.json",
                    "**/*.sqlite","**/*.sqlite-wal","**/*.sqlite-shm","**/*.key"):
        assert pattern in rules
        assert rules.index(pattern)>max(i for i,r in enumerate(rules) if r.startswith("!"))
