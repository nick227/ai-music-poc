from fastapi import APIRouter, Depends

from app.api.dependencies import get_preset_service
from app.services.preset_service import PresetService

router = APIRouter(prefix="/api", tags=["presets"])


@router.get("/presets")
def list_presets(service: PresetService = Depends(get_preset_service)):
    return {"presets": service.list()}
