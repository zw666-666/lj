"""管理员后台接口"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.core.database import get_db
from app.core.security import get_current_admin_user
from app.models.user import RefreshToken, User
from app.models.case import Case, CaseRelation

router = APIRouter(prefix="/api/admin", tags=["管理员"])

# ── 判决书元数据提取 ──
import re

_CN_NUM_DICT = {"〇": "0", "○": "0", "零": "0",
    "一": "1", "二": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
    "十": "10"}
_CN_DIGITS = "一二三四五六七八九"

def _cn_to_num(s: str) -> str:
    return "".join(_CN_NUM_DICT.get(c, c) for c in s)

def _parse_cn_or_digit(s: str) -> str | None:
    """解析单个数字：五→5, 十→10, 十一→11, 二十→20, 二十三→23, 2024→2024"""
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return s
    # 纯数字年份：二〇二四 → 2024
    if len(s) == 4:
        mapped = _cn_to_num(s)
        if mapped.isdigit() and len(mapped) == 4:
            return mapped
    # 月/日：1-3 个中文字
    if s == "十":
        return "10"
    total = 0
    if s.startswith("二") and len(s) > 1 and not s.startswith("二十"):
        pass  # not 二十X pattern
    if s.startswith("二十"):
        total = 20
        s = s[2:]
    elif s.startswith("三十"):
        total = 30
        s = s[2:]
    elif s.startswith("十"):
        total = 10
        s = s[1:]
    if not s:
        return str(total)
    # 剩余是单个数字 一~九
    idx = _CN_DIGITS.find(s)
    if idx >= 0:
        return str(total + idx + 1)
    # fallback: 纯映射
    return _cn_to_num(s)

_REGION_MAP = {
    "京":"北京市","沪":"上海市","津":"天津市","渝":"重庆市",
    "冀":"河北省","晋":"山西省","辽":"辽宁省","吉":"吉林省","黑":"黑龙江省",
    "苏":"江苏省","浙":"浙江省","皖":"安徽省","闽":"福建省","赣":"江西省",
    "鲁":"山东省","豫":"河南省","鄂":"湖北省","湘":"湖南省",
    "粤":"广东省","琼":"海南省","川":"四川省","黔":"贵州省","滇":"云南省",
    "陕":"陕西省","甘":"甘肃省","青":"青海省",
    "蒙":"内蒙古","桂":"广西","藏":"西藏","宁":"宁夏","新":"新疆",
}


def _extract_case_meta(case_no: str, title: str, full_text: str) -> dict:
    """从判决书全文提取缺失的元数据，返回需补充的字段"""
    result: dict = {}
    if not full_text:
        return result

    # 自动生成摘要：截取正文开头有意义的段落（跳过标题行和案号行）
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]
    useful = [l for l in lines if len(l) > 10 and not l.startswith(("民事判决书","刑事判决书","行政判决书"))
              and not re.match(r"^[（(]\d{4}[）)]", l)]
    if useful:
        result["summary"] = "".join(useful[:5])[:300]

    # 法院：从案号前缀推断
    if case_no:
        m = re.match(r"[（(]\d{4}[）)]([一-龥])", case_no)
        if m:
            abbr = m.group(1)
            region = _REGION_MAP.get(abbr, "")
            if region:
                if "最高" in case_no:
                    pass  # 最高人民法院不填
                elif "高" in case_no or "民终" in case_no[6:]:
                    result["court"] = f"{region}高级人民法院"
                    result["court_level"] = "high"
                elif "中" in case_no or "民终" in case_no or "刑终" in case_no:
                    result["court"] = f"{region}中级人民法院"
                    result["court_level"] = "intermediate"
                else:
                    result["court"] = f"{region}人民法院"
                    result["court_level"] = "basic"

    # 审判程序推断
    if case_no:
        if "民终" in case_no or "刑终" in case_no or "行终" in case_no:
            result["trial_procedure"] = "second"
        elif "民再" in case_no or "刑再" in case_no or "民申" in case_no:
            result["trial_procedure"] = "retrial"

    # 案由：从标题推导
    if title and not result.get("case_category_2"):
        tm = re.search(r"[一-龥A-Za-z0-9·]+?((?:[一-龥]+(?:纠纷|争议|赔偿|确认|认定|关系|责任|合同|权|转让|执行|竞业|审查|补偿|纠纷|确认|关系|责任|侵权|登记|许可|征收|复议|处罚|强制|公益|不正当竞争|垄断|环境|名誉|肖像|人格))[一-龥]*)案$", title)
        if tm:
            result["case_category_2"] = tm.group(1)
            cat = result["case_category_2"]
            if any(k in cat for k in ("行政","处罚","许可","征收","复议","强制")):
                result["case_category_1"] = "行政"
            elif any(k in cat for k in ("刑事","罪","诈骗","盗窃","贪污","受贿","职务","侵占","挪用","故意","过失")):
                result["case_category_1"] = "刑事"
            else:
                result["case_category_1"] = "民事"

    # 日期：匹配各种格式 "年-月-日"，再解析数字
    dm = re.search(
        r"([一-鿿\d〇○]{2,6})\s*年\s*"
        r"([一-鿿\d〇○]{1,3})\s*月\s*"
        r"([一-鿿\d〇○]{1,3})\s*日",
        full_text
    )
    if dm:
        y = _parse_cn_or_digit(dm.group(1))
        mo = _parse_cn_or_digit(dm.group(2))
        d = _parse_cn_or_digit(dm.group(3))
        if y and mo and d:
            result["judgment_date"] = f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    # 法官
    jm = re.search(r"(?:审判员|审判长|代理审判员|人民陪审员)\s*[：:]\s*([一-龥]{2,4})", full_text)
    if jm:
        result["judge_name"] = jm.group(1)

    # 标签：从案由和标题提取关键词
    tags = set()
    cat2 = result.get("case_category_2", "")
    if cat2:
        tags.add(cat2)
    if title:
        parts = re.split(r"[诉与和及、]", title)
        for p in parts:
            p = p.strip()
            if len(p) >= 2 and len(p) <= 10 and not re.match(r"^[\d\s]+$", p):
                tags.add(p)
    if tags:
        result["tags"] = list(tags)

    return result


@router.get("/cases/pending-review")
def get_pending_review(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """待审核案例（processing_status 不是 completed 或 failed）"""
    query = db.query(Case).filter(
        Case.is_deleted == False,
        Case.processing_status.notin_(["completed", "failed", "unpublished"]),
    )
    total = query.count()
    cases = query.order_by(Case.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [
            {
                "id": c.id, "case_no": c.case_no, "title": c.title,
                "court": c.court, "court_level": c.court_level,
                "case_category_2": c.case_category_2,
                "summary": c.summary, "full_text": (c.full_text or "")[:300],
                "processing_status": c.processing_status,
                "confidence": float(c.confidence_score or 0),
            }
            for c in cases
        ],
    }


@router.get("/cases/completed")
def get_completed_cases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """已通过/已完成的案例"""
    query = db.query(Case).filter(
        Case.is_deleted == False,
        Case.processing_status == "completed",  # 不含 unpublished
    )
    total = query.count()
    cases = query.order_by(Case.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [
            {
                "id": c.id, "case_no": c.case_no, "title": c.title,
                "court": c.court, "court_level": c.court_level,
                "case_category_2": c.case_category_2,
                "summary": c.summary, "full_text": (c.full_text or "")[:300],
                "processing_status": c.processing_status,
                "confidence": float(c.confidence_score or 0),
            }
            for c in cases
        ],
    }


@router.get("/cases/unpublished")
def get_unpublished_cases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """已下架的案例"""
    query = db.query(Case).filter(
        Case.is_deleted == False,
        Case.processing_status == "unpublished",
    )
    total = query.count()
    cases = query.order_by(Case.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [
            {
                "id": c.id, "case_no": c.case_no, "title": c.title,
                "court": c.court, "court_level": c.court_level,
                "case_category_2": c.case_category_2,
                "summary": c.summary, "full_text": (c.full_text or "")[:300],
                "processing_status": c.processing_status,
                "confidence": float(c.confidence_score or 0),
            }
            for c in cases
        ],
    }


@router.post("/cases/batch", status_code=201)
def batch_submit_cases(
    body: dict,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """批量提交案例"""
    cases_data = body.get("cases", [])
    if not cases_data or not isinstance(cases_data, list):
        raise HTTPException(status_code=400, detail="请提供案例列表")

    from datetime import date as date_type

    # 查重：用长度+前500字匹配，排除已驳回的案例
    def _find_duplicate(db: Session, text: str):
        if not text or len(text) < 100:
            return None
        text_len = len(text)
        prefix = text[:500]
        # 逐个匹配：先按长度过滤，再Python端比较前缀
        candidates = db.query(Case).filter(
            Case.is_deleted == False,
            Case.processing_status != "failed",
        ).all()
        for c in candidates:
            ft = c.full_text or ""
            if len(ft) == text_len and ft[:500] == prefix:
                return c
        return None

    submitted = []
    skipped: list = []
    for case_data in cases_data:
        full_text = (case_data.get("full_text") or "").strip()

        # 查重（异常不阻断提交）
        dup_case = None
        try:
            dup_case = _find_duplicate(db, full_text)
        except Exception:
            pass  # 查重失败时放行
        if dup_case:
            skipped.append({
                "title": case_data.get("title") or "未知标题",
                "case_no": case_data.get("case_no") or "未知案号",
                "dup_case_no": dup_case.case_no,
                "dup_title": dup_case.title,
            })
            continue
        title = (case_data.get("title") or "").strip()
        case_no = (case_data.get("case_no") or "").strip()
        full_text = (case_data.get("full_text") or "").strip()
        if not title or not case_no or not full_text:
            continue  # 跳过不完整的

        # 已驳回（failed）的案例允许重新提交：更新原记录而非插入新行
        existing_case = db.query(Case).filter(
            Case.case_no == case_no,
            Case.is_deleted == False,
        ).first()
        if existing_case and existing_case.processing_status == "failed":
            existing_case.title = title
            existing_case.full_text = full_text
            existing_case.court = (case_data.get("court") or "").strip() or ""
            existing_case.court_level = case_data.get("court_level") or "intermediate"
            existing_case.court_region = (case_data.get("court_region") or "").strip() or ""
            existing_case.judge_name = (case_data.get("judge_name") or "").strip() or ""
            existing_case.trial_procedure = case_data.get("trial_procedure") or "first"
            existing_case.case_category_1 = (case_data.get("case_category_1") or "").strip() or ""
            existing_case.case_category_2 = (case_data.get("case_category_2") or "").strip() or ""
            existing_case.case_category_3 = (case_data.get("case_category_3") or "").strip() or ""
            existing_case.summary = (case_data.get("summary") or "").strip() or ""
            existing_case.ruling_abstract = (case_data.get("ruling_abstract") or "").strip() or ""
            existing_case.tags = case_data.get("tags") or []
            existing_case.processing_status = "pending"
            existing_case.confidence_score = 0.0
            # 补充提取缺失字段（异常不阻断提交）
            try:
                extra = _extract_case_meta(case_no, title, full_text)
                for k, v in extra.items():
                    if not getattr(existing_case, k, None):
                        setattr(existing_case, k, v)
            except Exception:
                pass
            jd = case_data.get("judgment_date")
            if jd and isinstance(jd, str) and jd.strip():
                try:
                    existing_case.judgment_date = date_type.fromisoformat(jd.strip())
                except (ValueError, TypeError):
                    existing_case.judgment_date = None
            submitted.append({"id": existing_case.id, "case_no": case_no, "title": title})
            continue

        if existing_case:
            # case_no 已存在且不是 failed（如 pending/completed），视为重复
            skipped.append({
                "title": title, "case_no": case_no,
                "dup_case_no": existing_case.case_no, "dup_title": existing_case.title,
            })
            continue

        jd = case_data.get("judgment_date")
        if jd and isinstance(jd, str) and jd.strip():
            try:
                jd = date_type.fromisoformat(jd.strip())
            except (ValueError, TypeError):
                jd = None
        else:
            jd = None

        case = Case(
            case_no=case_no, title=title,
            court=(case_data.get("court") or "").strip() or "",
            court_level=case_data.get("court_level") or "intermediate",
            court_region=(case_data.get("court_region") or "").strip() or "",
            judge_name=(case_data.get("judge_name") or "").strip() or "",
            trial_procedure=case_data.get("trial_procedure") or "first",
            case_category_1=(case_data.get("case_category_1") or "").strip() or "",
            case_category_2=(case_data.get("case_category_2") or "").strip() or "",
            case_category_3=(case_data.get("case_category_3") or "").strip() or "",
            judgment_date=jd, full_text=full_text,
            summary=(case_data.get("summary") or "").strip() or "",
            ruling_abstract=(case_data.get("ruling_abstract") or "").strip() or "",
            tags=case_data.get("tags") or [],
            processing_status="pending", confidence_score=0.0,
        )
        # 后端补充提取缺失字段（异常不阻断提交）
        try:
            extra = _extract_case_meta(case_no, title, full_text)
            for k, v in extra.items():
                current_val = getattr(case, k, None)
                if not current_val:  # 仅补填空字段
                    setattr(case, k, v)
        except Exception:
            pass  # 提取失败不影响提交
        db.add(case)
        db.flush()
        submitted.append({"id": case.id, "case_no": case.case_no, "title": case.title})

    if not submitted:
        if skipped:
            dup_list = "；".join(
                f"「{s['title']}」→ 与已有案例「{s['dup_case_no']} {s['dup_title']}」重复"
                for s in skipped
            )
            raise HTTPException(status_code=409, detail=f"所有 {len(skipped)} 个案例均为重复：{dup_list}")
        raise HTTPException(status_code=400, detail="没有有效的案例数据（案号、标题、全文均为必填）")

    db.commit()
    msg = f"已提交 {len(submitted)} 个案例"
    if skipped:
        msg += f"，跳过 {len(skipped)} 个重复案例"
    return {
        "count": len(submitted), "items": submitted,
        "skipped": list(skipped), "message": msg,
    }


@router.post("/cases", status_code=201)
def submit_case(
    case_data: dict,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """管理员提交新案例（待审核状态）"""
    # 校验必填项
    if not case_data.get("title", "").strip():
        raise HTTPException(status_code=400, detail="标题为必填项")
    if not case_data.get("case_no", "").strip():
        raise HTTPException(status_code=400, detail="案号为必填项")
    if not case_data.get("full_text", "").strip():
        raise HTTPException(status_code=400, detail="判决书全文为必填项")

    from datetime import date as date_type

    case_no = case_data.get("case_no", "").strip()
    title = case_data.get("title", "").strip()
    full_text = case_data.get("full_text", "").strip()

    # 已驳回（failed）的案例重新提交 → 更新原记录
    existing = db.query(Case).filter(
        Case.case_no == case_no, Case.is_deleted == False
    ).first()
    if existing and existing.processing_status == "failed":
        existing.title = title
        existing.full_text = full_text
        existing.court = (case_data.get("court") or "").strip() or ""
        existing.court_level = case_data.get("court_level") or "intermediate"
        existing.court_region = (case_data.get("court_region") or "").strip() or ""
        existing.judge_name = (case_data.get("judge_name") or "").strip() or ""
        existing.trial_procedure = case_data.get("trial_procedure") or "first"
        existing.case_category_1 = (case_data.get("case_category_1") or "").strip() or ""
        existing.case_category_2 = (case_data.get("case_category_2") or "").strip() or ""
        existing.case_category_3 = (case_data.get("case_category_3") or "").strip() or ""
        existing.summary = (case_data.get("summary") or "").strip() or ""
        existing.ruling_abstract = (case_data.get("ruling_abstract") or "").strip() or ""
        existing.tags = case_data.get("tags") or []
        existing.processing_status = "pending"
        existing.confidence_score = 0.0
        jd = case_data.get("judgment_date")
        if jd and isinstance(jd, str) and jd.strip():
            try:
                existing.judgment_date = date_type.fromisoformat(jd.strip())
            except (ValueError, TypeError):
                existing.judgment_date = None
        db.commit()
        return {"id": existing.id, "case_no": case_no, "message": "案例已重新提交，等待审核"}

    if existing:
        raise HTTPException(status_code=409, detail=f"该案号已存在（{existing.title}），不可重复提交")

    # 日期解析
    jd = case_data.get("judgment_date")
    if jd and isinstance(jd, str) and jd.strip():
        try:
            jd = date_type.fromisoformat(jd.strip())
        except (ValueError, TypeError):
            jd = None
    else:
        jd = None

    case = Case(
        case_no=case_no, title=title,
        court=(case_data.get("court") or "").strip() or "",
        court_level=case_data.get("court_level") or "intermediate",
        court_region=(case_data.get("court_region") or "").strip() or "",
        judge_name=(case_data.get("judge_name") or "").strip() or "",
        trial_procedure=case_data.get("trial_procedure") or "first",
        case_category_1=(case_data.get("case_category_1") or "").strip() or "",
        case_category_2=(case_data.get("case_category_2") or "").strip() or "",
        case_category_3=(case_data.get("case_category_3") or "").strip() or "",
        judgment_date=jd, full_text=full_text,
        summary=(case_data.get("summary") or "").strip() or "",
        ruling_abstract=(case_data.get("ruling_abstract") or "").strip() or "",
        tags=case_data.get("tags") or [],
        processing_status="pending", confidence_score=0.0,
    )
    try:
        extra = _extract_case_meta(case_no, title, full_text)
        for k, v in extra.items():
            if not getattr(case, k, None):
                setattr(case, k, v)
    except Exception:
        pass
    db.add(case)
    db.commit()
    db.refresh(case)
    return {"id": case.id, "case_no": case.case_no, "message": "案例已提交，等待审核"}


@router.post("/cases/{case_id}/review")
def review_case(
    case_id: int,
    review: dict,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """审核通过/修正/驳回"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    action = review.get("action")
    if action == "confirm":
        # 审核通过：设为 completed，加入检索库
        case.processing_status = "completed"
        if review.get("summary"):
            case.summary = review["summary"]
        if review.get("case_category_2"):
            case.case_category_2 = review["case_category_2"]
        # 同步到 FTS5
        from app.core.config import settings
        if "sqlite" in settings.DATABASE_URL:
            db.execute(
                text(
                    "INSERT OR REPLACE INTO cases_fts(rowid, full_text) VALUES (:id, :text)"
                ),
                {"id": case.id, "text": case.full_text or ""},
            )
    elif action == "reject":
        case.processing_status = "failed"
    elif action == "unpublish":
        # 下架：设为 unpublished，从 FTS5 移除（不真删）
        case.processing_status = "unpublished"
        from app.core.config import settings
        if "sqlite" in settings.DATABASE_URL:
            db.execute(
                text("INSERT INTO cases_fts(cases_fts, rowid, full_text) VALUES('delete', :id, :text)"),
                {"id": case.id, "text": case.full_text or ""},
            )
    elif action == "restore":
        # 撤回下架：恢复为 completed，重新加入 FTS5
        case.processing_status = "completed"
        case.is_deleted = False
        from app.core.config import settings
        if "sqlite" in settings.DATABASE_URL:
            db.execute(
                text("INSERT OR REPLACE INTO cases_fts(rowid, full_text) VALUES (:id, :text)"),
                {"id": case.id, "text": case.full_text or ""},
            )
    elif action == "delete":
        # 永久删除
        from app.core.config import settings
        if "sqlite" in settings.DATABASE_URL:
            db.execute(
                text("INSERT INTO cases_fts(cases_fts, rowid, full_text) VALUES('delete', :id, :text)"),
                {"id": case.id, "text": case.full_text or ""},
            )
        db.delete(case)
        db.commit()
        return {"message": "案例已彻底删除"}
    elif action == "revise":
        for field in ["summary", "ruling_abstract", "case_category_2", "title"]:
            if field in review:
                setattr(case, field, review[field])
    else:
        raise HTTPException(status_code=400, detail="无效的审核操作")
    db.commit()
    return {"message": "审核完成"}


