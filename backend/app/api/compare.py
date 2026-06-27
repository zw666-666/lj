"""案例对标分析接口"""
import re
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user_optional, get_current_premium_optional
from app.models.user import User
from app.models.case import Case, DisputeFocus, LegalEntity, LegalRule
from app.schemas.profile import CompareRequest, CompareResponse, CompareMatrixRow, KeyVariable

router = APIRouter(prefix="/api/compare", tags=["对标分析"])

COURT_LEVEL_CN = {"supreme": "最高人民法院", "high": "高级人民法院", "intermediate": "中级人民法院", "basic": "基层人民法院"}
PROCEDURE_CN = {"first": "一审", "second": "二审", "retrial": "再审", "supervision": "审判监督"}


@router.get("/search")
def search_cases(
    q: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
):
    """搜索案例（用于对标分析添加案例）"""
    if not q:
        cases = db.query(Case).filter(
            Case.processing_status == "completed", Case.is_deleted == False,
        ).order_by(Case.judgment_date.desc()).limit(20).all()
    else:
        p = f"%{q}%"
        cases = db.query(Case).filter(
            Case.processing_status == "completed",
            Case.is_deleted == False,
            (Case.title.ilike(p)) | (Case.case_no.ilike(p)) | (Case.case_category_2.ilike(p)),
        ).order_by(Case.judgment_date.desc()).limit(30).all()
    return [
        {
            "id": c.id, "case_no": c.case_no, "title": c.title or c.case_no,
            "court": c.court, "case_category_2": c.case_category_2,
            "judgment_date": str(c.judgment_date) if c.judgment_date else None,
        }
        for c in cases
    ]


@router.post("/start", response_model=CompareResponse)
def compare_cases(
    req: CompareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_premium_optional),
):
    """多案例对比分析（2-5个案例）
    - 免费用户：基础9维度对比
    - 会员用户：扩展对比（含争议焦点、法律规则、AI深度分析等）
    """
    cases = list(db.query(Case).filter(
        Case.id.in_(req.case_ids), Case.is_deleted == False,
    ).all()) if req.case_ids else []

    # 构造上传案例的临时对象（自增负数ID，避免hash冲突）
    from collections import namedtuple
    TempCase = namedtuple("TempCase", ["id", "case_no", "title", "court", "court_level",
                                        "trial_procedure", "case_category_1", "case_category_2",
                                        "judgment_date", "summary", "ruling_abstract", "tags", "full_text"])
    _temp_id_counter = -1
    for uc in req.uploaded_cases:
        temp = TempCase(
            id=_temp_id_counter,
            case_no=uc.get("case_no", ""),
            title=uc.get("title", ""),
            court=uc.get("court", ""),
            court_level=uc.get("court_level", ""),
            trial_procedure=uc.get("trial_procedure", ""),
            case_category_1="",
            case_category_2=uc.get("case_category_2", ""),
            judgment_date=uc.get("judgment_date", ""),
            summary=uc.get("full_text", "")[:300],
            ruling_abstract="",
            tags="",
            full_text=uc.get("full_text", ""),
        )
        _temp_id_counter -= 1
        cases.append(temp)

    if len(cases) < 2:
        raise HTTPException(status_code=400, detail="至少需要2个有效案例")

    case_map = {c.id: c for c in cases}
    all_ids = req.case_ids + [c.id for c in cases if c.id < 0]
    ordered = [case_map[cid] for cid in all_ids if cid in case_map]

    is_premium = current_user is not None

    # 构建对比矩阵
    dimensions = [
        ("案号", lambda c: c.case_no or "-"),
        ("标题", lambda c: c.title or c.case_no or "-"),
        ("法院", lambda c: c.court or "-"),
        ("法院层级", lambda c: COURT_LEVEL_CN.get(c.court_level, c.court_level or "-")),
        ("审判程序", lambda c: PROCEDURE_CN.get(c.trial_procedure, c.trial_procedure or "-")),
        ("案由", lambda c: (c.case_category_2 or c.case_category_1 or "-")),
        ("判决日期", lambda c: str(c.judgment_date)[:10] if c.judgment_date else "-"),
        ("案情概要", lambda c: (c.summary or "-")[:80] if is_premium else (c.summary or "-")[:40]),
        ("裁判要旨", lambda c: (c.ruling_abstract or "-")[:80] if is_premium else (c.ruling_abstract or "-")[:40]),
    ]

    # 会员扩展维度
    if is_premium:
        dimensions.extend([
            ("争议焦点", lambda c: _get_dispute_focuses(c.id, db)),
            ("法律实体", lambda c: _get_legal_entities(c.id, db)),
            ("裁判规则", lambda c: _get_legal_rules(c.id, db)),
            ("AI深度分析", lambda c: _get_ai_analysis(c)),
        ])

    matrix = []
    for dim_name, fn in dimensions:
        values = [fn(c) for c in ordered]
        matrix.append(CompareMatrixRow(dimension=dim_name, values=values))

    # 识别关键差异变量
    key_vars = _detect_key_variables(ordered, is_premium)

    return CompareResponse(
        matrix=matrix,
        key_variables=key_vars,
        is_premium=is_premium,
    )


