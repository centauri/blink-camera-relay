import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
import app
from immis import read_frame, ReliableStream


def test_fragmented_header_and_payload():
    async def check():
        reader = asyncio.StreamReader()
        payload = b"\x47" + bytes(187)
        packet = b"\x00" + (1).to_bytes(4, "big") + len(payload).to_bytes(4, "big") + payload
        async def feed():
            for byte in packet:
                reader.feed_data(bytes([byte]))
                await asyncio.sleep(0)
        feed_task = asyncio.create_task(feed())
        assert await read_frame(reader) == (0, payload)
        await feed_task
    asyncio.run(check())


def test_control_empty_frame_and_video():
    async def check():
        reader = asyncio.StreamReader()
        reader.feed_data(b"\x0a" + bytes(8))
        assert await read_frame(reader) == (10, b"")
    asyncio.run(check())


@pytest.mark.parametrize("data", [b"\x00", bytes(8), b"\x00" + bytes(4) + (188).to_bytes(4, "big") + bytes(5)])
def test_truncation_is_explicit(data):
    async def check():
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        with pytest.raises(asyncio.IncompleteReadError):
            await read_frame(reader)
    asyncio.run(check())


def test_oversized_payload_rejected_before_reading():
    async def check():
        reader = asyncio.StreamReader()
        reader.feed_data(b"\x00" + bytes(4) + (999999999).to_bytes(4, "big"))
        with pytest.raises(ValueError):
            await read_frame(reader)
    asyncio.run(check())


def test_idle_timeout():
    async def check():
        with pytest.raises(TimeoutError):
            await read_frame(asyncio.StreamReader(), timeout=0.01)
    asyncio.run(check())


def test_camera_selection_never_silently_selects_first():
    camera = SimpleNamespace(serial="ABC")
    cameras = {"Mini Camera": camera}
    with pytest.raises(app.SetupRequired):
        app.select_camera(cameras)
    assert app.select_camera(cameras, name="mini camera") is camera
    assert app.select_camera(cameras, serial="ABC") is camera
    with pytest.raises(app.SetupRequired):
        app.select_camera(cameras, name="Mini Camera", serial="WRONG")


def test_retry_is_rate_limited_and_bounded():
    assert app.retry_delay(0, 5) == 55
    assert app.retry_delay(1, 5) == 115
    assert app.retry_delay(100, 0) == 600
    assert app.retry_delay(0, 240) == 10


def test_rtsp_path_rejects_injection(monkeypatch):
    monkeypatch.setenv("RTSP_PATH", "../other?x=y")
    with pytest.raises(app.SetupRequired):
        app.rtsp_target()


def test_video_profile_matches_onvif(monkeypatch):
    monkeypatch.setenv("RTSP_BASE", "rtsp://127.0.0.1:18554")
    cmd = app.ffmpeg_command(test=True)
    assert cmd[-1] == "rtsp://127.0.0.1:18554/blink-mini"
    assert cmd[cmd.index("-g") + 1] == "30"
    assert "baseline" in cmd
    assert "-an" in cmd


def test_atomic_credentials_and_health_progress(tmp_path, monkeypatch):
    async def check():
        path = tmp_path / "health.json"
        monkeypatch.setattr(app, "HEALTH", path)
        reader = asyncio.StreamReader()
        reader.feed_data(b"out_time_us=10\nout_time_us=N/A\nout_time_us=20\n")
        reader.feed_eof()
        await app.progress(reader)
        assert json.loads(path.read_text())["streaming"]
        assert not path.with_suffix(".tmp").exists()
    asyncio.run(check())


def test_feed_cancels_other_workers_on_eof():
    async def check():
        from urllib.parse import urlparse
        original = SimpleNamespace(camera=None, command_id=1, polling_interval=5,
                                   target=urlparse("immis://example.com:443/test"))
        stream = ReliableStream(original)
        stream.connected.set()
        stream.auth = AsyncMock()
        stream.recv = AsyncMock(side_effect=asyncio.IncompleteReadError(b"", 9))
        async def forever():
            await asyncio.Future()
        stream.send = forever
        stream.poll = forever
        with pytest.raises(asyncio.IncompleteReadError):
            await stream.feed()
        assert all(t.done() for t in stream.worker_tasks)
    asyncio.run(check())


