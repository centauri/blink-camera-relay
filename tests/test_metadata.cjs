const {test}=require('node:test');
const assert=require('node:assert/strict');
const {cameraSummary}=require('../bridge/static/metadata.js');

test('Mini config fills missing summary Wi-Fi and firmware with explicit units',()=>{
 const result=cameraSummary({cloud:{type:'mini',wifi:null},device_settings:{updated:20,values:{wifi:3,wifi_rssi:-65,fw_version:'22.24'}}},10);
 assert.equal(result.wifi,'-65 dBm · level 3');
 assert.equal(result.camera,'mini / 22.24');
 assert.equal(result.battery,'External power (Mini)');
 assert.equal(result.temperature,'Not reported');
});
test('zero values and false status are not lost; battery voltage is hundredths of volts',()=>{
 const result=cameraSummary({cloud:{wifi:0,battery:0,battery_voltage:165,temperature:0,online:false}},10);
 assert.equal(result.wifi,'level 0');
 assert.equal(result.battery,'level 0 · 1.65 V');
 assert.equal(result.temperature,'0 °C');
 assert.equal(result.online,false);
});
test('newer cloud readings beat older settings; missing fields still fall back',()=>{
 const result=cameraSummary({cloud:{wifi:2,firmware:'new'},device_settings:{updated:5,values:{wifi:3,wifi_rssi:-65,fw_version:'old'},metadata:{battery_state:'ok'}}},10);
 assert.equal(result.wifi,'-65 dBm · level 2');
 assert.equal(result.camera,'new');
 assert.equal(result.battery,'ok');
 assert.equal(result.settingsUpdated,5);
});
test('absent readings remain unknown',()=>{
 const result=cameraSummary({},0);
 assert.equal(result.wifi,'Not reported');
 assert.equal(result.battery,'Not reported');
 assert.equal(result.online,undefined);
});
