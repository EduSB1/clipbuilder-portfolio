"""Groups API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.admin.dependencies import RequireAdmin
from app.admin.groups import crud
from app.admin.groups.schemas import (
    GroupCreate,
    GroupOut,
    GroupUpdate,
    GroupUsageOut,
    MemberAdd,
    MemberOut,
)
from app.database import get_db

router = APIRouter(prefix="/groups", tags=["admin-groups"])


@router.get("", response_model=list[GroupOut])
def list_groups(_admin: RequireAdmin, db: Session = Depends(get_db)):
    groups = crud.get_groups(db)
    return [
        GroupOut(
            id=g.id,
            name=g.name,
            description=g.description,
            parent_group_id=g.parent_group_id,
            max_storage_gb=g.max_storage_gb,
            max_monthly_ai_requests=g.max_monthly_ai_requests,
            can_use_gemini=g.can_use_gemini,
            
            can_use_whisper=g.can_use_whisper,
            can_export_html=g.can_export_html,
            can_export_docx=g.can_export_docx,
            can_export_md=g.can_export_md,
            can_export_pdf=g.can_export_pdf,
            created_at=g.created_at,
            member_count=getattr(g, "member_count", 0),
        )
        for g in groups
    ]


@router.post("", response_model=GroupOut, status_code=201)
def create_group(
    body: GroupCreate,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    for g in crud.get_groups(db):
        if g.name.lower() == body.name.strip().lower():
            raise HTTPException(status_code=400, detail="Nome do grupo já existe")
    group = crud.create_group(
        db,
        name=body.name,
        description=body.description,
        parent_group_id=body.parent_group_id,
        max_storage_gb=body.max_storage_gb,
        max_monthly_ai_requests=body.max_monthly_ai_requests,
        can_use_gemini=body.can_use_gemini,
        
        can_use_whisper=body.can_use_whisper,
        can_export_html=body.can_export_html,
        can_export_docx=body.can_export_docx,
        can_export_md=body.can_export_md,
        can_export_pdf=body.can_export_pdf,
    )
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        parent_group_id=group.parent_group_id,
        max_storage_gb=group.max_storage_gb,
        max_monthly_ai_requests=group.max_monthly_ai_requests,
        can_use_gemini=group.can_use_gemini,
        
        can_use_whisper=group.can_use_whisper,
        can_export_html=group.can_export_html,
        can_export_docx=group.can_export_docx,
        can_export_md=group.can_export_md,
        can_export_pdf=group.can_export_pdf,
        created_at=group.created_at,
        member_count=0,
    )


@router.get("/{group_id}", response_model=GroupOut)
def get_group(group_id: int, _admin: RequireAdmin, db: Session = Depends(get_db)):
    group = crud.get_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    cnt = 0
    from sqlalchemy import func, select

    from app.admin.models import UserGroupMember
    cnt = db.scalar(select(func.count()).where(UserGroupMember.group_id == group_id)) or 0
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        parent_group_id=group.parent_group_id,
        max_storage_gb=group.max_storage_gb,
        max_monthly_ai_requests=group.max_monthly_ai_requests,
        can_use_gemini=group.can_use_gemini,
        
        can_use_whisper=group.can_use_whisper,
        can_export_html=group.can_export_html,
        can_export_docx=group.can_export_docx,
        can_export_md=group.can_export_md,
        can_export_pdf=group.can_export_pdf,
        created_at=group.created_at,
        member_count=cnt,
    )


@router.put("/{group_id}", response_model=GroupOut)
def update_group(
    group_id: int,
    body: GroupUpdate,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    group = crud.get_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    kwargs = body.model_dump(exclude_unset=True)
    group = crud.update_group(db, group, **kwargs)
    from sqlalchemy import func, select

    from app.admin.models import UserGroupMember
    cnt = db.scalar(select(func.count()).where(UserGroupMember.group_id == group_id)) or 0
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        parent_group_id=group.parent_group_id,
        max_storage_gb=group.max_storage_gb,
        max_monthly_ai_requests=group.max_monthly_ai_requests,
        can_use_gemini=group.can_use_gemini,
        
        can_use_whisper=group.can_use_whisper,
        can_export_html=group.can_export_html,
        can_export_docx=group.can_export_docx,
        can_export_md=group.can_export_md,
        can_export_pdf=group.can_export_pdf,
        created_at=group.created_at,
        member_count=cnt,
    )


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, _admin: RequireAdmin, db: Session = Depends(get_db)):
    group = crud.get_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    crud.delete_group(db, group)


@router.get("/{group_id}/members", response_model=list[MemberOut])
def list_members(group_id: int, _admin: RequireAdmin, db: Session = Depends(get_db)):
    group = crud.get_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    rows = crud.get_members(db, group_id)
    return [
        MemberOut(
            user_id=m.user_id,
            group_id=m.group_id,
            role=m.role,
            joined_at=m.joined_at,
            user_email=u.email,
            user_full_name=u.full_name,
        )
        for m, u in rows
    ]


@router.post("/{group_id}/members", status_code=201)
def add_member(
    group_id: int,
    body: MemberAdd,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    group = crud.get_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    from app.admin.crud import get_user
    user = get_user(db, body.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    from app.admin.models import UserGroupMember
    existing = db.get(UserGroupMember, (body.user_id, group_id))
    if existing:
        raise HTTPException(status_code=400, detail="Usuário já é membro do grupo")
    crud.add_member(db, group_id, body.user_id, body.role)
    return {"ok": True}


@router.delete("/{group_id}/members/{user_id}", status_code=204)
def remove_member(
    group_id: int,
    user_id: str,
    _admin: RequireAdmin,
    db: Session = Depends(get_db),
):
    group = crud.get_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    crud.remove_member(db, group_id, user_id)


@router.get("/{group_id}/usage", response_model=GroupUsageOut)
def group_usage(group_id: int, _admin: RequireAdmin, db: Session = Depends(get_db)):
    group = crud.get_group(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    return GroupUsageOut(**crud.get_group_usage(db, group_id))
