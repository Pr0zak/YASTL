"""Service for checking and applying application updates via git."""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field

logger = logging.getLogger("yastl")


@dataclass
class CommitInfo:
    """A single commit from the update log."""

    sha: str
    message: str
    author: str
    date: str


@dataclass
class UpdateStatus:
    """Current state of the update system."""

    update_available: bool = False
    current_version: str = ""
    current_sha: str = ""
    remote_sha: str = ""
    commits_behind: int = 0
    commits: list[CommitInfo] = field(default_factory=list)
    is_git_repo: bool = False
    remote_url: str = ""
    branch: str = ""
    updating: bool = False
    last_error: str = ""


class Updater:
    """Manages checking for and applying git-based updates."""

    def __init__(self, app_version: str = "0.1.0") -> None:
        self.app_version = app_version
        self._status = UpdateStatus()
        self._lock = asyncio.Lock()
        self._repo_root: str | None = None

    @property
    def status(self) -> UpdateStatus:
        return self._status

    def _find_repo_root(self) -> str | None:
        """Locate the git repository root directory."""
        if self._repo_root is not None:
            return self._repo_root

        # Check common locations in order of likelihood
        candidates = [
            # Running from source checkout (dev or LXC git install)
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
            # LXC git install path
            "/opt/yastl/src",
        ]

        for path in candidates:
            git_dir = os.path.join(path, ".git")
            if os.path.isdir(git_dir):
                self._repo_root = path
                return path

        return None

    def _run_git(
        self, *args: str, timeout: int = 30
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repo root."""
        repo = self._find_repo_root()
        if not repo:
            raise RuntimeError("Not a git repository")
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    async def check_for_updates(self) -> UpdateStatus:
        """Fetch from remote and check if updates are available."""
        async with self._lock:
            self._status.last_error = ""
            repo = self._find_repo_root()

            if not repo:
                self._status.is_git_repo = False
                self._status.last_error = (
                    "Application is not running from a git repository"
                )
                return self._status

            self._status.is_git_repo = True

            try:
                loop = asyncio.get_event_loop()

                # Get current branch
                result = await loop.run_in_executor(
                    None, lambda: self._run_git("rev-parse", "--abbrev-ref", "HEAD")
                )
                if result.returncode != 0:
                    self._status.last_error = "Failed to determine current branch"
                    return self._status
                branch = result.stdout.strip()
                self._status.branch = branch

                # Get remote URL
                result = await loop.run_in_executor(
                    None, lambda: self._run_git("remote", "get-url", "origin")
                )
                self._status.remote_url = (
                    result.stdout.strip() if result.returncode == 0 else ""
                )

                # Get current SHA
                result = await loop.run_in_executor(
                    None, lambda: self._run_git("rev-parse", "HEAD")
                )
                if result.returncode == 0:
                    self._status.current_sha = result.stdout.strip()

                # Fetch from origin
                result = await loop.run_in_executor(
                    None, lambda: self._run_git("fetch", "origin", branch, timeout=60)
                )
                if result.returncode != 0:
                    self._status.last_error = (
                        f"Failed to fetch from remote: {result.stderr.strip()}"
                    )
                    return self._status

                # Get remote SHA
                result = await loop.run_in_executor(
                    None,
                    lambda: self._run_git("rev-parse", f"origin/{branch}"),
                )
                if result.returncode == 0:
                    self._status.remote_sha = result.stdout.strip()

                # Count commits behind
                result = await loop.run_in_executor(
                    None,
                    lambda: self._run_git(
                        "rev-list", "--count", f"HEAD..origin/{branch}"
                    ),
                )
                if result.returncode == 0:
                    self._status.commits_behind = int(result.stdout.strip())
                else:
                    self._status.commits_behind = 0

                self._status.update_available = self._status.commits_behind > 0

                # Get commit log if updates available
                if self._status.update_available:
                    result = await loop.run_in_executor(
                        None,
                        lambda: self._run_git(
                            "log",
                            "--pretty=format:%H|%s|%an|%ad",
                            "--date=short",
                            f"HEAD..origin/{branch}",
                        ),
                    )
                    commits: list[CommitInfo] = []
                    if result.returncode == 0 and result.stdout.strip():
                        for line in result.stdout.strip().split("\n"):
                            parts = line.split("|", 3)
                            if len(parts) == 4:
                                commits.append(
                                    CommitInfo(
                                        sha=parts[0][:8],
                                        message=parts[1],
                                        author=parts[2],
                                        date=parts[3],
                                    )
                                )
                    self._status.commits = commits
                else:
                    self._status.commits = []

                self._status.current_version = self.app_version

            except Exception as e:
                logger.error("Update check failed: %s", e)
                self._status.last_error = str(e)

            return self._status

    async def apply_update(self) -> UpdateStatus:
        """Pull latest code, reinstall dependencies, and trigger a restart."""
        async with self._lock:
            if self._status.updating:
                self._status.last_error = "An update is already in progress"
                return self._status

            self._status.updating = True
            self._status.last_error = ""

            try:
                loop = asyncio.get_event_loop()
                branch = self._status.branch or "main"

                # Pull latest changes
                logger.info("Pulling latest changes from origin/%s...", branch)
                result = await loop.run_in_executor(
                    None,
                    lambda: self._run_git(
                        "pull", "--ff-only", "origin", branch, timeout=120
                    ),
                )
                if result.returncode != 0:
                    self._status.last_error = (
                        f"Git pull failed: {result.stderr.strip()}"
                    )
                    self._status.updating = False
                    return self._status

                logger.info("Git pull successful")

                # Reinstall dependencies
                logger.info("Reinstalling dependencies...")
                pip_exe = os.path.join(os.path.dirname(sys.executable), "pip")
                if not os.path.isfile(pip_exe):
                    pip_exe = sys.executable  # fallback to python -m pip
                    pip_args = [
                        pip_exe,
                        "-m",
                        "pip",
                        "install",
                        "--no-cache-dir",
                        "-q",
                        ".",
                    ]
                else:
                    pip_args = [pip_exe, "install", "--no-cache-dir", "-q", "."]

                repo = self._find_repo_root()
                result = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        pip_args,
                        cwd=repo,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    ),
                )
                if result.returncode != 0:
                    logger.warning(
                        "pip install had issues (continuing anyway): %s",
                        result.stderr.strip(),
                    )

                logger.info("Dependencies reinstalled")

                # Schedule restart after response is sent
                self._status.update_available = False
                self._status.commits_behind = 0
                self._status.commits = []
                self._status.updating = False

                logger.info("Scheduling service restart...")
                loop.call_later(1.5, self._trigger_restart)

                return self._status

            except Exception as e:
                logger.error("Update failed: %s", e)
                self._status.last_error = str(e)
                self._status.updating = False
                return self._status

    @staticmethod
    def _trigger_restart() -> None:
        """Restart the service.

        Works with Docker (restart: unless-stopped), systemd (Restart=always),
        and development (uvicorn --reload picks up changes automatically).
        We send SIGTERM to ourselves for a graceful shutdown; the process
        manager will restart us.
        """
        logger.info("Restarting service...")
        os.kill(os.getpid(), signal.SIGTERM)
