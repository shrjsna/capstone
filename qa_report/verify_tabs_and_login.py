import asyncio
import json
import urllib.request
import websockets
import base64

async def run_verification():
    print("=" * 60)
    print("AEGIS CONSOLE RESTYLE: TAB FIX & LOGIN VERIFICATION")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # PART 1: Admin session - Tab switching, single tab display, scroll height
    # -------------------------------------------------------------------------
    req = urllib.request.Request('http://127.0.0.1:9222/json/new?http://127.0.0.1:8000/', method='PUT')
    with urllib.request.urlopen(req) as r:
        info = json.loads(r.read().decode())
    target_id = info['id']
    ws = await websockets.connect(info['webSocketDebuggerUrl'])

    responses = {}

    await ws.send(json.dumps({'id': 1, 'method': 'Page.enable'}))
    await ws.send(json.dumps({'id': 2, 'method': 'Runtime.enable'}))
    await ws.send(json.dumps({'id': 3, 'method': 'Fetch.enable', 'params': {'patterns': [{'urlPattern': '*'}]}}))

    async def listener():
        try:
            async for raw in ws:
                m = json.loads(raw)
                if 'id' in m:
                    responses[m['id']] = m
                elif m.get('method') == 'Fetch.requestPaused':
                    rid = m['params']['requestId']
                    url = m['params']['request']['url']
                    if '/auth/me' in url:
                        b = json.dumps({'user': {'id':1,'username':'admin','role':'admin','must_change_password':0},'csrf_token':'t'}).encode()
                    elif '/admin/audit-log' in url:
                        b = json.dumps({'items':[],'total':0,'page':1,'pages':1}).encode()
                    else:
                        b = b'[]'
                    await ws.send(json.dumps({
                        'id': 99,
                        'method': 'Fetch.fulfillRequest',
                        'params': {
                            'requestId': rid,
                            'responseCode': 200,
                            'responseHeaders': [{'name': 'Content-Type', 'value': 'application/json'}],
                            'body': base64.b64encode(b).decode()
                        }
                    }))
        except Exception:
            pass

    t = asyncio.create_task(listener())
    await asyncio.sleep(2.0)

    results = {}

    tabs = [
        ('alerts', 'Alert Feed', 'tab-alerts'),
        ('stream', 'Live Stream', 'tab-stream'),
        ('zones', 'Draw Zone', 'tab-zones'),
        ('control', 'Control Panel', 'tab-control'),
        ('users', 'Users & Keys', 'tab-users'),
        ('audit', 'Audit Log', 'tab-audit')
    ]

    all_tabs_single = True
    tab_heights = {}

    for idx, (tab_key, tab_name, tab_id) in enumerate(tabs, 10):
        eval_code = f"""
            (() => {{
                const btn = document.querySelector('.tab-btn[data-tab="{tab_key}"]');
                if (!btn) return {{ error: 'btn not found for {tab_key}' }};
                btn.click();
                const allTabs = Array.from(document.querySelectorAll('.tab-content'));
                const displays = {{}};
                let nonNone = 0;
                let activeId = null;
                allTabs.forEach(t => {{
                    const d = window.getComputedStyle(t).display;
                    displays[t.id] = d;
                    if (d !== 'none') {{
                        nonNone++;
                        activeId = t.id;
                    }}
                }});
                const scrollH = document.documentElement.scrollHeight;
                const clientH = document.documentElement.clientHeight;
                return {{ tab: '{tab_key}', tabId: '{tab_id}', nonNone, activeId, displays, scrollH, clientH }};
            }})()
        """
        await ws.send(json.dumps({'id': idx, 'method': 'Runtime.evaluate', 'params': {'expression': eval_code, 'returnByValue': True}}))
        for _ in range(50):
            if idx in responses:
                res = responses.pop(idx)['result']['result']['value']
                tab_heights[tab_key] = res.get('scrollH')
                single_ok = (res.get('nonNone') == 1 and res.get('activeId') == tab_id)
                if not single_ok:
                    all_tabs_single = False
                disp = res.get('displays', {}).get(tab_id)
                print(f"[{'PASS' if single_ok else 'FAIL'}] {tab_name} ({tab_id}): display={disp}, non-none tabs={res.get('nonNone')}, page height={res.get('scrollH')}px")
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.15)

    results['tab_switching_single_display'] = all_tabs_single

    # -------------------------------------------------------------------------
    # PART 2: Tunnel & tag animation behavior on Alert Feed vs other tabs
    # -------------------------------------------------------------------------
    # Switch to alerts tab
    await ws.send(json.dumps({'id': 30, 'method': 'Runtime.evaluate', 'params': {
        'expression': """
            (() => {
                document.querySelector('.tab-btn[data-tab="alerts"]').click();
                const hero = document.querySelector('.fx-hero');
                if (hero) hero.dispatchEvent(new PointerEvent('pointermove', { clientX: 380, clientY: 260 }));
            })()
        """
    }}))
    await asyncio.sleep(0.4)

    # Read rect x
    await ws.send(json.dumps({'id': 31, 'method': 'Runtime.evaluate', 'params': {
        'expression': "document.querySelector('#fx-tunnel-rects rect')?.getAttribute('x')",
        'returnByValue': True
    }}))
    for _ in range(50):
        if 31 in responses:
            x_alerts_1 = responses.pop(31)['result']['result'].get('value')
            break
        await asyncio.sleep(0.05)

    await asyncio.sleep(0.2)
    await ws.send(json.dumps({'id': 32, 'method': 'Runtime.evaluate', 'params': {
        'expression': "document.querySelector('#fx-tunnel-rects rect')?.getAttribute('x')",
        'returnByValue': True
    }}))
    for _ in range(50):
        if 32 in responses:
            x_alerts_2 = responses.pop(32)['result']['result'].get('value')
            break
        await asyncio.sleep(0.05)

    print(f"Hero tunnel on Alert Feed (spring motion): x_start={x_alerts_1}, x_next={x_alerts_2}")

    # Now switch to Live Stream tab
    await ws.send(json.dumps({'id': 33, 'method': 'Runtime.evaluate', 'params': {
        'expression': "document.querySelector('.tab-btn[data-tab=\"stream\"]').click()",
    }}))
    await asyncio.sleep(0.4)

    # Check tunnel rect position on inactive alerts tab
    await ws.send(json.dumps({'id': 34, 'method': 'Runtime.evaluate', 'params': {
        'expression': "document.querySelector('#fx-tunnel-rects rect')?.getAttribute('x')",
        'returnByValue': True
    }}))
    for _ in range(50):
        if 34 in responses:
            x_stream_1 = responses.pop(34)['result']['result'].get('value')
            break
        await asyncio.sleep(0.05)

    await asyncio.sleep(0.3)
    await ws.send(json.dumps({'id': 35, 'method': 'Runtime.evaluate', 'params': {
        'expression': "document.querySelector('#fx-tunnel-rects rect')?.getAttribute('x')",
        'returnByValue': True
    }}))
    for _ in range(50):
        if 35 in responses:
            x_stream_2 = responses.pop(35)['result']['result'].get('value')
            break
        await asyncio.sleep(0.05)

    print(f"Hero tunnel on Live Stream (alerts tab inactive): x_start={x_stream_1}, x_next={x_stream_2}")
    tunnel_stopped_when_inactive = (x_stream_1 == x_stream_2)
    print(f"[{'PASS' if tunnel_stopped_when_inactive else 'FAIL'}] Hero tunnel animation pauses on non-alert tabs: {tunnel_stopped_when_inactive}")
    results['tunnel_animation_paused_on_other_tabs'] = tunnel_stopped_when_inactive

    # -------------------------------------------------------------------------
    # PART 3: Users & Keys - Create New Account form visible without scrolling past other tabs
    # -------------------------------------------------------------------------
    await ws.send(json.dumps({'id': 36, 'method': 'Runtime.evaluate', 'params': {
        'expression': """
            (() => {
                document.querySelector('.tab-btn[data-tab="users"]').click();
                const form = document.getElementById('form-create-user');
                const sidebar = document.querySelector('#tab-users .sidebar-panel');
                const titleBand = document.querySelector('#tab-users .fx-title-band');
                const formRect = form ? form.getBoundingClientRect() : null;
                const sidebarRect = sidebar ? sidebar.getBoundingClientRect() : null;
                const scrollY = window.scrollY;
                return {
                    formFound: !!form,
                    formTop: formRect ? formRect.top : null,
                    sidebarTop: sidebarRect ? sidebarRect.top : null,
                    scrollY
                };
            })()
        """,
        'returnByValue': True
    }}))
    for _ in range(50):
        if 36 in responses:
            users_res = responses.pop(36)['result']['result'].get('value')
            break
        await asyncio.sleep(0.05)

    form_near_top = users_res.get('formFound') and users_res.get('formTop', 9999) < 600 and users_res.get('scrollY') == 0
    print(f"[{'PASS' if form_near_top else 'FAIL'}] Users & Keys Create New Account form visible near top: top={users_res.get('formTop')}px, scrollY={users_res.get('scrollY')}")
    results['create_account_form_visible_near_top'] = form_near_top

    # Close admin tab
    t.cancel()
    await ws.close()
    try:
        urllib.request.urlopen(f'http://127.0.0.1:9222/json/close/{target_id}')
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # PART 4: Operator login - Users & Keys and Audit Log buttons stay hidden
    # -------------------------------------------------------------------------
    req = urllib.request.Request('http://127.0.0.1:9222/json/new?http://127.0.0.1:8000/', method='PUT')
    with urllib.request.urlopen(req) as r:
        info = json.loads(r.read().decode())
    target_id = info['id']
    ws = await websockets.connect(info['webSocketDebuggerUrl'])
    responses = {}

    await ws.send(json.dumps({'id': 1, 'method': 'Page.enable'}))
    await ws.send(json.dumps({'id': 2, 'method': 'Runtime.enable'}))
    await ws.send(json.dumps({'id': 3, 'method': 'Fetch.enable', 'params': {'patterns': [{'urlPattern': '*'}]}}))

    async def op_listener():
        try:
            async for raw in ws:
                m = json.loads(raw)
                if 'id' in m:
                    responses[m['id']] = m
                elif m.get('method') == 'Fetch.requestPaused':
                    rid = m['params']['requestId']
                    url = m['params']['request']['url']
                    if '/auth/me' in url:
                        b = json.dumps({'user': {'id':2,'username':'operator','role':'operator','must_change_password':0},'csrf_token':'t'}).encode()
                    else:
                        b = b'[]'
                    await ws.send(json.dumps({
                        'id': 99,
                        'method': 'Fetch.fulfillRequest',
                        'params': {
                            'requestId': rid,
                            'responseCode': 200,
                            'responseHeaders': [{'name': 'Content-Type', 'value': 'application/json'}],
                            'body': base64.b64encode(b).decode()
                        }
                    }))
        except Exception:
            pass

    t = asyncio.create_task(op_listener())
    await asyncio.sleep(2.0)

    await ws.send(json.dumps({'id': 40, 'method': 'Runtime.evaluate', 'params': {
        'expression': """
            (() => {
                const btnUsers = document.getElementById('tab-btn-users');
                const btnAudit = document.getElementById('tab-btn-audit');
                const btnControl = document.getElementById('tab-btn-control');
                return {
                    btnUsersDisplay: btnUsers ? window.getComputedStyle(btnUsers).display : null,
                    btnAuditDisplay: btnAudit ? window.getComputedStyle(btnAudit).display : null,
                    btnControlDisplay: btnControl ? window.getComputedStyle(btnControl).display : null
                };
            })()
        """,
        'returnByValue': True
    }}))
    for _ in range(50):
        if 40 in responses:
            op_res = responses.pop(40)['result']['result'].get('value')
            break
        await asyncio.sleep(0.05)

    op_hidden = (
        op_res.get('btnUsersDisplay') == 'none' and
        op_res.get('btnAuditDisplay') == 'none' and
        op_res.get('btnControlDisplay') == 'none'
    )
    print(f"[{'PASS' if op_hidden else 'FAIL'}] Operator role tab buttons hidden: Users={op_res.get('btnUsersDisplay')}, Audit={op_res.get('btnAuditDisplay')}, Control={op_res.get('btnControlDisplay')}")
    results['operator_buttons_hidden'] = op_hidden

    t.cancel()
    await ws.close()
    try:
        urllib.request.urlopen(f'http://127.0.0.1:9222/json/close/{target_id}')
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # PART 5: login.html loads with NO requests to fonts.googleapis.com
    # -------------------------------------------------------------------------
    req = urllib.request.Request('http://127.0.0.1:9222/json/new?http://127.0.0.1:8000/login.html', method='PUT')
    with urllib.request.urlopen(req) as r:
        info = json.loads(r.read().decode())
    target_id = info['id']
    ws = await websockets.connect(info['webSocketDebuggerUrl'])
    responses = {}
    external_font_requests = []

    await ws.send(json.dumps({'id': 1, 'method': 'Page.enable'}))
    await ws.send(json.dumps({'id': 2, 'method': 'Runtime.enable'}))
    await ws.send(json.dumps({'id': 3, 'method': 'Network.enable'}))

    async def login_listener():
        try:
            async for raw in ws:
                m = json.loads(raw)
                if 'id' in m:
                    responses[m['id']] = m
                elif m.get('method') == 'Network.requestWillBeSent':
                    u = m.get('params', {}).get('request', {}).get('url', '')
                    if 'fonts.googleapis.com' in u or 'fonts.gstatic.com' in u:
                        external_font_requests.append(u)
        except Exception:
            pass

    t = asyncio.create_task(login_listener())
    await asyncio.sleep(2.0)

    await ws.send(json.dumps({'id': 50, 'method': 'Runtime.evaluate', 'params': {
        'expression': """
            (() => {
                const title = document.querySelector('.login-brand-title');
                const body = document.body;
                return {
                    titleFont: title ? window.getComputedStyle(title).fontFamily : null,
                    bodyFont: body ? window.getComputedStyle(body).fontFamily : null
                };
            })()
        """,
        'returnByValue': True
    }}))
    for _ in range(50):
        if 50 in responses:
            font_res = responses.pop(50)['result']['result'].get('value')
            break
        await asyncio.sleep(0.05)

    no_google_fonts = len(external_font_requests) == 0
    print(f"[{'PASS' if no_google_fonts else 'FAIL'}] login.html external font requests: {external_font_requests} (count={len(external_font_requests)})")
    print(f"           login.html body computed font: {font_res.get('bodyFont')}")
    results['login_no_google_fonts'] = no_google_fonts

    t.cancel()
    await ws.close()
    try:
        urllib.request.urlopen(f'http://127.0.0.1:9222/json/close/{target_id}')
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------
    print("=" * 60)
    print("FINAL SUMMARY:")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    all_pass = all(results.values())
    print(f"OVERALL STATUS: {'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(run_verification())
