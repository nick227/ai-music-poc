from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_category_service
from app.api.schemas.taxonomy_api import CategoryBulkCreateRequest, CategoryCreateRequest, CategoryListResponse
from app.domain.enums import CategoryDimension
from app.domain.taxonomy import Category
from app.services.category_service import CategoryService

router = APIRouter(prefix="/api", tags=["categories"])


@router.get("/categories", response_model=CategoryListResponse)
def list_categories(
    dimension: CategoryDimension | None = Query(default=None),
    include_archived: bool = Query(default=False),
    category_service: CategoryService = Depends(get_category_service),
):
    category_service.seed_if_empty()
    return CategoryListResponse(categories=category_service.list(dimension=dimension, include_archived=include_archived))


@router.post("/categories", response_model=Category)
def create_category(
    request: CategoryCreateRequest,
    category_service: CategoryService = Depends(get_category_service),
):
    category_service.seed_if_empty()
    return category_service.create(
        name=request.name,
        dimension=request.dimension,
        slug=request.slug,
        description=request.description,
    )


@router.post("/categories/bulk", response_model=CategoryListResponse)
def create_categories_bulk(
    request: CategoryBulkCreateRequest,
    category_service: CategoryService = Depends(get_category_service),
):
    category_service.seed_if_empty()
    return CategoryListResponse(
        categories=category_service.create_many([item.model_dump() for item in request.categories])
    )


@router.get("/categories/{category_id}")
def get_category(
    category_id: str,
    category_service: CategoryService = Depends(get_category_service),
):
    category_service.seed_if_empty()
    return category_service.get_required(category_id)


@router.delete("/categories/{category_id}", response_model=Category)
def delete_category(
    category_id: str,
    category_service: CategoryService = Depends(get_category_service),
):
    category_service.seed_if_empty()
    return category_service.archive(category_id)
