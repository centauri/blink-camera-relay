"""Camera-free checks against the disposable CI container, never real Blink."""
import base64
import json
import subprocess
import urllib.request

base="http://127.0.0.1:8787"
headers={"Authorization":"Basic "+base64.b64encode(b"admin:ci-only-test-password").decode(),"Content-Type":"application/json"}
def call(path,data=None):
    req=urllib.request.Request(base+path,headers=headers,data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)
s=call("/api/status")
headers["X-CSRF-Token"]=s["csrf"]
s=call("/api/save",{"name":"CI synthetic","path":"ci-synthetic","onvif_port":8080})
camera=s["cameras"][0]
s=call("/api/onvif-start",{"id":camera["id"]})
assert s["cameras"][0]["onvif_running"]
subprocess.run(["docker","exec","relay-smoke","python","-c",
    "import urllib.request,socket; assert urllib.request.urlopen('http://127.0.0.1:8080/health').status==200; socket.create_connection(('127.0.0.1',8555),3).close()"],check=True)
call("/api/onvif-stop",{"id":camera["id"]})
print("Dashboard, ONVIF and MediaMTX integration passed")
