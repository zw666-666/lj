"""AI 加工流水线服务层"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.case import Case, ProcessingLog

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_stage_sync(db: Session, case_id: int, stage: str) -> bool:
    """同步执行单个处理阶段"""
    case = db.query(Case).get(case_id)
    if not case:
        logger.warning(f"Case {case_id} not found for stage {stage}")
        return False

    # 更新案例状态
    status_map = {
        "summarizing": "summarizing",
        "classifying": "classifying",
        "extracting": "extracting",
        "linking": "linking",
    }
    case.processing_status = status_map.get(stage, "summarizing")

    log = ProcessingLog(
        case_id=case_id, stage=stage, status="processing",
        started_at=_utcnow(),
    )
    db.add(log)
    db.commit()

    try:
        # 调用 AI（同步版本）
        result = _run_stage_ai(stage, case.full_text or "")
        _apply_stage_result(db, case, stage, result)
        log.status = "success"
        log.completed_at = _utcnow()
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Stage {stage} failed for case {case_id}: {e}")
        log.status = "failed"
        log.error_message = str(e)
        log.completed_at = _utcnow()
        db.commit()
        if log.retry_count < 3:
            log.status = "retrying"
            log.retry_count += 1
            db.commit()
        return False


async def run_stage(db: Session, case_id: int, stage: str) -> bool:
    """异步执行单个处理阶段（调用 Dify 工作流）"""
    case = db.query(Case).get(case_id)
    if not case:
        return False

    log = ProcessingLog(
        case_id=case_id, stage=stage, status="processing",
        started_at=_utcnow(),
    )
    db.add(log)
    db.commit()

    try:
        result = _run_stage_ai(stage, case.full_text or "")
        _apply_stage_result(db, case, stage, result)
        log.status = "success"
        log.completed_at = _utcnow()
        db.commit()
        return True
    except Exception as e:
        log.status = "failed"
        log.error_message = str(e)
        log.completed_at = _utcnow()
        db.commit()
        if log.retry_count < 3:
            log.status = "retrying"
            log.retry_count += 1
            db.commit()
        return False


def _run_stage_ai(stage: str, full_text: str) -> dict:
    """执行单个 AI 处理阶段（当前为模拟实现，后续可接入任意 LLM）"""
    return {
        "status": "ok",
        "stage": stage,
        "summary": f"本案涉及{full_text[:30]}...相关法律争议",
        "ruling_abstract": f"法院认为，根据相关法律规定，{full_text[:50]}...",
        "category_1": "民事",
        "category_2": "合同纠纷",
        "tags": ["合同", "履行", "违约"],
        "confidence": 0.85,
    }


def _apply_stage_result(db: Session, case: Case, stage: str, result: dict):
    """将 AI 处理结果写入数据库"""
    if stage == "summarizing":
        case.summary = result.get("summary", "")
        case.ruling_abstract = result.get("ruling_abstract", "")
        case.processing_status = "classifying"
    elif stage == "classifying":
        case.case_category_1 = result.get("category_1", "")
        case.case_category_2 = result.get("category_2", "")
        case.tags = result.get("tags", [])
        case.processing_status = "extracting"
    elif stage == "extracting":
        case.processing_status = "linking"
    elif stage == "linking":
        case.processing_status = "completed"
    case.confidence_score = float(result.get("confidence", 0.85))
