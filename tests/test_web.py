import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
import web as dashboard


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "DATA", tmp_path / "data")
    monkeypatch.setattr(dashboard, "RUNTIME", tmp_path / "runtime")
    return dashboard.Manager()


def test_ui_security_and_validation(manager):
    async def check():
        async with TestClient(TestServer(dashboard.create_app(manager))) as client:
            response = await client.get("/api/status")
            status = await response.json()
            assert response.status == 200
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
            assert (await client.post("/api/save", json={})).status == 403
            headers = {"X-CSRF-Token": status["csrf"], "Origin": "https://evil.example"}
            assert (await client.post("/api/save", headers=headers, json={})).status == 403
            assert (await client.get("/api/status", headers={"Host": "evil.example"})).status == 403
            headers.pop("Origin")
            for path in ("../auth", "name\npaths:", "rtsp://other", "CAPITAL"):
                assert (await client.post("/api/save", headers=headers, json={"name": "Test", "path": path})).status == 400
            response = await client.post("/api/save", headers=headers, json={"name": "Test", "path": "test", "onvif_port": 8082})
            assert response.status == 200
            assert len((await response.json())["cameras"]) == 1
            assert (await client.post("/api/save", headers=headers, json={"name":"Other", "path":"test", "onvif_port":8083})).status == 400
    asyncio.run(check())


def test_full_login_two_factor_flow_and_secret_redaction(manager, monkeypatch):
    fake = SimpleNamespace(available=True, cameras={}, auth=None,
        start=AsyncMock(side_effect=dashboard.BlinkTwoFARequiredError()), send_2fa_code=AsyncMock(return_value=True))
    monkeypatch.setattr(dashboard, "Blink", lambda **kwargs: fake)
    monkeypatch.setattr(dashboard, "Auth", lambda *args, **kwargs: SimpleNamespace(login_attributes={"refresh_token":"do-not-return"}))
    async def check():
        async with TestClient(TestServer(dashboard.create_app(manager))) as client:
            headers={"X-CSRF-Token":manager.csrf}
            response=await client.post("/api/login", headers=headers, json={"email":"test@example.test", "password":"secret-password"})
            assert response.status == 200
            assert (await response.json())["account"]["status"] == "two_factor"
            assert not (dashboard.DATA / "auth.json").exists()
            response=await client.post("/api/verify", headers=headers, json={"code":"123456"})
            body=await response.text()
            assert response.status == 200 and '"connected"' in body
            assert "do-not-return" not in body and "secret-password" not in body
            assert json.loads((dashboard.DATA / "auth.json").read_text())["refresh_token"] == "do-not-return"
            fake.send_2fa_code.assert_awaited_once_with("123456")
    asyncio.run(check())


def test_expired_two_factor_and_failed_login_preserve_existing_auth(manager, monkeypatch):
    saved=dashboard.DATA / "auth.json"
    saved.write_text('{"refresh_token":"previous"}')
    fake=SimpleNamespace(start=AsyncMock(return_value=False))
    monkeypatch.setattr(dashboard,"Blink",lambda **kwargs:fake)
    async def check():
        async with TestClient(TestServer(dashboard.create_app(manager))) as client:
            h={"X-CSRF-Token":manager.csrf}
            assert (await client.post("/api/login",headers=h,json={"email":"x", "password":"x"})).status == 400
            assert (await client.post("/api/verify",headers=h,json={"code":"123456"})).status == 400
            assert json.loads(saved.read_text())["refresh_token"] == "previous"
    asyncio.run(check())


def test_stale_health_not_reported_live(manager, monkeypatch):
    camera=dashboard.validate_camera({"name":"Test", "path":"test"},{})
    manager.config["cameras"]=[camera]
    health=dashboard.RUNTIME / "old-health.json"
    health.write_text('{"streaming":true,"updated":1}')
    manager.processes["source-"+camera["id"]]={"pid":123, "health":str(health)}
    monkeypatch.setattr(dashboard,"alive",lambda pid: bool(pid))
    result=asyncio.run(manager.status())
    assert not result["cameras"][0]["publishing"]


def test_camera_identity_survives_edits():
    original=dashboard.validate_camera({"name":"One", "path":"one"},{})
    updated=dashboard.validate_camera({"name":"Two", "path":"two"},original)
    for field in ("id","uuid","mac"):
        assert original[field]==updated[field]


def test_process_identity_guard(manager, monkeypatch):
    # Never terminate a stale PID pointing at a different program.
    monkeypatch.setattr(dashboard,"alive",lambda pid:True)
    fake=SimpleNamespace(communicate=AsyncMock(return_value=(b"unrelated-program.exe",b"")))
    monkeypatch.setattr(dashboard.asyncio,"create_subprocess_exec",AsyncMock(return_value=fake))
    monkeypatch.setattr(dashboard.sys,"platform","win32")
    with pytest.raises(ValueError,match="identity changed"):
        asyncio.run(manager.owned({"pid":123,"needle":"bridge/app.py"}))


