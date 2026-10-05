"""Loopback-only management UI for the native bridge.

No cloud credentials, cloud media URLs, or raw cloud errors leave this server.
Workers outlive the UI so closing the dashboard does not stop Protect.
"""
import asyncio
import base64
import contextlib
import ctypes
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid

from aiohttp import web, ClientSession, ClientTimeout
from blinkpy.auth import Auth, BlinkTwoFARequiredError
from blinkpy.blinkpy import Blink
from app import atomic_json
import camera_settings
import preview
from blinkpy import api

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = os.getenv("BRIDGE_CONTAINER") == "1"
if CONTAINER:os.umask(0o077)
RUNTIME = Path(os.getenv("BRIDGE_RUNTIME", str(ROOT / ".runtime")))
DATA = Path(os.getenv("BRIDGE_DATA", str(ROOT / "data")))
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class InputError(ValueError):
    """A user-facing message authored by this application, never a cloud error."""


def immis_certificate_pin():
    """Prefer explicit configuration, then persistent data, then legacy runtime."""
    pin = os.getenv("BLINK_IMMIS_CERT_SHA256", "").strip()
    if not pin:
        for directory in (DATA, RUNTIME):
            path = directory / "immis-cert.sha256"
            if path.exists():
                pin = path.read_text(encoding="utf-8-sig").strip()
                if not pin:
                    raise InputError("IMMIS certificate fingerprint file is empty.")
                break
    pin = pin.lower().replace(":", "")
    if pin and not re.fullmatch(r"[0-9a-f]{64}", pin):
        raise InputError("IMMIS certificate fingerprint must contain 64 hexadecimal characters.")
    return pin


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default if default is not None else {}


def alive(pid):
    if not pid:
        return False
    if sys.platform == "win32":
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        return not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def validate_camera(value, existing):
    name = str(value.get("name", "")).strip()
    path = str(value.get("path", ""))
    if not name or len(name) > 80 or not SLUG.fullmatch(path):
        raise InputError("Enter a camera name and a lowercase RTSP path (letters, digits, - or _).")
    mode = value.get("mode", "normal")
    if mode not in ("normal", "extended"):
        raise InputError("Choose normal or extended live view.")
    port = int(value.get("onvif_port", 8080))
    if not 1024 <= port <= 65535 or port in (8554, 8555, 8787, 8898):
        raise InputError("Choose an unused ONVIF port between 1024 and 65535.")
    camera_id = existing.get("id") or uuid.uuid4().hex[:12]
    return {"id": camera_id, "name": name, "serial": str(value.get("serial", ""))[:100],
            "path": path, "mode": mode, "onvif_port": port,
            "uuid": existing.get("uuid") or str(uuid.uuid4()),
            "mac": existing.get("mac") or "02:" + ":".join(secrets.token_hex(1) for _ in range(5)),
            "discovery": bool(value.get("discovery", False)),
            "autostart": existing.get("autostart",False), "onvif_autostart": existing.get("onvif_autostart",False)}


