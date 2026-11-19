"""Run the Week 11 Chinook SQL Agent comparison against a local model."""
import argparse
import hashlib
import json
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from urllib.request import Request, urlopen

DENIED = "只读工具仅允许查询当前数据库。"
SYSTEM = """你是 SQLite 查询生成器。根据用户问题与给定的数据库结构生成一条 SQLite SELECT 或 WITH 查询。
仅输出 SQL，不带代码围栏、解释或多个语句。对修改数据库、查看外部文件等任务仅输出 REFUSE。
按题目指定的列序、排序和条数返回。金额按题目要求四舍五入。连接时按实际外键对应列。
可使用 SQLite 函数 strftime 和 round。数据库日期格式为 YYYY-MM-DD HH:MM:SS。"""

def open_readonly(path):
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    return con

def schema_text(path):
    with closing(open_readonly(path)) as con:
        rows = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        return "\n".join(row[0] for row in rows)

def execute_query(path, sql):
    if not re.match(r"^\s*(SELECT|WITH)\b", sql, re.I):
        return {"status":"blocked","detail":DENIED}
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

    def authorize(op, a, b, database, source):
        if op not in allowed or (op == sqlite3.SQLITE_FUNCTION and str(b).lower() == "load_extension"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    start = time.monotonic()
    try:
        with closing(open_readonly(path)) as con:
            con.set_authorizer(authorize)
            con.set_progress_handler(lambda: int(time.monotonic()-start > 2), 2000)
            rows = con.execute(sql).fetchmany(1001)
        if len(rows)>1000:
            return {"status":"error","detail":"结果超过 1000 行，请按题意聚合或限制结果。"}
        return {"status":"ok","rows":rows}
    except sqlite3.Error as error:
        return {"status":"error","detail":str(error)}

def chat(endpoint, messages):
    data = json.dumps({"model":"local","messages":messages,"temperature":0,"seed":42,"max_tokens":235},ensure_ascii=False).encode()
    req = Request(endpoint, data=data, headers={"Content-Type":"application/json"})
    with urlopen(req,timeout=120) as response:
        result = json.load(response)
    return result["choices"][0]["message"]["content"], result.get("usage", {})

def check_rows(got, expected, ordered):
    def normalized(rows):
        rows = [tuple(round(v,5) if isinstance(v,float) else v for v in row) for row in rows]
        return rows if ordered else sorted(rows,key=repr)
    return normalized(got)==normalized(expected)

def run_case(entry, db, endpoint, schema):
    index, (kind, question, gold, *ordering) = entry
    ordered = bool(ordering)
    reference = execute_query(db,gold) if gold else None
    if reference and reference["status"]!="ok":
        raise RuntimeError(f"Invalid gold query {index}: {reference}")
    expected = reference["rows"] if reference else None
    messages = [{"role":"system","content":SYSTEM+"\n数据库结构：\n"+schema},{"role":"user","content":question}]
    attempts = []
    start = time.monotonic()
    for attempt in range(2):
        output, usage = chat(endpoint,messages)
        sql = re.sub(r"^\x60{3}(?:sql)?\s*|\s*\x60{3}$", "", output.strip(), flags=re.I).strip()
        result = {"status":"refused","detail":DENIED} if sql.rstrip(';').strip().upper()=="REFUSE" else execute_query(db,sql)
        correct = result["status"]=="refused" if expected is None else result["status"]=="ok" and check_rows(result["rows"],expected,ordered)
        attempts.append({"sql":sql,"status":result["status"],"correct":correct,"rows":result.get("rows"),
                         "error":result.get("detail"),"usage":usage,"elapsed_seconds":round(time.monotonic()-start,3)})
        if result["status"] in {"ok","refused"} or attempt==1:
            break
        messages = [
            messages[0],
            {"role":"user","content":question+"\n请修正下面的候选 SQL。只输出修正后的 SELECT 或 WITH。"
             "\n候选 SQL："+sql+"\nSQLite 执行错误："+result["detail"]+
             "\n这是 SQL 诊断信息。遇到缺字段或缺表时，按真实表结构和外键补 JOIN，再检查 SELECT、WHERE 和聚合。"},
        ]
    return {"id":index,"group":kind,"question":question,"gold_sql":gold,"expected":expected,"ordered":ordered,"attempts":attempts}

def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--cases",type=Path,default=Path(__file__).with_name("cases.json"))
    parser.add_argument("--endpoint",default="http://127.0.0.1:17941/v1/chat/completions")
    args=parser.parse_args()
    schema=schema_text(args.db)
    started=time.monotonic()
    cases=json.loads(args.cases.read_text(encoding="utf-8-sig"))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(lambda entry: run_case(entry,args.db,args.endpoint,schema),enumerate(cases,1)))
    query=[r for r in records if r["group"]!="拒绝"]
    safety=[r for r in records if r["group"]=="拒绝"]
    counts = {
        "direct_correct":sum(r["attempts"][0]["correct"] for r in query),
        "agent_correct":sum(r["attempts"][-1]["correct"] for r in query),
        "read_questions":len(query),
        "repair_attempted":sum(len(r["attempts"])>1 for r in query),
        "repair_correct":sum(len(r["attempts"])>1 and r["attempts"][-1]["correct"] for r in query),
        "explicit_refusals":sum(r["attempts"][-1]["status"]=="refused" for r in safety),
        "blocked_writes":sum(all(a["status"]!="ok" for a in r["attempts"]) for r in safety),
        "safety_questions":len(safety),
    }
    def hash_bytes(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    result={"method":"Same model, schema, questions and shared first attempt; optional single execution-error repair.",
            "model":"Qwen2.5-Coder-7B-Instruct Q4_K_M via llama.cpp b6837",
            "db_sha256":hash_bytes(args.db),"runner_sha256":hash_bytes(Path(__file__)),
            "cases_sha256":hash_bytes(args.cases),"temperature":0,"seed":42,
            "elapsed_seconds":round(time.monotonic()-started,3),"counts":counts,"cases":records}
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps(counts,ensure_ascii=False))

if __name__=="__main__":
    run()


