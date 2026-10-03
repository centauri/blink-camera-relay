"""Local ONVIF/restream integration harness. Set FFMPEG and MEDIAMTX_BIN; compile vendor/onvif first."""
import asyncio,sys,os,json,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tests'))
sys.path.insert(0,str(root/'bridge'))
import app
from verify_onvif import verify,discover
from integration import wait_port

async def main():
    os.environ['RTSP_BASE']='rtsp://127.0.0.1:18554'
    os.environ['RTSP_PATH']='blink-mini-poc'
    with tempfile.TemporaryDirectory() as directory:
        app.HEALTH=Path(directory)/'health.json'
        conf=Path(directory)/'mediamtx.yml'
        conf.write_text('rtspAddress: 127.0.0.1:18554\nrtspTransports: [tcp]\nrtmp: false\nhls: false\nwebrtc: false\nsrt: false\nmoq: false\npaths:\n  all_others:\n    source: publisher\n')
        mtx=await asyncio.create_subprocess_exec(os.environ['MEDIAMTX_BIN'],str(conf),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        node=None
        restream=None
        publisher=None
        decoder=None
        try:
            await wait_port(18554)
            restream_env=dict(os.environ,MTX_RTSPADDRESS='127.0.0.1:28554',MTX_RTSPTRANSPORTS='tcp',MTX_RTMP='no',MTX_HLS='no',MTX_WEBRTC='no',MTX_SRT='no',MTX_PATHDEFAULTS_SOURCE=app.rtsp_target(),MTX_PATHDEFAULTS_RTSPTRANSPORT='tcp',MTX_PATHDEFAULTS_SOURCEONDEMAND='yes')
            restream=await asyncio.create_subprocess_exec(os.environ['MEDIAMTX_BIN'],str(root/'vendor/onvif/mediamtx.yml'),env=restream_env,cwd=directory,stdout=None,stderr=None)
            await wait_port(28554)
            advertised='rtsp://127.0.0.1:28554/blink-mini-poc'
            env=dict(os.environ,DISCOVERY_PORT='37020',MEDIAMTX_EXTERNAL='1',CAMERA_ID='blink-mini-poc',CAMERA_NAME='Blink Mini PoC',CAMERA_RTSP_URL=app.rtsp_target(),HOST_IP='127.0.0.1',RTSP_HOST='127.0.0.1',RTSP_STREAM_PORT='28554',CAMERA_PORT='18080',CAMERA_MAC='02:b1:1c:00:00:01',CAMERA_UUID='04dd6d1e-8ce4-4e81-b1ac-934d6c9b4a79')
            node=await asyncio.create_subprocess_exec('node',str(root/'vendor/onvif/dist/src/server.js'),env=env,stdout=None,stderr=None)
            await wait_port(18080)
            result=await asyncio.to_thread(verify,'http://127.0.0.1:18080',advertised)
            identity=await asyncio.to_thread(discover,'127.0.0.1',37020)
            assert identity=='urn:uuid:04dd6d1e-8ce4-4e81-b1ac-934d6c9b4a79',identity
            assert await asyncio.to_thread(discover,'127.0.0.1',37020)==identity
            result['unicast_discovery']='passed, stable configured UUID'
            publisher=asyncio.create_task(app.publish(test=True,max_seconds=30))
            for _ in range(100):
                if app.HEALTH.exists() and json.loads(app.HEALTH.read_text()).get('streaming'): break
                await asyncio.sleep(.1)
            decoder=await asyncio.create_subprocess_exec(os.environ['FFMPEG'],'-hide_banner','-loglevel','error','-rtsp_transport','tcp','-i',result['rtsp_uri'],'-t','4','-f','framemd5','pipe:1',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            out,err=await asyncio.wait_for(decoder.communicate(),15)
            assert decoder.returncode==0,err.decode(errors='replace')
            frames=[x for x in out.decode().splitlines() if x and not x.startswith('#')]
            assert len(frames)>=45,len(frames)
            result['decoded_frames_from_advertised_uri']=len(frames)
            print(json.dumps(result,indent=2))
        finally:
            if publisher:
                publisher.cancel()
                await asyncio.gather(publisher,return_exceptions=True)
            for process in (decoder,node,restream,mtx):
                if process: await app.stop_process(process)

asyncio.run(main())




