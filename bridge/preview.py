"""On-demand HLS from existing local RTSP; served through dashboard authentication."""
import asyncio
import re
from urllib.parse import urlsplit, parse_qsl, urlencode
from aiohttp import web, ClientTimeout, ClientError

PORT = 8898
ASSET = re.compile(r"[A-Za-z0-9_-]+\.(?:m3u8|mp4|ts)\Z")

def valid_query(key, value):
    return (key == 'session' and re.fullmatch(r'[A-Za-z0-9-]{1,80}',value)) or (key == 'cookieCheck' and value == '1')

async def start(manager, runtime):
    cameras = manager.config['cameras']
    config = runtime / 'preview.yml'
    content = ('logLevel: warn\nrtsp: false\nrtmp: false\nwebrtc: false\nsrt: false\nmoq: false\n'
               f'hls: true\nhlsAddress: 127.0.0.1:{PORT}\nhlsVariant: fmp4\n'
               'hlsAlwaysRemux: false\nhlsSegmentDuration: 1s\nhlsSegmentCount: 4\n'
               'hlsSegmentMaxSize: 8M\nhlsMuxerCloseAfter: 10s\npaths:\n')
    for cam in cameras:
        content += (f"  {cam['id']}:\n    source: rtsp://127.0.0.1:8554/{cam['path']}\n"
                    '    rtspTransport: tcp\n    sourceOnDemand: true\n    sourceOnDemandCloseAfter: 10s\n')
    if config.exists() and config.read_text(encoding='utf-8') != content:
        await manager.stop('preview')
    config.write_text(content, encoding='utf-8')
    if not await manager.port('127.0.0.1', PORT):
        manager.spawn('preview', [manager.runtime.get('mediamtx','mediamtx'),str(config)])
        for _ in range(30):
            if await manager.port('127.0.0.1', PORT):return
            await asyncio.sleep(.1)
        raise web.HTTPServiceUnavailable(text='Preview service could not start.')

def install(app, manager):
    async def media(request):
        cam=manager.camera(request.match_info['id'])
        asset=request.match_info['asset']
        if not ASSET.fullmatch(asset) or any(not valid_query(k,v) for k,v in request.query.items()):
            raise web.HTTPBadRequest(text='Invalid preview asset')
        # Fixed loopback destination and validated filenames: never an arbitrary URL proxy.
        try:
            async with manager.session.get(f"http://127.0.0.1:{PORT}/{cam['id']}/{asset}",
                    params=request.query,timeout=ClientTimeout(total=20),allow_redirects=False) as upstream:
                if upstream.status in (301,302,307,308):
                    location=urlsplit(upstream.headers.get('Location',''))
                    query=parse_qsl(location.query)
                    if (location.scheme or location.netloc or location.path not in (asset,f"/{cam['id']}/{asset}")
                            or not query or any(not valid_query(k,v) for k,v in query)):
                        raise web.HTTPBadGateway(text='Invalid preview redirect')
                    raise web.HTTPFound(location=f"/api/preview/{cam['id']}/{asset}?{urlencode(query)}")
                if upstream.status != 200:
                    raise web.HTTPServiceUnavailable(text='Waiting for local video')
                data=bytearray()
                async for chunk in upstream.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data)>8*1024*1024:raise web.HTTPBadGateway(text='Preview segment too large')
                return web.Response(body=data,content_type='application/vnd.apple.mpegurl' if asset.endswith('.m3u8') else 'video/mp4',headers={'Cache-Control':'no-store'})
        except (ClientError,asyncio.TimeoutError):
            raise web.HTTPServiceUnavailable(text='Waiting for local video') from None
    app.router.add_get('/api/preview/{id}/{asset}',media)
