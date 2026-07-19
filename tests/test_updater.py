"""Tests for the git-based updater (app/services/updater.py).

Covers apply_update failure handling: a failed pip install or frontend
build must surface an error and NOT schedule a restart, otherwise the
service restarts on top of a broken install / serves a stale UI.
"""

import subprocess
from unittest.mock import patch

import pytest

from app.services.updater import Updater


def _completed(cmd, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


def _run_side_effect(pip_rc=0, npm_rc=0):
    """subprocess.run replacement routing by command."""

    def run(cmd, **kwargs):
        prog = cmd[0]
        if prog == "git":
            return _completed(cmd, 0, stdout="ok")
        if "pip" in prog or (len(cmd) > 2 and cmd[1] == "-m" and cmd[2] == "pip"):
            return _completed(cmd, pip_rc, stderr="pip exploded" if pip_rc else "")
        if prog == "npm":
            return _completed(cmd, npm_rc, stderr="vite exploded" if npm_rc else "")
        return _completed(cmd, 0)

    return run


@pytest.fixture
def updater(tmp_path):
    u = Updater(app_version="test")
    u._repo_root = str(tmp_path)
    return u


@pytest.mark.asyncio
async def test_pip_failure_aborts_update(updater):
    with (
        patch.object(Updater, "_trigger_restart") as restart,
        patch(
            "app.services.updater.subprocess.run",
            side_effect=_run_side_effect(pip_rc=1),
        ),
    ):
        status = await updater.apply_update()

    assert "pip install failed" in status.last_error
    assert status.updating is False
    restart.assert_not_called()


@pytest.mark.asyncio
async def test_frontend_build_failure_aborts_update(updater, tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}")

    with (
        patch.object(Updater, "_trigger_restart") as restart,
        patch(
            "app.services.updater.subprocess.run",
            side_effect=_run_side_effect(npm_rc=1),
        ),
    ):
        status = await updater.apply_update()

    assert "Frontend build failed" in status.last_error
    assert status.updating is False
    restart.assert_not_called()


@pytest.mark.asyncio
async def test_successful_update_builds_frontend(updater, tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}")
    npm_calls = []

    def run(cmd, **kwargs):
        if cmd[0] == "npm":
            npm_calls.append(cmd)
        return _run_side_effect()(cmd, **kwargs)

    with (
        patch.object(Updater, "_trigger_restart"),
        patch("app.services.updater.subprocess.run", side_effect=run),
    ):
        status = await updater.apply_update()

    assert status.last_error == ""
    assert status.updating is False
    assert ["npm", "run", "build"] in npm_calls
