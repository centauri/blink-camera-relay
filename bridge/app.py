"""Blink live view -> FFmpeg -> MediaMTX. No recorded clips are requested."""
import argparse
import asyncio
import contextlib
import getpass
import json
import logging
import os
from pathlib import Path
import re
import signal
import ssl
import sys
import time
import traceback
import tempfile
import telemetry

from aiohttp import ClientSession, ClientTimeout
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink
from blinkpy import api
from blinkpy.livestream import BlinkLiveStream
from immis import ReliableStream

LOG = logging.getLogger("bridge")
STATE = Path(os.getenv("BLINK_STATE", "/data/auth.json"))
HEALTH = Path(os.getenv("BRIDGE_HEALTH", "/tmp/bridge-health.json"))


class SetupRequired(Exception):
    pass


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(data, file)
    for attempt in range(21):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt == 20:
                raise
            # Windows readers/AV can briefly hold the old destination open.
            time.sleep(0.05)
    os.chmod(path, 0o600)


def save_auth(blink):
    atomic_json(STATE, blink.auth.login_attributes)


async def login(session, interactive=False):
    if STATE.exists():
        data = json.loads(STATE.read_text(encoding="utf-8"))
    elif interactive:
        credentials = Path(os.getenv("BLINK_CREDENTIALS_FILE", "/data/credentials.json"))
        data = json.loads(credentials.read_text()) if credentials.exists() else {}
        data["username"] = data.get("username") or input("Blink email: ").strip()
        data["password"] = data.get("password") or getpass.getpass("Blink password: ")
    else:
        raise SetupRequired("Run the interactive auth command first.")
    blink = Blink(session=session)
    blink.auth = Auth(data, no_prompt=True, session=session,
                      callback=lambda: save_auth(blink))
    try:
        ok = await blink.start()
    except BlinkTwoFARequiredError:
        if not interactive:
            raise SetupRequired("Blink needs 2FA again: stop bridge, then run auth.") from None
        code = getpass.getpass("Blink 2FA code (not saved): ").strip()
        ok = await blink.send_2fa_code(code)
    if not ok or not blink.available:
        raise SetupRequired("Blink login/setup failed; check credentials with auth.")
    save_auth(blink)
    return blink


def select_camera(cameras, name="", serial=""):
    if not name and not serial:
        raise SetupRequired("Set BLINK_CAMERA_NAME or BLINK_CAMERA_SERIAL after list.")
    matches = [cam for key, cam in cameras.items()
               if (not name or key.casefold() == name.casefold())
               and (not serial or cam.serial == serial)]
    if len(matches) != 1:
        raise SetupRequired("Camera selection must match exactly one camera; run list.")
    return matches[0]


def rtsp_target():
    path = os.getenv("RTSP_PATH", "blink-mini")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", path):
        raise SetupRequired("RTSP_PATH must contain only lowercase letters, digits, _ or -.")
    base = os.getenv("RTSP_BASE", "rtsp://mediamtx:8554")
    if not base.startswith("rtsp://"):
        raise SetupRequired("RTSP_BASE must start with rtsp://")
    return f"{base.rstrip('/')}/{path}"


