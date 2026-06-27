"""语义搜索服务 —— 同义词映射 + MySQL回退 + ES集成"""
from typing import List, Tuple, Dict
from functools import lru_cache
from app.core.config import settings

# ============================================================
# ES 单例 + 健康检查（避免每次请求 5s 超时等待）
# ============================================================
_es_client = None
_es_available = None  # None=未检查 / True=可用 / False=不可用
_es_check_time = 0.0


async def _get_es_client():
    """返回可复用的 ES 客户端，若 ES 不可用返回 None。
    首次调用会做一次 1s 超时的 ping，结果缓存 60 秒。
    """
    global _es_client, _es_available, _es_check_time
    import time as _time
    now = _time.time()

    if _es_available is not None and (now - _es_check_time) < 60:
        return _es_client if _es_available else None

    try:
        from elasticsearch import AsyncElasticsearch
        if _es_client is None:
            _es_client = AsyncElasticsearch(settings.ES_URL, request_timeout=1)
        if await _es_client.ping():
            _es_available = True
            _es_check_time = now
            return _es_client
    except Exception:
        pass

    _es_available = False
    _es_check_time = now
    if _es_client:
        try:
            await _es_client.close()
        except Exception:
            pass
        _es_client = None
    return None


# ============================================================
# 同义词库：口语/生活用语 → 法律术语
# ============================================================
SYNONYM_MAP: Dict[str, List[str]] = {
    # 欠钱/债务
    "欠钱": ["借款", "民间借贷", "借贷", "欠款", "拖欠"],
    "欠债": ["借款", "民间借贷", "欠款"],
    "不还": ["拖欠", "违约", "未归还", "未偿还"],
    "还钱": ["还款", "偿还", "归还借款"],
    "借钱": ["借款", "民间借贷", "借贷合同"],
    "讨债": ["追偿", "债权", "债务纠纷"],
    "老赖": ["失信被执行人", "拒不执行", "恶意拖欠"],
    # 买卖/货款
    "不给钱": ["拖欠", "违约", "拒付", "未支付"],
    "拖着": ["拖延", "逾期", "迟延履行"],
    "收货": ["交付", "验收", "接收"],
    "供货": ["出卖人", "供应", "销售", "卖方"],
    "买方": ["买受人", "购买方", "需方"],
    "卖方": ["出卖人", "销售方", "供方"],
    "货款": ["价款", "货款", "报酬", "费用"],
    "交货": ["交付", "给付", "移交"],
    "尾款": ["余款", "剩余价款"],
    # 工程
    "工程款": ["工程价款", "建设工程", "施工费"],
    "包工头": ["实际施工人", "承包人", "施工方"],
    "烂尾": ["停工", "未完工", "中途停工"],
    "讨薪": ["追索劳动报酬", "工资", "劳务费"],
    # 伤害/侵权
    "车祸": ["交通事故", "机动车事故", "车辆碰撞"],
    "撞人": ["交通肇事", "人身损害", "碰撞行人"],
    "打人": ["故意伤害", "殴打", "人身侵害"],
    "受伤": ["人身损害", "伤残", "伤害"],
    "医疗事故": ["医疗损害", "医疗过错", "医疗纠纷"],
    "假货": ["假冒伪劣", "产品质量", "不合格产品"],
    # 婚姻
    "离婚": ["离婚纠纷", "解除婚姻关系"],
    "孩子": ["子女", "抚养权", "未成年人"],
    "抚养权": ["抚养", "监护权", "子女抚养"],
    "分财产": ["财产分割", "夫妻共同财产", "析产"],
    "出轨": ["婚外情", "不忠", "过错方"],
    # 劳动
    "开除": ["解除劳动合同", "辞退", "解雇"],
    "加班": ["加班费", "延长工作时间", "加班工资"],
    "工伤": ["工伤保险", "工伤认定", "工伤赔偿"],
    "辞职": ["解除劳动关系", "离职"],
    "拖欠工资": ["劳动报酬", "欠薪", "工资"],
    # 商标/知产
    "抄袭": ["剽窃", "抄袭", "复制", "侵权"],
    "盗版": ["著作权侵权", "未经许可复制", "盗版"],
    "山寨": ["商标侵权", "仿冒", "近似商标"],
    "冒牌": ["假冒", "仿冒", "商标侵权"],
    # 行政
    "告政府": ["行政诉讼", "行政处罚", "行政决定"],
    "罚款": ["行政处罚", "罚款"],
    "拆迁": ["征收", "拆迁补偿", "房屋征收"],
    # 刑事
    "坐牢": ["有期徒刑", "刑事处罚", "监禁"],
    "判刑": ["刑事判决", "定罪", "量刑"],
    "诈骗": ["诈骗罪", "合同诈骗", "集资诈骗"],
    "偷": ["盗窃", "盗窃罪", "非法占有"],
    "贪污": ["贪污贿赂", "职务犯罪", "腐败"],
    # 常用口语动词
    "怎么办": ["处理", "解决", "应对"],
    "能不能": ["可否", "是否可以"],
    "怎么样": ["如何"],
    "应该": [],
    "可以": [],
    "已经": [],
    "而且": [],
    "因为": [],
    "所以": [],
    "但是": [],
}

