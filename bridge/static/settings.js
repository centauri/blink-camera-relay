'use strict';
let settingsSignature='';
function settingsValue(v){return v===null||v===undefined?'Unavailable':typeof v==='object'?JSON.stringify(v):typeof v==='boolean'?(v?'Yes':'No'):String(v);}
function renderCameraSettings(){
 const camera=current(), data=camera?.device_settings;
 const picker=$('settings-camera');
 const names=JSON.stringify(state.cameras.map(c=>[c.id,c.name]));
 if(picker.dataset.names!==names){picker.dataset.names=names;picker.replaceChildren();state.cameras.forEach(c=>picker.add(new Option(c.name,c.id)));}
 picker.value=selected||'';picker.disabled=busy;
 $('settings-read').disabled=busy||!camera;
 $('settings-status').textContent=data?`Read from camera ${stamp(data.updated)} · ${data.controls.filter(c=>c.writable).length} editable settings · ${Object.keys(data.values).length} reported fields`:'Load the camera configuration to see its supported options.';
 $('settings-result').textContent=data?.verification?`${data.verification.key}: ${data.verification.result} (${stamp(data.verification.time)})`:data?.message||'';
 const sig=JSON.stringify([selected,data]);
 if(sig!==settingsSignature){
  settingsSignature=sig;
  const container=$('settings-fields');container.replaceChildren();
  const groups=[...new Set((data?.controls||[]).map(c=>c.group))];
  for(const group of groups){
   const section=document.createElement('section');section.className='settings-group';
   const title=document.createElement('h2');title.textContent=group;section.append(title);
   for(const row of data.controls.filter(c=>c.group===group)){
    const form=document.createElement('form');form.className='setting-row';
    const label=document.createElement('label');label.textContent=row.label;
    const help=document.createElement('small');help.textContent=row.note||row.evidence;label.append(help);
    const isBoolean=row.choices?.length===2&&row.choices.every(v=>typeof v==='boolean');
    const isRange=row.writable&&!row.choices&&Number.isFinite(row.minimum)&&Number.isFinite(row.maximum);
    const input=row.choices&&!isBoolean?document.createElement('select'):document.createElement('input');
    input.id='device-setting-'+row.key;label.htmlFor=input.id;
    help.id=input.id+'-help';input.setAttribute('aria-describedby',help.id);
    let control=input;
    if(isBoolean||isRange){
     control=document.createElement('div');control.className=isBoolean?'boolean-control':'range-control';
     const output=document.createElement('output');output.htmlFor=input.id;
     if(isBoolean){input.type='checkbox';input.checked=row.value===true;}
     else{input.type='range';input.min=row.minimum;input.max=row.maximum;input.step=1;input.value=row.value;}
     const refreshValue=()=>{output.textContent=isBoolean?(input.checked?'On':'Off'):input.value+(row.key==='retrigger_time'?' s':'');if(isRange)input.setAttribute('aria-valuetext',output.textContent);};
     input.addEventListener('input',refreshValue);refreshValue();control.append(input,output);
     if(isRange){const bounds=document.createElement('span');bounds.className='range-bounds';bounds.textContent=`${row.minimum}–${row.maximum}`;control.append(bounds);}
    }
    else if(row.choices){for(const choice of row.choices){const text=row.key==='illuminator_intensity'?({1:'Low',4:'Medium',7:'High'}[choice]||String(choice)):String(choice);const option=new Option(text,JSON.stringify(choice));input.add(option);}input.value=JSON.stringify(row.value);if(input.selectedIndex<0){input.add(new Option(settingsValue(row.value),JSON.stringify(row.value)));input.value=JSON.stringify(row.value);}}
    else{input.type='number';input.min=row.minimum;input.max=row.maximum;input.step=1;input.value=row.value;}
    input.dataset.readonly=String(!row.writable);input.disabled=!row.writable||busy;
    const button=document.createElement('button');button.type='submit';button.textContent=row.writable?'Apply':'Read only';button.dataset.settingReadonly=String(!row.writable);button.disabled=!row.writable||busy;
    form.append(label,control,button);
    form.onsubmit=async event=>{event.preventDefault();const newValue=isBoolean?input.checked:row.choices?JSON.parse(input.value):Number(input.value);if(newValue===row.value){notice('This value is already set.');return;}await action('settings-write',{id:camera.id,operation:'setting',key:row.key,value:newValue,expected:row.value},'Camera operation finished. Check the read-back result below.');};
    section.append(form);
   }
   container.append(section);
  }
  list('device-readonly',Object.entries({...data?.values,...Object.fromEntries(Object.entries(data?.zones||{}).map(([k,v])=>['zones: '+k,v]))}).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>[k.replaceAll('_',' '),settingsValue(v)]));
  list('device-metadata',Object.entries(data?.metadata||{}).map(([k,v])=>[k.replaceAll('_',' '),settingsValue(v)]));
  list('device-system',Object.entries(data?.system||{}).map(([k,v])=>[k,settingsValue(v)]));
 }
 document.querySelectorAll('[data-setting-readonly]').forEach(b=>b.disabled=busy||b.dataset.settingReadonly==='true');
 document.querySelectorAll('#settings-fields input,#settings-fields select').forEach(e=>e.disabled=busy||e.dataset.readonly==='true');
 document.querySelectorAll('[data-camera-command]').forEach(b=>b.disabled=busy||!data||(b.dataset.cameraCommand.startsWith('spotlight')&&data.values.spotlight_compatible!==true));
}
$('settings-camera').onchange=()=>{selected=$('settings-camera').value;render();};
$('settings-read').onclick=()=>action('settings-read',{id:selected},'Camera configuration loaded.');
document.querySelectorAll('[data-camera-command]').forEach(button=>button.onclick=()=>action('settings-write',{id:selected,operation:button.dataset.cameraCommand,scope_acknowledged:$('system-scope').checked},'Command finished. Check the read-back result.'));
