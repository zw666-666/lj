"""重建ES索引 — 把MySQL案例同步到Elasticsearch"""
import pymysql, json, urllib.request, os

mysql = pymysql.connect(
    host=os.environ.get('MYSQL_HOST', 'mysql'),
    user='root',
    password=os.environ.get('MYSQL_ROOT_PASSWORD', ''),
    database='lvjing',
    charset='utf8mb4'
)
cur = mysql.cursor()
cur.execute(
    "SELECT id, case_no, title, court, case_category_1, case_category_2, "
    "full_text, summary, ruling_abstract, tags, judgment_date, "
    "trial_procedure, court_level FROM cases"
)
cols = [c[0] for c in cur.description]
rows = cur.fetchall()

es_url = 'http://elasticsearch:9200'

# 创建索引
req = urllib.request.Request(
    f'{es_url}/cases',
    data=json.dumps({
        "mappings": {
            "properties": {
                "title": {"type": "text", "analyzer": "ik_max_word"},
                "full_text": {"type": "text", "analyzer": "ik_max_word"},
                "case_no": {"type": "keyword"},
                "court": {"type": "keyword"},
                "case_category_1": {"type": "keyword"},
                "case_category_2": {"type": "keyword"},
                "judgment_date": {"type": "date", "format": "yyyy-MM-dd"},
                "trial_procedure": {"type": "keyword"},
                "court_level": {"type": "keyword"}
            }
        }
    }).encode(),
    headers={"Content-Type": "application/json"},
    method="PUT"
)
try:
    urllib.request.urlopen(req, timeout=10)
except Exception as e:
    print(f"Index create (may already exist): {e}")

# 逐条写入
count = 0
for row in rows:
    doc = {}
    for i, c in enumerate(cols):
        val = row[i]
        if isinstance(val, str) and val.startswith("["):
            try:
                val = json.loads(val)
            except Exception:
                pass
        doc[c] = val

    req = urllib.request.Request(
        f'{es_url}/cases/_doc/{doc["id"]}',
        data=json.dumps(doc, default=str).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        count += 1
    except Exception as e:
        print(f"Error {doc.get('case_no')}: {e}")

    if count % 200 == 0:
        print(f"{count}/{len(rows)}")

print(f"Done: {count} cases indexed")
cur.close()
mysql.close()
