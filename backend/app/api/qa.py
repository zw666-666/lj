"""法律智能问答接口（SSE 流式，直接接入 DeepSeek）"""
import json
import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User
from app.models.user_content import QASession, QAMessage
from app.services.usage_service import UsageService

router = APIRouter(prefix="/api/qa", tags=["智能问答"])

SYSTEM_PROMPT = """你叫"律镜AI助手"，是律镜法律智能平台的AI法律顾问。你的回答基于中国法律和真实裁判案例。

## 你的能力
你可以回答法律咨询、分析案情、查找法规、预测裁判倾向、辅助撰写法律文书。

## 回答规则
1. 先给结论（1-2句话，直接回答"能/不能""是/不是""会/不会"）
2. 如果用户提供了案例数据，必须引用真实案例，格式：【案号】法院 — 核心裁判观点
3. 如果案例之间有观点冲突，必须指出并分析原因
4. 最后给出实务建议
5. 不使用 markdown 标题（# ##），用自然段落
6. 如果有不确定的地方，诚实说明
"""

def _search_cases(query: str) -> list[dict]:
    """调用内部搜索 API"""
    try:
        from app.services.search_service import expand_query, fts5_fulltext_search
        from app.core.database import SessionLocal as SearchDb
        db = SearchDb()
        try:
            from app.models.case import Case
            pk, sk = expand_query(query)
            keywords = list(pk)[:8] + list(sk)[:8]

            # 先尝试 FTS5
            fts_ids = fts5_fulltext_search(db, query, limit=8)
            if fts_ids and len(fts_ids) > 0 and fts_ids[0] != -1:
                cases = db.query(Case).filter(
                    Case.processing_status == "completed",
                    Case.id.in_(fts_ids[:8])
                ).all()
            elif keywords:
                from sqlalchemy import or_ as sql_or
                conditions = []
                for kw in keywords[:8]:
                    p = f"%{kw}%"
                    conditions.append(Case.title.ilike(p))
                    conditions.append(Case.case_category_2.ilike(p))
                cases = db.query(Case).filter(
                    Case.processing_status == "completed",
                    sql_or(*conditions)
                ).limit(8).all()
            else:
                cases = []

            return [
                {
                    "title": c.title or c.case_no,
                    "case_no": c.case_no,
                    "court": c.court or "",
                    "category": c.case_category_2 or "",
                    "summary": (c.summary or "")[:150],
                    "ruling": (c.ruling_abstract or "")[:150],
                }
                for c in cases
            ]
        finally:
            db.close()
    except Exception:
        return []


def _build_user_prompt(question: str, cases: list[dict], file_content: str = "", file_name: str = "") -> str:
    parts = [f"用户提问：{question}"]

    # 用户上传的文件内容
    if file_content:
        truncated = file_content[:8000]
        parts.append(f"\n用户上传的文件（{file_name}）内容如下：\n{truncated}\n")
        parts.append("请结合用户上传的文件内容回答用户的问题。")

    if not cases:
        parts.append("\n未检索到直接相关案例，请基于你的法律知识回答。")
    else:
        parts.append(f"\n检索到的相关案例（共{len(cases)}个）：")
        for i, c in enumerate(cases):
            parts.append(
                f"\n案例{i+1}：{c['title']}\n"
                f"  案号：{c['case_no']}\n"
                f"  法院：{c['court']}\n"
                f"  案由：{c['category']}\n"
                f"  概要：{c['summary']}\n"
                f"  要旨：{c['ruling']}"
            )
        parts.append("\n请基于以上案例和你的法律专业知识，回答用户的问题。")
    return "\n".join(parts)


@router.post("/ask")
async def ask_question(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """流式问答 —— 使用原生 StreamingResponse 实现 SSE"""
    body = await request.json()
    question_text = body.get("question", "")
    session_id = body.get("session_id")
    file_content = body.get("file_content", "") or ""
    file_name = body.get("file_name", "") or ""

    # 使用独立 DB 会话避免生命周期问题
    db = SessionLocal()
    try:
        # 检查每日QA次数（免费用户限制，会员不限）
        allowed, current, limit = UsageService.check_and_increment_qa(
            current_user.id, current_user.role, db
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"今日问答次数已用完（{limit}次/天），升级会员即可无限使用",
            )

        if not session_id:
            session = QASession(user_id=current_user.id, session_title=question_text[:30])
            db.add(session)
            db.commit()
            session_id = session.id
            new_session_created = True
        else:
            new_session_created = False

        # 存储用户问题
        msg = QAMessage(session_id=session_id, role="user", content=question_text)
        db.add(msg)
        db.commit()
    finally:
        db.close()

    # 先检索案例
    cases = _search_cases(question_text)

    async def event_generator():
        full_answer = ""
        # 通知前端新建的会话 ID，便于同步侧边栏选中状态
        if new_session_created:
            yield f"data: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"
        api_key = settings.DEEPSEEK_API_KEY
        if not api_key:
            yield f"data: {json.dumps({'content': 'DeepSeek API Key 未配置，请在 .env 中设置 DEEPSEEK_API_KEY'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
            return

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{settings.DEEPSEEK_API_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.DEEPSEEK_MODEL,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": _build_user_prompt(question_text, cases, file_content, file_name)},
                        ],
                        "stream": True,
                        "temperature": 0.3,
                        "max_tokens": 2048,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        error_text = error_body[:200].decode("utf-8", errors="replace")
                        yield f"data: {json.dumps({'content': 'AI 服务异常（' + str(resp.status_code) + '）：' + error_text}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                        return

                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        try:
                            delta = json.loads(chunk)
                            content = delta.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                full_answer += content
                                yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                        except json.JSONDecodeError:
                            continue

        except httpx.ConnectError:
            yield f"data: {json.dumps({'content': '无法连接到 DeepSeek API，请检查网络'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'AI 服务异常：{str(e)[:100]}'}, ensure_ascii=False)}\n\n"

        # 存储 AI 回答
        if full_answer:
            db2 = SessionLocal()
            try:
                ai_msg = QAMessage(session_id=session_id, role="assistant", content=full_answer)
                db2.add(ai_msg)
                db2.commit()
            finally:
                db2.close()

        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-Id": str(session_id) if new_session_created else "",
        },
    )


@router.get("/sessions")
def get_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sessions = db.query(QASession).filter(QASession.user_id == current_user.id).order_by(
        QASession.created_at.desc()
    ).all()
    return [{"id": s.id, "title": s.session_title, "created_at": str(s.created_at)} for s in sessions]


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 验证会话属于当前用户
    session = db.query(QASession).filter(
        QASession.id == session_id,
        QASession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = db.query(QAMessage).filter(QAMessage.session_id == session_id).order_by(
        QAMessage.created_at
    ).all()
    return [
        {"id": m.id, "role": m.role, "content": m.content, "citations": m.citations, "created_at": str(m.created_at)}
        for m in messages
    ]


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除指定问答会话（含所有消息）"""
    session = db.query(QASession).filter(
        QASession.id == session_id,
        QASession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 先删消息再删会话
    db.query(QAMessage).filter(QAMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"message": "会话已删除"}


@router.get("/quota")
def get_qa_quota(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取今日剩余问答次数（会员返回-1表示无限）"""
    remaining = UsageService.get_remaining_qa(current_user.id, current_user.role, db)
    return {
        "remaining": remaining,
        "unlimited": current_user.role in ("premium", "admin"),
        "daily_limit": 5 if current_user.role == "normal" else -1,
    }
