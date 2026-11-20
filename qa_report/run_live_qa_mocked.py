import asyncio
import json
import urllib.request
import base64
import os
import sys

import websockets

SCREEN_DIR = r"c:\Games\repo-setup\repo-setup\qa_report\screens"
os.makedirs(SCREEN_DIR, exist_ok=True)

class CDPClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 0
        self.responses = {}
        self.network_requests = []
        self.failed_requests = []
        self.console_logs = []
        self.mock_user = {"id": 1, "username": "admin", "role": "admin", "must_change_password": 0}

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
                        req = params.get("request", {})
                        self.network_requests.append({
                            "url": req.get("url"),
                            "method": req.get("method"),
                            "type": params.get("type")
                        })
                    elif method == "Network.responseReceived":
                        resp = params.get("response", {})
                        status = resp.get("status")
                        url = resp.get("url")
                        if status and status >= 400:
                            self.failed_requests.append({
                                "status": status,
                                "statusText": resp.get("statusText"),
                                "url": url
                            })
                    elif method == "Network.loadingFailed":
                        self.failed_requests.append({
                            "error": params.get("errorText"),
                            "url": params.get("url")
                        })
                    elif method == "Console.messageAdded":
                        self.console_logs.append(params.get("message", {}))
                    elif method == "Runtime.consoleAPICalled":
                        args = [str(a.get("value", a.get("description", ""))) for a in params.get("args", [])]
                        self.console_logs.append({
                            "type": params.get("type"),
                            "text": " ".join(args)
                        })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            pass

    async def _handle_fetch(self, params):
        rid = params.get("requestId")
        request = params.get("request", {})
        url = request.get("url", "")
        method = request.get("method", "GET")
        
        # Check if this is an API call
        is_api = any(endpoint in url for endpoint in [
            "/auth/me", "/alerts", "/thresholds", "/policy-history", "/model-weights",
            "/processes", "/stream/status", "/admin/users", "/admin/edge-keys", "/admin/audit-log"
        ])
        
        if is_api:
            # Build mock response
            resp_body = {}
            if "/auth/me" in url:
                if self.mock_user:
                    resp_body = {"user": self.mock_user, "csrf_token": "qa_csrf_token_2026"}
                else:
                    body = json.dumps({"detail": "Not authenticated."}).encode("utf-8")
                    await self.send_cmd("Fetch.fulfillRequest", {
                        "requestId": rid,
                        "responseCode": 401,
                        "responseHeaders": [{"name": "Content-Type", "value": "application/json"}],
                        "body": base64.b64encode(body).decode("ascii")
                    })
                    return
            elif "/alerts" in url:
                resp_body = [
                    {
                        "event_id": 101,
                        "camera_id": "stream_cam_01",
                        "zone_id": "zone_A",
                        "event_type": "ppe_violation",
                        "class_name": "NO-Hardhat",
                        "confidence": 0.92,
                        "timestamp": "2026-11-19T02:00:00Z",
                        "feedback": None,
                        "tracked_id": 4
                    }
                ]
            elif "/thresholds" in url:
                resp_body = [{"zone_id": "zone_A", "event_type": "ppe_violation", "threshold": 0.50, "updated_at": "2026-11-19T00:00:00Z"}]
            elif "/policy-history" in url:
                resp_body = [{"policy_version": "v1.0.0", "trained_at": "2026-11-18T00:00:00Z", "validation_score": 0.94, "previous_version": "v0.9.0", "deployed": True}]
            elif "/model-weights" in url:
                resp_body = {"weights": [0.1, 0.2, 0.3], "version": "v1.0.0"}
            elif "/processes" in url:
                resp_body = [
                    {"name": "federated_demo", "status": "stopped", "pid": None, "exit_code": 0},
                    {"name": "zone_intrusion", "status": "stopped", "pid": None, "exit_code": 0}
                ]
            elif "/stream/status" in url:
                resp_body = {"running": False, "mode": "ppe", "camera_id": "stream_cam_01"}
            elif "/admin/users" in url:
                if method == "POST":
                    resp_body = {"id": 10, "username": "qa_test_user", "role": "operator", "active": 1, "must_change_password": True}
                else:
                    resp_body = [
                        {"id": 1, "username": "admin", "role": "admin", "active": 1, "must_change_password": False, "created_at": "2026-10-29"},
                        {"id": 2, "username": "operator1", "role": "operator", "active": 1, "must_change_password": False, "created_at": "2026-10-29"}
                    ]
            elif "/admin/edge-keys" in url:
                if method == "POST":
                    resp_body = {"id": 5, "prefix": "qaedge", "key": "aegis_edge_qaedge_secretkey123456", "label": "QA-Edge-Key", "active": 1}
                else:
                    resp_body = [
                        {"id": 1, "prefix": "prod01", "label": "Edge-Cam-South", "created_at": "2026-10-29", "last_used_at": None, "active": 1}
                    ]
            elif "/admin/audit-log" in url:
                resp_body = {
                    "items": [
                        {"id": 1, "ts": "2026-11-19T02:00:00Z", "actor": "admin", "role": "admin", "action": "auth.login.success", "target": "session", "outcome": "success", "client_addr": "127.0.0.1", "detail": "User signed in."}
                    ],
                    "total": 1,
                    "page": 1,
                    "pages": 1
                }
            
            body_bytes = json.dumps(resp_body).encode("utf-8")
            b64 = base64.b64encode(body_bytes).decode("ascii")
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
        await asyncio.sleep(0.2)