def test_unattended_login_requires_saved_state(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "STATE", tmp_path / "missing.json")
    async def check():
        with pytest.raises(app.SetupRequired, match="interactive auth"):
            await app.login(None)
    asyncio.run(check())


@pytest.mark.parametrize("interactive", [False, True])
def test_two_factor_flow_and_session_persistence(tmp_path, monkeypatch, interactive):
    path = tmp_path / "auth.json"
    path.write_text('{"username":"fixture","password":"fixture"}')
    monkeypatch.setattr(app, "STATE", path)
    fake = SimpleNamespace(available=True, auth=None,
        start=AsyncMock(side_effect=app.BlinkTwoFARequiredError()),
        send_2fa_code=AsyncMock(return_value=True))
    monkeypatch.setattr(app, "Blink", lambda **kwargs: fake)
    monkeypatch.setattr(app, "Auth", lambda *args, **kwargs:
                        SimpleNamespace(login_attributes={"refresh_token": "fixture-token"}))
    monkeypatch.setattr(app.getpass, "getpass", lambda prompt: "123456")
    async def check():
        if interactive:
            assert await app.login(None, True) is fake
            fake.send_2fa_code.assert_awaited_once_with("123456")
            assert json.loads(path.read_text()) == {"refresh_token": "fixture-token"}
        else:
            with pytest.raises(app.SetupRequired, match="2FA"):
                await app.login(None)
            fake.send_2fa_code.assert_not_awaited()
    asyncio.run(check())


@pytest.mark.parametrize("mode", ["default", "match", "mismatch"])
def test_immis_tls_pin_checked_before_auth(monkeypatch, mode):
    import hashlib
    import ssl
    from unittest.mock import Mock
    from urllib.parse import urlparse
    import immis
    cert = b"fixture-certificate"
    monkeypatch.delenv("BLINK_IMMIS_CERT_SHA256", raising=False)
    if mode != "default":
        monkeypatch.setenv("BLINK_IMMIS_CERT_SHA256",
            hashlib.sha256(cert).hexdigest() if mode == "match" else "0" * 64)
    writer = Mock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    writer.get_extra_info.return_value.getpeercert.return_value = cert
    connect = AsyncMock(return_value=(Mock(), writer))
    monkeypatch.setattr(immis.asyncio, "open_connection", connect)
    original = SimpleNamespace(camera=None, command_id=1, polling_interval=5,
                               target=urlparse("immis://example.com:443/test"))
    stream = ReliableStream(original)
    stream.get_auth_header = Mock(return_value=b"auth")
    async def check():
        if mode == "mismatch":
            with pytest.raises(ssl.SSLError):
                await stream.auth()
            writer.write.assert_not_called()
            writer.close.assert_called_once()
        else:
            await stream.auth()
            writer.write.assert_called_once_with(b"auth")
        ctx = connect.call_args.kwargs["ssl"]
        if mode == "default":
            assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    asyncio.run(check())


def test_live_session_metadata_does_not_log_secrets(monkeypatch, caplog):
    import logging
    response = {"duration": 360, "extended_duration": 5400,
                "server": "immis://fixture.invalid/secret-token", "command_id": 1,
                "polling_interval": 15}
    camera = SimpleNamespace(sync=SimpleNamespace(blink=object(), network_id=2),
                             camera_id=3, camera_type="mini")
    request = AsyncMock(return_value=response)
    monkeypatch.setattr(app.api, "request_camera_liveview", request)
    with caplog.at_level(logging.INFO, logger="bridge"):
        stream = asyncio.run(app.open_live_session(camera))
    assert stream.command_id == 1
    assert "360" in caplog.text and "5400" in caplog.text
    assert "secret-token" not in caplog.text and "fixture.invalid" not in caplog.text
    request.assert_awaited_once_with(camera.sync.blink, 2, 3, camera_type="mini")


@pytest.mark.parametrize("previous,elapsed,expected", [(0,1,1),(4,59,5),(4,60,0),(10,361,0)])
def test_healthy_session_eof_resets_backoff(previous, elapsed, expected):
    count = app.next_failure_count(previous, elapsed)
    assert count == expected
    if elapsed >= 60:
        assert app.retry_delay(count, elapsed) == 10