# 口语噪声词（直接删除）
STOP_WORDS = set("""
的了吗呢吧啊呀嗯哦啦嘛哈哇嘿哟呗
是的有要和就对从到把被让给为之其
也都很这那个些种点还就你能会要可以
我们我你他她它他们她们
一下怎么怎样如何请问什么为什么哪个哪些哪里谁
能不能可不可以是不是要不要
一个几个好多很多非常比较相对
已经正在将要快要马上立刻已经
大概大约差不多基本上
""".replace("\n","").split())


@lru_cache(maxsize=256)
def expand_query(raw: str) -> tuple:
    """
    将自然语言查询扩展为法律关键词列表。
    返回 (primary_keywords, secondary_keywords) 的元组（可哈希，支持 lru_cache）
    - primary: 来自原始查询词的 n-gram（高权重）
    - secondary: 来自同义词映射的法律术语（低权重）
    """
    import re as _re
    primary = set()
    secondary = set()

    # Step 1: 删除噪声词
    clean = raw
    for w in STOP_WORDS:
        clean = clean.replace(w, " ")

    # Step 2: 同义词映射 —— 归入 secondary
    for slang, legal_terms in SYNONYM_MAP.items():
        if slang in raw:
            primary.add(slang)  # 原始口语词保留为 primary
            for t in legal_terms:
                secondary.add(t)

    # Step 3: 按标点分词 → primary
    segments = _re.split(r'[，。！？；、：""''（）\s,.!?;]+', clean)
    for seg in segments:
        seg = seg.strip()
        if not seg or len(seg) < 2: continue
        primary.add(seg)
        # 2-gram → primary
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                chunk = seg[i:i+2]
                if not all(c in STOP_WORDS for c in chunk):
                    primary.add(chunk)
        # 3-gram → primary
        if len(seg) >= 3:
            for i in range(len(seg) - 2):
                chunk = seg[i:i+3]
                primary.add(chunk)

    # 去噪
    def clean_set(s, exclude=None):
        result = []
        for kw in s:
            kw = kw.strip()
            if len(kw) < 2: continue
            if kw in STOP_WORDS: continue
            if all(c in STOP_WORDS for c in kw): continue
            if exclude and kw in exclude: continue
            result.append(kw)
        return result

    primary_list = clean_set(primary)[:15]
    # secondary 去重：排除已在 primary 中的词
    secondary_list = clean_set(secondary, exclude=primary)[:10]

    return primary_list, secondary_list


