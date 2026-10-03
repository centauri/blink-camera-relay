import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
import preview
import web as dashboard
from aiohttp import web, ClientSession
from aiohttp.test_utils import TestClient, TestServer

def test_preview_config_uses_only_existing_local_rtsp(tmp_path):
    manager=SimpleNamespace(config={'cameras':[{'id':'garden','path':'camera'}]},runtime={},
        stop=AsyncMock(),port=AsyncMock(side_effect=[False,True]),spawn=Mock())
    asyncio.run(preview.start(manager,tmp_path))
    config=(tmp_path/'preview.yml').read_text()
    assert 'source: rtsp://127.0.0.1:8554/camera' in config
    assert 'hlsAddress: 127.0.0.1:8898' in config
    assert 'sourceOnDemand: true' in config
    assert 'hlsAlwaysRemux: false' in config
    assert manager.spawn.call_count==1

def test_preview_proxy_preserves_segment_bytes_and_rejects_bad_assets(monkeypatch):
    async def check():
        async def segment(request):return web.Response(body=b'video-data'*20000)
        async def playlist(request):
            if not request.query.get('cookieCheck'):
                raise web.HTTPFound('/garden/index.m3u8?cookieCheck=1')
            return web.Response(text='#EXTM3U\nsegment.mp4?session=demo-123\n')
        upstream=web.Application();upstream.router.add_get('/garden/segment.mp4',segment)
        upstream.router.add_get('/garden/index.m3u8',playlist)
        async with TestServer(upstream) as server, ClientSession() as session:
            monkeypatch.setattr(preview,'PORT',server.port)
            app=web.Application()
            preview.install(app,SimpleNamespace(camera=lambda key:{'id':'garden'},session=session))
            async with TestClient(TestServer(app)) as client:
                response=await client.get('/api/preview/garden/segment.mp4')
                assert response.status==200
                assert await response.read()==b'video-data'*20000
                response=await client.get('/api/preview/garden/index.m3u8')
                assert response.status==200
                assert 'session=demo-123' in await response.text()
                assert (await client.get('/api/preview/garden/segment.mp4?session=demo-123')).status==200
                for path in ('config.yml','index.m3u8?url=http://example.com','bad.name.mp4'):
                    assert (await client.get('/api/preview/garden/'+path)).status==400
    asyncio.run(check())

def test_preview_respects_dashboard_login_and_csrf(tmp_path,monkeypatch):
    monkeypatch.setattr(dashboard,'DATA',tmp_path/'data')
    monkeypatch.setattr(dashboard,'RUNTIME',tmp_path/'runtime')
    monkeypatch.setattr(dashboard,'CONTAINER',True)
    monkeypatch.setenv('BRIDGE_ADMIN_PASSWORD','test-password-long')
    async def check():
        async with TestClient(TestServer(dashboard.create_app())) as client:
            assert (await client.get('/api/preview/garden/index.m3u8')).status==401
            assert (await client.post('/api/preview-start',json={'id':'garden'})).status==401
    asyncio.run(check())
