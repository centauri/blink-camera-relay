"""Reject private artifacts from the actual Git index; do not print file contents."""
from pathlib import Path
import hashlib
import re
import ssl
import subprocess

files=subprocess.check_output(["git","ls-files","-z"]).decode().split("\0")
errors=[]
if "bridge/certificates/blink-immis.pem" not in files:
    errors.append("Missing bundled public IMMIS certificate")
for name in filter(None,files):
    p=Path(name)
    if any(part in {"data",".runtime",".venv","node_modules","__pycache__","tools","work"} for part in p.parts):
        errors.append(name+": private/generated directory")
    public_cert = name == "bridge/certificates/blink-immis.pem"
    if public_cert:
        certificate = ssl.PEM_cert_to_DER_cert(p.read_text(encoding="ascii"))
        if hashlib.sha256(certificate).hexdigest() != "b1bfa71ba445f0de14172a1382db19e8848f93b850eb78bd13fdabc1be7e2481":
            errors.append(name+": public certificate changed; provenance review required")
    if not public_cert and (p.name in {".env","auth.json","credentials.json"} or p.suffix.lower() in {".apk",".apkm",".exe",".dll",".pem",".key",".log"}):
        errors.append(name+": private/binary artifact")
    text=p.read_text(encoding="utf-8",errors="replace")
    patterns=[r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",r"gh[pousr]_[A-Za-z0-9]{30,}",r"github_pat_[A-Za-z0-9_]{50,}"]
    if any(re.search(pattern,text) for pattern in patterns):errors.append(name+": credential pattern")
if errors:raise SystemExit("\n".join(errors))
print("Release index checks passed")
