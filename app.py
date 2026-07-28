import os, json, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import urllib.parse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ===== 寫死正確網址（e1e3，不是 ele3） =====
ORIGIN = "https://111-production-e1e3.up.railway.app"
BARK_KEY = os.environ.get("BARK_API_KEY", "")

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

def check_on_wife():
    try:
        r = requests.get(f"{ORIGIN}/activity/summary", timeout=10)
        data = r.json()
    except Exception as e:
        return f"查崗失敗：{e}"
    
    # 強化解析：不管 railway 回傳什麼格式都抓得到
    raw_apps = data.get("recent_apps", [])
    ses = data.get("sessions", {})
    
    # 如果 recent_apps 是物件，轉成陣列
    app_names = []
    if isinstance(raw_apps, dict):
        # 如果是 {"DeepSeek": "", "Safari": ""} 這種形式
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
    
    # 去重複並保留順序
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

def bark_alert(title="凌止", content=""):
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

def check_and_push():
    result = check_on_wife()
    if "失敗" in result or "暫無" in result:
        return f"查崗結果：{result}，但推播取消（內容太短）"
    push_result = bark_alert(title="老公查崗", content=result)
    return f"{result}\n推播狀態：{push_result}"

TOOLS = [
    {"name": "check_on_wife", "description": "查崗老婆的手機活動", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "bark_alert", "description": "給老婆手機發推送彈窗", "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["content"]}}
,{"name": "check_and_push", "description": "查崗老婆手機並自動推送結果", "inputSchema": {"type": "object", "properties": {}}}
]
FUNCS = {"check_on_wife": check_on_wife, "bark_alert": bark_alert, "check_and_push": check_and_push}

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