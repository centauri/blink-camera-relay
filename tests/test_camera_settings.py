import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"bridge"))
import camera_settings as settings


def test_capabilities_types_and_limits():
    config={"led_state":"off","enabled":True,"motion_sensitivity":5,"spotlight_enabled":False,
            "spotlight_compatible":False,"clip_length":10,"clip_length_max":20,
            "light_duration":30,"light_duration_options":[30,60]}
    assert settings.validate(config,"led_state","recording")=="recording"
    for key,value in [("led_state","evil"),("enabled",1),("enabled","true"),("motion_sensitivity",True),
                      ("motion_sensitivity",10),("clip_length",60),("spotlight_enabled",True),("password","secret")]:
        with pytest.raises(settings.SettingsError):settings.validate(config,key,value)


def test_read_only_for_unknown_encoding_or_options():
    rows={r['key']:r for r in settings.controls({"illuminator_enable":2,"snapshot_period_minutes":60})}
    assert not rows['illuminator_enable']['writable']
    assert not rows['snapshot_period_minutes']['writable']


def test_secrets_and_unknown_nested_fields_are_not_exported():
    result=settings.sanitize({"led_state":"off","token":"secret","server":"immis://secret",
        "wifi":"https://secret","advanced_motion_regions":[1,2],
        "detection_modes":{"person_detection":True,"token":"secret"},
        "motion_record_and_alert":{"record_type":"motion_detection","auth":"secret"}})
    assert result=={"led_state":"off","advanced_motion_regions":[1,2],
                    "detection_modes":{"person_detection":True},"motion_record_and_alert":{"record_type":"motion_detection"}}


def camera():
    return SimpleNamespace(camera_type='mini',product_type='chickadee',network_id=1,camera_id=2,
                           sync=SimpleNamespace(blink=object()))


def test_read_maps_new_mini_to_owl_endpoint(monkeypatch):
    read=AsyncMock(return_value={"enabled":True,"led_state":"off"})
    monkeypatch.setattr(settings.api,'request_get_config',read)
    result=asyncio.run(settings.read(camera()))
    assert result['values']['led_state']=='off'
    assert read.call_args.kwargs['product_type']=='owl'


def test_write_requires_current_value_then_verifies_readback(monkeypatch):
    get=AsyncMock(side_effect=[{"enabled":True,"led_state":"off"},{"enabled":True,"led_state":"on"}])
    post=AsyncMock(return_value=SimpleNamespace(status=200,release=lambda:None))
    monkeypatch.setattr(settings.api,'request_get_config',get)
    monkeypatch.setattr(settings.api,'request_update_config',post)
    result=asyncio.run(settings.write(camera(),'led_state','on','off'))
    assert result['verification']['result']=='Read-back confirmed'
    assert post.call_args.kwargs['data']=='{"led_state": "on"}'


def test_stale_settings_never_write(monkeypatch):
    monkeypatch.setattr(settings.api,'request_get_config',AsyncMock(return_value={"enabled":True,"led_state":"recording"}))
    post=AsyncMock();monkeypatch.setattr(settings.api,'request_update_config',post)
    with pytest.raises(settings.SettingsError,match='changed since'):
        asyncio.run(settings.write(camera(),'led_state','on','off'))
    post.assert_not_awaited()


def test_rejected_and_ignored_writes_are_not_success(monkeypatch):
    monkeypatch.setattr(settings.api,'request_get_config',AsyncMock(return_value={"enabled":True,"led_state":"off"}))
    monkeypatch.setattr(settings.api,'request_update_config',AsyncMock(return_value=SimpleNamespace(status=403,release=lambda:None)))
    with pytest.raises(settings.SettingsError,match='HTTP 403'):
        asyncio.run(settings.write(camera(),'led_state','on','off'))
    monkeypatch.setattr(settings.api,'request_update_config',AsyncMock(return_value=SimpleNamespace(status=200,release=lambda:None)))
    monkeypatch.setattr(settings.asyncio,'sleep',AsyncMock())
    result=asyncio.run(settings.write(camera(),'led_state','on','off'))
    assert result['verification']['result'].startswith('Not confirmed')


@pytest.mark.parametrize("model,maximum", [("chickadee",3),("hawk",3),("superior",10)])
def test_brightness_model_limits(model,maximum):
    values={"light_brightness":3,"spotlight_compatible":True}
    row=settings.controls(values,model)[0]
    assert row["minimum"]==1 and row["maximum"]==maximum
    if model!="superior":assert settings.validate(values,"light_brightness",maximum,model)==maximum
    for invalid in (0,maximum+1,True):
        with pytest.raises(settings.SettingsError):
            settings.validate(values,"light_brightness",invalid,model)


def test_unknown_brightness_model_is_read_only():
    values={"light_brightness":3,"spotlight_compatible":True}
    assert not settings.controls(values,"unknown")[0]["writable"]


def test_invalid_brightness_never_reaches_camera(monkeypatch):
    monkeypatch.setattr(settings.api,'request_get_config',AsyncMock(return_value={"enabled":True,"light_brightness":3,"spotlight_compatible":True}))
    post=AsyncMock();monkeypatch.setattr(settings.api,'request_update_config',post)
    with pytest.raises(settings.SettingsError):
        asyncio.run(settings.write(camera(),'light_brightness',10,3))
    post.assert_not_awaited()


@pytest.mark.parametrize("key", ["volume_control","chime_volume"])
def test_audio_ranges_match_android_app(key):
    values={key:5,"chime_compatible":True}
    for value in (1,8):assert settings.validate(values,key,value,"chickadee")==value
    for value in (0,9,10,True):
        with pytest.raises(settings.SettingsError):settings.validate(values,key,value,"chickadee")


def test_missing_clip_limit_and_malformed_duration_are_read_only():
    rows=settings.controls({"clip_length":10,"light_duration":30,"spotlight_compatible":True,"light_duration_options":None},"chickadee")
    assert all(not r["writable"] for r in rows)


def test_unmapped_models_and_out_of_range_values_are_read_only():
    assert not settings.controls({"volume_control":10},"chickadee")[0]["writable"]
    assert not settings.controls({"enabled":True},"catalina")[0]["writable"]
