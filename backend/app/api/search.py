"""语义类案检索接口 —— 同义词扩展 + SQL回退"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, case as sql_case
from app.core.database import get_db
from app.models.user import User
from app.models.case import Case
from app.schemas.case import CaseSearchRequest, CaseSearchResponse, CaseCardResponse
from app.services.search_service import semantic_search_es, expand_query, fts5_search_subquery, fts5_fulltext_search
from app.core.security import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/search", tags=["检索"])


@router.post("/semantic", response_model=CaseSearchResponse)
async def semantic_search(
    req: CaseSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
):
    """语义检索 —— 自然语言搜索案例（同义词扩展+SQL LIKE回退）"""
    raw_query = req.query.strip()
    search_mode = req.mode or "semantic"

    # 生成搜索描述（先构建，等结果后再写入活动日志）
    if search_mode == "structured":
        parts = []
        if req.cause and len(req.cause) > 0:
            parts.append(f"案由={'/'.join(req.cause)}")
        if req.court_level:
            parts.append(f"法院层级={req.court_level}")
        if req.procedure:
            parts.append(f"程序={req.procedure}")
        if req.region:
            parts.append(f"地域={req.region}")
        if req.date_from:
            parts.append(f"从{req.date_from}")
        if req.date_to:
            parts.append(f"至{req.date_to}")
        if raw_query:
            parts.append(raw_query[:100])
        detail = "结构化检索：" + ("，".join(parts) if parts else "未设置筛选条件")
    elif search_mode == "case_to_case":
        detail = "以案搜案：" + (raw_query[:200] if raw_query else "（未粘贴判决书内容）")
    else:
        detail = raw_query[:500] if raw_query else "语义检索（无关键词）"

    # 辅助函数：记录搜索活动（含检索结果）
    def _record_search(result_total: int, result_cases: list = None):
        if not current_user:
            return
        from app.models.user_content import UserActivity
        current_user.search_count = (current_user.search_count or 0) + 1
        db.add(current_user)
        result_data = {
            "total": result_total,
            "cases": []
        }
        if result_cases:
            result_data["cases"] = []
            for c in result_cases[:5]:
                if isinstance(c, dict):
                    result_data["cases"].append({
                        "id": c.get("case_id", c.get("id", 0)),
                        "title": (c.get("title") or c.get("case_no") or ""),
                        "case_no": c.get("case_no", ""),
                    })
                else:
                    result_data["cases"].append({
                        "id": getattr(c, "id", 0),
                        "title": (getattr(c, "title", None) or getattr(c, "case_no", None) or ""),
                        "case_no": getattr(c, "case_no", None) or "",
                    })
        db.add(UserActivity(user_id=current_user.id, activity_type="search", detail=detail[:500], result_data=result_data))
        db.commit()

    # 尝试 ES（如果可用）
    es_total, es_results = await semantic_search_es(raw_query, page=req.page, page_size=req.page_size)
    if es_total > 0:
        results = [CaseCardResponse(
            id=r["case_id"], case_no=r.get("case_no", ""), title=r.get("title"),
            court=r.get("court"), court_level=r.get("court_level"),
            trial_procedure=r.get("trial_procedure"), judgment_date=r.get("judgment_date"),
            ai_summary=(r.get("summary") or "")[:50] if r.get("summary") else None,
            matched_focus=r.get("case_category_2"), relevance_score=r.get("_score", 0.85),
            processing_status="completed",
        ) for r in es_results]
        _record_search(es_total, es_results)
        return CaseSearchResponse(total=es_total, page=req.page, page_size=req.page_size,
                                  results=results, fallback_note=None)

    # ====== SQL 回退搜索（FTS5 + 结构化过滤提前 + 减少 COUNT） ======
    primary_kws_raw, secondary_kws_raw = expand_query(raw_query)
    primary_kws = list(primary_kws_raw)
    secondary_kws = list(secondary_kws_raw)

    # 基础过滤（索引列优先）
    def base_filter(q):
        return q.filter(
            Case.is_deleted == False,
            Case.processing_status.in_(["completed", "linking", "extracting"]),
        )

    # 结构化筛选提前应用（缩小后续扫描范围）
    def apply_structured(q):
        if req.cause:
            q = q.filter(Case.case_category_2.in_(req.cause))
        if req.court_level:
            q = q.filter(Case.court_level == req.court_level)
        if req.procedure:
            q = q.filter(Case.trial_procedure == req.procedure)
        if req.region:
            q = q.filter(Case.court_region.ilike(f"%{req.region}%"))
        if req.date_from:
            q = q.filter(Case.judgment_date >= req.date_from)
        if req.date_to:
            q = q.filter(Case.judgment_date <= req.date_to)
        return q

    # 相关度评分（在 case-to-case 和后续流程中复用）
    def calc_relevance(c: Case, pkws: list, skws: list) -> float:
        score = 0.15
        matched = 0
        for kw in pkws:
            kwl = kw.lower()
            # 案号精确匹配 → 最高优先级
            if c.case_no and kwl in c.case_no: score += 0.50; matched += 5
            if c.case_category_2 and kwl == c.case_category_2: score += 0.30; matched += 3
            elif c.case_category_2 and kwl in c.case_category_2: score += 0.15; matched += 2
            if c.title and kwl in c.title.lower(): score += 0.10; matched += 1
            if c.case_category_3 and kwl in (c.case_category_3 or ""): score += 0.08; matched += 1
            if c.summary and kwl in c.summary.lower(): score += 0.05; matched += 1
        for kw in skws:
            kwl = kw.lower()
            if c.case_no and kwl in c.case_no: score += 0.30; matched += 3
            if c.case_category_2 and kwl in c.case_category_2: score += 0.06; matched += 1
            if c.title and kwl in c.title.lower(): score += 0.03; matched += 0.5
            if c.summary and kwl in c.summary.lower(): score += 0.02; matched += 0.3
        score += matched * 0.04
        return min(score, 0.99)

    # ====== 以案搜案：整份判决书直接 FTS5 全文匹配 ======
    is_case_to_case = (search_mode == "case_to_case" and raw_query and len(raw_query) > 50)
    if is_case_to_case:
        fts_full_ids = fts5_fulltext_search(db, raw_query, limit=100)
        if fts_full_ids and len(fts_full_ids) > 0 and fts_full_ids[0] != -1:
            ctc_q = apply_structured(base_filter(db.query(Case))).filter(Case.id.in_(fts_full_ids))
            ctc_total = ctc_q.count()
            if ctc_total > 0:
                ctc_q = ctc_q.order_by(
                    # 保持 FTS5 BM25 顺序（按 ID 在 fts_full_ids 中出现顺序）
                    sql_case(
                        {cid: i for i, cid in enumerate(fts_full_ids)},
                        value=Case.id,
                        else_=9999,
                    )
                )
                ctc_cases = ctc_q.offset((req.page - 1) * req.page_size).limit(req.page_size).all()
                ctc_results = [
                    CaseCardResponse(
                        id=c.id, case_no=c.case_no, title=c.title,
                        court=c.court, court_level=c.court_level,
                        trial_procedure=c.trial_procedure, judgment_date=c.judgment_date,
                        ai_summary=(c.summary or "")[:50] if c.summary else None,
                        matched_focus=c.case_category_2,
                        relevance_score=0.99 - (i * 0.01),  # 按 FTS5 BM25 排名给分
                        processing_status=c.processing_status,
                    )
                    for i, c in enumerate(ctc_cases)
                ]
                _record_search(ctc_total, ctc_cases)
                return CaseSearchResponse(
                    total=ctc_total, page=req.page, page_size=req.page_size,
                    results=ctc_results, fallback_note=None,
                )
        # FTS5 全文匹配无结果 → 继续走下面的关键词回退

    # ====== 以案搜案：跳过 Stage 1，直接走全文匹配 ======

    # ====== 案号精确搜索（query 匹配案号格式时优先走案号匹配） ======
    import re as _re
    cleaned = raw_query.replace(' ','')
    case_no_match = _re.match(r'^[（(]\d{4}[）)][一-龥\d]{2,20}号?$', cleaned)
    if case_no_match:
        alt1 = cleaned.replace('(','（').replace(')','）')
        alt2 = cleaned.replace('（','(').replace('）',')')
        case_q = apply_structured(base_filter(db.query(Case))).filter(
            or_(Case.case_no.like(f"%{alt1}%"), Case.case_no.like(f"%{alt2}%"))
        )
        case_results = case_q.order_by(Case.judgment_date.desc()).offset(
            (req.page - 1) * req.page_size
        ).limit(req.page_size).all()
        case_total = case_q.count()
        if case_total > 0:
            results = [CaseCardResponse(
                id=c.id, case_no=c.case_no, title=c.title,
                court=c.court, court_level=c.court_level,
                trial_procedure=c.trial_procedure, judgment_date=c.judgment_date,
                ai_summary=(c.summary or "")[:50] if c.summary else None,
                matched_focus=c.case_category_2,
                relevance_score=0.99,
                processing_status=c.processing_status,
            ) for c in case_results]
            _record_search(case_total, case_results)
            return CaseSearchResponse(
                total=case_total, page=req.page, page_size=req.page_size,
                results=results, fallback_note=None,
            )

    # Stage 1: primary 关键词搜 title + category + case_no（以案搜案模式下跳过）
    if not is_case_to_case and primary_kws:
        stage1_conditions = []
        for kw in primary_kws[:10]:
            p = f"%{kw}%"
            stage1_conditions.append(Case.case_no.ilike(p))
            stage1_conditions.append(Case.title.ilike(p))
            stage1_conditions.append(Case.case_category_2.ilike(p))
            stage1_conditions.append(Case.case_category_1.ilike(p))
        base_q = apply_structured(base_filter(db.query(Case))).filter(or_(*stage1_conditions))
    else:
        base_q = apply_structured(base_filter(db.query(Case)))

    quick_check = base_q.limit(10).all()
    # 仅在快检不足且有必要时 COUNT
    total = base_q.count() if len(quick_check) < 10 else max(len(quick_check), base_q.limit(50).count()) if primary_kws and not is_case_to_case else base_q.count()

    # Stage 2: 不足 10 条时，用 secondary 关键词扩展到全文（以案搜案直接走这里）
    if (len(quick_check) < 10 or is_case_to_case) and (secondary_kws or primary_kws):
        specific_secondary = [kw for kw in secondary_kws
                              if kw not in {"合同", "纠纷", "违法", "违约", "责任", "处理", "解决",
                                            "赔偿", "损害", "民事", "刑事", "行政", "法律"}]
        # 以案搜案：仅用 secondary 法律术语搜全文 + category
        search_kws = specific_secondary[:8] if not is_case_to_case else [kw for kw in secondary_kws if kw not in {"合同", "纠纷", "违法", "责任", "处理", "解决", "赔偿", "损害", "民事", "刑事", "行政", "法律"}][:15]
        if search_kws:
            ext_conditions = []
            for kw in search_kws[:10]:
                p = f"%{kw}%"
                ext_conditions.append(Case.case_category_2.ilike(p))
                # 以案搜案直接用 LIKE 搜全文（不用 FTS5 逐词搜索，FTS5 n-gram 效果差）
                if is_case_to_case:
                    ext_conditions.append(Case.full_text.ilike(p))
                else:
                    fts_ids = fts5_search_subquery(db, [kw])
                    if fts_ids is not None:
                        ext_conditions.append(Case.id.in_(fts_ids))
                    ext_conditions.append(Case.full_text.ilike(p))
            if ext_conditions:
                ext_q = apply_structured(base_filter(db.query(Case))).filter(or_(*ext_conditions))
                ext_total = ext_q.count()
                if ext_total > total:
                    base_q = ext_q
                    total = ext_total

    # Stage 3: 还不够时按案由类别放宽
    if total < 5:
        fallback_conds = []
        for kw in (primary_kws + secondary_kws)[:5]:
            p = f"%{kw}%"
            fallback_conds.append(Case.case_category_2.ilike(p))
        if fallback_conds:
            fb_q = apply_structured(base_filter(db.query(Case))).filter(or_(*fallback_conds))
            fb_total = fb_q.count()
            if fb_total > total:
                base_q = fb_q
                total = fb_total

    # 排序
    if req.sort_by == "date":
        base_q = base_q.order_by(Case.judgment_date.desc())
    else:
        base_q = base_q.order_by(Case.judgment_date.desc())

    # ---- 无结果降级：展示同案由案例 ----
    fallback_cases = []
    fallback_note = None
    if total == 0:
        fallback_note = "虽然没有完全匹配的案例，但以下案例在相关法律原则上具有参考价值"
        for kw in (primary_kws + secondary_kws)[:3]:
            fb = base_filter(db.query(Case)).filter(
                Case.case_category_2.ilike(f"%{kw}%"),
            ).limit(5).all()
            if fb:
                fallback_cases = fb
                total = len(fb)
                break

    offset = (req.page - 1) * req.page_size
    cases = base_q.offset(offset).limit(req.page_size).all() if total > 0 else fallback_cases[:req.page_size]

    results = [
        CaseCardResponse(
            id=c.id, case_no=c.case_no, title=c.title,
            court=c.court, court_level=c.court_level,
            trial_procedure=c.trial_procedure, judgment_date=c.judgment_date,
            ai_summary=(c.summary or "")[:50] if c.summary else None,
            matched_focus=c.case_category_2,
            relevance_score=calc_relevance(c, primary_kws, secondary_kws),
            processing_status=c.processing_status,
        )
        for c in cases
    ]

    # 按相关度排序
    results.sort(key=lambda r: r.relevance_score, reverse=True)

    _record_search(total, cases)
    return CaseSearchResponse(
        total=total, page=req.page, page_size=req.page_size,
        results=results, fallback_note=fallback_note,
    )


@router.get("/history")
async def search_history(current_user: User = Depends(get_current_user)):
    return {"history": []}