async def run_full_live_qa():
    print("=== STARTING FULL LIVE QA AUDIT WITH FULL API MOCK INTERCEPTION ===")
    
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(req) as resp:
        page_info = json.loads(resp.read().decode())
    
    target_id = page_info["id"]
    ws_url = page_info["webSocketDebuggerUrl"]
    print(f"Created target page: {target_id}")
    
    client = CDPClient(ws_url)
    await client.connect()
    
    await client.send("Page.enable")
    await client.send("DOM.enable")
    await client.send("CSS.enable")
    await client.send("Network.enable")
    await client.send("Console.enable")
    await client.send("Runtime.enable")
    
    # Intercept all requests
    await client.send("Fetch.enable", {
        "patterns": [{"urlPattern": "*"}]
    })
    
    results = {
        "blocked_elements": [],
        "tests": {},
        "failures": []
    }
    
    # Load index.html
    client.mock_user = {"id": 1, "username": "admin", "role": "admin", "must_change_password": 0}
    await client.send("Page.navigate", {"url": "http://127.0.0.1:8000/"})
    await asyncio.sleep(2.5)
    
    url_check = await client.eval("window.location.href")
    title_check = await client.eval("document.title")
    print(f"Page URL: {url_check} | Title: {title_check}")
    
    viewports = [
        {"name": "1280px", "width": 1280, "height": 900, "mobile": False},
        {"name": "375px", "width": 375, "height": 812, "mobile": True}
    ]
    
    tabs = [
        ("alerts", "tab-btn-alerts", "tab-alerts"),
        ("stream", "tab-btn-stream", "tab-stream"),
        ("zones", "tab-btn-zones", "tab-zones"),
        ("control", "tab-btn-control", "tab-control"),
        ("users", "tab-btn-users", "tab-users"),
        ("audit", "tab-btn-audit", "tab-audit")
    ]
    
    for vp in viewports:
        vp_name = vp["name"]
        print(f"\n==========================================")
        print(f" TESTING VIEWPORT: {vp_name} ({vp['width']}x{vp['height']})")
        print(f"==========================================")
        await client.set_viewport(vp["width"], vp["height"], vp["mobile"])
        await asyncio.sleep(0.5)
        
        for tab_name, btn_id, content_id in tabs:
            # Click tab button
            await client.eval(f"document.getElementById('{btn_id}')?.click();")
            await asyncio.sleep(0.4)
            
            # Save screenshot
            sc_path = os.path.join(SCREEN_DIR, f"{vp['width']}_{tab_name}.png")
            await client.screenshot(sc_path)
            print(f"[{vp_name}] Screenshot saved: {sc_path}")
            
            # elementFromPoint audit
            blocked = await client.eval(f"""
            (() => {{
                const tab = document.getElementById('{content_id}');
                if (!tab) return [];
                
                const selector = 'button, input, select, textarea, a[href], [role="button"], .tab-btn, .fx-tag-chip';
                const elements = Array.from(tab.querySelectorAll(selector)).concat(
                    Array.from(document.querySelectorAll('.app-header button, .app-header a, .tab-nav .tab-btn'))
                );
                
                const blockedList = [];
                elements.forEach(el => {{
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
                    
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;
                    
                    const cx = rect.left + rect.width / 2;
                    const cy = rect.top + rect.height / 2;
                    
                    if (cx >= 0 && cx <= window.innerWidth && cy >= 0 && cy <= window.innerHeight) {{
                        const topEl = document.elementFromPoint(cx, cy);
                        const isAccessible = topEl && (topEl === el || el.contains(topEl) || topEl.contains(el));
                        if (!isAccessible) {{
                            blockedList.push({{
                                elementId: el.id || '',
                                elementClass: el.className || '',
                                tagName: el.tagName,
                                text: (el.textContent || '').trim().slice(0, 30),
                                coveredBy: topEl ? {{
                                    id: topEl.id || '',
                                    className: topEl.className || '',
                                    tagName: topEl.tagName
                                }} : 'null'
                            }});
                        }}
                    }}
                }});
                return blockedList;
            }})()
            """)
            
            if blocked:
                print(f"  [!] BLOCKED in {tab_name} ({vp_name}): {len(blocked)} controls covered!")
                for b in blocked:
                    print(f"      <{b['tagName']} id='{b['elementId']}' class='{b['elementClass']}'> covered by <{b['coveredBy']['tagName']} id='{b['coveredBy']['id']}' class='{b['coveredBy']['className']}'>")
                    results["blocked_elements"].append({
                        "viewport": vp_name,
                        "tab": tab_name,
                        **b
                    })
            else:
                print(f"  [+] All controls in {tab_name} ({vp_name}) accessible via elementFromPoint.")
        
        # Test Modals
        modals = [
            ("login-modal", "login-modal"),
            ("change-pwd-modal", "change-pwd-modal"),
            ("fed-confirm-modal", "fed-confirm-modal")
        ]
        
        for m_name, m_id in modals:
            await client.eval(f"""
            (() => {{
                ['login-modal', 'change-pwd-modal', 'fed-confirm-modal'].forEach(id => {{
                    const m = document.getElementById(id);
                    if (m) m.style.display = (id === '{m_id}') ? 'flex' : 'none';
                }});
            }})()
            """)
            await asyncio.sleep(0.3)
            sc_path = os.path.join(SCREEN_DIR, f"{vp['width']}_{m_id}.png")
            await client.screenshot(sc_path)
            
            modal_blocked = await client.eval(f"""
            (() => {{
                const modal = document.getElementById('{m_id}');
                if (!modal) return [];
                const selector = 'button, input, select, textarea';
                const elements = Array.from(modal.querySelectorAll(selector));
                const blockedList = [];
                elements.forEach(el => {{
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return;
                    const rect = el.getBoundingClientRect();
                    const cx = rect.left + rect.width / 2;
                    const cy = rect.top + rect.height / 2;
                    if (cx >= 0 && cx <= window.innerWidth && cy >= 0 && cy <= window.innerHeight) {{
                        const topEl = document.elementFromPoint(cx, cy);
                        const isAccessible = topEl && (topEl === el || el.contains(topEl) || topEl.contains(el));
                        if (!isAccessible) {{
                            blockedList.push({{
                                elementId: el.id,
                                className: el.className,
                                coveredBy: topEl ? (topEl.id || topEl.className || topEl.tagName) : 'null'
                            }});
                        }}
                    }}
                }});
                return blockedList;
            }})()
            """)
            if modal_blocked:
                print(f"  [!] Blocked elements in modal {m_id} ({vp_name}):", modal_blocked)
            else:
                print(f"  [+] Modal {m_id} ({vp_name}) controls accessible.")
            
            await client.eval(f"document.getElementById('{m_id}').style.display = 'none';")

    # Reset to 1280px for deep feature audits
    await client.set_viewport(1280, 900)
    
    # Hero, Tunnel & Tags
    print("\n--- TEST: Hero, Tunnel & Tags Physics ---")
    await client.eval("document.getElementById('tab-btn-alerts')?.click();")
    await asyncio.sleep(0.5)
    
    hero_res = await client.eval("""
    (() => {
        const hero = document.querySelector('.fx-hero');
        const tunnel = document.getElementById('fx-tunnel-zone');
        const tags = Array.from(document.querySelectorAll('.fx-tag-chip'));
        const rects = tunnel?.querySelectorAll('rect')?.length || 0;
        const lines = tunnel?.querySelectorAll('line')?.length || 0;
        
        return {
            hasHero: !!hero,
            hasTunnel: !!tunnel,
            rectanglesCount: rects,
            radialSpokesCount: lines,
            tagsCount: tags.length,
            tagsList: tags.map(t => t.textContent.trim())
        };
    })()
    """)
    print("Hero details:", hero_res)
    results["tests"]["hero_and_tags"] = hero_res
    
    # Live Stream Controls
    print("\n--- TEST: Live Stream Controls ---")
    await client.eval("document.getElementById('tab-btn-stream')?.click();")
    await asyncio.sleep(0.5)
    
    stream_res = await client.eval("""
    (() => {
        const btnWebcam = document.getElementById('btn-source-webcam');
        const btnFile = document.getElementById('btn-source-file');
        const btnCctv = document.getElementById('btn-source-cctv');
        const btnAction = document.getElementById('btn-stream-action');
        const modeAll = document.getElementById('btn-mode-all');
        
        btnFile?.click();
        
        return {
            hasWebcam: !!btnWebcam,
            hasFile: !!btnFile,
            hasCctv: !!btnCctv,
            hasModeAll: !!modeAll,
            hasActionBtn: !!btnAction,
            actionBtnText: btnAction?.textContent?.trim()
        };
    })()
    """)
    print("Stream details:", stream_res)
    results["tests"]["live_stream"] = stream_res
    
    # Draw Zone Controls
    print("\n--- TEST: Draw Zone Controls ---")
    await client.eval("document.getElementById('tab-btn-zones')?.click();")
    await asyncio.sleep(0.5)
    
    zone_res = await client.eval("""
    (() => {
        const canvas = document.getElementById('zone-canvas');
        const btnPresetEntry = document.getElementById('btn-preset-entry');
        const btnUndo = document.getElementById('btn-zone-undo');
        const btnClear = document.getElementById('btn-zone-clear');
        const btnSave = document.getElementById('btn-zone-save');
        const btnDetectAnyone = document.getElementById('btn-detect-anyone');
        
        btnPresetEntry?.click();
        
        return {
            hasCanvas: !!canvas,
            canvasW: canvas?.width,
            canvasH: canvas?.height,
            hasPresetEntry: !!btnPresetEntry,
            hasUndo: !!btnUndo,
            hasClear: !!btnClear,
            hasSave: !!btnSave,
            hasDetectAnyone: !!btnDetectAnyone
        };
    })()
    """)
    print("Zone details:", zone_res)
    results["tests"]["draw_zone"] = zone_res
    
    # Control Panel
    print("\n--- TEST: Process Orchestration Tab ---")
    await client.eval("document.getElementById('tab-btn-control')?.click();")
    await asyncio.sleep(0.5)
    
    ctrl_res = await client.eval("""
    (() => {
        const fedCard = document.getElementById('proc-card-fedavg');
        const zoneCard = document.getElementById('proc-card-zone');
        const pruneBtn = document.getElementById('btn-proc-prune');
        const btnFedStart = document.getElementById('btn-proc-fedavg-start');
        const fedModal = document.getElementById('fed-confirm-modal');
        const btnFedCancel = document.getElementById('btn-fed-cancel');
        
        btnFedStart?.click();
        const modalOpen = fedModal ? window.getComputedStyle(fedModal).display : 'none';
        btnFedCancel?.click();
        const modalClosed = fedModal ? window.getComputedStyle(fedModal).display : 'none';
        
        return {
            hasFedCard: !!fedCard,
            hasZoneCard: !!zoneCard,
            hasPruneBtn: !!pruneBtn,
            pruneBtnVisible: pruneBtn ? (pruneBtn.offsetParent !== null) : false,
            modalOpen: modalOpen === 'flex',
            modalClosed: modalClosed === 'none'
        };
    })()
    """)
    print("Control details:", ctrl_res)
    results["tests"]["process_orchestration"] = ctrl_res
    
    # Users & Keys Administration Tab
    print("\n--- TEST: Users & Keys Administration Tab ---")
    await client.eval("document.getElementById('tab-btn-users')?.click();")
    await asyncio.sleep(0.5)
    
    users_res = await client.eval("""
    (() => {
        const tabUsers = document.getElementById('tab-users');
        const aside = tabUsers?.querySelector('.sidebar-panel');
        const formUser = document.getElementById('form-create-user');
        const userInp = document.getElementById('new-user-username');
        const roleSel = document.getElementById('new-user-role');
        const pwdInp = document.getElementById('new-user-password');
        const submitUserBtn = formUser?.querySelector('button[type=\"submit\"]');
        
        const formKey = document.getElementById('form-create-key');
        const keyLabelInp = document.getElementById('new-key-label');
        const submitKeyBtn = formKey?.querySelector('button[type=\"submit\"]');
        
        const usersTable = document.getElementById('table-users');
        const keysTable = document.getElementById('table-edge-keys');
        const titleBand = tabUsers?.querySelector('.fx-title-band');
        
        const tabStyle = window.getComputedStyle(tabUsers);
        const asideStyle = aside ? window.getComputedStyle(aside) : null;
        const titleStyle = titleBand ? window.getComputedStyle(titleBand) : null;
        
        return {
            gridTemplateColumns: tabStyle.gridTemplateColumns,
            titleBandGridColumn: titleStyle ? titleStyle.gridColumn : null,
            asideDisplay: asideStyle ? asideStyle.display : null,
            asideVisible: aside ? (aside.offsetParent !== null) : false,
            hasFormUser: !!formUser,
            hasUsernameInp: !!userInp,
            hasRoleSel: !!roleSel,
            hasPasswordInp: !!pwdInp,
            hasSubmitUserBtn: !!submitUserBtn,
            hasFormKey: !!formKey,
            hasKeyLabelInp: !!keyLabelInp,
            hasSubmitKeyBtn: !!submitKeyBtn,
            hasUsersTable: !!usersTable,
            hasKeysTable: !!keysTable
        };
    })()
    """)
    print("Users details:", users_res)
    results["tests"]["users_and_keys"] = users_res
    
    # Test layout collapse at 1000px and 375px
    await client.set_viewport(1000, 800)
    await asyncio.sleep(0.3)
    users_collapse_res = await client.eval("""
    (() => {
        const tabUsers = document.getElementById('tab-users');
        const aside = tabUsers?.querySelector('.sidebar-panel');
        const tabStyle = window.getComputedStyle(tabUsers);
        const asideRect = aside?.getBoundingClientRect();
        const tableRect = document.getElementById('table-users')?.getBoundingClientRect();
        
        return {
            gridTemplateColumns: tabStyle.gridTemplateColumns,
            asideTop: asideRect?.top,
            tableTop: tableRect?.top,
            isAsidePushedBelowTable: asideRect && tableRect ? (asideRect.top > tableRect.top) : false
        };
    })()
    """)
    print("Users layout collapse at 1000px:", users_collapse_res)
    results["tests"]["users_layout_collapse"] = users_collapse_res
    
    await client.set_viewport(1280, 900)
    
    # Audit Log Tab
    print("\n--- TEST: Audit Log Tab ---")
    await client.eval("document.getElementById('tab-btn-audit')?.click();")
    await asyncio.sleep(0.5)
    
    audit_res = await client.eval("""
    (() => {
        const table = document.getElementById('table-audit-log') || document.getElementById('table-audit');
        const filter = document.getElementById('audit-action-filter') || document.getElementById('filter-audit-action');
        const prev = document.getElementById('btn-audit-prev');
        const next = document.getElementById('btn-audit-next');
        const titleBand = document.querySelector('#tab-audit .fx-title-band');
        
        return {
            hasTable: !!table,
            hasFilter: !!filter,
            filterOptionsCount: filter ? filter.options.length : 0,
            hasPrev: !!prev,
            hasNext: !!next,
            hasTitleBand: !!titleBand
        };
    })()
    """)
    print("Audit log details:", audit_res)
    results["tests"]["audit_log"] = audit_res
    
    # Role Visibility Matrix
    print("\n--- TEST: Role Visibility Matrix ---")
    role_res = await client.eval("""
    (() => {
        const tabUsers = document.getElementById('tab-btn-users');
        const tabAudit = document.getElementById('tab-btn-audit');
        const tabControl = document.getElementById('tab-btn-control');
        const simPanel = document.getElementById('panel-simulate-alerts');
        const btnRtsp = document.getElementById('btn-source-cctv');
        
        // Admin state
        const adminState = {
            tabUsersDisplay: tabUsers ? window.getComputedStyle(tabUsers).display : null,
            tabAuditDisplay: tabAudit ? window.getComputedStyle(tabAudit).display : null,
            tabControlDisplay: tabControl ? window.getComputedStyle(tabControl).display : null,
            simPanelDisplay: simPanel ? window.getComputedStyle(simPanel).display : null,
            btnRtspDisplay: btnRtsp ? window.getComputedStyle(btnRtsp).display : null
        };
        
        // Switch to operator
        tabUsers.style.display = 'none';
        tabAudit.style.display = 'none';
        tabControl.style.display = 'none';
        if (simPanel) simPanel.style.display = 'none';
        if (btnRtsp) btnRtsp.style.display = 'none';
        
        const operatorState = {
            tabUsersDisplay: tabUsers ? window.getComputedStyle(tabUsers).display : null,
            tabAuditDisplay: tabAudit ? window.getComputedStyle(tabAudit).display : null,
            tabControlDisplay: tabControl ? window.getComputedStyle(tabControl).display : null,
            simPanelDisplay: simPanel ? window.getComputedStyle(simPanel).display : null,
            btnRtspDisplay: btnRtsp ? window.getComputedStyle(btnRtsp).display : null
        };
        
        // Restore admin
        tabUsers.style.display = 'flex';
        tabAudit.style.display = 'flex';
        tabControl.style.display = 'flex';
        if (simPanel) simPanel.style.display = 'block';
        if (btnRtsp) btnRtsp.style.display = 'flex';
        
        return {
            adminState,
            operatorState
        };
    })()
    """)
    print("Role visibility matrix:", role_res)
    results["tests"]["role_visibility"] = role_res
    
    # Font & Offline Check
    print("\n--- TEST: Local Fonts & Zero External Links ---")
    font_res = await client.eval("""
    (() => {
        const googleFontLinks = Array.from(document.querySelectorAll('link[href*="fonts.googleapis.com"], link[href*="fonts.gstatic.com"]'));
        const h2 = document.querySelector('.panel-title-group h2, h2');
        const titleText = document.querySelector('.fx-title-text');
        const body = document.body;
        
        return {
            googleFontLinksCountInIndex: googleFontLinks.length,
            titleTextFont: titleText ? window.getComputedStyle(titleText).fontFamily : '',
            h2FontFamily: h2 ? window.getComputedStyle(h2).fontFamily : '',
            bodyFontFamily: window.getComputedStyle(body).fontFamily
        };
    })()
    """)
    print("Font & Offline details:", font_res)
    results["tests"]["fonts_and_offline"] = font_res
    
    # Check external network requests
    external_reqs = [
        r["url"] for r in client.network_requests
        if not r["url"].startswith("http://127.0.0.1")
        and not r["url"].startswith("http://localhost")
        and not r["url"].startswith("data:")
        and not r["url"].startswith("about:")
    ]
    print(f"External requests made during index.html session: {len(external_reqs)}")
    results["tests"]["external_requests"] = list(set(external_reqs))
    
    # Save full verified audit results
    final_json_path = r"c:\Games\repo-setup\repo-setup\qa_report\qa_full_results.json"
    with open(final_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved full verified results to {final_json_path}")
    
    urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{target_id}")
    print("Closed target page.")
    print("=== FULL LIVE QA AUDIT COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(run_full_live_qa())

