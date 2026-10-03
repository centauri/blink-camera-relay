"""Capability-gated camera settings. Cloud responses never reach the UI wholesale.

Wire fields/enums are based on Blink's Android 55 OwlApi/UpdateOwlBody and
the pinned BlinkPy API. Unknown fields remain unavailable, never generic writes.
"""
import asyncio
import json
import time
from blinkpy import api


class SettingsError(ValueError):
    pass


def option(label, group, choices=None, minimum=None, maximum=None, capability=None, note=""):
    return dict(label=label, group=group, choices=choices, minimum=minimum,
                maximum=maximum, capability=capability, note=note)


SCHEMA = {
    "enabled": option("Motion detection", "Motion", [False, True], note="Camera detection only; the Blink system must also be armed."),
    "motion_sensitivity": option("Motion sensitivity", "Motion", minimum=1, maximum=9),
    "retrigger_time": option("Retrigger delay (seconds)", "Motion", minimum=10, maximum=60),
    "early_notification": option("Early motion notification", "Motion", [False, True], capability="early_notification_compatible"),
    "video_recording_enable": option("Motion clip recording", "Recording", [False, True], capability="video_recording_optional", note="Blink recording setting; does not enable Protect recording or a subscription."),
    "clip_length": option("Motion clip length (seconds)", "Recording", [10,20,30,40,50,60]),
    "early_termination": option("End clip when motion stops", "Recording", [False, True], capability="early_termination_supported"),
    "record_audio_enable": option("Record camera audio", "Audio", [False, True], note="Camera recording only. The RTSP bridge still outputs video without audio."),
    "volume_control": option("Camera speaker volume", "Audio", minimum=1, maximum=8, note="App-defined levels 1–8; read-back checked after Apply."),
    "chime_volume": option("Doorbell chime volume", "Audio", minimum=1, maximum=8, capability="chime_compatible", note="App-defined levels 1–8; read-back checked after Apply."),
    "led_state": option("Status LED", "Lighting", ["on","off","recording"]),
    "illuminator_enable": option("Infrared night vision", "Lighting", ["off","on","auto"]),
    "illuminator_intensity": option("Infrared intensity (1 low / 4 medium / 7 high)", "Lighting", [1,4,7]),
    "spotlight_enabled": option("Motion-activated spotlight", "Lighting", [False, True], capability="spotlight_compatible"),
    "light_brightness": option("Spotlight brightness", "Lighting", minimum=1, capability="spotlight_compatible", note="Model-specific brightness levels. Requires a brief stream pause. Does not turn the spotlight on or reset its timer."),
    "light_duration": option("Motion spotlight duration (seconds)", "Lighting", capability="spotlight_compatible"),
    "manual_light_duration": option("Manual spotlight duration (seconds)", "Lighting", capability="spotlight_compatible", note="The manual spotlight turns off automatically after this duration. Brightness does not extend it."),
    "video_quality": option("Source video quality", "Video", ["saver","standard","best"], note="Changes the camera source. The local stream remains normalized to 720p / 15 fps."),
    "flip_video": option("Flip camera image", "Video", [False, True], capability="flip_video_compatible"),
    "snapshot_enabled": option("Blink Photo Capture", "Photos", [False, True], note="Cloud feature availability may require a plan. This is separate from local Capture frame."),
    "snapshot_period_minutes": option("Photo Capture interval (minutes)", "Photos"),
    "auto_update_thumbnail_enabled": option("Automatic thumbnail updates", "Photos", [False, True]),
    "camera_location_indoor": option("Camera mounted indoors", "Video", [False, True]),
}

READ_KEYS = set(SCHEMA) | set("""name updated_at fw_version fcc_id ic_id model_number status
 led_enabled illuminator_enable_v2 night_vision_control night_vision_exposure_compatible
 illuminator_duration wifi wifi_rssi wifi_mac clip_length_max early_notification_compatible
 early_termination_supported flip_video_compatible local_storage_enabled local_storage_compatible
 chime_compatible video_recording_optional motion_regions_compatible privacy_zones_compatible
 spotlight_compatible light_status light_duration_options manual_light_duration_options
 snapshot_period_minutes_options extended_clip_recording_support zone_version motion_regions
 advanced_motion_regions""".split())


def scalar(value):
    return value is None or type(value) in (bool, int, float) or (isinstance(value,str) and len(value)<=200 and "://" not in value)


def sanitize(raw):
    result = {}
    for key in READ_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if scalar(value) or (isinstance(value,list) and len(value)<=512 and all(type(v) in (int,bool) for v in value)):
            result[key] = value
    modes = raw.get("detection_modes")
    if isinstance(modes,dict):
        result["detection_modes"] = {k:v for k,v in modes.items() if k in ("motion_detection","person_detection","vehicle_detection") and type(v) is bool}
    recording = raw.get("motion_record_and_alert", {}).get("record_type") if isinstance(raw.get("motion_record_and_alert"),dict) else None
    if recording in ("motion_detection","person_detection","vehicle_detection","all_motion"):
        result["motion_record_and_alert"] = {"record_type":recording}
    return result


BRIGHTNESS_MAX = {"chickadee": 3, "hawk": 3, "superior": 10}


