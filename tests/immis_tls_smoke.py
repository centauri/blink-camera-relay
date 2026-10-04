"""Exercise packaged TLS trust and reject an impostor without cloud access."""
import asyncio
import hashlib
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(os.getenv("BRIDGE_SOURCE_ROOT", Path(__file__).resolve().parents[1])) / "bridge"))
from immis import video_tls


async def check():
    ctx, name = video_tls("127.0.0.1")
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    certs = ctx.get_ca_certs(binary_form=True)
    assert len(certs) == 1
    assert hashlib.sha256(certs[0]).hexdigest() == "b1bfa71ba445f0de14172a1382db19e8848f93b850eb78bd13fdabc1be7e2481"
    openssl = shutil.which("openssl") or r"C:\Program Files\Git\usr\bin\openssl.exe"
    with tempfile.TemporaryDirectory() as directory:
        key, cert = Path(directory) / "key.pem", Path(directory) / "cert.pem"
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=*.immedia-semi.com"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert, key)
        def connected(reader, writer):
            writer.close()
        server = await asyncio.start_server(connected, "127.0.0.1", 0, ssl=server_context)
        async with server:
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(
                    "127.0.0.1", server.sockets[0].getsockname()[1],
                    ssl=ctx, server_hostname=name), 5)
            except ssl.SSLCertVerificationError:
                pass
            else:
                writer.close()
                await writer.wait_closed()
                raise AssertionError("Unrelated certificate was accepted")
    print("Packaged IMMIS trust verified; unrelated certificate rejected")


if __name__ == "__main__":
    asyncio.run(check())
