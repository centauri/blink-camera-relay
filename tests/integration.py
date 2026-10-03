"""Real FFmpeg/RTSP test with simulated, fragmented IMMIS messages; no Blink login.

Set FFMPEG and MEDIAMTX_BIN to executable paths, then run this file from project root.
"""
import asyncio
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
import app
from immis import ReliableStream


async def wait_port(port):
    for _ in range(50):
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), .3)
            writer.close()
            await writer.wait_closed()
            return
        except (OSError, TimeoutError):
            await asyncio.sleep(0.1)
    raise RuntimeError("MediaMTX did not start")


class FakeTLSWriter:
    def __init__(self):
        self.closed = False
    def is_closing(self):
        return self.closed
    def close(self):
        self.closed = True


class SimulatedIMMIS(ReliableStream):
    async def auth(self):
        self.target_reader = asyncio.StreamReader()
        self.target_writer = FakeTLSWriter()
        self.encoder = await asyncio.create_subprocess_exec(
            os.environ["FFMPEG"], "-hide_banner", "-loglevel", "error", "-re",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=15",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-g", "15", "-f", "mpegts", "pipe:1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        self.pump_task = asyncio.create_task(self.pump())

    async def pump(self):
        while True:
            try:
                payload = await self.encoder.stdout.readexactly(188 * 7)
            except asyncio.IncompleteReadError:
                self.target_reader.feed_eof()
                return
            frame = b"\x00" + bytes(4) + len(payload).to_bytes(4, "big") + payload
            # Split inside both header and payload, as the network can do.
            for part in (frame[:3], frame[3:11], frame[11:211], frame[211:]):
                self.target_reader.feed_data(part)
                await asyncio.sleep(0)

    async def send(self):
        await asyncio.Future()

    async def poll(self):
        await asyncio.Future()

    async def close_fixture(self):
        self.pump_task.cancel()
        await asyncio.gather(self.pump_task, return_exceptions=True)
        await app.stop_process(self.encoder)


async def check_session():
    original = SimpleNamespace(camera=None, command_id=1, polling_interval=5,
                              target=urlparse("immis://fixture.invalid:443/test"))
    stream = SimulatedIMMIS(original)
    publisher = asyncio.create_task(app.publish(stream, max_seconds=30))
    consumer = None
    try:
        for _ in range(100):
            if app.HEALTH.exists() and json.loads(app.HEALTH.read_text()).get("streaming"):
                break
            if publisher.done():
                publisher.result()
                raise RuntimeError("Publisher ended before RTSP became ready")
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("No publishing progress")
        consumer = await asyncio.create_subprocess_exec(
            os.environ["FFMPEG"], "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", "tcp", "-i", app.rtsp_target(), "-frames:v", "90",
            "-map", "0:v:0", "-f", "framemd5", "pipe:1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(consumer.communicate(), 20)
        if consumer.returncode:
            raise RuntimeError(err.decode(errors="replace"))
        frames = [line for line in out.decode().splitlines() if line and not line.startswith("#")]
        assert len(frames) == 90, len(frames)
        hashes = {line.rsplit(",", 1)[-1].strip() for line in frames}
        assert len(hashes) > 60, "Stream is not changing"
        return {"decoded_frames": len(frames), "unique_frames": len(hashes)}
    finally:
        if consumer:
            await app.stop_process(consumer)
        publisher.cancel()
        await asyncio.gather(publisher, return_exceptions=True)
        if hasattr(stream, "encoder"):
            await stream.close_fixture()
        assert not json.loads(app.HEALTH.read_text())["streaming"]


async def main():
    os.environ["RTSP_BASE"] = "rtsp://127.0.0.1:18554"
    os.environ["RTSP_PATH"] = "integration"
    with tempfile.TemporaryDirectory() as directory:
        app.HEALTH = Path(directory) / "health.json"
        config = Path(directory) / "mediamtx.yml"
        config.write_text("rtspAddress: 127.0.0.1:18554\nrtspTransports: [tcp]\nrtmp: false\nhls: false\nwebrtc: false\nsrt: false\nmoq: false\npaths:\n  all_others:\n    source: publisher\n")
        mtx = await asyncio.create_subprocess_exec(os.environ["MEDIAMTX_BIN"], str(config),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await wait_port(18554)
            results = []
            for _ in range(2):
                results.append(await check_session())
                await asyncio.sleep(1)
            print(json.dumps({"simulated_immis_rtsp_sessions": results}, indent=2))
        finally:
            await app.stop_process(mtx)


if __name__ == "__main__":
    asyncio.run(main())
