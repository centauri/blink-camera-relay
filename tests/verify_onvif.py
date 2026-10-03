"""Probe a running ONVIF endpoint. No Blink or Protect credentials are used."""
import argparse
import json
import socket
import urllib.request
import uuid
import xml.etree.ElementTree as ET


def soap(base, action, service="device", body=""):
    namespace = ("http://www.onvif.org/ver10/device/wsdl" if service == "device"
                 else "http://www.onvif.org/ver10/media/wsdl")
    xml = f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body><a:{action} xmlns:a="{namespace}">{body}</a:{action}></s:Body></s:Envelope>'
    req = urllib.request.Request(f"{base}/onvif/{service}_service", data=xml.encode(),
                                 headers={"Content-Type": "application/soap+xml"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return ET.fromstring(response.read())


def verify(base, expected_rtsp):
    for action in ("GetScopes", "GetServices", "GetCapabilities", "GetSystemDateAndTime", "GetUsers"):
        assert soap(base, action).find(f".//{{*}}{action}Response") is not None
    assert soap(base, "GetVideoSources", "media").find(".//{*}VideoSources") is not None
    profile = soap(base, "GetProfiles", "media")
    profiles = profile.findall(".//{*}Profiles")
    assert len(profiles) == 1
    token = profiles[0].attrib["token"]
    assert profile.findtext(".//{*}Width") == "1280"
    assert profile.findtext(".//{*}Height") == "720"
    assert profile.findtext(".//{*}FrameRateLimit") == "15"
    stream = soap(base, "GetStreamUri", "media", f"<ProfileToken>{token}</ProfileToken>")
    uri = stream.findtext(".//{*}Uri")
    assert uri == expected_rtsp, (uri, expected_rtsp)
    device = soap(base, "GetDeviceInformation")
    assert device.findtext(".//{*}SerialNumber")
    network = soap(base, "GetNetworkInterfaces")
    assert network.findtext(".//{*}HwAddress")
    snapshot = soap(base, "GetSnapshotUri", "media")
    assert snapshot.find(".//{*}Fault") is not None
    return {"rtsp_uri": uri, "profile": "1280x720 H264 Baseline 15fps",
            "identity": device.findtext(".//{*}SerialNumber"), "soap": "passed"}


def discover(host, port=3702):
    message_id = f"urn:uuid:{uuid.uuid4()}"
    data = f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"><s:Header><w:MessageID>{message_id}</w:MessageID></s:Header><s:Body><d:Probe/></s:Body></s:Envelope>'
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.sendto(data.encode(), (host, port))
        reply, _ = sock.recvfrom(65535)
    root = ET.fromstring(reply)
    assert root.findtext(".//{*}RelatesTo") == message_id
    return root.findtext(".//{*}Address")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base", help="http://ONVIF_IP:8080")
    parser.add_argument("rtsp", help="rtsp://ONVIF_IP:8554/ONVIF_ID")
    args = parser.parse_args()
    print(json.dumps(verify(args.base, args.rtsp), indent=2))