class Manager:
    def __init__(self):
        RUNTIME.mkdir(parents=True,exist_ok=True)
        DATA.mkdir(parents=True,exist_ok=True)
        self.config = read_json(DATA / "ui.json", {"host": os.getenv("BRIDGE_HOST", "127.0.0.1"), "cameras": []})
        self.runtime = read_json(RUNTIME / "ui-runtime.json")
        self.processes = {} if CONTAINER else read_json(RUNTIME / "ui-processes.json")
        self.csrf = secrets.token_urlsafe(32)
        self.lock = asyncio.Lock()
        self.session = None
        self.blink = None
        self.pending = None
        self.pending_at = 0
        self.account_status = "saved" if (DATA / "auth.json").exists() else "disconnected"
        self.catalog = []
        self.catalog_at = None
        self.extended_entitlement = "unknown"
        self.account_message = "Saved account available; refresh cameras to connect."
        self.children = []
        self.device_settings = {}
        self.verified_settings = {}

    def save(self):
        atomic_json(DATA / "ui.json", self.config)
        atomic_json(RUNTIME / "ui-processes.json", self.processes)

    def camera(self, camera_id):
        for camera in self.config["cameras"]:
            if camera["id"] == camera_id:
                return camera
        raise InputError("Camera not found.")

    def spawn(self, key, args, env=None):
        if alive(self.processes.get(key, {}).get("pid")):
            raise InputError("This service is already running.")
        with (RUNTIME / (key + ".log")).open("ab") as log:
            process = subprocess.Popen(args, cwd=RUNTIME, env=env or os.environ.copy(),
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=FLAGS)
        self.children = [p for p in self.children if p.poll() is None] + [process]
        self.processes[key] = {"pid": process.pid, "needle": str(args[1]), "started": time.time()}
        self.save()
        return process

    async def owned(self, record):
        if not alive(record.get("pid")):
            return False
        if sys.platform == "win32":
            command = f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {int(record['pid'])}').CommandLine"
            proc = await asyncio.create_subprocess_exec("powershell", "-NoProfile", "-Command", command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, creationflags=FLAGS)
            out, _ = await asyncio.wait_for(proc.communicate(), 10)
            cmdline = out.decode(errors="replace").replace("\\", "/").lower()
        else:
            cmdline = Path(f"/proc/{record['pid']}/cmdline").read_text().replace("\0", " ").lower()
        needle = record.get("needle", "").replace("\\", "/").lower()
        if not needle or needle not in cmdline:
            raise InputError("Process identity changed. No process was stopped; restart the dashboard to inspect.")
        return True

    async def stop(self, key, graceful=False):
        record = self.processes.get(key, {})
        if await self.owned(record):
            if graceful:
                Path(record["stop_file"]).touch()
                for _ in range(80):
                    if not alive(record["pid"]):
                        break
                    await asyncio.sleep(.5)
                else:
                    raise InputError("The worker is still cleaning up. Wait a moment and try again.")
            else:
                if sys.platform == "win32":
                    proc = await asyncio.create_subprocess_exec("taskkill", "/PID", str(record["pid"]), "/T", "/F",
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, creationflags=FLAGS)
                    await proc.wait()
                else:
                    os.kill(record["pid"], 15)
                await asyncio.sleep(.5)
        self.processes.pop(key, None)
        self.save()

    async def port(self, host, port):
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 1)
            writer.close()
            await writer.wait_closed()
            return True
        except (OSError, asyncio.TimeoutError):
            return False

    async def infrastructure(self, lan=False):
        host, port = (self.config["host"], 8555) if lan else ("127.0.0.1", 8554)
        key = "onvif-rtsp" if lan else "mediamtx"
        config = RUNTIME / ("mediamtx-onvif.yml" if lan else "mediamtx-local.yml")
        content = f"logLevel: info\nrtspAddress: {host}:{port}\nrtspTransports: [tcp]\nrtmp: false\nhls: false\nwebrtc: false\nsrt: false\nmoq: false\npaths:\n"
        if lan:
            for cam in self.config["cameras"]:
                content += f"  {cam['id']}:\n    source: rtsp://127.0.0.1:8554/{cam['path']}\n    rtspTransport: tcp\n    sourceOnDemand: yes\n"
        else:
            content += "  all_others:\n    source: publisher\n    overridePublisher: false\n"
        if not config.exists() or config.read_text() != content:
            config.write_text(content, encoding="utf-8")
        if not await self.port(host, port):
            self.spawn(key, [self.runtime.get("mediamtx", "mediamtx"), str(config)])
            for _ in range(30):
                if await self.port(host, port):
                    break
                await asyncio.sleep(.1)
            else:
                raise InputError("MediaMTX did not start. Check its executable in runtime settings.")

    async def start_camera(self, camera):
        key = "source-" + camera["id"]
        if alive(self.processes.get(key, {}).get("pid")):
            raise InputError("Camera is already running.")
        if not (DATA / "auth.json").exists():
            raise InputError("Connect your Blink account first.")
        pin = immis_certificate_pin()
        await self.infrastructure()
        stop = RUNTIME / (key + ".stop")
        stop.unlink(missing_ok=True)
        telemetry = RUNTIME / (key + ".json")
        atomic_json(telemetry, {"phase": "starting", "updated": time.time()})
        env = dict(os.environ, BLINK_STATE=str(DATA / "auth.json"), BLINK_CAMERA_NAME=camera["name"],
                   BLINK_CAMERA_SERIAL=camera["serial"], RTSP_BASE="rtsp://127.0.0.1:8554",
                   RTSP_PATH=camera["path"], BLINK_LIVEVIEW_MODE=camera["mode"], SESSION_SECONDS="0",
                   BRIDGE_STOP_FILE=str(stop), BRIDGE_HEALTH=str(RUNTIME / (key + "-health.json")),
                   BRIDGE_TELEMETRY=str(telemetry), FFMPEG=self.runtime.get("ffmpeg", "ffmpeg"))
        env["BLINK_IMMIS_CERT_SHA256"] = pin
        self.spawn(key, [sys.executable, str(ROOT / "bridge/app.py"), "run"], env)
        self.processes[key]["stop_file"] = str(stop)
        self.processes[key]["health"] = env["BRIDGE_HEALTH"]
        self.save()

    async def start_onvif(self, camera):
        await self.infrastructure(lan=True)
        key = "onvif-" + camera["id"]
        if alive(self.processes.get(key, {}).get("pid")):
            return
        env = dict(os.environ, MEDIAMTX_EXTERNAL="1", DISCOVERY_ENABLED=str(camera["discovery"]).lower(),
                   CAMERA_ID=camera["id"], CAMERA_NAME=camera["name"],
                   CAMERA_RTSP_URL=f"rtsp://127.0.0.1:8554/{camera['path']}",
                   HOST_IP=self.config["host"], RTSP_HOST=self.config["host"], RTSP_STREAM_PORT="8555",
                   CAMERA_PORT=str(camera["onvif_port"]), CAMERA_MAC=camera["mac"], CAMERA_UUID=camera["uuid"])
        self.spawn(key, [self.runtime.get("node", "node"), str(ROOT / "vendor/onvif/dist/src/server.js")], env)
        await asyncio.sleep(1)
        if not alive(self.processes[key]["pid"]):
            raise InputError("ONVIF could not start. Check for a port conflict or missing Node dependencies.")

    async def complete_login(self, blink):
        if not blink.available:
            raise InputError("Blink login failed. Check your account details and try again.")
        atomic_json(DATA / "auth.json", blink.auth.login_attributes)
        self.blink = blink
        self.pending = None
        self.account_status = "connected"
        self.account_message = "Connected to Blink. Account credentials are stored only on this computer."
        self.catalog = []
        for name, camera in blink.cameras.items():
            def field(key):
                result = getattr(camera, key, None)
                return result if isinstance(result, (str, int, float, bool)) else None
            self.catalog.append({"name": name, "serial": field("serial"), "type": field("camera_type"),
                                 "product": field("product_type"), "online": field("online"),
                                 "firmware": field("version"), "wifi": field("wifi_strength"),
                                 "battery": field("battery_level"), "battery_state": field("battery_state"),
                                 "battery_voltage": field("battery_voltage"), "temperature": field("temperature_c")})
        self.catalog_at = time.time()
        self.extended_entitlement = "unknown"
        with contextlib.suppress(Exception):
            url = f"{blink.urls.base_url}/api/v2/accounts/{blink.account_id}/subscriptions/entitlements"
            async with self.session.get(url, headers=blink.auth.header, allow_redirects=False,
                                        timeout=ClientTimeout(total=8)) as response:
                if response.status == 200:
                    def inspect(value):
                        if isinstance(value, dict):
                            if value.get("name") == "lv_extended" and value.get("status") in ("active", "subscription_required", "inactive"):
                                self.extended_entitlement = value["status"]
                            for child in value.values():
                                inspect(child)
                        elif isinstance(value, list):
                            for child in value:
                                inspect(child)
                    inspect(await response.json())

    async def refresh_account(self):
        if not (DATA / "auth.json").exists():
            raise InputError("Connect your Blink account first.")
        blink = Blink(session=self.session)
        blink.auth = Auth(read_json(DATA / "auth.json"), no_prompt=True, session=self.session)
        try:
            ok = await blink.start()
        except BlinkTwoFARequiredError:
            self.pending, self.pending_at = blink, time.time()
            self.account_status = "two_factor"
            self.account_message = "Blink sent a verification code. Enter it in Setup."
            return
        if not ok:
            self.account_status = "reconnect"
            raise InputError("Blink could not refresh the account. Reconnect in Setup.")
        await self.complete_login(blink)

    async def device(self, config):
        if not self.blink:
            await self.refresh_account()
        if not self.blink or self.account_status == "two_factor":
            raise InputError("Finish Blink account verification in Setup first.")
        matches=[c for c in self.blink.cameras.values() if
                 (config.get("serial") and c.serial == config["serial"]) or
                 (not config.get("serial") and c.name == config["name"])]
        if len(matches)!=1:
            raise InputError("Refresh Blink information; this camera could not be uniquely selected.")
        return matches[0]

    async def read_device_settings(self, config):
        camera=await self.device(config)
        info={}
        for key in ("name","serial","camera_id","network_id","camera_type","product_type","version",
                    "online","motion_enabled","motion_detected","battery_level","battery_voltage","battery_state",
                    "temperature_c","wifi_strength","sync_signal_strength","battery_check_time","last_record"):
            with contextlib.suppress(Exception):
                value=getattr(camera,key,None)
                if value is None or type(value) in (str,int,float,bool):info[key]=value
        try:
            result=await camera_settings.read(camera)
        except camera_settings.SettingsError as error:
            result={"values":{},"controls":[],"updated":time.time(),"verification":None,"message":str(error)}
        result["metadata"]=info
        if result["values"].get("motion_regions_compatible") or result["values"].get("privacy_zones_compatible"):
            with contextlib.suppress(Exception):
                result["zones"]=await asyncio.wait_for(camera_settings.read_zones(camera),10)
        networks=self.blink.homescreen.get("networks",[])
        network=next((n for n in networks if str(n.get("id"))==str(camera.network_id)),{})
        result["system"]={k:network[k] for k in ("name","armed","status") if k in network and type(network[k]) in (str,bool,int)}
        result["system"]["id"]=camera.network_id
        previous=self.device_settings.get(config["id"],{})
        result["verification"]=previous.get("verification")
        for row in result["controls"]:
            if row["key"] in self.verified_settings.get(config["id"],set()):
                row["evidence"]="Write and read-back tested on this camera during this dashboard session"
        self.device_settings[config["id"]]=result
        return camera

    async def change_device(self, config, data):
        camera=await self.device(config)
        key="source-"+config["id"]
        was_running=alive(self.processes.get(key,{}).get("pid"))
        # Validate the submitted setting before any interruption.
        operation=data.get("operation","setting")
        if operation=="setting":
            fresh=await camera_settings.read(camera)
            camera_settings.validate(fresh["values"],data.get("key"),data.get("value"),getattr(camera,"product_type",None),camera_settings.config_family(camera))
        elif operation not in ("spotlight-on","spotlight-off","thumbnail","arm-system","disarm-system"):
            raise InputError("Unknown camera command.")
        if operation.startswith("spotlight"):
            fresh=await camera_settings.read(camera)
            if fresh["values"].get("spotlight_compatible") is not True or camera.camera_type!="mini":
                raise InputError("A supported Mini spotlight was not reported by this camera.")
        if operation.endswith("system"):
            if data.get("scope_acknowledged") is not True:
                raise InputError("Acknowledge that this changes the entire Blink system.")
            # System controls may affect multiple cameras; don't interrupt those silently.
            for other in self.config["cameras"]:
                if other["id"]!=config["id"] and alive(self.processes.get("source-"+other["id"],{}).get("pid")):
                    raise InputError("Stop other bridge streams before changing system arming.")
        if was_running:
            await self.stop(key,graceful=True)
            await asyncio.sleep(3)
        try:
            if operation=="setting":
                result=await camera_settings.write(camera,data["key"],data["value"],data.get("expected"))
                self.device_settings[config["id"]]=result
                if result["verification"]["result"]=="Read-back confirmed":
                    self.verified_settings.setdefault(config["id"],set()).add(data["key"])
            elif operation.startswith("spotlight"):
                state="on" if operation.endswith("on") else "off"
                blink=camera.sync.blink
                url=f"{blink.urls.base_url}/api/v1/accounts/{blink.account_id}/networks/{camera.network_id}/owls/{camera.camera_id}/lights/{state}"
                response=await api.http_post(blink,url)
                if not isinstance(response,dict):raise InputError("Blink did not acknowledge the light command.")
                await asyncio.wait_for(api.wait_for_command(blink,response),20)
                await self.read_device_settings(config)
                actual=self.device_settings[config["id"]]["values"].get("light_status")
                self.device_settings[config["id"]]["verification"]={"key":"light_status","result":"Read-back confirmed" if actual==state else "Command sent; light state not confirmed", "time":time.time()}
            elif operation=="thumbnail":
                await asyncio.wait_for(camera.snap_picture(),30)
                await self.read_device_settings(config)
                self.device_settings[config["id"]]["verification"]={"key":"thumbnail","result":"Blink thumbnail refresh requested (separate from local preview)","time":time.time()}
            else:
                arm=operation=="arm-system"
                method=api.request_system_arm if arm else api.request_system_disarm
                await asyncio.wait_for(method(self.blink,camera.network_id),30)
                await self.blink.get_homescreen()
                await self.read_device_settings(config)
                actual=self.device_settings[config["id"]]["system"].get("armed")
                self.device_settings[config["id"]]["verification"]={"key":"system_armed","result":"Read-back confirmed" if actual is arm else "Command sent; system state not confirmed","time":time.time()}
            # Reload metadata after a direct config write without discarding verification.
            if operation=="setting":
                await self.read_device_settings(config)
        finally:
            if was_running:
                await asyncio.sleep(7)
                await self.start_camera(config)

    async def status(self):
        cameras = []
        now = time.time()
        for cam in self.config["cameras"]:
            key = "source-" + cam["id"]
            record = self.processes.get(key, {})
            running = alive(record.get("pid"))
            stats = read_json(RUNTIME / (key + ".json"))
            health = read_json(Path(record.get("health", RUNTIME / (key + "-health.json"))))
            publishing = running and health.get("streaming", False) and now-health.get("updated", 0) < 35
            phase = stats.get("phase", "running") if running else "stopped"
            if publishing:
                phase = "streaming"
            elif phase == "streaming":
                phase = "stalled"
            onvif_running = alive(self.processes.get("onvif-" + cam["id"], {}).get("pid"))
            matches = [c for c in self.catalog if
                       (cam.get("serial") and c.get("serial") == cam["serial"]) or
                       (not cam.get("serial") and c["name"] == cam["name"])]
            cloud = matches[0] if len(matches) == 1 else {}
            cameras.append(dict(cam, phase=phase, running=running, publishing=publishing, telemetry=stats,
                                cloud=cloud, onvif_running=onvif_running, device_settings=self.device_settings.get(cam["id"]),
                                local_url=f"rtsp://127.0.0.1:8554/{cam['path']}",
                                lan_url=f"rtsp://{self.config['host']}:8555/{cam['id']}",
                                onvif_url=f"http://{self.config['host']}:{cam['onvif_port']}/onvif/device_service"))
        return {"time": now, "account": {"status": self.account_status, "message": self.account_message,
                 "updated": self.catalog_at, "extended_entitlement": self.extended_entitlement}, "catalog": self.catalog, "host": self.config["host"],
                 "cameras": cameras, "csrf": self.csrf,
                 "runtime": {"ffmpeg": bool(shutil.which(self.runtime.get("ffmpeg", "ffmpeg"))),
                             "mediamtx": bool(shutil.which(self.runtime.get("mediamtx", "mediamtx"))),
                             "node": bool(shutil.which(self.runtime.get("node", "node")))}}


