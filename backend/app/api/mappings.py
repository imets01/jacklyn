from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import CustomCSVMapping
from app.models._common import utcnow
from app.schemas.api import MappingIn, MappingOut

router = APIRouter(prefix="/api/mappings", tags=["mappings"])


@router.get("", response_model=list[MappingOut])
def list_mappings(session: DbSession, user: CurrentUser) -> list[MappingOut]:
    rows = session.scalars(
        select(CustomCSVMapping).where(CustomCSVMapping.user_id == user.id).order_by(CustomCSVMapping.name)
    )
    return [MappingOut.model_validate(row) for row in rows]


@router.post("", response_model=MappingOut, status_code=status.HTTP_201_CREATED)
def save_mapping(payload: MappingIn, session: DbSession, user: CurrentUser) -> MappingOut:
    """Create a preset, or overwrite the one with the same name."""
    mapping = session.scalar(
        select(CustomCSVMapping).where(CustomCSVMapping.user_id == user.id, CustomCSVMapping.name == payload.name)
    )
    config = payload.config.model_dump(mode="json")
    if mapping is None:
        mapping = CustomCSVMapping(
            user_id=user.id, name=payload.name, header_signature=payload.header_signature, config=config
        )
        session.add(mapping)
    else:
        mapping.header_signature = payload.header_signature
        mapping.config = config
        mapping.updated_at = utcnow()
    session.commit()
    return MappingOut.model_validate(mapping)


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping(mapping_id: int, session: DbSession, user: CurrentUser) -> Response:
    mapping = session.get(CustomCSVMapping, mapping_id)
    if mapping is None or mapping.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mapping preset not found")
    session.delete(mapping)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