@router.get("/stats")
def get_admin_stats(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """管理员统计面板"""
    total_users = db.query(User).count()
    status_rows = db.query(Case.processing_status, func.count(Case.id)).filter(
        Case.is_deleted == False
    ).group_by(Case.processing_status).all()
    status_map = dict(status_rows)

    # 中文标签 + 计数
    STATUS_LABELS = {
        "pending": ("待处理", "info"),
        "summarizing": ("AI摘要中", "warning"),
        "classifying": ("案由分类中", "warning"),
        "extracting": ("实体提取中", "warning"),
        "linking": ("关联图谱中", "warning"),
        "completed": ("已上线", "success"),
        "failed": ("已驳回", "danger"),
        "unpublished": ("已下架", "danger"),
    }

    detail = []
    for key, (label, tag_type) in STATUS_LABELS.items():
        count = status_map.get(key, 0)
        if count > 0:
            detail.append({"status": key, "label": label, "count": count, "type": tag_type})

    # 总数 = 未删除案例数
    total_cases = sum(item["count"] for item in detail)

    return {
        "total_cases": total_cases,
        "total_users": total_users,
        "detail": detail,
    }


@router.get("/users")
def list_users(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    """用户列表"""
    total = db.query(User).count()
    users = db.query(User).order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "email": u.email,
                "phone": u.phone,
                "nickname": u.nickname,
                "role": u.role,
                "is_locked": u.is_locked,
                "search_count": u.search_count or 0,
                "read_count": u.read_count or 0,
                "created_at": str(u.created_at),
            }
            for u in users
        ],
    }


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    body: dict,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """修改用户角色"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    new_role = body.get("role")
    # 兼容旧数据：user = normal
    if new_role == "user":
        new_role = "normal"
    if new_role not in ("normal", "premium", "admin"):
        raise HTTPException(status_code=400, detail="无效角色（仅支持 普通用户/会员/管理员）")
    user.role = new_role
    # 手动设置角色：清除订阅到期时间（管理员手动设为会员 = 永久会员）
    if new_role in ("premium", "admin"):
        user.subscription_expires_at = None
    elif new_role == "normal":
        user.subscription_expires_at = None  # 降级为普通用户时清除
    db.commit()
    labels = {"normal": "普通用户", "premium": "会员", "admin": "管理员"}
    return {"message": f"用户 {user.email} 已设为 {labels.get(new_role, new_role)}"}


@router.put("/users/{user_id}/lock")
def toggle_user_lock(
    user_id: int,
    body: dict,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """锁定/解锁用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    locked = body.get("is_locked", False)
    user.is_locked = locked
    if locked:
        from datetime import datetime, timedelta, timezone
        user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=365)
    else:
        user.locked_until = None
        user.login_attempts = 0
    db.commit()
    return {"message": f"用户 {'已锁定' if locked else '已解锁'}"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """管理员注销用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能注销自己")

    from app.models.user_content import Favorite, Note, CaseGroup, CaseGroupItem, QASession, QAMessage, UserActivity, Notification
    from app.models.subscription import Subscription, PaymentOrder
    from app.models.usage import UsageDaily

    # 清除 CaseGroup → CaseGroupItem 的关联
    user_groups = db.query(CaseGroup).filter(CaseGroup.user_id == user_id).all()
    for g in user_groups:
        db.query(CaseGroupItem).filter(CaseGroupItem.group_id == g.id).delete()
    # 清除 QASession → QAMessage 的关联
    user_sessions = db.query(QASession).filter(QASession.user_id == user_id).all()
    for s in user_sessions:
        db.query(QAMessage).filter(QAMessage.session_id == s.id).delete()

    # 清除所有用户数据
    for model in [Favorite, Note, CaseGroup, QASession, UserActivity, Notification]:
        db.query(model).filter(model.user_id == user_id).delete()
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
    db.query(Subscription).filter(Subscription.user_id == user_id).delete()
    db.query(PaymentOrder).filter(PaymentOrder.user_id == user_id).delete()
    db.query(UsageDaily).filter(UsageDaily.user_id == user_id).delete()

    db.delete(user)
    db.commit()
    return {"message": f"用户 {user.email or user.phone} 已注销"}
