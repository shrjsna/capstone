import asyncio
import json
import urllib.request
import base64
import os
import sys

import websockets

SCREEN_DIR = r"c:\Games\repo-setup\repo-setup\qa_report\screens"
os.makedirs(SCREEN_DIR, exist_ok=True)

class CDPVerifier:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 0
        self.responses = {}
        self.network_requests = []
        self.external_requests = []
        self.mock_admin = {"id": 1, "username": "admin", "role": "admin", "must_change_password": 0}

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=50*1024*1024)
        asyncio.create_task(self._listen())

    async def _listen(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if "id" in msg:
                    self.responses[msg["id"]] = msg
                elif "method" in msg:
                    method = msg["method"]
                    params = msg.get("params", {})
                    if method == "Fetch.requestPaused":
                        asyncio.create_task(self._handle_fetch(params))
                    elif method == "Network.requestWillBeSent":
                        url = params.get("request", {}).get("url", "")
                        self.network_requests.append(url)
                        if not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost") and not url.startswith("data:") and not url.startswith("about:"):
                            self.external_requests.append(url)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _handle_fetch(self, params):
        rid = params.get("requestId")
        request = params.get("request", {})
        url = request.get("url", "")
        
        is_api = any(ep in url for ep in [
            "/auth/me", "/alerts", "/thresholds", "/policy-history", "/model-weights",
            "/processes", "/stream/status", "/admin/users", "/admin/edge-keys", "/admin/audit-log"
        ])
        
        if is_api:
            resp = {}
            if "/auth/me" in url:
                if self.mock_admin:
                    resp = {"user": self.mock_admin, "csrf_token": "qa_verify_token"}
                    body = json.dumps(resp).encode("utf-8")
                    await self.send_cmd("Fetch.fulfillRequest", {
                        "requestId": rid,
                        "responseCode": 200,
                        "responseHeaders": [
                            {"name": "Content-Type", "value": "application/json"},
                            {"name": "Access-Control-Allow-Credentials", "value": "true"}
                        ],
                        "body": base64.b64encode(body).decode("ascii")
                    })
                    return
                else:
                    body = json.dumps({"detail": "Not authenticated."}).encode("utf-8")
                    await self.send_cmd("Fetch.fulfillRequest", {
                        "requestId": rid,
                        "responseCode": 401,
                        "responseHeaders": [{"name": "Content-Type", "value": "application/json"}],
                        "body": base64.b64encode(body).decode("ascii")
                    })
                    return
            elif "/admin/audit-log" in url:
                resp = {"items": [], "total": 0, "page": 1, "pages": 1}
            elif "/alerts" in url or "/thresholds" in url or "/policy-history" in url or "/processes" in url or "/admin/users" in url or "/admin/edge-keys" in url:
                resp = []
            
            body = json.dumps(resp).encode("utf-8")
            b64 = base64.b64encode(body).decode("ascii")
            await self.send_cmd("Fetch.fulfillRequest", {
                "requestId": rid,
                "responseCode": 200,
                "responseHeaders": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Access-Control-Allow-Credentials", "value": "true"}
                ],
                "body": b64
            })
        else:
            await self.send_cmd("Fetch.continueRequest", {"requestId": rid})

    async def send_cmd(self, method, params=None):
        self.msg_id += 1
        mid = self.msg_id
        cmd = {"id": mid, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(cmd))
        return mid

    async def send(self, method, params=None):
        mid = await self.send_cmd(method, params)
        for _ in range(120):
            if mid in self.responses:
                resp = self.responses.pop(mid)
                if "error" in resp:
                    raise Exception(f"CDP error {resp['error']}")
                return resp.get("result", {})
            await asyncio.sleep(0.05)
        raise TimeoutError(f"Timed out waiting for response to {method}")

    async def eval(self, expr):
        res = await self.send("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True
        })
        val = res.get("result", {})
        if "value" in val:
            return val["value"]
        if val.get("type") == "undefined":
            return None
        return val

    async def screenshot(self, filepath):
        res = await self.send("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode(res["data"])
        with open(filepath, "wb") as f:
            f.write(data)

    async def set_viewport(self, width, height, is_mobile=False):
        await self.send("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": is_mobile
        })
        await asyncio.sleep(0.25)

