from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.generators.ace_step.health import (
    check_ace_packages,
    get_ace_status,
    recommended_actions,
    run_ace_python_diagnostic,
    run_ace_runner_dry_run,
)

router = APIRouter(prefix="/api", tags=["model-status"])


@router.get("/model-status")
def model_status(settings: Settings = Depends(get_settings)):
    status = get_ace_status(settings)
    return status


@router.post("/model-status/test")
def model_status_test(settings: Settings = Depends(get_settings)):
    status = get_ace_status(settings)
    diagnostic = run_ace_python_diagnostic(settings)
    packages = check_ace_packages(settings)
    dry_run = run_ace_runner_dry_run(settings)
    actions = recommended_actions(status, diagnostic, packages, dry_run)
    ready = bool(status.can_generate and packages.get("ok") and dry_run.get("ok"))
    return {
        "ok": ready,
        "message": "ACE diagnostic completed. This does not run full model inference.",
        "diagnostic": diagnostic,
        "packages": packages,
        "dry_run": dry_run,
        "recommended_actions": actions,
        "status": status,
    }
