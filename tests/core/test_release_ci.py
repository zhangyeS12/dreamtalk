import importlib.util
import sys
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


def _clean_checkout(monkeypatch, *argv):
    outputs = {"rev-parse": "a" * 40 + "\n", "status": ""}
    monkeypatch.setattr(
        release_ci.subprocess, "check_output", lambda args, **kwargs: outputs[args[1]]
    )
    monkeypatch.setattr(sys, "argv", ["check-release-ci.py", *argv])
    monkeypatch.delenv("DREAMTALK_RELEASE_SKIP_CI", raising=False)


def test_release_build_requires_ci_by_default(monkeypatch):
    _clean_checkout(monkeypatch)

    def offline(*args, **kwargs):
        raise release_ci.urllib.error.URLError("offline")

    monkeypatch.setattr(release_ci.urllib.request, "urlopen", offline)
    with pytest.raises(SystemExit, match="release_ci_verification_failed"):
        release_ci.main()


@pytest.mark.parametrize("override", ["flag", "env"])
def test_skipping_release_ci_is_an_explicit_logged_override(monkeypatch, capsys, override):
    _clean_checkout(monkeypatch, *(["--skip-ci"] if override == "flag" else []))
    if override == "env":
        monkeypatch.setenv("DREAMTALK_RELEASE_SKIP_CI", "1")

    def unexpected(*args, **kwargs):
        pytest.fail("skipped CI must not query GitHub")

    monkeypatch.setattr(release_ci.urllib.request, "urlopen", unexpected)
    release_ci.main()
    assert "CI SKIPPED BY EXPLICIT OVERRIDE" in capsys.readouterr().out
