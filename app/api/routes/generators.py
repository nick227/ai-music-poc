from fastapi import APIRouter, Depends

from app.api.dependencies import get_registry
from app.generators.registry import GeneratorRegistry

router = APIRouter(prefix="/api", tags=["generators"])


@router.get("/generators")
def list_generators(registry: GeneratorRegistry = Depends(get_registry)):
    return {"generators": registry.list()}
