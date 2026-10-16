import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_ci", Path(__file__).resolve().parents[2] / "scripts/check-release-ci.py"
)
release_ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_ci)

privacy_spec = importlib.util.spec_from_file_location(
    "release_privacy", Path(__file__).resolve().parents[2] / "scripts/check-release-privacy.py"
)
privacy = importlib.util.module_from_spec(privacy_spec)
privacy_spec.loader.exec_module(privacy)


def run(number=1, sha="a" * 40, conclusion="success", status="completed", **kwargs):
    return {
        "run_number": number,
        "head_sha": sha,
        "conclusion": conclusion,
        "status": status,
        "path": ".github/workflows/foundation.yml",
        "event": "push",
        "html_url": "https://github.com/example/repo/actions/runs/1",
        **kwargs,
    }


def test_release_requires_same_commit_and_successful_latest_ci_attempt():
    assert release_ci.validate_runs({"workflow_runs": [run()]}, "a" * 40).startswith("https://")
    for runs in (
        [],
        [run(sha="b" * 40)],
        [run(event="pull_request")],
        [run(conclusion="failure")],
        [run(), run(number=2, conclusion=None, status="in_progress")],
        [run(run_attempt=1), run(run_attempt=2, conclusion="cancelled")],
    ):
        with pytest.raises(ValueError):
            release_ci.validate_runs({"workflow_runs": runs}, "a" * 40)


def test_only_reviewed_original_example_bytes_can_ship_as_authored_content():
    root = Path(__file__).resolve().parents[2]
    original = (root / privacy.PUBLIC_EXAMPLE_SOURCE).read_bytes()
    assert not privacy.findings(privacy.PUBLIC_EXAMPLE_SOURCE, original, source=True)
    assert not privacy.findings(privacy.PUBLIC_EXAMPLE_PACKAGE, original, source=False)
    assert "authored_content_export" in privacy.findings("other/campus.json", original, source=True)
    changed = original.replace(b'"campus-v1"', b'"other-example"')
    assert "authored_content_export" in privacy.findings(
        privacy.PUBLIC_EXAMPLE_SOURCE, changed, source=True
    )
    canary = ("sk-SYNTHETIC_NOT_REAL_" + "x" * 32).encode()
    assert "credential_literal" in privacy.findings(
        privacy.PUBLIC_EXAMPLE_SOURCE, original + canary, source=True
    )
