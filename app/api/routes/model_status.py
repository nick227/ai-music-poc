from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.generators.ace_step.health import (
    check_ace_packages,
    enrich_status_with_packages,
    get_ace_status,
    recommended_actions,
    run_ace_python_diagnostic,
    run_ace_runner_dry_run,
)

router = APIRouter(prefix="/api", tags=["model-status"])


@router.get("/model-status")
def model_status(settings: Settings = Depends(get_settings)):
    """
    Fast wiring check — no subprocesses.
    Fields: wiring_ok, hf_cache_configured, hf_cache_exists, user_message.
    packages_ok and cuda_available are None until POST /api/model-status/test is called.
    """
    return get_ace_status(settings)


@router.post("/model-status/test")
def model_status_test(settings: Settings = Depends(get_settings)):
    """
    Full diagnostic — runs subprocesses to probe packages and CUDA.
    Returns an enriched ModelStatus with packages_checked=True, packages_ok, cuda_available.
    This does NOT run model inference.
    """
    status = get_ace_status(settings)
    diagnostic = run_ace_python_diagnostic(settings)
    packages = check_ace_packages(settings)
    dry_run = run_ace_runner_dry_run(settings)
    enriched = enrich_status_with_packages(status, packages, diagnostic)
    actions = recommended_actions(enriched, diagnostic, packages, dry_run)
    ready = bool(
        enriched.wiring_ok
        and enriched.packages_ok
        and enriched.cuda_ready is not False
        and dry_run.get("ok")
    )
    return {
        "ok": ready,
        "message": enriched.user_message,
        "diagnostic": diagnostic,
        "packages": packages,
        "dry_run": dry_run,
        "recommended_actions": actions,
        "status": enriched,
    }
