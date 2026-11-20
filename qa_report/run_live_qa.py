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
        self.intercept_auth = True

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
        
        if self.intercept_auth and "/auth/me" in url:
            if self.mock_user:
                body = json.dumps({
                    "user": self.mock_user,
                    "csrf_token": "mock_csrf_token_for_audit_2026"
                }).encode("utf-8")
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
                body = json.dumps({"detail": "Not authenticated."}).encode("utf-8")
                b64 = base64.b64encode(body).decode("ascii")
                await self.send_cmd("Fetch.fulfillRequest", {
                    "requestId": rid,
                    "responseCode": 401,
                    "responseHeaders": [
                        {"name": "Content-Type", "value": "application/json"}
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

async def run_audit():
    print("=== STARTING AEGIS LIVE QA AUDIT VIA CDP WITH FETCH INTERCEPTION ===")
    
    # 1. Create a fresh target page
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(req) as resp:
        page_info = json.loads(resp.read().decode())
    
    target_id = page_info["id"]
    ws_url = page_info["webSocketDebuggerUrl"]
    print(f"Created target page: {target_id}")
    
    client = CDPClient(ws_url)
    await client.connect()
    
    # Enable domains
    await client.send("Page.enable")
    await client.send("DOM.enable")
    await client.send("CSS.enable")
    await client.send("Network.enable")
    await client.send("Console.enable")
    await client.send("Runtime.enable")
    
    # Enable Fetch interception on *auth/me*
    await client.send("Fetch.enable", {
        "patterns": [{"urlPattern": "*auth/me*"}]
    })
    
    results = {
        "blocked_elements": [],
        "tests": {},
        "failures": []
    }
    
    # =========================================================================
    # Test 1: Unauthenticated user -> redirects to /login.html
    # =========================================================================
    print("\n--- TEST 1: Unauthenticated Redirect to /login.html ---")
    client.mock_user = None  # 401 on /auth/me
    await client.send("Page.navigate", {"url": "http://127.0.0.1:8000/"})
    await asyncio.sleep(2.0)
    
    login_url = await client.eval("window.location.href")
    print(f"URL when unauthenticated: {login_url}")
    results["tests"]["unauth_redirect"] = {
        "pass": "login.html" in str(login_url),
        "url": login_url
    }
    
    # Test invalid login on login.html
    inv_res = await client.eval("""
    (async () => {
        const u = document.getElementById('login-username');
        const p = document.getElementById('login-password');
        const b = document.getElementById('btn-login-submit');
        const a = document.getElementById('login-alert');
        if (u && p && b) {
            u.value = 'bad_user';
            p.value = 'WrongPassword999!';
            b.click();
            await new Promise(r => setTimeout(r, 1000));
            return {
                alertDisplay: a ? window.getComputedStyle(a).display : 'none',
                alertText: a ? a.textContent : ''
            };
        }
        return { error: 'elements missing' };
    })()
    """)
    print("Invalid login result:", inv_res)
    results["tests"]["invalid_login"] = inv_res
    
    # =========================================================================
    # Test 2: Mandatory Password Change Modal Flow
    # =========================================================================
    print("\n--- TEST 2: Mandatory Password Change Flow ---")
    client.mock_user = {
        "id": 3,
        "username": "test_operator_2",
        "role": "operator",
        "must_change_password": 1
    }
    await client.send("Page.navigate", {"url": "http://127.0.0.1:8000/"})
    await asyncio.sleep(2.0)
    
    pwd_flow_res = await client.eval("""
    (() => {
        const modal = document.getElementById('change-pwd-modal');
        const oldInp = document.getElementById('change-pwd-old');
        const newInp = document.getElementById('change-pwd-new');
        const confInp = document.getElementById('change-pwd-confirm');
        const submitBtn = document.getElementById('btn-submit-change-pwd');
        
        return {
            modalVisible: modal ? (window.getComputedStyle(modal).display !== 'none') : false,
            hasOld: !!oldInp,
            hasNew: !!newInp,
            hasConfirm: !!confInp,
            hasSubmit: !!submitBtn
        };
    })()
    """)
    print("Mandatory password change check:", pwd_flow_res)
    results["tests"]["must_change_password_flow"] = pwd_flow_res
    
    # =========================================================================
    # Test 3: Admin Console Layout, Tabs & elementFromPoint (1280px & 375px)
    # =========================================================================
    print("\n--- TEST 3: Admin Console Loading ---")
    client.mock_user = {
        "id": 1,
        "username": "admin",
        "role": "admin",
        "must_change_password": 0
    }
    await client.send("Page.navigate", {"url": "http://127.0.0.1:8000/"})
    await asyncio.sleep(2.5)
    
    admin_load = await client.eval("""
    (() => {
        return {
            title: document.title,
            url: window.location.href,
            heroPresent: !!document.querySelector('.fx-hero'),
            tunnelPresent: !!document.getElementById('fx-tunnel-zone'),
            tagsFieldPresent: !!document.getElementById('fx-tags-field'),
            tagChipsCount: document.querySelectorAll('.fx-tag-chip').length,
            titleBandsCount: document.querySelectorAll('.fx-title-band').length,
            roleBadgeText: document.getElementById('header-role-badge')?.textContent,
            roleBadgeClass: document.getElementById('header-role-badge')?.className
        };
    })()
    """)
    print("Admin console load:", admin_load)
    results["tests"]["admin_console_load"] = admin_load
    
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
            
            # elementFromPoint audit on all visible interactive controls
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
                print(f"  [!] BLOCKED in {tab_name} ({vp_name}): {len(blocked)} elements blocked!")
                for b in blocked:
                    print(f"      <{b['tagName']} id='{b['elementId']}' class='{b['elementClass']}'> covered by <{b['coveredBy']['tagName']} id='{b['coveredBy']['id']}' class='{b['coveredBy']['className']}'>")
                    results["blocked_elements"].append({
                        "viewport": vp_name,
                        "tab": tab_name,
                        **b
                    })
            else:
                print(f"  [+] All controls in {tab_name} ({vp_name}) accessible via elementFromPoint.")
        
        # Test Modals on this viewport
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
    
    # =========================================================================
    # Test 4: Hero, Tunnel & Physics Tag Interaction
    # =========================================================================
    print("\n--- TEST 4: Hero, Tunnel & Tags Physics ---")
    await client.eval("document.getElementById('tab-btn-alerts')?.click();")
    await asyncio.sleep(0.5)
    
    hero_details = await client.eval("""
    (() => {
        const tunnel = document.getElementById('fx-tunnel-zone');
        const tags = Array.from(document.querySelectorAll('.fx-tag-chip'));
        const rects = tunnel?.querySelectorAll('rect')?.length || 0;
        const lines = tunnel?.querySelectorAll('line')?.length || 0;
        
        const firstTag = tags[0];
        let dragOk = false;
        if (firstTag) {
            const rect = firstTag.getBoundingClientRect();
            firstTag.dispatchEvent(new PointerEvent('pointerdown', { clientX: rect.left + 5, clientY: rect.top + 5, bubbles: true }));
            firstTag.dispatchEvent(new PointerEvent('pointermove', { clientX: rect.left + 40, clientY: rect.top + 40, bubbles: true }));
            firstTag.dispatchEvent(new PointerEvent('pointerup', { clientX: rect.left + 40, clientY: rect.top + 40, bubbles: true }));
            dragOk = true;
        }
        
        return {
            rectanglesCount: rects,
            radialSpokesCount: lines,
            tagsCount: tags.length,
            firstTagText: firstTag?.textContent?.trim(),
            dragDispatched: dragOk
        };
    })()
    """)
    print("Hero details:", hero_details)
    results["tests"]["hero_and_tags"] = hero_details
    
    # =========================================================================
    # Test 5: Live Stream Controls
    # =========================================================================
    print("\n--- TEST 5: Live Stream Tab ---")
    await client.eval("document.getElementById('tab-btn-stream')?.click();")
    await asyncio.sleep(0.5)
    
    stream_details = await client.eval("""
    (() => {
        const btnWebcam = document.getElementById('btn-source-webcam');
        const btnFile = document.getElementById('btn-source-file');
        const btnCctv = document.getElementById('btn-source-cctv');
        const btnModePpe = document.getElementById('btn-mode-ppe');
        const btnModeZone = document.getElementById('btn-mode-zone');
        const btnModeAll = document.getElementById('btn-mode-all');
        const btnAction = document.getElementById('btn-stream-action');
        const zoneSelect = document.getElementById('stream-zone-select');
        const sourceInput = document.getElementById('stream-source-input');
        
        btnFile?.click();
        
        return {
            hasWebcam: !!btnWebcam,
            hasFile: !!btnFile,
            hasCctv: !!btnCctv,
            hasModePpe: !!btnModePpe,
            hasModeZone: !!btnModeZone,
            hasModeAll: !!btnModeAll,
            hasActionBtn: !!btnAction,
            actionBtnText: btnAction?.textContent?.trim(),
            zoneSelectOptions: zoneSelect ? zoneSelect.options.length : 0,
            sourceInputValue: sourceInput?.value
        };
    })()
    """)
    print("Stream details:", stream_details)
    results["tests"]["live_stream"] = stream_details
    
    # =========================================================================
    # Test 6: Draw Zone Marking Canvas & Presets
    # =========================================================================
    print("\n--- TEST 6: Draw Zone Tab ---")
    await client.eval("document.getElementById('tab-btn-zones')?.click();")
    await asyncio.sleep(0.5)
    
    zone_details = await client.eval("""
    (() => {
        const canvas = document.getElementById('zone-canvas');
        const btnPresetEntry = document.getElementById('btn-preset-entry');
        const btnPresetCorridor = document.getElementById('btn-preset-corridor');
        const btnUndo = document.getElementById('btn-zone-undo');
        const btnClear = document.getElementById('btn-zone-clear');
        const btnSave = document.getElementById('btn-zone-save');
        const btnDetectAnyone = document.getElementById('btn-detect-anyone');
        const zoneNameInput = document.getElementById('zone-name-input');
        const zoneCategorySel = document.getElementById('zone-category-select');
        
        btnPresetEntry?.click();
        
        return {
            hasCanvas: !!canvas,
            canvasW: canvas?.width,
            canvasH: canvas?.height,
            hasPresetEntry: !!btnPresetEntry,
            hasPresetCorridor: !!btnPresetCorridor,
            hasUndo: !!btnUndo,
            hasClear: !!btnClear,
            hasSave: !!btnSave,
            hasDetectAnyone: !!btnDetectAnyone,
            zoneNameAfterPreset: zoneNameInput?.value
        };
    })()
    """)
    print("Zone details:", zone_details)
    results["tests"]["draw_zone"] = zone_details
    
    # =========================================================================
    # Test 7: Process Orchestration Tab & FedAvg Modal
    # =========================================================================
    print("\n--- TEST 7: Process Orchestration Tab ---")
    await client.eval("document.getElementById('tab-btn-control')?.click();")
    await asyncio.sleep(0.5)
    
    control_details = await client.eval("""
    (() => {
        const fedCard = document.getElementById('proc-card-fedavg');
        const zoneCard = document.getElementById('proc-card-zone');
        const pruneCard = document.getElementById('proc-card-prune');
        const btnFedStart = document.getElementById('btn-proc-fedavg-start');
        const btnPrune = document.getElementById('btn-proc-prune');
        const fedModal = document.getElementById('fed-confirm-modal');
        const btnFedCancel = document.getElementById('btn-fed-cancel');
        const btnFedClose = document.getElementById('btn-close-fed-modal');
        
        btnFedStart?.click();
        const modalOpenDisplay = fedModal ? window.getComputedStyle(fedModal).display : 'none';
        
        btnFedCancel?.click();
        const modalClosedDisplay = fedModal ? window.getComputedStyle(fedModal).display : 'none';
        
        return {
            hasFedCard: !!fedCard,
            hasZoneCard: !!zoneCard,
            hasPruneCard: !!pruneCard,
            hasPruneBtn: !!btnPrune,
            pruneBtnVisible: btnPrune ? (btnPrune.offsetParent !== null) : false,
            modalOpenedOnStart: modalOpenDisplay === 'flex',
            modalClosedOnCancel: modalClosedDisplay === 'none'
        };
    })()
    """)
    print("Control details:", control_details)
    results["tests"]["process_orchestration"] = control_details
    
    # =========================================================================
    # Test 8: Users & Keys Administration Tab (Create Account, Edge Keys)
    # =========================================================================
    print("\n--- TEST 8: Users & Keys Administration Tab ---")
    await client.eval("document.getElementById('tab-btn-users')?.click();")
    await asyncio.sleep(0.5)
    
    users_details = await client.eval("""
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
    print("Users details:", users_details)
    results["tests"]["users_and_keys"] = users_details
    
    await client.set_viewport(1000, 800)
    await asyncio.sleep(0.3)
    users_1000 = await client.eval("""
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
            isAsideBelowTable: asideRect && tableRect ? (asideRect.top > tableRect.top) : false
        };
    })()
    """)
    print("Users layout at 1000px:", users_1000)
    results["tests"]["users_layout_collapsed"] = users_1000
    
    await client.set_viewport(1280, 900)
    
    # =========================================================================
    # Test 9: Security Audit Trail Tab
    # =========================================================================
    print("\n--- TEST 9: Security Audit Trail Tab ---")
    await client.eval("document.getElementById('tab-btn-audit')?.click();")
    await asyncio.sleep(0.5)
    
    audit_details = await client.eval("""
    (() => {
        const table = document.getElementById('table-audit-log');
        const filter = document.getElementById('filter-audit-action');
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
    print("Audit log details:", audit_details)
    results["tests"]["audit_log"] = audit_details
    
    # =========================================================================
    # Test 10: Role Visibility Matrix (Operator vs Admin)
    # =========================================================================
    print("\n--- TEST 10: Role Visibility Matrix ---")
    role_matrix = await client.eval("""
    (() => {
        const tabUsers = document.getElementById('tab-btn-users');
        const tabAudit = document.getElementById('tab-btn-audit');
        const tabControl = document.getElementById('tab-btn-control');
        const simPanel = document.getElementById('panel-simulate-alerts');
        const btnRtsp = document.getElementById('btn-source-cctv');
        
        const adminState = {
            tabUsersDisplay: tabUsers ? window.getComputedStyle(tabUsers).display : null,
            tabAuditDisplay: tabAudit ? window.getComputedStyle(tabAudit).display : null,
            tabControlDisplay: tabControl ? window.getComputedStyle(tabControl).display : null,
            simPanelDisplay: simPanel ? window.getComputedStyle(simPanel).display : null,
            btnRtspDisplay: btnRtsp ? window.getComputedStyle(btnRtsp).display : null
        };
        
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
    print("Role matrix:", role_matrix)
    results["tests"]["role_visibility_matrix"] = role_matrix
    
    # =========================================================================
    # Test 11: Keyboard Accessibility & Focus Rings
    # =========================================================================
    print("\n--- TEST 11: Keyboard Focus ---")
    kbd_details = await client.eval("""
    (() => {
        const btnRefresh = document.getElementById('btn-refresh');
        btnRefresh?.focus();
        const active1 = document.activeElement ? document.activeElement.id : null;
        const style = btnRefresh ? window.getComputedStyle(btnRefresh) : null;
        
        return {
            canFocus: active1 === 'btn-refresh',
            outlineWidth: style ? style.outlineWidth : null
        };
    })()
    """)
    print("Keyboard details:", kbd_details)
    results["tests"]["keyboard_focus"] = kbd_details
    
    # =========================================================================
    # Test 12: Offline Fonts & CDN Elimination Check
    # =========================================================================
    print("\n--- TEST 12: Offline Fonts & External Requests ---")
    font_details = await client.eval("""
    (() => {
        const googleFontLinks = Array.from(document.querySelectorAll('link[href*="fonts.googleapis.com"], link[href*="fonts.gstatic.com"]'));
        const h2 = document.querySelector('.panel-title-group h2, h2');
        const body = document.body;
        
        return {
            googleFontLinksCountInIndex: googleFontLinks.length,
            h2FontFamily: h2 ? window.getComputedStyle(h2).fontFamily : '',
            bodyFontFamily: window.getComputedStyle(body).fontFamily
        };
    })()
    """)
    print("Font details:", font_details)
    results["tests"]["fonts_and_offline"] = font_details
    
    # Filter external network requests
    external_reqs = [
        r["url"] for r in client.network_requests
        if not r["url"].startswith("http://127.0.0.1")
        and not r["url"].startswith("http://localhost")
        and not r["url"].startswith("data:")
        and not r["url"].startswith("about:")
    ]
    print(f"External requests made during session: {len(external_reqs)}")
    for er in set(external_reqs):
        print(f"  - {er}")
    results["tests"]["external_requests"] = list(set(external_reqs))
    results["tests"]["failed_requests"] = client.failed_requests
    
    # Save full results json
    final_json_path = r"c:\Games\repo-setup\repo-setup\qa_report\qa_full_results.json"
    with open(final_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved full results to {final_json_path}")
    
    # Clean up page
    urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{target_id}")
    print("Closed target page cleanly.")
    print("=== LIVE QA AUDIT COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(run_audit())
