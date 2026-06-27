from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_category_service
from app.api.schemas.taxonomy_api import CategoryListResponse
from app.domain.enums import CategoryDimension
from app.services.category_service import CategoryService

router = APIRouter(prefix="/api", tags=["categories"])


@router.get("/categories", response_model=CategoryListResponse)
def list_categories(
    dimension: CategoryDimension | None = Query(default=None),
    category_service: CategoryService = Depends(get_category_service),
):
    category_service.seed_if_empty()
    return CategoryListResponse(categories=category_service.list(dimension=dimension))


@router.get("/categories/{category_id}")
def get_category(
    category_id: str,
    category_service: CategoryService = Depends(get_category_service),
):
    category_service.seed_if_empty()
    return category_service.get_required(category_id)
