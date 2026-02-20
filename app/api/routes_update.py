"""API routes for checking and applying application updates."""

import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("yastl")

router = APIRouter(prefix="/api/update", tags=["update"])


def _get_updater(request: Request):
    """Retrieve the Updater instance from FastAPI app state."""
    updater = getattr(request.app.state, "updater", None)
    if updater is None:
        raise HTTPException(
            status_code=503,
            detail="Update service is not available",
        )
    return updater


@router.get("/check")
async def check_for_updates(request: Request):
    """Check the remote repository for available updates."""
    updater = _get_updater(request)
    status = await updater.check_for_updates()

    return {
        "update_available": status.update_available,
        "current_version": status.current_version,
        "current_sha": status.current_sha,
        "remote_sha": status.remote_sha,
        "commits_behind": status.commits_behind,
        "commits": [
            {
                "sha": c.sha,
                "message": c.message,
                "author": c.author,
                "date": c.date,
            }
            for c in status.commits
        ],
        "is_git_repo": status.is_git_repo,
        "remote_url": status.remote_url,
        "branch": status.branch,
        "error": status.last_error or None,
    }


@router.post("/apply")
async def apply_update(request: Request):
    """Pull latest changes, reinstall dependencies, and restart the service."""
    updater = _get_updater(request)

    if updater.status.updating:
        raise HTTPException(
            status_code=409,
            detail="An update is already in progress",
        )

    if not updater.status.is_git_repo:
        raise HTTPException(
            status_code=400,
            detail="Application is not running from a git repository",
        )

    logger.info("Update requested via API")
    status = await updater.apply_update()

    if status.last_error:
        raise HTTPException(
            status_code=500,
            detail=f"Update failed: {status.last_error}",
        )

    return {
        "detail": "Update applied successfully. Service is restarting...",
        "restarting": True,
    }


@router.get("/status")
async def update_status(request: Request):
    """Return the current update/restart status."""
    updater = _get_updater(request)
    status = updater.status

    return {
        "updating": status.updating,
        "is_git_repo": status.is_git_repo,
        "current_version": status.current_version,
        "branch": status.branch,
        "current_sha": status.current_sha,
        "error": status.last_error or None,
    }