# ============================================================
# ES 搜索（使用单例客户端，1s 超时）
# ============================================================
async def semantic_search_es(query: str, filters: dict = None,
                              page: int = 1, page_size: int = 20) -> Tuple[int, List[dict]]:
    es = await _get_es_client()
    if es is None:
        return 0, []  # ES 不可用，快速回退
    try:
        body = {
            "query": {
                "bool": {
                    "must": [{"multi_match": {
                        "query": query,
                        "fields": ["full_text^2", "summary^3", "title^2", "case_no^1"],
                        "type": "best_fields", "fuzziness": "AUTO",
                    }}],
                    "filter": [],
                }
            },
            "from": (page - 1) * page_size,
            "size": page_size,
        }
        if filters:
            for k, v in filters.items():
                if v: body["query"]["bool"]["filter"].append({"term": {k: v}})

        resp = await es.search(index="cases", body=body)
        total = resp["hits"]["total"]["value"]
        hits = resp["hits"]["hits"]
        results = [{**h["_source"], "_score": h["_score"]} for h in hits]
        return total, results
    except Exception:
        return 0, []


def build_es_document(case) -> dict:
    return {
        "case_id": case.id, "case_no": case.case_no, "title": case.title,
        "full_text": case.full_text, "summary": case.summary,
        "court": case.court, "court_level": case.court_level,
        "judge_name": case.judge_name,
        "case_category_1": case.case_category_1,
        "case_category_2": case.case_category_2,
        "judgment_date": str(case.judgment_date) if case.judgment_date else None,
        "tags": case.tags,
    }


# ============================================================
# 以案搜案：整份判决书直接走 FTS5 全文匹配
# ============================================================
def fts5_fulltext_search(db_session, full_query: str, limit: int = 100):
    """将完整判决书文本作为 FTS5 MATCH 输入，返回匹配的 case ID 列表。
    FTS5 会自行分词并计算 BM25 相关性排序。
    """
    from sqlalchemy import text as sa_text

    if "sqlite" not in settings.DATABASE_URL or not full_query:
        return None

    result = db_session.execute(
        sa_text("SELECT name FROM sqlite_master WHERE type='table' AND name='cases_fts'")
    ).fetchone()
    if not result:
        return None

    # 清洗文本用于 FTS5：去除换行、多余空格和 FTS5 特殊字符
    import re
    cleaned = full_query.replace("\n", " ").replace("\r", " ")
    # 去除 FTS5 运算符字符（% - ( ) * " + , . : ; ? ! [ ] { } ^ ~ = < > 等）
    cleaned = re.sub(r'[%\-()*",.+:;?!\[\]{}^~=<>#@&|/\\]', ' ', cleaned)
    # 合并空格，截取前 2000 字
    cleaned = " ".join(cleaned.split())[:2000]
    if not cleaned:
        return None

    # FTS5 MATCH 支持自然语言文本作为输入
    rows = db_session.execute(
        sa_text("SELECT rowid FROM cases_fts WHERE cases_fts MATCH :q ORDER BY rank LIMIT :lim"),
        {"q": cleaned, "lim": limit},
    ).fetchall()
    return [row[0] for row in rows] if rows else [-1]


# ============================================================
# FTS5 全文搜索辅助（SQLite 专用，替代 LIKE '%keyword%'）
# ============================================================
def build_fts5_condition(keywords: list) -> str:
    """将关键词列表构建为 FTS5 MATCH 查询字符串。"""
    terms = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        if " " in kw:
            terms.append(f'"{kw}"')
        else:
            terms.append(kw)
    return " OR ".join(terms) if terms else ""


def fts5_search_subquery(db_session, keywords: list):
    """返回匹配的 case ID 列表（使用 SQLite FTS5）。
    如果当前不是 SQLite 或 FTS5 表不存在，返回 None（调用方回退到 LIKE）。
    """
    from sqlalchemy import text as sa_text

    if "sqlite" not in settings.DATABASE_URL:
        return None

    # 检查 FTS5 表是否存在
    result = db_session.execute(
        sa_text("SELECT name FROM sqlite_master WHERE type='table' AND name='cases_fts'")
    ).fetchone()
    if not result:
        return None

    match_str = build_fts5_condition(keywords)
    if not match_str:
        return None

    rows = db_session.execute(
        sa_text("SELECT rowid FROM cases_fts WHERE cases_fts MATCH :terms"),
        {"terms": match_str},
    ).fetchall()
    return [row[0] for row in rows] if rows else [-1]  # -1 保证 IN 查询不报错且返回空
