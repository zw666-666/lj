"""AI 加工流水线 Celery 任务"""
import asyncio
import logging
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.case import Case, ProcessingLog
from app.services.pipeline import run_stage_sync

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_case_pipeline(self, case_id: int):
    """处理单个文书的完整流水线（同步版本）"""
    db = SessionLocal()
    try:
        stages = ["summarizing", "classifying", "extracting", "linking"]
        for stage in stages:
            success = run_stage_sync(db, case_id, stage)
            if not success:
                raise Exception(f"Stage {stage} failed for case {case_id}")
    except Exception as exc:
        logger.error(f"Pipeline failed for case {case_id}: {exc}")
        try:
            self.retry(exc=exc)
        except Exception:
            # 超过最大重试次数，标记为失败
            case = db.query(Case).get(case_id)
            if case:
                case.processing_status = "failed"
                db.commit()
    finally:
        db.close()


@celery_app.task
def batch_import_cases(case_data_list: list):
    """批量导入文书并触发流水线处理"""
    db = SessionLocal()
    try:
        for data in case_data_list:
            case = Case(
                case_no=data.get("case_no"),
                title=data.get("title"),
                full_text=data.get("full_text"),
                court=data.get("court"),
                court_level=data.get("court_level"),
                trial_procedure=data.get("trial_procedure"),
                judgment_date=data.get("judgment_date"),
            )
            db.add(case)
            db.flush()
            process_case_pipeline.delay(case.id)
        db.commit()
    finally:
        db.close()


@celery_app.task
def update_judge_profiles():
    """定时更新法官画像"""
    db = SessionLocal()
    try:
        from sqlalchemy import func
        from app.models.case import JudgeProfile

        # 获取所有有案例的法官名字
        judges = db.query(
            Case.judge_name,
            Case.court,
            func.count(Case.id).label("case_count"),
        ).filter(
            Case.judge_name.isnot(None),
            Case.is_deleted == False,
        ).group_by(Case.judge_name, Case.court).all()

        for row in judges:
            profile = db.query(JudgeProfile).filter(
                JudgeProfile.judge_name == row.judge_name
            ).first()
            if not profile:
                profile = JudgeProfile(judge_name=row.judge_name, court=row.court)
                db.add(profile)
            profile.total_cases = row.case_count
            profile.updated_at = func.now()

        db.commit()
        logger.info(f"Updated {len(judges)} judge profiles")
    except Exception as e:
        logger.error(f"Judge profile update failed: {e}")
    finally:
        db.close()


@celery_app.task
def sync_es_index():
    """定时同步 MySQL 案例到 ES 索引"""
    db = SessionLocal()
    try:
        from app.services.search_service import build_es_document
        from elasticsearch import Elasticsearch
        from app.core.config import settings

        es = Elasticsearch(settings.ES_URL, request_timeout=5)
        if not es.ping():
            logger.warning("ES not reachable, skip sync")
            return

        cases = db.query(Case).filter(Case.processing_status == "completed").limit(1000).all()
        for case in cases:
            doc = build_es_document(case)
            es.index(index="cases", id=case.id, body=doc)

        logger.info(f"Synced {len(cases)} cases to ES")
    except ImportError:
        logger.info("ES client not installed, skip sync")
    except Exception as e:
        logger.error(f"ES sync failed: {e}")
    finally:
        db.close()