def test_busy_operation_and_running_config_guards(manager, monkeypatch):
    camera=dashboard.validate_camera({"name":"One","path":"one"},{})
    manager.config["cameras"]=[camera]
    manager.processes["source-"+camera["id"]]={"pid":123}
    monkeypatch.setattr(dashboard,"alive",lambda pid:bool(pid))
    async def check():
        async with TestClient(TestServer(dashboard.create_app(manager))) as client:
            h={"X-CSRF-Token":manager.csrf}
            assert (await client.post("/api/save",headers=h,json=camera)).status==400
            assert (await client.post("/api/login",headers=h,json={"email":"x","password":"x"})).status==400
            await manager.lock.acquire()
            assert (await client.post("/api/refresh",headers=h,json={})).status==409
            manager.lock.release()
    asyncio.run(check())


def test_cloud_exception_body_never_reaches_browser(manager, monkeypatch):
    fake=SimpleNamespace(start=AsyncMock(side_effect=ValueError("secret-cloud-token")))
    monkeypatch.setattr(dashboard,"Blink",lambda **kwargs:fake)
    async def check():
        async with TestClient(TestServer(dashboard.create_app(manager))) as client:
            response=await client.post("/api/login",headers={"X-CSRF-Token":manager.csrf},json={"email":"x", "password":"x"})
            assert response.status==500
            assert "secret-cloud-token" not in await response.text()
    asyncio.run(check())


def test_setting_failure_always_resumes_previous_stream(manager,monkeypatch):
    import camera_settings
    cam={"id":"test","name":"Test"}
    manager.device=AsyncMock(return_value=object())
    manager.stop=AsyncMock();manager.start_camera=AsyncMock()
    monkeypatch.setattr(dashboard,'alive',lambda pid:True)
    monkeypatch.setattr(dashboard.asyncio,'sleep',AsyncMock())
    monkeypatch.setattr(camera_settings,'read',AsyncMock(return_value={"values":{"led_state":"off"}}))
    monkeypatch.setattr(camera_settings,'write',AsyncMock(side_effect=camera_settings.SettingsError('Rejected')))
    with pytest.raises(camera_settings.SettingsError):
        asyncio.run(manager.change_device(cam,{"key":"led_state","value":"on","expected":"off"}))
    manager.stop.assert_awaited_once_with('source-test',graceful=True)
    manager.start_camera.assert_awaited_once_with(cam)


def test_invalid_setting_does_not_interrupt_video(manager,monkeypatch):
    import camera_settings
    manager.device=AsyncMock(return_value=object());manager.stop=AsyncMock()
    monkeypatch.setattr(camera_settings,'read',AsyncMock(return_value={"values":{"led_state":"off"}}))
    with pytest.raises(camera_settings.SettingsError):
        asyncio.run(manager.change_device({"id":"test"},{"key":"token","value":"secret"}))
    manager.stop.assert_not_awaited()


def test_invalid_brightness_does_not_interrupt_video(manager,monkeypatch):
    import camera_settings
    manager.device=AsyncMock(return_value=SimpleNamespace(product_type="chickadee"))
    manager.stop=AsyncMock();manager.start_camera=AsyncMock()
    monkeypatch.setattr(dashboard,'alive',lambda pid:True)
    monkeypatch.setattr(camera_settings,'read',AsyncMock(return_value={"values":{"light_brightness":3,"spotlight_compatible":True}}))
    with pytest.raises(camera_settings.SettingsError):
        asyncio.run(manager.change_device({"id":"test"},{"key":"light_brightness","value":10,"expected":3}))
    manager.stop.assert_not_awaited()
    manager.start_camera.assert_not_awaited()


def test_container_requires_password_and_protects_status(manager,monkeypatch):
    monkeypatch.setattr(dashboard,"CONTAINER",True)
    monkeypatch.setenv("BRIDGE_ADMIN_PASSWORD","")
    with pytest.raises(ValueError):dashboard.create_app(manager)
    monkeypatch.setenv("BRIDGE_ADMIN_PASSWORD","test-password-long")
    async def check():
        from aiohttp import BasicAuth
        async with TestClient(TestServer(dashboard.create_app(manager))) as client:
            assert (await client.get("/api/status")).status==401
            response=await client.get("/api/status",auth=BasicAuth("admin","test-password-long"))
            assert response.status==200
            token=(await response.json())["csrf"]
            response=await client.post("/api/refresh",auth=BasicAuth("admin","test-password-long"),headers={"Origin":"http://evil.invalid","X-CSRF-Token":token},json={})
            assert response.status==403
    asyncio.run(check())


def test_camera_edit_preserves_container_autostart():
    old=dashboard.validate_camera({"name":"One","path":"one"},{})
    old.update(autostart=True,onvif_autostart=True)
    new=dashboard.validate_camera({"name":"One","path":"one"},old)
    assert new["autostart"] and new["onvif_autostart"]
