"""Small, tested reliability adapter around the pinned BlinkPy IMMIS client."""
import asyncio
import contextlib
import ssl
import os
import hashlib
import hmac
import ipaddress
import logging
from pathlib import Path
import time
import telemetry

from blinkpy.livestream import BlinkLiveStream
from blinkpy import api


def video_tls(hostname, pin=""):
    """Trust Blink's app certificate only for IP-addressed IMMIS endpoints."""
    if pin:
        if len(pin) != 64 or any(c not in "0123456789abcdef" for c in pin):
            raise ValueError("Invalid IMMIS certificate fingerprint")
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context, hostname
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return ssl.create_default_context(), hostname
    context = ssl.create_default_context(
        cafile=str(Path(__file__).with_name("certificates") / "blink-immis.pem"))
    # The signed Android app uses this logical service name for IP endpoints.
    # Keep chain, signature, validity and hostname verification enabled.
    return context, "*.immedia-semi.com"


async def read_packet(reader, timeout=25, max_payload=8 * 1024 * 1024):
    """TCP reads may split anywhere, including in the nine-byte header."""
    header = await asyncio.wait_for(reader.readexactly(9), timeout)
    length = int.from_bytes(header[5:9], "big")
    if length > max_payload:
        raise ValueError("IMMIS payload exceeds safety limit")
    payload = await asyncio.wait_for(reader.readexactly(length), timeout)
    return header[0], int.from_bytes(header[1:5], "big"), payload


async def read_frame(reader, timeout=25, max_payload=8 * 1024 * 1024):
    kind, _, payload = await read_packet(reader, timeout, max_payload)
    return kind, payload


class ReliableStream(BlinkLiveStream):
    def __init__(self, original, timeout=25):
        super().__init__(original.camera, {
            "command_id": original.command_id,
            "polling_interval": original.polling_interval,
            "server": original.target.geturl(),
        })
        self.timeout = timeout
        self.connected = asyncio.Event()
        self.worker_tasks = []
        self.session_status = None
        self.media_bytes = 0
        self.media_packets = 0
        self.sample_at = time.monotonic()
        self.sample_bytes = 0

    async def auth(self):
        pin = os.getenv("BLINK_IMMIS_CERT_SHA256", "").strip().lower().replace(":", "")
        context, server_hostname = video_tls(self.target.hostname, pin)
        self.target_reader, self.target_writer = await asyncio.wait_for(
            asyncio.open_connection(self.target.hostname, self.target.port,
                                    ssl=context, server_hostname=server_hostname), self.timeout)
        if pin:
            cert = self.target_writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
            if not hmac.compare_digest(hashlib.sha256(cert).hexdigest(), pin):
                self.target_writer.close()
                await self.target_writer.wait_closed()
                raise ssl.SSLError("IMMIS certificate fingerprint changed")
        self.target_writer.write(self.get_auth_header())
        await self.target_writer.drain()

    async def join(self, reader, writer):
        self.connected.set()
        await super().join(reader, writer)

    async def recv(self):
        while True:
            kind, sequence, payload = await read_packet(self.target_reader, self.timeout)
            if kind in (1, 24):
                # Metadata only: no media, URLs, tokens, or arbitrary payloads.
                logging.getLogger("bridge").info(
                    "IMMIS control: type=%d code=%d payload_bytes=%d",
                    kind, sequence, len(payload))
                if kind == 24:
                    self.session_status = sequence
            if kind == 0 and payload and payload[0] == 0x47:
                self.media_bytes += len(payload)
                self.media_packets += 1
                now = time.monotonic()
                if now - self.sample_at >= 1:
                    telemetry.update(incoming_bytes=self.media_bytes, incoming_packets=self.media_packets,
                                     incoming_mbps=round((self.media_bytes-self.sample_bytes)*8/(now-self.sample_at)/1e6, 3),
                                     incoming_at=time.time())
                    self.sample_at, self.sample_bytes = now, self.media_bytes
                for writer in list(self.clients):
                    if not writer.is_closing():
                        writer.write(payload)
                        await asyncio.wait_for(writer.drain(), self.timeout)

    async def poll(self):
        try:
            while True:
                response = await api.request_command_status(
                    self.camera.sync.blink, self.camera.network_id, self.command_id)
                code = response.get("status_code", 0)
                if code != 908:
                    logging.getLogger("bridge").warning(
                        "Command polling stopped: numeric status %s",
                        code if isinstance(code, int) else "unknown")
                    raise RuntimeError("Command polling failed")
                for command in response.get("commands", []):
                    if command.get("id") == self.command_id:
                        state = command.get("state_condition")
                        if state not in ("new", "running"):
                            logging.getLogger("bridge").info(
                                "Command is terminal; waiting for media EOF or watchdog")
                            # Command bookkeeping is not a media-liveness signal.
                            # In particular, an extended-mode transition may end
                            # the initiating command while transport remains live.
                            await asyncio.Future()
                await asyncio.sleep(self.polling_interval)
        finally:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(api.request_command_done(
                    self.camera.sync.blink, self.camera.network_id, self.command_id), 10)

    async def feed(self):
        try:
            # Do not lose the beginning of MPEG-TS before FFmpeg connects.
            await asyncio.wait_for(self.connected.wait(), self.timeout)
            await self.auth()
            self.worker_tasks = [asyncio.create_task(fn(), name=fn.__name__)
                                 for fn in (self.recv, self.send, self.poll)]
            done, _ = await asyncio.wait(self.worker_tasks,
                                         return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                logging.getLogger("bridge").info("IMMIS worker ended: %s", task.get_name())
                task.result()
        finally:
            self.stop()
            for task in self.worker_tasks:
                task.cancel()
            if self.worker_tasks:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.gather(*self.worker_tasks,
                                              return_exceptions=True), 10)
            if self.server:
                await self.server.wait_closed()
