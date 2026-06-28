"""律师个人工作台接口"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.case import Case
from app.models.user_content import Favorite, Note, CaseGroup, CaseGroupItem

router = APIRouter(prefix="/api/workspace", tags=["工作台"])


# ===== 收藏 =====
@router.get("/favorites")
def get_favorites(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.case import Case
    favs = (
        db.query(Favorite, Case)
        .join(Case, Case.id == Favorite.case_id)
        .filter(Favorite.user_id == current_user.id)
        .all()
    )
    return [
        {
            "id": f.Favorite.id,
            "case_id": f.Favorite.case_id,
            "title": f.Case.title or f.Case.case_no,
            "case_no": f.Case.case_no,
            "court": f.Case.court,
            "tags": f.Favorite.personal_tags,
            "created_at": str(f.Favorite.created_at),
        }
        for f in favs
    ]


@router.post("/favorites/{case_id}", status_code=201)
def add_favorite(
    case_id: int,
    body: dict = {},
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 检查案例是否存在
    from app.models.case import Case
    case = db.query(Case).filter(Case.id == case_id, Case.is_deleted == False).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    existing = db.query(Favorite).filter(Favorite.user_id == current_user.id, Favorite.case_id == case_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="已收藏")
    fav = Favorite(user_id=current_user.id, case_id=case_id)
    db.add(fav)
    db.flush()

    # 如果指定了分组，同时加入分组
    group_id = body.get("group_id") if body else None
    if group_id:
        group = db.query(CaseGroup).filter(
            CaseGroup.id == group_id, CaseGroup.user_id == current_user.id
        ).first()
        if group:
            db.add(CaseGroupItem(group_id=group_id, case_id=case_id))

    db.commit()
    return {"id": fav.id, "case_id": case_id, "message": "收藏成功"}


@router.put("/favorites/{case_id}")
def update_favorite_tags(
    case_id: int,
    body: dict = {},
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新收藏案例的个人标签"""
    fav = db.query(Favorite).filter(Favorite.user_id == current_user.id, Favorite.case_id == case_id).first()
    if not fav:
        raise HTTPException(status_code=404, detail="未收藏")
    tags = body.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    fav.personal_tags = tags
    db.commit()
    return {"id": fav.id, "case_id": case_id, "tags": tags, "message": "标签已更新"}


