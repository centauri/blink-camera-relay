'use strict';
let state, selected, busy=false, snapshotBusy=false, snapshotUrl;
const $=id=>document.getElementById(id);
const show=(id,value)=>$(id).hidden=!value;
const value=v=>v===null||v===undefined||v===''?'—':String(v);
const duration=s=>s==null?'—':s<60?`${Math.max(0,Math.floor(s))}s`:`${Math.floor(s/60)}m ${Math.floor(s%60)}s`;
const stamp=s=>s?new Date(s*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';
function notice(text,error=false){$('notice').textContent=text;$('notice').className=error?'error':'';show('notice',true);}
function tab(id){document.querySelectorAll('.tab').forEach(e=>e.hidden=e.id!==id);document.querySelectorAll('nav button').forEach(e=>e.classList.toggle('active',e.dataset.tab===id));}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab));
function list(id,rows){const dl=$(id);dl.replaceChildren();for(const [key,val] of rows){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=value(val);dl.append(dt,dd);}}
function current(){return state?.cameras.find(c=>c.id===selected);}
async function action(name,data={},message='Saved.'){
 if(busy)return;busy=true;render();notice('Working…');
 try{const response=await fetch(`/api/${name}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||'Request failed');state=result;notice(message);render();return true;}catch(error){notice(error.message,true);return false;}finally{busy=false;render();}
}
function render(){
 if(!state)return;
 $('connection').textContent='LOCAL DASHBOARD · CONNECTED';
 $('account-summary').textContent=`Blink account / ${state.account.status.replaceAll('_',' ')}`;
 $('catalog-time').textContent=state.account.updated?`Cloud metadata refreshed ${stamp(state.account.updated)}`:'Cloud metadata not refreshed yet';
 $('runtime-summary').textContent=Object.entries(state.runtime).map(([k,v])=>`${k} ${v?'ready':'missing'}`).join(' · ');
 $('account-message').textContent=state.account.message;
 show('verify-form',state.account.status==='two_factor');
 if(document.activeElement!==$('host-form').elements.host)$('host-form').elements.host.value=state.host;
 const catalog=$('catalog');const signature=JSON.stringify(state.catalog);
 if(catalog.dataset.signature!==signature){catalog.dataset.signature=signature;catalog.replaceChildren(new Option('Choose a discovered camera…',''));state.catalog.forEach((c,i)=>catalog.add(new Option(`${c.name} · ${c.product||c.type||'Blink'}`,String(i))));}
 if(!state.cameras.some(c=>c.id===selected))selected=state.cameras[0]?.id;
 show('empty',state.cameras.length===0);show('detail',!!selected);
 const tbody=$('camera-rows');tbody.replaceChildren();
 for(const c of state.cameras){const row=document.createElement('tr');row.className=c.id===selected?'selected':'';const t=c.telemetry, fresh=state.time-(t.incoming_at||0)<10&&c.running;
 const fields=[c.name,c.phase,fresh&&c.publishing?'Publishing':c.publishing?'Publishing':'No fresh video',c.running&&t.session_started?duration(state.time-t.session_started):'—',fresh?`${Number(t.incoming_mbps||0).toFixed(2)} Mbps`:'—',c.onvif_running?'Service running':'Disabled'];
 fields.forEach((text,i)=>{const td=document.createElement('td');if(i===0){const button=document.createElement('button');button.textContent=text;button.onclick=()=>{if(selected!==c.id){show('picture',false);show('picture-placeholder',true);$('picture-time').textContent='Snapshot preview · live video is available in VLC and Protect.';}selected=c.id;render();};td.append(button);}else{if(i===1||i===2){const dot=document.createElement('span');dot.className='dot '+((i===1?fresh:c.publishing)?'live':c.running?'wait':'');td.append(dot);}td.append(document.createTextNode(text));}row.append(td);});tbody.append(row);}
 const c=current();if(c){const t=c.telemetry, cloud=cameraSummary(c,state.account.updated), fresh=c.running&&state.time-(t.incoming_at||0)<10;
 $('camera-title').textContent=c.name;$('local-url').value=c.local_url;$('lan-url').value=c.lan_url;
 list('incoming', [['Extended entitlement',(state.account.extended_entitlement||'unknown').replaceAll('_',' ')],['Camera / firmware',cloud.camera],['Cloud camera status',cloud.online==null?'Unknown':cloud.online?'Online at last refresh':'Offline at last refresh'],['Wi-Fi signal',cloud.wifi],['Requested → granted mode',`${c.mode} → ${t.granted_mode||'awaiting session'}`],['Advertised session limit',t.advertised_duration?duration(t.advertised_duration):'Unknown'],['Session / previous duration',`${t.sessions||0} / ${duration(t.previous_session_seconds)}`],['Received this session',t.incoming_bytes==null?'—':`${(t.incoming_bytes/1048576).toFixed(1)} MiB`],['Last incoming media',fresh?`${duration(state.time-t.incoming_at)} ago`:'No fresh measurement'],['Battery / power',cloud.battery],['Temperature',cloud.temperature],['Camera settings refreshed',cloud.settingsUpdated?stamp(cloud.settingsUpdated):'Not loaded']]);
 list('outgoing',[['Local video',c.publishing?'Fresh encoded frames':c.phase],['Configured video profile','H.264 baseline · 1280 × 720 · 15 fps'],['Encoder speed / measured FPS',c.publishing?`${t.output?.speed??'—'} / ${t.output?.fps??'—'}`:'—'],['Frames in this session',c.publishing?t.output?.frame:'—'],['Encoder target bitrate','2.048 Mbps (configured)'],['Transport / audio','RTSP over TCP / off'],['Last measured interruption',duration(t.last_gap)],['Next renewal attempt',c.running&&t.retry_at&&t.retry_at>state.time?`in ${duration(t.retry_at-state.time)}`:'—']]);
 list('onvif-info',[['Service endpoint',c.onvif_url],['Status',c.onvif_running?'Process running · check adoption in Protect':'Disabled'],['Stable identity',c.uuid],['MAC address',c.mac]]);
 $('onvif-toggle').textContent=c.onvif_running?'Stop ONVIF':'Enable ONVIF';$('discovery').checked=c.discovery;
 const events=$('events');events.replaceChildren();for(const e of [...(t.events||[])].reverse()){const li=document.createElement('li'),time=document.createElement('time');time.textContent=stamp(e.time);li.append(time,document.createTextNode(e.message));events.append(li);}if(!events.children.length){const li=document.createElement('li');li.textContent='Restart the stream to begin detailed telemetry.';events.append(li);}
 }
 document.querySelectorAll('button').forEach(b=>b.disabled=busy);
 if(c){$('start').disabled=busy||c.running;$('stop').disabled=busy||!c.running;$('restart').disabled=busy||!c.running;$('snapshot').disabled=busy||snapshotBusy||!c.publishing;$('discovery').disabled=busy;}
 if(typeof renderCameraSettings==='function')renderCameraSettings();
}
$('refresh').onclick=()=>action('refresh',{},'Blink camera information refreshed.');
$('login-form').onsubmit=async e=>{e.preventDefault();const f=e.target;const password=f.elements.password.value;f.elements.password.value='';await action('login',{email:f.elements.email.value,password},'Account step completed. Enter a verification code if requested.');};
$('verify-form').onsubmit=async e=>{e.preventDefault();const code=e.target.elements.code.value;e.target.elements.code.value='';await action('verify',{code},'Blink account connected. Select your camera below.');};
$('catalog').onchange=()=>{const camera=state.catalog[Number($('catalog').value)];if($('catalog').value===''||!camera)return;const f=$('camera-form');f.elements.id.value='';f.elements.name.value=camera.name;f.elements.serial.value=camera.serial||'';f.elements.path.value=camera.name.toLowerCase().replace(/[^a-z0-9_-]/g,'-').slice(0,64);f.elements.onvif_port.value=Math.max(8080,...state.cameras.map(c=>c.onvif_port))+1;};
$('camera-form').onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));if(await action('save',data,'Camera saved. Start it from Monitor.'))tab('monitor');};
$('host-form').onsubmit=async e=>{e.preventDefault();await action('host',{host:e.target.elements.host.value},'LAN address saved.');};
$('new-camera').onclick=()=>{$('camera-form').reset();$('camera-form').elements.id.value='';$('camera-form').elements.serial.value='';};
$('edit').onclick=()=>{const c=current(),f=$('camera-form');for(const name of ['id','name','serial','path','mode','onvif_port'])f.elements[name].value=c[name];tab('setup');};
for(const name of ['start','stop','restart'])$(name).onclick=()=>action(name,{id:selected},name==='stop'?'Stream stopped.':name==='restart'?'A fresh session is starting.':'Stream starting. Allow Blink a moment to respond.');
$('onvif-toggle').onclick=()=>action(current().onvif_running?'onvif-stop':'onvif-start',{id:selected},'ONVIF service updated.');
$('discovery').onchange=()=>action('discovery',{id:selected,enabled:$('discovery').checked},'Discovery updated.');
document.querySelectorAll('[data-copy]').forEach(b=>b.onclick=async()=>{try{await navigator.clipboard.writeText($(b.dataset.copy).value);notice('Stream address copied.');}catch{$(b.dataset.copy).select();notice('Select and copy the address.');}});
$('snapshot').onclick=async()=>{const id=selected;snapshotBusy=true;$('snapshot').disabled=true;try{const r=await fetch(`/api/snapshot/${id}`);if(!r.ok)throw Error('Frame capture failed. The stream may be renewing; try again shortly.');const blob=await r.blob();if(id!==selected)return;if(snapshotUrl)URL.revokeObjectURL(snapshotUrl);snapshotUrl=URL.createObjectURL(blob);$('picture').src=snapshotUrl;show('picture',true);show('picture-placeholder',false);$('picture-time').textContent=`Snapshot captured ${new Date().toLocaleTimeString()} · this is not continuous playback.`;}catch(e){notice(e.message,true);}finally{snapshotBusy=false;render();}};
async function poll(){try{const r=await fetch('/api/status');if(!r.ok)throw Error();state=await r.json();render();}catch{$('connection').textContent='DASHBOARD DISCONNECTED';}finally{setTimeout(poll,2000);}}
poll();
