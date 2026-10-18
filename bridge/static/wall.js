"use strict";
const wall=document.getElementById('wall'),message=document.getElementById('message');
const ids=[...new Set(new URLSearchParams(location.search).getAll('camera'))];
let players=[],generation=0,retryTimer,idleTimer;
function stopWall(){generation++;clearTimeout(retryTimer);for(const p of players)p.stop();players=[];wall.replaceChildren();}
async function startWall(){
 stopWall();const run=generation;
 if(!ids.length){message.hidden=false;message.textContent='No cameras selected. Choose cameras in Multi-view and open a viewing window.';return;}
 try{
  const response=await fetch('/api/status',{cache:'no-store'});
  if(!response.ok)throw Error('Dashboard unavailable');
  const state=await response.json();if(run!==generation)return;
  const cameras=ids.map(id=>state.cameras.find(c=>c.id===id)).filter(Boolean);
  if(!cameras.length){message.hidden=false;message.textContent='The selected cameras are no longer configured.';return;}
  message.hidden=true;
  const columns=multiViewColumns(cameras.length);
  wall.dataset.count=String(cameras.length);wall.style.setProperty('--columns',columns);
  wall.style.setProperty('--rows',Math.ceil(cameras.length/columns));
  for(const camera of cameras){
   if(run!==generation)return;
   const tile=document.createElement('section'),video=document.createElement('video'),status=document.createElement('p');
   video.muted=true;video.playsInline=true;video.setAttribute('aria-label',camera.name);video.tabIndex=0;
   status.setAttribute('role','status');tile.append(video,status);wall.append(tile);
   const player=new MultiViewPlayer(video,status,camera.id,{Hls:window.Hls,
    setTimeout:(fn,ms)=>setTimeout(fn,ms),clearTimeout:id=>clearTimeout(id),
    prepare:async(id,signal)=>{
     status.hidden=false;
     const response=await fetch('/api/status',{signal,cache:'no-store'});
     if(!response.ok)return response;
     const current=await response.json();
     return fetch('/api/preview-start',{method:'POST',signal,headers:{'Content-Type':'application/json','X-CSRF-Token':current.csrf},body:JSON.stringify({id})});
    }});
   video.addEventListener('playing',()=>{status.hidden=true;});
   video.addEventListener('waiting',()=>{status.hidden=false;});
   video.addEventListener('error',()=>{status.hidden=false;});
   const play=()=>video.play().catch(()=>{status.hidden=false;status.textContent='Select this camera to resume playback.';});
   video.onclick=play;video.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();play();}};
   players.push(player);await player.start();
  }
 }catch(error){if(run!==generation)return;message.hidden=false;message.textContent='Cannot reach the dashboard. Retrying…';retryTimer=setTimeout(startWall,5000);}
}
async function fullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{message.hidden=false;message.textContent='Fullscreen is unavailable. Use your browser’s fullscreen command.';}}
document.getElementById('fullscreen').onclick=fullscreen;wall.ondblclick=fullscreen;
function activity(){document.body.classList.remove('idle');clearTimeout(idleTimer);idleTimer=setTimeout(()=>document.body.classList.add('idle'),2500);}
document.addEventListener('pointermove',activity);document.addEventListener('keydown',activity);activity();
window.addEventListener('pagehide',()=>{stopWall();clearTimeout(idleTimer);});
window.addEventListener('pageshow',e=>{if(e.persisted){activity();startWall();}});
startWall();