@router.delete("/favorites/{case_id}")
def remove_favorite(case_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fav = db.query(Favorite).filter(Favorite.user_id == current_user.id, Favorite.case_id == case_id).first()
    if not fav:
        raise HTTPException(status_code=404, detail="未收藏")
    db.delete(fav)
    db.commit()
    return {"message": "取消收藏成功"}


# ===== 笔记 =====
@router.get("/notes/{case_id}")
def get_notes(case_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notes = db.query(Note).filter(Note.user_id == current_user.id, Note.case_id == case_id).all()
    return [{"id": n.id, "content": n.content, "paragraph_ref": n.paragraph_ref, "created_at": str(n.created_at)} for n in notes]


@router.get("/notes")
def get_all_notes(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前用户所有笔记（含案例信息）"""
    from app.models.case import Case
    notes = (
        db.query(Note, Case)
        .join(Case, Case.id == Note.case_id)
        .filter(Note.user_id == current_user.id)
        .order_by(Note.created_at.desc())
        .all()
    )
    return [
        {
            "id": n.Note.id,
            "case_id": n.Note.case_id,
            "case_title": n.Case.title or n.Case.case_no,
            "case_no": n.Case.case_no,
            "content": n.Note.content,
            "paragraph_ref": n.Note.paragraph_ref,
            "created_at": str(n.Note.created_at),
        }
        for n in notes
    ]


@router.post("/notes/{case_id}", status_code=201)
def add_note(case_id: int, note_data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = Note(
        user_id=current_user.id, case_id=case_id,
        content=note_data.get("content", ""),
        paragraph_ref=note_data.get("paragraph_ref"),
        entity_ref=note_data.get("entity_ref"),
    )
    db.add(note)
    db.commit()
    return {"id": note.id, "content": note.content, "created_at": str(note.created_at)}


@router.put("/notes/{note_id}")
def update_note(note_id: int, note_data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id, Note.user_id == current_user.id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    if "content" in note_data:
        note.content = note_data["content"]
    if "paragraph_ref" in note_data:
        note.paragraph_ref = note_data["paragraph_ref"]
    db.commit()
    return {"id": note.id, "content": note.content, "created_at": str(note.created_at)}


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id, Note.user_id == current_user.id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    db.delete(note)
    db.commit()
    return {"message": "笔记已删除"}


# ===== 分组 =====
@router.get("/groups")
def get_groups(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    groups = db.query(CaseGroup).filter(CaseGroup.user_id == current_user.id).order_by(CaseGroup.sort_order).all()
    result = []
    for g in groups:
        items = db.query(CaseGroupItem).filter(CaseGroupItem.group_id == g.id).count()
        result.append({"id": g.id, "name": g.group_name, "description": g.description, "item_count": items, "created_at": str(g.created_at)})
    return result


@router.post("/groups", status_code=201)
def create_group(group_data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = CaseGroup(user_id=current_user.id, group_name=group_data.get("name", "新分组"), description=group_data.get("description"))
    db.add(group)
    db.commit()
    return {"id": group.id, "message": "分组创建成功"}


@router.post("/groups/{group_id}/items/{case_id}")
def add_to_group(group_id: int, case_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(CaseGroup).filter(CaseGroup.id == group_id, CaseGroup.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")
    item = CaseGroupItem(group_id=group_id, case_id=case_id)
    db.add(item)
    db.commit()
    return {"message": "添加到分组成功"}


@router.get("/groups/{group_id}/items")
def get_group_items(group_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.case import Case
    group = db.query(CaseGroup).filter(CaseGroup.id == group_id, CaseGroup.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")
    items = (
        db.query(CaseGroupItem, Case)
        .join(Case, Case.id == CaseGroupItem.case_id)
        .filter(CaseGroupItem.group_id == group_id)
        .all()
    )
    return [
        {
            "id": item.CaseGroupItem.id,
            "case_id": item.CaseGroupItem.case_id,
            "title": item.Case.title or item.Case.case_no,
            "case_no": item.Case.case_no,
            "court": item.Case.court,
            "judgment_date": str(item.Case.judgment_date) if item.Case.judgment_date else None,
        }
        for item in items
    ]


@router.delete("/groups/{group_id}/items/{case_id}")
def remove_from_group(
    group_id: int,
    case_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = db.query(CaseGroup).filter(CaseGroup.id == group_id, CaseGroup.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")
    item = db.query(CaseGroupItem).filter(
        CaseGroupItem.group_id == group_id, CaseGroupItem.case_id == case_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="该案例不在分组中")
    db.delete(item)
    db.commit()
    return {"message": "已从分组移除"}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(CaseGroup).filter(CaseGroup.id == group_id, CaseGroup.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")
    # 显式删除组内所有案例（SQLite 默认不启外键，需手动清理）
    db.query(CaseGroupItem).filter(CaseGroupItem.group_id == group_id).delete()
    db.delete(group)
    db.commit()
    return {"message": "分组已删除"}


# ===== 导出报告（会员功能，免费用户终身2次） =====

EXPORT_LIFETIME_LIMIT = 2


@router.post("/export/case/{case_id}")
def export_case_report(
    case_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出案例报告
    - 免费用户：终身只能导出2次
    - 会员/管理员：不限次数
    """
    case = db.query(Case).filter(Case.id == case_id, Case.is_deleted == False).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")

    is_premium = current_user.role in ("premium", "admin")

    if not is_premium:
        # 检查终身导出次数
        used = current_user.lifetime_export_count or 0
        if used >= EXPORT_LIFETIME_LIMIT:
            raise HTTPException(
                status_code=402,
                detail=f"免费导出次数已用完（{EXPORT_LIFETIME_LIMIT}次），升级会员即可无限导出",
            )
        # 递增导出计数
        current_user.lifetime_export_count = used + 1
        db.commit()

    # 构建导出内容（简易文本格式，后续可扩展为PDF/DOCX）
    lines = []
    lines.append(f"# 案例报告")
    lines.append(f"## 案号：{case.case_no or '无'}")
    lines.append(f"## 标题：{case.title or case.case_no or '无'}")
    lines.append(f"## 审理法院：{case.court or '无'}")
    lines.append(f"## 案由：{case.case_category_2 or case.case_category_1 or '无'}")
    lines.append(f"## 裁判日期：{str(case.judgment_date)[:10] if case.judgment_date else '无'}")
    lines.append(f"")
    if case.summary:
        lines.append(f"## 案情概要")
        lines.append(case.summary)
        lines.append(f"")
    if case.ruling_abstract:
        lines.append(f"## 裁判要旨")
        lines.append(case.ruling_abstract)
        lines.append(f"")

    if is_premium:
        lines.append(f"## 判决书全文")
        lines.append(case.full_text or "无全文")

    content = "\n".join(lines)

    return PlainTextResponse(
        content=content,
        headers={
            "Content-Disposition": f'attachment; filename="case_{case_id}_report.txt"',
            "X-Export-Remaining": str(max(0, EXPORT_LIFETIME_LIMIT - (current_user.lifetime_export_count or 0)))
            if not is_premium else "unlimited",
        },
    )


@router.post("/export/comparison")
def export_comparison_report(
    body: dict = {},
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出多案例对标分析报告
    - 接受 case_ids（数据库案例）和 uploaded_cases（上传案例）
    - 生成包含案例概览、对比矩阵、关键差异变量、案例详情的报告
    - 免费用户：终身只能导出2次
    - 会员/管理员：不限次数，含判决书全文
    """
    case_ids: list = body.get("case_ids", []) or []
    uploaded_cases: list = body.get("uploaded_cases", []) or []

    if len(case_ids) + len(uploaded_cases) < 2:
        raise HTTPException(status_code=400, detail="至少需要2个案例才能导出对比报告")
    if len(case_ids) + len(uploaded_cases) > 5:
        raise HTTPException(status_code=400, detail="最多支持5个案例对比")

    is_premium = current_user.role in ("premium", "admin")

    if not is_premium:
        used = current_user.lifetime_export_count or 0
        if used >= EXPORT_LIFETIME_LIMIT:
            raise HTTPException(
                status_code=402,
                detail=f"免费导出次数已用完（{EXPORT_LIFETIME_LIMIT}次），升级会员即可无限导出",
            )
        current_user.lifetime_export_count = used + 1
        db.commit()

    # 载入数据库案例并按 case_ids 顺序排列
    db_cases = (
        db.query(Case).filter(Case.id.in_(case_ids), Case.is_deleted == False).all()
        if case_ids
        else []
    )
    db_map = {c.id: c for c in db_cases}

    # 统一案例信息结构（dict，方便后续处理）
    cases_info: list[dict] = []
    for cid in case_ids:
        c = db_map.get(cid)
        if not c:
            continue
        cases_info.append({
            "case_no": c.case_no or "",
            "title": c.title or c.case_no or "",
            "court": c.court or "",
            "court_level": c.court_level or "",
            "trial_procedure": c.trial_procedure or "",
            "case_category_1": c.case_category_1 or "",
            "case_category_2": c.case_category_2 or "",
            "judgment_date": str(c.judgment_date)[:10] if c.judgment_date else "",
            "summary": c.summary or "",
            "ruling_abstract": c.ruling_abstract or "",
            "full_text": c.full_text or "",
            "source": "数据库",
        })
    for uc in uploaded_cases:
        cases_info.append({
            "case_no": uc.get("case_no", "") or "",
            "title": uc.get("title", "") or "",
            "court": uc.get("court", "") or "",
            "court_level": uc.get("court_level", "") or "",
            "trial_procedure": uc.get("trial_procedure", "") or "",
            "case_category_1": "",
            "case_category_2": uc.get("case_category_2", "") or "",
            "judgment_date": uc.get("judgment_date", "") or "",
            "summary": (uc.get("full_text") or "")[:300],
            "ruling_abstract": "",
            "full_text": uc.get("full_text", "") or "",
            "source": "用户上传",
        })

    if len(cases_info) < 2:
        raise HTTPException(status_code=400, detail="有效案例不足2个，无法生成对比报告")

    COURT_LEVEL_CN = {
        "supreme": "最高人民法院",
        "high": "高级人民法院",
        "intermediate": "中级人民法院",
        "basic": "基层人民法院",
    }
    PROCEDURE_CN = {
        "first": "一审",
        "second": "二审",
        "retrial": "再审",
        "supervision": "审判监督",
    }

    from datetime import datetime, date as date_cls

    lines: list[str] = []
    sep = "=" * 60
    lines.append(sep)
    lines.append("# 案例对标分析报告")
    lines.append(sep)
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"对比案例数：{len(cases_info)}")
    lines.append(f"报告类型：{'会员深度版' if is_premium else '基础版'}")
    lines.append("")

    # 一、案例概览
    lines.append("## 一、案例概览")
    lines.append("-" * 60)
    for i, c in enumerate(cases_info, 1):
        lines.append(f"【案例{i}】{c['title']}")
        lines.append(f"  案号：{c['case_no'] or '无'}")
        lines.append(f"  法院：{c['court'] or '无'}")
        lines.append(f"  法院层级：{COURT_LEVEL_CN.get(c['court_level'], c['court_level'] or '无')}")
        lines.append(f"  审判程序：{PROCEDURE_CN.get(c['trial_procedure'], c['trial_procedure'] or '无')}")
        lines.append(f"  案由：{c['case_category_2'] or c['case_category_1'] or '无'}")
        lines.append(f"  裁判日期：{c['judgment_date'] or '无'}")
        lines.append(f"  来源：{c['source']}")
        lines.append("")

    # 二、对比矩阵
    lines.append("## 二、对比矩阵")
    lines.append("-" * 60)
    dimensions = [
        ("案号", lambda c: c["case_no"] or "-"),
        ("标题", lambda c: c["title"] or "-"),
        ("法院", lambda c: c["court"] or "-"),
        ("法院层级", lambda c: COURT_LEVEL_CN.get(c["court_level"], c["court_level"] or "-")),
        ("审判程序", lambda c: PROCEDURE_CN.get(c["trial_procedure"], c["trial_procedure"] or "-")),
        ("案由", lambda c: c["case_category_2"] or c["case_category_1"] or "-"),
        ("判决日期", lambda c: c["judgment_date"] or "-"),
        (
            "案情概要",
            lambda c: (c["summary"] or "-")[:80]
            if is_premium
            else (c["summary"] or "-")[:40],
        ),
        (
            "裁判要旨",
            lambda c: (c["ruling_abstract"] or "-")[:80]
            if is_premium
            else (c["ruling_abstract"] or "-")[:40],
        ),
    ]

    for dim_name, fn in dimensions:
        lines.append(f"■ {dim_name}")
        for i, c in enumerate(cases_info, 1):
            lines.append(f"  案例{i}：{fn(c)}")
        lines.append("")

    # 三、关键差异变量
    lines.append("## 三、关键差异变量")
    lines.append("-" * 60)
    diffs: list[str] = []

    # 审判程序差异
    procedures = set(
        PROCEDURE_CN.get(c["trial_procedure"], c["trial_procedure"])
        for c in cases_info
        if c["trial_procedure"]
    )
    if len(procedures) > 1:
        diffs.append(
            f"审判程序不同：{'、'.join(procedures)}。不同程序可能影响举证责任分配和审查标准"
        )

    # 法院层级差异
    levels = set(
        COURT_LEVEL_CN.get(c["court_level"], c["court_level"])
        for c in cases_info
        if c["court_level"]
    )
    if len(levels) > 1:
        diffs.append(
            f"审理法院层级不同：{'、'.join(levels)}。不同层级法院的裁判观点权威性不同"
        )

    # 案由差异
    categories = set(c["case_category_2"] for c in cases_info if c["case_category_2"])
    if len(categories) > 1:
        diffs.append(
            f"案由分类不同：{'、'.join(categories)}。需关注不同案由下法律适用要件的差异"
        )

    # 裁判日期跨度
    dates: list = []
    for c in cases_info:
        d = c["judgment_date"]
        if not d:
            continue
        if isinstance(d, str):
            try:
                d = date_cls.fromisoformat(d[:10])
            except ValueError:
                continue
        dates.append(d)
    if len(dates) >= 2:
        span = (max(dates) - min(dates)).days
        if span > 365:
            diffs.append(
                f"裁判时间跨度达{span}天（约{span // 365}年），需注意法律修订或司法解释变化的影响"
            )

    # 裁判结果倾向
    rulings = [c["ruling_abstract"] or "" for c in cases_info]
    if len(rulings) >= 2 and any(rulings):
        support_kw = ["支持", "判令", "支付", "赔偿", "返还"]
        reject_kw = ["驳回", "不予支持", "不成立"]
        patterns = []
        for r in rulings:
            s = sum(1 for k in support_kw if k in r)
            d = sum(1 for k in reject_kw if k in r)
            patterns.append("支持" if s > d else "驳回" if d > s else "其他")
        if len(set(patterns)) > 1:
            diffs.append(
                f"裁判结果倾向不同：{' vs '.join(patterns)}。需分析导致不同结果的关键事实或法律适用差异"
            )

    if diffs:
        for idx, d in enumerate(diffs, 1):
            lines.append(f"{idx}. {d}")
    else:
        lines.append("这些案例在基本维度上较为相似。深入分析需要结合判决书全文进行AI辅助对比")
    lines.append("")

    # 四、案例详情
    lines.append("## 四、案例详情")
    lines.append("-" * 60)
    for i, c in enumerate(cases_info, 1):
        lines.append(f"【案例{i}】{c['title']}")
        if c["summary"]:
            lines.append("【案情概要】")
            lines.append(c["summary"])
            lines.append("")
        if c["ruling_abstract"]:
            lines.append("【裁判要旨】")
            lines.append(c["ruling_abstract"])
            lines.append("")
        if is_premium and c["full_text"]:
            lines.append("【判决书全文】")
            lines.append(c["full_text"])
            lines.append("")
        lines.append("")

    lines.append(sep)
    lines.append("报告生成完毕  ·  律镜")
    lines.append(sep)

    content = "\n".join(lines)

    return PlainTextResponse(
        content=content,
        headers={
            "Content-Disposition": f'attachment; filename="comparison_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt"',
            "X-Export-Remaining": str(
                max(0, EXPORT_LIFETIME_LIMIT - (current_user.lifetime_export_count or 0))
            )
            if not is_premium
            else "unlimited",
        },
    )


@router.get("/export/quota")
def get_export_quota(current_user: User = Depends(get_current_user)):
    """查询导出配额"""
    is_premium = current_user.role in ("premium", "admin")
    if is_premium:
        return {"used": 0, "limit": -1, "remaining": -1, "is_premium": True}
    used = current_user.lifetime_export_count or 0
    return {
        "used": used,
        "limit": EXPORT_LIFETIME_LIMIT,
        "remaining": max(0, EXPORT_LIFETIME_LIMIT - used),
        "is_premium": False,
    }
