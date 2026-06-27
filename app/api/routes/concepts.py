from fastapi import APIRouter, Depends

from app.api.dependencies import get_category_service, get_concept_service
from app.api.schemas.taxonomy_api import ConceptCreateRequest, ConceptListResponse
from app.domain.taxonomy import Concept
from app.services.category_service import CategoryService
from app.services.concept_service import ConceptService

router = APIRouter(prefix="/api", tags=["concepts"])


@router.get("/concepts", response_model=ConceptListResponse)
def list_concepts(concept_service: ConceptService = Depends(get_concept_service)):
    return ConceptListResponse(concepts=concept_service.list())


@router.post("/concepts", response_model=Concept)
def create_concept(
    request: ConceptCreateRequest,
    category_service: CategoryService = Depends(get_category_service),
    concept_service: ConceptService = Depends(get_concept_service),
):
    category_service.seed_if_empty()
    return concept_service.create(
        name=request.name,
        category_ids=request.category_ids,
        slug=request.slug,
        description=request.description,
    )


@router.get("/concepts/{concept_id}", response_model=Concept)
def get_concept(
    concept_id: str,
    concept_service: ConceptService = Depends(get_concept_service),
):
    return concept_service.get_required(concept_id)
