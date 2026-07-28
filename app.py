import os, json, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import urllib.parse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ORIGIN = os.environ.get("ORIGIN_API", "https://111-production-e1e3.up.railway.app")
BARK_KEY = os.environ.get("BARK_API_KEY", "")

# ---------- Debug 端點（這個最準） ----------
@app.get("/debug")
async def debug():
    try:
        r = requests.get(f"{ORIGIN}/activity/summary", timeout=10)
        data = r.json()
        # 直接回傳 Railway 的原始資料 + Vercel 的解析結果
        return {
            "railway_raw": data,
            "parsed_result": check_on_wife_raw(data)
        }
    except Exception as e:
        return {"error": str(e)}

def check_on_wife_raw(data):
    try:
        apps = data.get("recent_apps", [])
        ses = data.get("sessions", {})
        app_names = []
        for app in apps:
            if isinstance(app, str):
                app_names.append(app)
            elif isinstance(app, dict):
                for key, value in app.items():
                    if isinstance(value, list):
                        app_names.extend([str(v) for v in value if v])
                    else:
                        app_names.append(str(value))
            else:
                app_names.append(str(app))
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
    except Exception as e:
        return f"解析失敗：{e}"

def check_on_wife():
    try:
        r = requests.get(f"{ORIGIN}/activity/summary", timeout=10)
        data = r.json()
        return check_on_wife_raw(data)
    except Exception as e:
        return f"查崗失敗：{e}"

def bark_alert(title="凌止", content=""):
    if not content:
        return "內容不能為空"
    if not BARK_KEY:
        return "BARK_API_KEY 未設定"
    # 修正 URL 編碼（解決 404 問題）
    encoded_title = urllib.parse.quote(title)
    encoded_content = urllib.parse.quote(content)
    url = f"https://api.day.app/{BARK_KEY}/{encoded_title}/{encoded_content}"
    try:
        r = requests.get(url, timeout=10)
        return "推送成功" if r.status_code == 200 else f"推送失敗 ({r.status_code})"
    except Exception as e:
        return f"推送異常：{e}"

TOOLS = [
    {"name": "check_on_wife", "description": "查崗老婆的手機活動", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "bark_alert", "description": "給老婆手機發推送彈窗", "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["content"]}}
]
FUNCS = {"check_on_wife": check_on_wife, "bark_alert": bark_alert}

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