import asyncio
import json
import base64
import urllib.request
import websockets

async def test():
    req = urllib.request.Request('http://127.0.0.1:9222/json/new?about:blank', method='PUT')
    with urllib.request.urlopen(req) as r:
        info = json.loads(r.read().decode())
    target_id = info['id']
    ws = await websockets.connect(info['webSocketDebuggerUrl'])
    
    # Enable Fetch
    await ws.send(json.dumps({'id': 1, 'method': 'Fetch.enable', 'params': {'patterns': [{'urlPattern': '*auth/me*'}]}}))
    await ws.send(json.dumps({'id': 2, 'method': 'Page.enable'}))
    await ws.send(json.dumps({'id': 3, 'method': 'Runtime.enable'}))
    
    async def handler():
        try:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get('method') == 'Fetch.requestPaused':
                    rid = msg['params']['requestId']
                    body = json.dumps({'user': {'id': 1, 'username': 'admin', 'role': 'admin', 'must_change_password': 0}, 'csrf_token': 'mock'}).encode()
                    b64 = base64.b64encode(body).decode()
                    await ws.send(json.dumps({
                        'id': 100,
                        'method': 'Fetch.fulfillRequest',
                        'params': {
                            'requestId': rid,
                            'responseCode': 200,
                            'responseHeaders': [{'name': 'Content-Type', 'value': 'application/json'}],
                            'body': b64
                        }
                    }))
        except Exception:
            pass

    t = asyncio.create_task(handler())
    await ws.send(json.dumps({'id': 4, 'method': 'Page.navigate', 'params': {'url': 'http://127.0.0.1:8000/'}}))
    await asyncio.sleep(2.0)
    
    # Check URL and tabs
    await ws.send(json.dumps({
        'id': 5,
        'method': 'Runtime.evaluate',
        'params': {
            'expression': 'JSON.stringify({url: location.href, hasHero: !!document.querySelector(".fx-hero"), hasUsersTab: !!document.getElementById("tab-users"), title: document.title})',
            'returnByValue': True
        }
    }))
    
    for _ in range(30):
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get('id') == 5:
            print('Result:', msg.get('result', {}).get('result', {}).get('value'))
            break
            
    t.cancel()
    await ws.close()
    urllib.request.urlopen(f'http://127.0.0.1:9222/json/close/{target_id}')

asyncio.run(test())