def _get_dispute_focuses(case_id: int, db: Session) -> str:
    """获取案例争议焦点摘要"""
    focuses = db.query(DisputeFocus).filter(DisputeFocus.case_id == case_id).limit(3).all()
    if not focuses:
        return "无"
    return "；".join(f.focus_name for f in focuses if f.focus_name)


def _get_legal_entities(case_id: int, db: Session) -> str:
    """获取案例法律实体摘要"""
    entities = db.query(LegalEntity).filter(LegalEntity.case_id == case_id).limit(5).all()
    if not entities:
        return "无"
    return "、".join(e.entity_name for e in entities if e.entity_name)


def _get_legal_rules(case_id: int, db: Session) -> str:
    """获取案例裁判规则摘要"""
    rules = db.query(LegalRule).filter(LegalRule.case_id == case_id).limit(3).all()
    if not rules:
        return "无"
    return "；".join((r.rule_text or "")[:60] for r in rules)


def _get_ai_analysis(case: Case) -> str:
    """AI深度分析概要"""
    parts = []
    if case.summary:
        parts.append(f"案情：{case.summary[:120]}")
    if case.ruling_abstract:
        parts.append(f"裁判：{case.ruling_abstract[:120]}")
    if case.tags:
        parts.append(f"标签：{case.tags}")
    return " | ".join(parts) if parts else "暂无深度分析"


def _detect_key_variables(cases: list, is_premium: bool = False) -> list:
    """识别案例间的关键差异"""
    vars_found = []
    n = len(cases)

    # 1. 审判程序差异
    procedures = set(PROCEDURE_CN.get(c.trial_procedure, c.trial_procedure) for c in cases)
    if len(procedures) > 1:
        vars_found.append(KeyVariable(
            description=f"审判程序不同：{'、'.join(procedures)}。不同程序可能影响举证责任分配和审查标准",
            case_a=cases[0].case_no or "", case_b=cases[1].case_no or "",
            evidence_refs=["审判程序差异"],
        ))

    # 2. 法院层级差异
    levels = set(COURT_LEVEL_CN.get(c.court_level, c.court_level) for c in cases)
    if len(levels) > 1:
        vars_found.append(KeyVariable(
            description=f"审理法院层级不同：{'、'.join(levels)}。不同层级法院的裁判观点权威性不同",
            case_a=cases[0].case_no or "", case_b=cases[1].case_no or "",
            evidence_refs=["法院层级差异"],
        ))

    # 3. 案由差异
    categories = set(c.case_category_2 for c in cases if c.case_category_2)
    if len(categories) > 1:
        vars_found.append(KeyVariable(
            description=f"案由分类不同：{'、'.join(categories)}。需关注不同案由下法律适用要件的差异",
            case_a=cases[0].case_no or "", case_b=cases[1].case_no or "",
            evidence_refs=["案由差异"],
        ))

    # 4. 裁判日期跨度
    from datetime import date
    dates = []
    for c in cases:
        d = c.judgment_date
        if not d:
            continue
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d[:10])
            except ValueError:
                continue
        dates.append(d)
    if len(dates) >= 2:
        date_span = (max(dates) - min(dates)).days
        if date_span > 365:
            vars_found.append(KeyVariable(
                description=f"裁判时间跨度达{date_span}天（约{date_span//365}年），需注意法律修订或司法解释变化的影响",
                case_a=cases[0].case_no or "", case_b=cases[-1].case_no or "",
                evidence_refs=["时间跨度"],
            ))

    # 5. 裁判结果倾向（从 ruling_abstract 简单分析）
    rulings = [c.ruling_abstract or "" for c in cases]
    if len(rulings) >= 2:
        # 简单检测：是否包含"支持"/"驳回"等关键词
        support_keywords = ["支持", "判令", "支付", "赔偿", "返还"]
        reject_keywords = ["驳回", "不予支持", "不成立"]
        patterns = []
        for r in rulings:
            s = sum(1 for k in support_keywords if k in r)
            d = sum(1 for k in reject_keywords if k in r)
            patterns.append("支持" if s > d else "驳回" if d > s else "其他")
        if len(set(patterns)) > 1:
            vars_found.append(KeyVariable(
                description=f"裁判结果倾向不同：{' vs '.join(patterns)}。需分析导致不同结果的关键事实或法律适用差异",
                case_a=cases[0].case_no or "", case_b=cases[1].case_no or "",
                evidence_refs=["裁判结果分析"],
            ))

    if not vars_found:
        vars_found.append(KeyVariable(
            description="这些案例在基本维度上较为相似。深入分析需要结合判决书全文进行AI辅助对比",
            case_a="", case_b="",
            evidence_refs=["建议使用AI工具进行全文深度对比"],
        ))

    return vars_found


