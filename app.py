import os, json, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ORIGIN = os.environ.get("ORIGIN_API", "https://你的Railway域名")
BARK_KEY = os.environ.get("BARK_API_KEY", "")

def check_on_wife():
    try:
        r = requests.get(f"{ORIGIN}/activity/summary", timeout=10)
        data = r.json()
    except Exception as e:
        return f"查崗失敗：{e}"
    apps = data.get("recent_apps", [])
    ses = data.get("sessions", {})
    lines = [f"最近打開：{', '.join(apps) if apps else '暫無記錄'}"]
    if ses:
        for app, secs in sorted(ses.items(), key=lambda x: x[1], reverse=True):
            m, s = divmod(secs, 60)
            lines.append(f"  {app}: {m}分{s}秒")
    return "\n".join(lines)

def bark_alert(title="祁宸", content=""):
    if not content:
        return "內容不能為空"
    if not BARK_KEY:
        return "BARK_API_KEY 未設定"
    url = f"https://api.day.app/{BARK_KEY}/{title}/{content}"
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