def ffmpeg_command(source=None, test=False):
    command = [os.getenv("FFMPEG", "ffmpeg"), "-hide_banner", "-loglevel", "error",
               "-nostdin", "-nostats", "-progress", "pipe:1"]
    if test:
        command += ["-re", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=15"]
    else:
        command += ["-rw_timeout", "25000000", "-fflags", "+genpts+discardcorrupt",
                    "-analyzeduration", "1000000", "-probesize", "1048576",
                    "-f", "mpegts", "-i", source]
    # Normalize both cameras to a known ONVIF profile for the first milestone.
    # Audio is deliberately omitted until the real camera codec is inspected.
    # Keep one H.264 slice per frame: the two-slice stream decoded in FFmpeg,
    # but Protect showed a green lower half and iPhone playback was black.
    command += ["-map", "0:v:0", "-an", "-vf",
                "scale=1280:720:force_original_aspect_ratio=decrease,"
                "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=15",
                "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
                "-profile:v", "baseline", "-pix_fmt", "yuv420p", "-g", "30",
                "-keyint_min", "30", "-sc_threshold", "0", "-b:v", "2048k",
                "-maxrate", "2048k", "-bufsize", "4096k", "-threads", "1",
                "-x264-params", "sliced-threads=0:slices=1",
                "-f", "rtsp", "-rtsp_transport", "tcp", rtsp_target()]
    return command


async def progress(reader):
    previous = -1
    metrics = {}
    while line := await reader.readline():
        key, _, value = line.decode(errors="replace").strip().partition("=")
        if key in ("frame", "fps", "speed", "bitrate"):
            metrics[key] = value
        if key == "out_time_us":
            with contextlib.suppress(ValueError):
                current = int(value)
                if current > previous:
                    previous = current
                    atomic_json(HEALTH, {"streaming": True, "updated": time.time()})
                    now = time.time()
                    if telemetry.state.get("phase") != "streaming":
                        last = telemetry.state.get("last_frame_at")
                        telemetry.event("Local video is publishing", last_gap=round(now-last, 1) if last else None)
                    telemetry.update(phase="streaming", last_frame_at=now, output=metrics.copy())


async def watchdog(timeout=40):
    started = time.time()
    while True:
        await asyncio.sleep(2)
        updated = started
        if HEALTH.exists():
            state = json.loads(HEALTH.read_text())
            if state.get("streaming"):
                updated = state["updated"]
        if time.time() - updated > timeout:
            raise TimeoutError("FFmpeg stopped publishing frames")


async def stop_process(process):
    if process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


async def publish(stream=None, test=False, max_seconds=240):
    atomic_json(HEALTH, {"streaming": False, "updated": time.time()})
    process = None
    tasks = []
    try:
        if stream:
            await stream.start(host="127.0.0.1", port=0)
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_command(stream.url if stream else None, test),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        tasks = [asyncio.create_task(process.wait()),
                 asyncio.create_task(progress(process.stdout)),
                 asyncio.create_task(watchdog())]
        if stream:
            tasks.append(asyncio.create_task(stream.feed()))
        if max_seconds:
            tasks.append(asyncio.create_task(asyncio.sleep(max_seconds)))
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        # stdout EOF can win the race with process.wait(); collect its exit
        # status before deciding whether the encoder completed successfully.
        if tasks[1] in done and process.returncode is None:
            await asyncio.wait_for(process.wait(), 5)
        if process.returncode not in (None, 0):
            raise RuntimeError("FFmpeg exited with an error; check MediaMTX logs")
    finally:
        if stream:
            stream.stop()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if process:
            await stop_process(process)
        atomic_json(HEALTH, {"streaming": False, "updated": time.time()})


def next_failure_count(previous, elapsed):
    # A sustained live session is healthy even when Blink closes its socket.
    return 0 if elapsed >= 60 else previous + 1


def retry_delay(failures, elapsed):
    # Never request new live sessions more often than once per minute.
    interval = min(600, 60 * 2 ** min(failures, 4))
    return max(10, interval - elapsed)


async def open_live_session(camera):
    mode = os.getenv("BLINK_LIVEVIEW_MODE", "normal")
    if mode not in ("normal", "extended"):
        raise SetupRequired("BLINK_LIVEVIEW_MODE must be normal or extended")
    if mode == "extended":
        if camera.camera_type != "mini":
            raise SetupRequired("Extended mode is currently supported only for Mini cameras")
        blink = camera.sync.blink
        url = (f"{blink.urls.base_url}/api/v2/accounts/{blink.account_id}"
               f"/networks/{camera.sync.network_id}/owls/{camera.camera_id}/liveview")
        response = await api.http_post(blink, url, data=json.dumps({
            "intent": "extended_liveview", "motion_event_start_time": None}))
        await api.wait_for_command(blink, response)
    else:
        response = await api.request_camera_liveview(
            camera.sync.blink, camera.sync.network_id, camera.camera_id,
            camera_type=camera.camera_type)
    LOG.info("Requested Blink live-view mode: %s", mode)
    # Whitelist only duration metadata; never log URLs, tokens or identifiers.
    limits = {key: response[key] for key in ("duration", "extended_duration")
              if type(response.get(key)) in (int, float)}
    LOG.info("Blink duration metadata: %s", limits)
    if response.get("type") in ("lv", "elv", "liveview", "extended_liveview"):
        LOG.info("Blink returned stream type: %s", response["type"])
    if mode == "extended" and (response.get("type") == "lv" or
            (response.get("type") not in ("elv", "extended_liveview") and
             0 < limits.get("duration", float("inf")) <= 300)):
        LOG.warning("Blink did not grant extended mode; using the returned normal live-view session")
    if not response["server"].startswith("immis://"):
        raise NotImplementedError("Unsupported stream transport")
    stream = BlinkLiveStream(camera, response)
    telemetry.update(advertised_duration=limits.get("duration"),
                     granted_mode="extended" if response.get("type") in ("elv", "extended_liveview") else "normal",
                     requested_mode=mode)
    return stream


async def run(command):
    if command == "test":
        await publish(test=True, max_seconds=0)
        return
    async with ClientSession(timeout=ClientTimeout(total=45)) as session:
        blink = await login(session, interactive=command == "auth")
        if command in ("auth", "list"):
            for name, camera in blink.cameras.items():
                print(f"{name}\tserial={camera.serial}\ttype={camera.camera_type}")
            return
        camera = select_camera(blink.cameras, os.getenv("BLINK_CAMERA_NAME", ""),
                                os.getenv("BLINK_CAMERA_SERIAL", ""))
        rtsp_target()  # Validate before requesting any live view.
        max_seconds = int(os.getenv("SESSION_SECONDS", "0"))
        if max_seconds != 0 and not 30 <= max_seconds <= 3600:
            raise SetupRequired("SESSION_SECONDS must be 0 (no local cutoff) or 30..3600")
        failures = 0
        while True:
            started = time.monotonic()
            telemetry.event("Opening Blink live view", phase="connecting", retry_at=None,
                            incoming_bytes=0, incoming_mbps=0, incoming_at=None)
            try:
                original = await asyncio.wait_for(open_live_session(camera), 45)
                telemetry.event("Blink session opened", session_started=time.time(), sessions=telemetry.state["sessions"]+1)
                LOG.info("Live session opened; local cutoff: %s",
                         f"{max_seconds} seconds" if max_seconds else "disabled")
                await publish(ReliableStream(original), max_seconds=max_seconds)
                LOG.info("Live session finished after %.1f seconds", time.monotonic() - started)
                failures = next_failure_count(failures, time.monotonic() - started)
            except SetupRequired:
                raise
            except BlinkTwoFARequiredError:
                raise SetupRequired("Re-authentication required; run auth again.") from None
            except NotImplementedError:
                raise SetupRequired("Camera returned a non-IMMIS stream; model needs an adapter.") from None
            except Exception as error:
                # Avoid printing server URLs, tokens, or raw Blink API responses.
                if isinstance(error, ssl.SSLCertVerificationError):
                    message = ("Blink video server certificate verification failed. "
                               "Configure an independently verified BLINK_IMMIS_CERT_SHA256 fingerprint.")
                    LOG.warning(message)
                    telemetry.event(message)
                LOG.warning("Live session ended after %.1f seconds (%s)",
                            time.monotonic() - started, type(error).__name__)
                LOG.info("Failure location: %s", " -> ".join(
                    f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                    for frame in traceback.extract_tb(error.__traceback__)[-4:]))
                failures = next_failure_count(failures, time.monotonic() - started)
            finally:
                save_auth(blink)
            delay = retry_delay(failures, time.monotonic() - started)
            telemetry.event("Waiting to renew Blink session", phase="renewing", retry_at=time.time()+delay,
                            previous_session_seconds=round(time.monotonic()-started, 1))
            LOG.info("Starting a new live session in %.0f seconds", delay)
            await asyncio.sleep(delay)


async def watch_stop_file(task, path):
    while not path.exists():
        await asyncio.sleep(0.5)
    LOG.info("Graceful stop requested")
    task.cancel()


async def main_async(command):
    task = asyncio.create_task(run(command))
    stop_path = os.getenv("BRIDGE_STOP_FILE")
    stopper = (asyncio.create_task(watch_stop_file(task, Path(stop_path)))
               if command == "run" and stop_path else None)
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        telemetry.event("Worker stopped", phase="stopped")
        if stopper:
            stopper.cancel()
            await asyncio.gather(stopper, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["auth", "list", "run", "test", "health"])
    command = parser.parse_args().command
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # BlinkPy logs some API response bodies even at ERROR. Do not expose tokens.
    logging.getLogger("blinkpy").setLevel(logging.CRITICAL + 1)
    if command == "health":
        try:
            data = json.loads(HEALTH.read_text())
            return 0 if data.get("streaming") and time.time() - data["updated"] < 35 else 1
        except (OSError, ValueError):
            return 1
    try:
        asyncio.run(main_async(command))
        return 0
    except SetupRequired as error:
        telemetry.event(str(error), phase="error")
        LOG.error("%s", error)
        return 2
    except (KeyboardInterrupt, EOFError):
        return 1
    except Exception as error:
        telemetry.event(f"Worker stopped ({type(error).__name__}); check account and connectivity", phase="error")
        LOG.error("Stopped (%s); check configuration and connectivity", type(error).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