def controls(values, product_type=None):
    rows=[]
    for key, spec in SCHEMA.items():
        if key not in values:
            continue
        row=dict(spec,key=key,value=values[key],writable=True,evidence="API-mapped; not yet changed on this device")
        if spec["capability"] and values.get(spec["capability"]) is not True:
            row.update(writable=False,note="Camera has not reported this capability as supported.")
        if key == "light_brightness":
            row["maximum"] = BRIGHTNESS_MAX.get(product_type)
            if row["maximum"] is None:
                row.update(writable=False, note="Brightness range is not mapped for this model.")
        if key in ("light_duration","manual_light_duration","snapshot_period_minutes"):
            choices=values.get(key+"_options",[])
            if not isinstance(choices,list):choices=[]
            row["choices"]=[v for v in choices if type(v) is int and 0<v<=86400]
            if not row["choices"]:
                row.update(writable=False,note="Camera did not report permitted values.")
        if key=="clip_length":
            maximum=values.get("clip_length_max")
            row["choices"]=[v for v in spec["choices"] if type(maximum) is int and v<=maximum]
        choices=row["choices"]
        if choices is not None and not any(type(values[key]) is type(v) and values[key]==v for v in choices):
            row.update(writable=False,note="Current value uses an unrecognized encoding; read-only until mapped.")
        if choices is None and type(values[key]) is not int:
            row.update(writable=False,note="Unexpected value type; read-only.")
        if choices is None and type(values[key]) is int and row["minimum"] is not None and row["maximum"] is not None:
            if not row["minimum"] <= values[key] <= row["maximum"]:
                row.update(writable=False,note="Reported value is outside the mapped range; read-only until investigated.")
        if product_type is not None and product_type not in ("owl","hawk","chickadee"):
            row.update(writable=False,note="Setting writes have not been mapped for this camera model.")
        rows.append(row)
    return rows


def validate(values,key,value,product_type=None):
    row=next((r for r in controls(values, product_type) if r["key"]==key),None)
    if not row or not row["writable"]:
        raise SettingsError("This setting is unavailable or read-only on this camera.")
    if row["choices"] is not None:
        if not any(type(value) is type(v) and value==v for v in row["choices"]):
            raise SettingsError("Choose one of the camera's permitted values.")
    elif type(value) is not int or not row["minimum"]<=value<=row["maximum"]:
        raise SettingsError("Value is outside the supported range.")
    return value


def config_family(camera):
    if camera.camera_type=="mini":
        return "owl"  # Includes Mini 2K+ / chickadee; upstream only recognizes product owl.
    if camera.product_type=="catalina":
        return "catalina"
    raise SettingsError("Configuration endpoint is not mapped for this model. Camera metadata is still available.")


async def read(camera):
    result=await api.request_get_config(camera.sync.blink,camera.network_id,camera.camera_id,product_type=config_family(camera))
    if not isinstance(result,dict):
        raise SettingsError("Camera configuration could not be read.")
    if isinstance(result.get("camera"),list):
        result=result["camera"][0] if result["camera"] else {}
    values=sanitize(result)
    if "enabled" not in values and "led_state" not in values:
        raise SettingsError("Blink returned no recognized camera configuration.")
    return {"values":values,"controls":controls(values, camera.product_type),"updated":time.time(),"verification":None}


async def read_zones(camera):
    if camera.camera_type!="mini":return {}
    blink=camera.sync.blink
    url=f"{blink.urls.base_url}/api/v2/accounts/{blink.account_id}/networks/{camera.network_id}/owls/{camera.camera_id}/zones"
    raw=await api.http_get(blink,url)
    if not isinstance(raw,dict):return {}
    result={k:v for k,v in raw.items() if k in ("basic_zone_columns","basic_zone_rows","sub_zone_columns","sub_zone_rows","use_analytics_for_motion") and type(v) in (int,bool)}
    mask=raw.get("zone_mask")
    if isinstance(mask,list) and len(mask)<=1024 and all(type(v) is int for v in mask):result["zone_mask"]=mask
    spans=raw.get("privacy_zones")
    if isinstance(spans,list) and len(spans)<=64:
        result["privacy_zones"]=[{k:v for k,v in span.items() if k in ("x","y","w","h") and type(v) is int} for span in spans if isinstance(span,dict)]
    return result


async def write(camera, key, value, expected):
    before=await read(camera)
    validate(before["values"],key,value,camera.product_type)
    if before["values"].get(key)!=expected or type(before["values"].get(key)) is not type(expected):
        raise SettingsError("This setting changed since it was loaded. Refresh settings before applying.")
    response=await api.request_update_config(camera.sync.blink,camera.network_id,camera.camera_id,
        product_type=config_family(camera),data=json.dumps({key:value}))
    if response is None:
        raise SettingsError("Blink did not acknowledge the setting update.")
    status=response.status
    response.release()
    if status not in (200,201,202):
        raise SettingsError(f"Blink rejected this setting (HTTP {status}).")
    after=None
    for attempt in range(4):
        if attempt:
            await asyncio.sleep(1.5)
        after=await read(camera)
        actual=after["values"].get(key)
        if actual==value and type(actual) is type(value):
            after["verification"]={"key":key,"result":"Read-back confirmed", "time":time.time()}
            for row in after["controls"]:
                if row["key"]==key:row["evidence"]="Read-back confirmed on this device"
            return after
    after["verification"]={"key":key,"result":f"Not confirmed: requested {value}, camera returned {actual}", "time":time.time()}
    return after