@router.post("/extract")
async def extract_judgment(file: UploadFile = File(...)):
    """从判决书文本中提取案号、标题、法院等元数据（用于对标分析添加对比案例）"""
    from app.api.admin import _extract_case_meta

    content = (await file.read()).decode("utf-8", errors="ignore")
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    lines = [l.strip() for l in content.split("\n") if l.strip()]

    # 案号
    case_no = ""
    for pat in [re.compile(r"[（(]\s*\d{4}\s*[）)]\s*[一-龥\d]{2,25}号"),
                re.compile(r"案\s*号[：:]\s*([（(]\d{4}[）)][一-龥\d]{2,20}号)")]:
        m = pat.search(content[:2000])
        if m:
            case_no = m.group(0).replace("（", "(").replace("）", ")").replace("　", "").replace(" ", "")
            break

    # 标题：从文书首部提取
    title = ""
    # 先尝试匹配完整标题行（如"XXX纠纷一案民事判决书"）
    for l in lines[:20]:
        lc = l.strip().replace("　", " ")
        if "判决书" in lc and any(k in lc for k in ("民事","刑事","行政","赔偿")):
            t = lc
            # 去掉"XXX人民法院"前缀
            t = re.sub(r"^.{0,20}人民法院\s*", "", t)
            if len(t) > 5:
                title = t; break
    if not title:
        for l in lines[:20]:
            ls = l.strip().replace("　", " ")
            if len(ls) > 10 and ("判决书" in ls or ls.endswith("案")):
                if any(k in ls for k in ("纠纷","争议","合同","权","责任","赔偿","确认","关系","犯罪","侵权")):
                    title = ls; break
    if not title:
        title = file.filename.replace(".txt", "") if file.filename else (case_no or "未命名判决书")

    # 用 admin 的完整提取逻辑补充字段
    extracted = _extract_case_meta(case_no, title, content)

    # 法院
    court = extracted.get("court", "")
    for l in lines[:10]:
        lc = l.strip().replace("　", " ")
        if "人民法院" in lc and not court:
            court = lc; break

    # 法院层级：从法院名称推断
    court_level = extracted.get("court_level", "")
    if not court_level and court:
        if "最高" in court: court_level = "supreme"
        elif "高级" in court: court_level = "high"
        elif "中级" in court: court_level = "intermediate"
        elif "基层" in court or "人民法院" in court: court_level = "basic"

    # 审判程序
    trial_procedure = extracted.get("trial_procedure", "")
    if not trial_procedure and case_no:
        if "民终" in case_no or "刑终" in case_no or "行终" in case_no: trial_procedure = "second"
        elif "民再" in case_no or "刑再" in case_no or "民申" in case_no: trial_procedure = "retrial"
        elif "民特" in case_no: trial_procedure = "supervision"

    # 案由：也尝试从正文中提取
    case_category_2 = extracted.get("case_category_2", "")
    if not case_category_2:
        for l in lines[:30]:
            m = re.search(r"案由[：:]\s*(.{2,30})", l)
            if m:
                case_category_2 = m.group(1).strip(); break
    if not case_category_2:
        for l in lines[:50]:
            m = re.search(r"([一-龥A-Za-z]{2,10}(?:纠纷|争议|赔偿|确认|认定|关系|责任|合同|权|转让|执行|竞业|审查|补偿|侵权|犯罪))", l)
            if m:
                case_category_2 = m.group(1); break

    # 摘要
    summary = extracted.get("summary", "")
    if not summary:
        useful = [l for l in lines if len(l) > 10
                  and not l.startswith(("民事判决书","刑事判决书","行政判决书"))
                  and not re.match(r"^[（(]\d{4}[）)]", l)]
        if useful:
            summary = "".join(useful[:5])[:300]

    return {
        "case_no": case_no,
        "title": title,
        "court": court,
        "court_level": court_level,
        "trial_procedure": trial_procedure,
        "case_category_2": case_category_2,
        "judgment_date": extracted.get("judgment_date", ""),
        "summary": summary,
        "full_text": content[:5000],
    }
