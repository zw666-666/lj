"""法官/法院画像接口"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_premium_optional
from app.models.user import User
from app.models.case import JudgeProfile, Case
from app.schemas.profile import JudgeProfileResponse

router = APIRouter(prefix="/api/profile", tags=["画像"])


@router.get("/judge/{name}", response_model=JudgeProfileResponse)
def get_judge_profile(
    name: str,
    case_category: str = Query(default=None),
    year_from: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_premium_optional),
):
    """获取法官画像。免费用户基础统计，会员深度分析。"""
    profile = db.query(JudgeProfile).filter(JudgeProfile.judge_name == name).first()
    if not profile:
        case_count = db.query(Case).filter(Case.judge_name == name, Case.is_deleted == False).count()
        if case_count == 0:
            raise HTTPException(status_code=404, detail="未找到该法官信息")
        profile = JudgeProfile(
            judge_name=name,
            court=db.query(Case).filter(Case.judge_name == name).first().court,
            total_cases=case_count,
        )

    is_premium = current_user is not None

    return JudgeProfileResponse(
        id=profile.id or 0,
        judge_name=profile.judge_name,
        court=profile.court,
        division=profile.division if is_premium else None,
        total_cases=profile.total_cases or 0,
        # 会员：完整深度分析数据
        avg_duration_days=float(profile.avg_duration_days) if is_premium and profile.avg_duration_days else None,
        support_plaintiff_ratio=float(profile.support_plaintiff_ratio) if is_premium and profile.support_plaintiff_ratio else None,
        support_defendant_ratio=float(profile.support_defendant_ratio) if is_premium and profile.support_defendant_ratio else None,
        partial_support_ratio=float(profile.partial_support_ratio) if is_premium and profile.partial_support_ratio else None,
        appeal_reversal_ratio=float(profile.appeal_reversal_ratio) if is_premium and profile.appeal_reversal_ratio else None,
        reversed_by_superior_ratio=float(profile.reversed_by_superior_ratio) if is_premium and profile.reversed_by_superior_ratio else None,
        avg_opinion_length=profile.avg_opinion_length if is_premium else None,
        top_articles=profile.top_articles if is_premium else [],
        case_type_distribution=profile.case_type_distribution if is_premium else [],
        style_tags=profile.style_tags if is_premium else [],
    )


@router.get("/court/{name}")
def get_court_profile(name: str, db: Session = Depends(get_db)):
    """获取法院画像"""
    total = db.query(Case).filter(Case.court == name, Case.is_deleted == False).count()
    return {
        "court_name": name,
        "total_cases": total,
        "support_ratio_distribution": {},
        "reversal_ratio": None,
    }
