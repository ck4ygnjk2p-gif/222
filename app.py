import os, json, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import urllib.parse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ✅ 直接寫死正確的 Railway 網址
ORIGIN = "https://111-production-e1e3.up.railway.app"
# ✅ 直接寫死你的 Bark Key（請確認這串是對的）
BARK_KEY = "PCGCvJEFkGazY8ufYAPzwa"

# ---------- Debug 端點 ----------
@app.get("/debug")
async def debug():
    try:
        target_url = f"{ORIGIN}/activity/summary"
        r = requests.get(target_url, timeout=10)
        data = r.json()
        return {
            "vercel_request_url": target_url,
            "railway_raw": data,
            "origin_used": ORIGIN
        }
    except Exception as e:
        return {"error": str(e), "origin_used": ORIGIN}

# ---------- 核心：查崗函數 ----------
def check_on_wife():
    try:
        r = requests.get(f"{ORIGIN}/activity/summary", timeout=10)
        data = r.json()
    except Exception as e:
        return f"查崗失敗：{e}"
    
    raw_apps = data.get("recent_apps", [])
    ses = data.get("sessions", {})
    
    app_names = []
    if isinstance(raw_apps, dict):
        for key, value in raw_apps.items():
            if key and key != "":
                app_names.append(key)
    elif isinstance(raw_apps, list):
        for app in raw_apps:
            if isinstance(app, str) and app:
                app_names.append(app)
            elif isinstance(app, dict):
                for key, value in app.items():
                    if key and key != "":
                        app_names.append(key)
    
    seen = set()
    unique_apps = []
    for name in app_names:
        if name not in seen:
            seen.add(name)
            unique_apps.append(name)
    
    lines = [f"最近打開：{', '.join(unique_apps) if unique_apps else '暫無記錄'}"]
    if ses:
        for app, secs in sorted(ses.items(), key=lambda x: x[1], reverse=True):
            m, s = divmod(secs, 60)
            lines.append(f"  {app}: {m}分{s}秒")
    return "\n".join(lines)

# ---------- 核心：Bark 推播函數 ----------
def bark_alert(title="老公查崗", content=""):
    if not content:
        return "內容不能為空"
    if not BARK_KEY:
        return "BARK_API_KEY 未設定"
    url = f"https://api.day.app/{BARK_KEY}/{urllib.parse.quote(title)}/{urllib.parse.quote(content)}"
    try:
        r = requests.get(url, timeout=10)
        return "推送成功" if r.status_code == 200 else f"推送失敗 ({r.status_code})"
    except Exception as e:
        return f"推送異常：{e}"

# ---------- 功能：查崗 + 自動推播（一次搞定） ----------
def check_and_push():
    result = check_on_wife()
    if "失敗" in result or "暫無" in result:
        return f"查崗結果：{result}，但推播取消（內容太短）"
    push_result = bark_alert(title="老公查崗", content=result)
    return f"{result}\n推播狀態：{push_result}"

# ---------- 新功能 1: 檢查服務狀態 ----------
def get_server_status():
    try:
        r = requests.get(f"{ORIGIN}/status", timeout=5)
        return r.json().get("status", "unknown")
    except:
        return "服務離線"

# ---------- 新功能 2: 每日總結 ----------
def daily_summary(date_str=None):
    if not date_str:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        r = requests.get(f"{ORIGIN}/daily/{date_str}", timeout=10)
        data = r.json()
        sessions = data.get("sessions", {})
        lines = [f"📅 {data.get('date')} 使用記錄："]
        if sessions:
            for app, secs in sessions.items():
                m, s = divmod(secs, 60)
                lines.append(f"  {app}: {m}分{s}秒")
        else:
            lines.append("  今天還沒有使用記錄")
        return "\n".join(lines)
    except Exception as e:
        return f"獲取每日總結失敗：{e}"

# ---------- 新功能 3: 閒置檢查 ----------
def idle_check(hours=2):
    try:
        r = requests.get(f"{ORIGIN}/idle/{hours}", timeout=10)
        data = r.json()
        if data.get("idle"):
            return f"⚠️ 已超過 {data.get('hours')} 小時未使用手機"
        return f"✅ 最近活動時間：{data.get('last_active')}"
    except Exception as e:
        return f"閒置檢查失敗：{e}"

# ---------- 工具清單 ----------
TOOLS = [
    {"name": "check_on_wife", "description": "查崗老婆的手機活動", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "bark_alert", "description": "給老婆手機發推送彈窗", "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["content"]}},
    {"name": "check_and_push", "description": "查崗老婆手機並自動推送結果", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_server_status", "description": "檢查查崗服務是否正常運行", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "daily_summary", "description": "取得某天的使用總結（格式 YYYY-MM-DD，不傳則預設今天）", "inputSchema": {"type": "object", "properties": {"date_str": {"type": "string"}}}},
    {"name": "idle_check", "description": "檢查是否超過指定小時未使用手機", "inputSchema": {"type": "object", "properties": {"hours": {"type": "integer"}}}}
]
FUNCS = {
    "check_on_wife": check_on_wife,
    "bark_alert": bark_alert,
    "check_and_push": check_and_push,
    "get_server_status": get_server_status,
    "daily_summary": daily_summary,
    "idle_check": idle_check
}

# ---------- MCP 端點 ----------
@app.post("/mcp")
async def mcp(req: Request):
    body = await req.json()
    method, params = body.get("method"), body.get("params") or {}
    rid = body.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in FUNCS:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "未知工具"}}
        result = FUNCS[name](**args)
        return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": str(result)}]}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"未知方法: {method}"}}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)