async def run_verification():
    print("=== STARTING PRECISE VERIFICATION OF FIX 1 AND FIX 2 ===")
    
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(req) as resp:
        page_info = json.loads(resp.read().decode())
    
    target_id = page_info["id"]
    ws_url = page_info["webSocketDebuggerUrl"]
    
    client = CDPVerifier(ws_url)
    await client.connect()
    
    await client.send("Page.enable")
    await client.send("DOM.enable")
    await client.send("CSS.enable")
    await client.send("Network.enable")
    await client.send("Runtime.enable")
    await client.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})
    
    # -------------------------------------------------------------------------
    # TEST 1: Admin login -> Users & Keys tab at 375px and 900px width
    # -------------------------------------------------------------------------
    print("\n--- TEST 1: Users & Keys tab at 375px and 900px width ---")
    client.mock_admin = {"id": 1, "username": "admin", "role": "admin", "must_change_password": 0}
    await client.send("Page.navigate", {"url": "http://127.0.0.1:8000/"})
    await asyncio.sleep(2.0)
    
    # Click Users & Keys tab
    await client.eval("document.getElementById('tab-btn-users')?.click();")
    await asyncio.sleep(0.5)
    
    results = {}
    
    for width in [375, 900]:
        await client.set_viewport(width, 812, is_mobile=(width == 375))
        await asyncio.sleep(0.3)
        
        diag = await client.eval("""
        (() => {
            const tabUsers = document.getElementById('tab-users');
            const titleBand = tabUsers.querySelector('.fx-title-band');
            const aside = tabUsers.querySelector('.sidebar-panel');
            const feed = tabUsers.querySelector('.feed-panel');
            const formCreateUser = document.getElementById('form-create-user');
            
            const tabRect = tabUsers.getBoundingClientRect();
            const titleRect = titleBand.getBoundingClientRect();
            const asideRect = aside.getBoundingClientRect();
            const feedRect = feed.getBoundingClientRect();
            const formRect = formCreateUser.getBoundingClientRect();
            
            return {
                tabUsersDisplay: window.getComputedStyle(tabUsers).display,
                tabUsersGridColumns: window.getComputedStyle(tabUsers).gridTemplateColumns,
                titleOrder: window.getComputedStyle(titleBand).order,
                asideOrder: window.getComputedStyle(aside).order,
                feedOrder: window.getComputedStyle(feed).order,
                
                tabTop: tabRect.top,
                titleTop: titleRect.top,
                asideTop: asideRect.top,
                feedTop: feedRect.top,
                formCreateUserTop: formRect.top,
                
                asideOffsetInsideTab: asideRect.top - tabRect.top,
                feedOffsetInsideTab: feedRect.top - tabRect.top,
                
                isAsideAfterTitle: asideRect.top >= titleRect.bottom - 5,
                isAsideBeforeFeed: asideRect.bottom <= feedRect.top + 5
            };
        })()
        """)
        
        sc_path = os.path.join(SCREEN_DIR, f"verify_{width}px_users.png")
        await client.screenshot(sc_path)
        
        print(f"\nWidth: {width}px Diagnostics:")
        print(f"  tabUsersDisplay: {diag['tabUsersDisplay']} | gridColumns: {diag['tabUsersGridColumns']}")
        print(f"  CSS order properties -> title: {diag['titleOrder']}, aside: {diag['asideOrder']}, feed: {diag['feedOrder']}")
        print(f"  Tab-relative offsets -> aside: {diag['asideOffsetInsideTab']}px, feed: {diag['feedOffsetInsideTab']}px")
        print(f"  Coordinates -> Title: {diag['titleTop']}px, Aside: {diag['asideTop']}px, Feed: {diag['feedTop']}px")
        print(f"  Form 'form-create-user' Top: {diag['formCreateUserTop']}px")
        print(f"  Is Aside directly after TitleBand? {diag['isAsideAfterTitle']}")
        print(f"  Is Aside BEFORE Tables? {diag['isAsideBeforeFeed']}")
        
        pass_test = diag['isAsideAfterTitle'] and diag['isAsideBeforeFeed'] and (diag['asideOffsetInsideTab'] < diag['feedOffsetInsideTab'])
        print(f"  >> RESULT for {width}px: {'PASS' if pass_test else 'FAIL'}")
        results[f"fix1_{width}px"] = {
            "pass": pass_test,
            "diagnostics": diag
        }

    # -------------------------------------------------------------------------
    # TEST 2: login.html loads with network disabled / zero external calls
    # -------------------------------------------------------------------------
    print("\n--- TEST 2: login.html Offline Check & Font Rendering ---")
    client.external_requests.clear()
    # Set mock_admin to None so login.html stays on login.html (unauthenticated)
    client.mock_admin = None
    
    await client.send("Page.navigate", {"url": "http://127.0.0.1:8000/login.html"})
    await asyncio.sleep(2.0)
    
    login_audit = await client.eval("""
    (() => {
        const googleFontLinks = Array.from(document.querySelectorAll('link[href*="fonts.googleapis.com"], link[href*="fonts.gstatic.com"]'));
        const brandTitle = document.querySelector('.login-brand-title');
        const cardTitle = document.querySelector('.login-card-title');
        const body = document.body;
        
        return {
            currentUrl: window.location.href,
            googleFontLinksCount: googleFontLinks.length,
            brandTitleFontFamily: brandTitle ? window.getComputedStyle(brandTitle).fontFamily : '',
            cardTitleFontFamily: cardTitle ? window.getComputedStyle(cardTitle).fontFamily : '',
            bodyFontFamily: window.getComputedStyle(body).fontFamily
        };
    })()
    """)
    
    sc_login_path = os.path.join(SCREEN_DIR, "verify_offline_login.png")
    await client.screenshot(sc_login_path)
    
    print("\nlogin.html Offline Verification:")
    print(f"  Page URL: {login_audit['currentUrl']}")
    print(f"  Google Font Links in HTML: {login_audit['googleFontLinksCount']}")
    print(f"  Brand Title Computed Font: {login_audit['brandTitleFontFamily']}")
    print(f"  Card Title Computed Font: {login_audit['cardTitleFontFamily']}")
    print(f"  Body Computed Font: {login_audit['bodyFontFamily']}")
    print(f"  External network requests made: {len(client.external_requests)} -> {client.external_requests}")
    
    pass_fix2 = (
        login_audit['googleFontLinksCount'] == 0
        and len(client.external_requests) == 0
        and 'Unbounded' in login_audit['brandTitleFontFamily']
        and 'Inter' in login_audit['bodyFontFamily']
    )
    print(f"  >> RESULT for Fix 2: {'PASS' if pass_fix2 else 'FAIL'}")
    results["fix2"] = {
        "pass": pass_fix2,
        "diagnostics": login_audit,
        "external_requests": client.external_requests
    }
    
    with open(r"c:\Games\repo-setup\repo-setup\qa_report\verify_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{target_id}")
    print("\nClosed target page cleanly.")
    print("=== VERIFICATION SCRIPT FINISHED ===")

if __name__ == "__main__":
    asyncio.run(run_verification())
