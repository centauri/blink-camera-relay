'use strict';
// Merge only the public, sanitized camera fields. Zero and false are valid data.
function cameraSummary(camera, catalogUpdated) {
 const cloud=camera.cloud||{}, settings=camera.device_settings||{};
 const values=settings.values||{}, metadata=settings.metadata||{};
 const present=v=>v!==null&&v!==undefined&&v!=='';
 const first=(...items)=>items.find(present);
 const latest=(summary,detail)=>settings.updated>=catalogUpdated?first(detail,summary):first(summary,detail);
 const wifi=latest(cloud.wifi,first(values.wifi,metadata.wifi_strength));
 const rssi=values.wifi_rssi;
 const firmware=latest(cloud.firmware,first(values.fw_version,metadata.version));
 const product=first(cloud.product,metadata.product_type,cloud.type,metadata.camera_type);
 const battery=latest(cloud.battery,metadata.battery_level);
 const batteryState=latest(cloud.battery_state,metadata.battery_state);
 const voltage=latest(cloud.battery_voltage,metadata.battery_voltage);
 const temperature=latest(cloud.temperature,metadata.temperature_c);
 const batteryParts=[];
 if(present(batteryState))batteryParts.push(String(batteryState));
 if(present(battery))batteryParts.push(`level ${battery}`);
 if(typeof voltage==='number')batteryParts.push(`${(voltage/100).toFixed(2)} V`);
 const signal=[];
 if(typeof rssi==='number')signal.push(`${rssi} dBm`);
 if(present(wifi))signal.push(`level ${wifi}`);
 return {
  camera:[product,firmware].filter(present).join(' / ')||'Not reported',
  wifi:signal.join(' · ')||'Not reported',
  battery:batteryParts.join(' · ')||([cloud.type,metadata.camera_type].includes('mini')?'External power (Mini)':'Not reported'),
  temperature:present(temperature)?`${temperature} °C`:'Not reported',
  online:first(cloud.online,metadata.online),
  settingsUpdated:settings.updated
 };
}
if(typeof module!=='undefined'&&module.exports)module.exports={cameraSummary};