@pytest.mark.parametrize("duration,stream_type", [(5400,"elv"),(300,"lv"),(300,"elv")])
def test_extended_intent_uses_app_request_and_does_not_log_secrets(monkeypatch, caplog,duration,stream_type):
    import logging
    blink = SimpleNamespace(urls=SimpleNamespace(base_url="https://fixture.invalid"), account_id=11)
    camera = SimpleNamespace(sync=SimpleNamespace(blink=blink, network_id=22),
                             camera_id=33, camera_type="mini")
    response = {"duration":duration,"type":stream_type,"extended_duration":5400,
                "server":"immis://fixture.invalid:443/secret-token",
                "command_id":1,"polling_interval":15}
    post = AsyncMock(return_value=response)
    wait = AsyncMock()
    normal = AsyncMock()
    monkeypatch.setenv("BLINK_LIVEVIEW_MODE", "extended")
    monkeypatch.setattr(app.api,"http_post",post)
    monkeypatch.setattr(app.api,"wait_for_command",wait)
    monkeypatch.setattr(app.api,"request_camera_liveview",normal)
    with caplog.at_level(logging.INFO, logger="bridge"):
        stream=asyncio.run(app.open_live_session(camera))
    assert stream.command_id == 1
    assert post.call_args.args == (blink,"https://fixture.invalid/api/v2/accounts/11/networks/22/owls/33/liveview")
    assert json.loads(post.call_args.kwargs["data"]) == {
        "intent":"extended_liveview","motion_event_start_time":None}
    wait.assert_awaited_once_with(blink,response)
    normal.assert_not_awaited()
    assert "5400" in caplog.text
    assert ("did not grant extended mode" in caplog.text) == (stream_type == "lv")
    assert "secret-token" not in caplog.text and "fixture.invalid" not in caplog.text


@pytest.mark.parametrize("mode,camera_type", [("typo","mini"),("extended","default")])
def test_invalid_live_mode_fails_before_api(monkeypatch,mode,camera_type):
    monkeypatch.setenv("BLINK_LIVEVIEW_MODE",mode)
    post=AsyncMock()
    monkeypatch.setattr(app.api,"http_post",post)
    with pytest.raises(app.SetupRequired):
        asyncio.run(app.open_live_session(SimpleNamespace(camera_type=camera_type)))
    post.assert_not_awaited()


def test_session_ack_retains_command_code_without_payload():
    from immis import read_packet
    async def check():
        reader=asyncio.StreamReader()
        reader.feed_data(bytes.fromhex("18 00 00 00 06 00 00 00 00"))
        assert await read_packet(reader) == (24,6,b"")
    asyncio.run(check())


def test_terminal_command_does_not_kill_live_media(monkeypatch):
    from urllib.parse import urlparse
    import immis
    camera = SimpleNamespace(sync=SimpleNamespace(blink=None), network_id=2)
    original = SimpleNamespace(camera=camera,command_id=1,polling_interval=5,
                               target=urlparse("immis://fixture.invalid:443/test"))
    status = AsyncMock(return_value={"status_code":908,"commands":[{"id":1,"state_condition":"done"}]})
    done = AsyncMock()
    monkeypatch.setattr(immis.api,"request_command_status",status)
    monkeypatch.setattr(immis.api,"request_command_done",done)
    async def check():
        task = asyncio.create_task(ReliableStream(original).poll())
        await asyncio.sleep(0)
        assert not task.done()
        assert status.await_count == 1
        done.assert_not_awaited()
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        done.assert_awaited_once_with(None,2,1)
    asyncio.run(check())


def test_graceful_stop_file_cancels_run(tmp_path):
    async def check():
        cleanup=[]
        async def running():
            try: await asyncio.Future()
            finally: cleanup.append(True)
        task=asyncio.create_task(running())
        await asyncio.sleep(0)
        path=tmp_path/"stop";path.write_text("stop")
        await app.watch_stop_file(task,path)
        await asyncio.gather(task,return_exceptions=True)
        assert task.cancelled() and cleanup == [True]
    asyncio.run(check())


def test_atomic_write_retries_transient_windows_lock(tmp_path, monkeypatch):
    real_replace=app.os.replace
    attempts=[]
    def replace(source,target):
        attempts.append(True)
        if len(attempts)==1: raise PermissionError("fixture sharing violation")
        return real_replace(source,target)
    monkeypatch.setattr(app.os,"replace",replace)
    monkeypatch.setattr(app.time,"sleep",lambda _:None)
    target=tmp_path/"state.json"
    app.atomic_json(target,{"streaming":True})
    assert len(attempts)==2 and json.loads(target.read_text())["streaming"]
