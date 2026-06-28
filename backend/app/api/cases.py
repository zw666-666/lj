"""案例阅读相关接口"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user_optional
from app.models.user import User
from app.models.case import Case, DisputeFocus, LegalRule, LegalEntity, CaseRelation
from app.schemas.case import CaseDetailResponse, RelatedCaseResponse, DisputeFocusResponse, LegalRuleResponse

router = APIRouter(prefix="/api/case", tags=["案例"])


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
):
    """获取案例详情（双栏阅读器数据）"""
    case = db.query(Case).filter(Case.id == case_id, Case.is_deleted == False).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")

    # 记录阅读次数和阅读历史（仅登录用户）
    if current_user:
        from app.models.user_content import UserActivity
        from datetime import datetime, timezone
        current_user.read_count = (current_user.read_count or 0) + 1
        db.add(current_user)
        # 先记录旧活动（以便后面删除），然后插入新活动
        db.add(UserActivity(
            user_id=current_user.id,
            activity_type="read",
            detail=(case.title or case.case_no)[:500],
            case_id=case.id,
        ))
        db.commit()

    focuses = db.query(DisputeFocus).filter(DisputeFocus.case_id == case_id).all()
    rules = db.query(LegalRule).filter(LegalRule.case_id == case_id).all()
    articles = db.query(LegalEntity).filter(
        LegalEntity.case_id == case_id, LegalEntity.entity_type == "article"
    ).all()

    return CaseDetailResponse(
        id=case.id,
        case_no=case.case_no,
        title=case.title,
        court=case.court,
        court_level=case.court_level,
        court_region=case.court_region,
        judge_name=case.judge_name,
        trial_procedure=case.trial_procedure,
        case_category_1=case.case_category_1,
        case_category_2=case.case_category_2,
        case_category_3=case.case_category_3,
        judgment_date=case.judgment_date,
        full_text=case.full_text,
        summary=case.summary,
        ruling_abstract=case.ruling_abstract,
        tags=case.tags or [],
        processing_status=case.processing_status,
        confidence_score=float(case.confidence_score or 0),
        dispute_focuses=[
            DisputeFocusResponse(
                id=f.id, focus_name=f.focus_name,
                plaintiff_claim=f.plaintiff_claim, defendant_defense=f.defendant_defense,
                court_finding=f.court_finding,
            ) for f in focuses
        ],
        legal_rules=[
            LegalRuleResponse(
                id=r.id, rule_text=r.rule_text, rule_type=r.rule_type,
                related_article=r.related_article,
            ) for r in rules
        ],
        articles=[a.entity_name for a in articles],
        created_at=case.created_at,
    )


@router.get("/{case_id}/related", response_model=list[RelatedCaseResponse])
def get_related_cases(case_id: int, db: Session = Depends(get_db)):
    """获取关联案例"""
    relations = db.query(CaseRelation).filter(
        (CaseRelation.source_case_id == case_id) | (CaseRelation.target_case_id == case_id)
    ).limit(20).all()

    results = []
    for rel in relations:
        target_id = rel.target_case_id if rel.source_case_id == case_id else rel.source_case_id
        target = db.query(Case).filter(Case.id == target_id, Case.is_deleted == False).first()
        if target:
            results.append(RelatedCaseResponse(
                id=target.id,
                case_no=target.case_no,
                title=target.title,
                court=target.court,
                relation_type=rel.relation_type,
                relation_detail=rel.relation_detail,
            ))
    return results