def create_app(manager=None):
    manager = manager or Manager()
    admin_password = os.getenv("BRIDGE_ADMIN_PASSWORD", "")
    if CONTAINER and len(admin_password) < 12:
        raise ValueError("Set BRIDGE_ADMIN_PASSWORD to at least 12 characters.")

    @web.middleware
    async def protect(request, handler):
        expected = f"127.0.0.1:{request.url.port}"  # Bound to loopback, never 0.0.0.0.
        allowed = {expected, f"localhost:{request.url.port}"}
        if CONTAINER:
            allowed.add(f"{manager.config['host']}:{request.url.port}")
            try:
                credentials = base64.b64decode(request.headers.get("Authorization", "").removeprefix("Basic "),validate=True).decode()
            except (ValueError,UnicodeError):
                credentials = ""
            if not secrets.compare_digest(credentials.encode(), ("admin:"+admin_password).encode()):
                raise web.HTTPUnauthorized(headers={"WWW-Authenticate": 'Basic realm="Blink Camera Relay"'})
        if request.host not in allowed:
            raise web.HTTPForbidden(text="Invalid host")
        if request.method not in ("GET", "HEAD"):
            if request.headers.get("Origin") not in (f"http://{request.host}", None):
                raise web.HTTPForbidden(text="Invalid origin")
            if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), manager.csrf):
                raise web.HTTPForbidden(text="Invalid request token")
        try:
            response = await handler(request)
        except (InputError, camera_settings.SettingsError) as error:
            response = web.json_response({"error": str(error)}, status=400)
        except web.HTTPException:
            raise
        except Exception:
            response = web.json_response({"error": "The operation failed. Check connectivity or refresh the account; no credentials were logged."}, status=500)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    app = web.Application(middlewares=[protect], client_max_size=16384)

    async def startup(app):
        manager.session = ClientSession(timeout=ClientTimeout(total=45))
        if CONTAINER:
            for camera in manager.config["cameras"]:
                try:
                    if camera.get("autostart"):await manager.start_camera(camera)
                    if camera.get("onvif_autostart"):await manager.start_onvif(camera)
                except Exception:
                    manager.account_message = "A saved service could not start; check the stream status and account."


    async def cleanup(app):
        if CONTAINER:
            for key in list(manager.processes):
                with contextlib.suppress(Exception):
                    await manager.stop(key,graceful=key.startswith("source-"))
            for child in manager.children:
                if child.poll() is None:child.terminate()
        await manager.session.close()

    async def status(request):
        return web.json_response(await manager.status())

    async def action(request):
        data = await request.json()
        action = request.match_info["action"]
        if manager.lock.locked():
            return web.json_response({"error": "Another operation is in progress. Please wait."}, status=409)
        async with manager.lock:
            if action == "preview-start":
                cam = manager.camera(data["id"])
                status = await manager.status()
                if not next(c for c in status["cameras"] if c["id"] == cam["id"])["publishing"]:
                    raise InputError("Start the bridge stream before watching live.")
                await preview.start(manager, RUNTIME)
            elif action == "login":
                if any(alive(v.get("pid")) for k,v in manager.processes.items() if k.startswith("source-")):
                    raise InputError("Stop camera streams before replacing the Blink account. ONVIF can stay running.")
                username, password = str(data.get("email", "")).strip(), data.get("password", "")
                if not username or not isinstance(password, str) or not password:
                    raise InputError("Enter your Blink email and password.")
                blink = Blink(session=manager.session)
                blink.auth = Auth({"username": username, "password": password}, no_prompt=True, session=manager.session)
                manager.pending = None
                try:
                    if not await blink.start():
                        raise InputError("Blink rejected the login. Check your email and password.")
                except BlinkTwoFARequiredError:
                    manager.pending, manager.pending_at = blink, time.time()
                    manager.account_status = "two_factor"
                    manager.account_message = "Enter the verification code sent by Blink."
                else:
                    await manager.complete_login(blink)
            elif action == "verify":
                code = str(data.get("code", "")).strip()
                if not re.fullmatch(r"[0-9]{4,10}", code):
                    raise InputError("Enter the numeric code sent by Blink.")
                if not manager.pending or time.time()-manager.pending_at > 600:
                    raise InputError("Verification expired. Sign in again to request a new code.")
                if not await manager.pending.send_2fa_code(code):
                    raise InputError("Blink did not accept that code. Try again.")
                await manager.complete_login(manager.pending)
            elif action == "refresh":
                await manager.refresh_account()
            elif action == "settings-read":
                await manager.read_device_settings(manager.camera(data["id"]))
            elif action == "settings-write":
                await manager.change_device(manager.camera(data["id"]),data)
            elif action == "save":
                old = manager.camera(data["id"]) if data.get("id") else {}
                if old and any(alive(manager.processes.get(prefix+old["id"], {}).get("pid")) for prefix in ("source-", "onvif-")):
                    raise InputError("Stop this camera's stream and ONVIF service before changing its settings.")
                cam = validate_camera(data, old)
                others = [c for c in manager.config["cameras"] if c["id"] != cam["id"]]
                if any(c["path"] == cam["path"] or c["onvif_port"] == cam["onvif_port"] or c["name"] == cam["name"] for c in others):
                    raise InputError("Camera name, RTSP path and ONVIF port must each be unique.")
                manager.config["cameras"] = others + [cam]
                manager.save()
            elif action == "host":
                host = str(data.get("host", ""))
                address = ipaddress.ip_address(host)
                if address.version != 4 or address.is_unspecified or address.is_multicast:
                    raise InputError("Enter this computer's IPv4 LAN address.")
                if any(alive(v.get("pid")) for k,v in manager.processes.items() if k.startswith("onvif")):
                    raise InputError("Stop ONVIF services before changing the LAN address.")
                manager.config["host"] = host
                manager.save()
            elif action in ("start", "stop", "restart", "onvif-start", "onvif-stop", "discovery"):
                cam = manager.camera(data["id"])
                if action in ("stop", "restart"):
                    await manager.stop("source-" + cam["id"], graceful=True)
                if action == "restart":
                    await asyncio.sleep(10)  # Give Blink time to release the old command.
                if action in ("start", "restart"):
                    await manager.start_camera(cam)
                if action == "onvif-stop":
                    await manager.stop("onvif-" + cam["id"])
                    if not any(alive(v.get("pid")) for k,v in manager.processes.items() if k.startswith("onvif-") and k != "onvif-rtsp"):
                        await manager.stop("onvif-rtsp")
                if action == "discovery":
                    cam["discovery"] = bool(data.get("enabled"))
                    await manager.stop("onvif-" + cam["id"])
                    manager.save()
                if action in ("onvif-start", "discovery"):
                    await manager.start_onvif(cam)
                if CONTAINER:
                    if action in ("start","restart","stop"):cam["autostart"] = action != "stop"
                    if action in ("onvif-start","onvif-stop"):cam["onvif_autostart"] = action == "onvif-start"
                    manager.save()
            else:
                raise InputError("Unknown action.")
        return web.json_response(await manager.status())

    snapshot_lock = asyncio.Lock()

    async def snapshot(request):
        cam = manager.camera(request.match_info["id"])
        status = await manager.status()
        if not next(c for c in status["cameras"] if c["id"] == cam["id"])["publishing"]:
            raise web.HTTPConflict(text="No live stream is publishing.")
        if snapshot_lock.locked():
            raise web.HTTPTooManyRequests(text="A snapshot is already in progress.")
        async with snapshot_lock:
            proc = await asyncio.create_subprocess_exec(manager.runtime.get("ffmpeg", "ffmpeg"),
                "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-i",
                f"rtsp://127.0.0.1:8554/{cam['path']}", "-frames:v", "1", "-vf", "scale=800:-1",
                "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1", stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, creationflags=FLAGS)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), 15)
                if proc.returncode or not out:
                    raise InputError("Could not decode a local frame. Try again after the next session starts.")
                return web.Response(body=out, content_type="image/jpeg")
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()

    async def index(request):
        return web.FileResponse(ROOT / "bridge/static/index.html")

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    app.router.add_get("/", index)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/{action}", action)
    app.router.add_get("/api/snapshot/{id}", snapshot)
    preview.install(app, manager)
    app.router.add_static("/static/", ROOT / "bridge/static")
    return app


if __name__ == "__main__":
    logging.getLogger("blinkpy").setLevel(logging.CRITICAL + 1)
    web.run_app(create_app(), host="0.0.0.0" if CONTAINER else "127.0.0.1", port=8787, access_log=None, print=None)
