'use strict';
// Each tile owns its player, request and retry timer. Stale callbacks cannot restart it.
class MultiViewPlayer {
 constructor(video, status, id, deps){
  Object.assign(this,{video,status,id,deps,generation:0,player:null,timer:null,request:null,active:false});
  video.addEventListener('playing',()=>{if(this.active)status.textContent='Live local preview · audio off';});
  video.addEventListener('waiting',()=>{if(this.active)status.textContent='Buffering / session renewal…';});
  video.addEventListener('error',()=>{if(this.active)this.retry(this.generation);});
 }
 stop(){
  this.active=false;this.generation++;this.deps.clearTimeout(this.timer);this.timer=null;
  this.request?.abort();this.request=null;this.player?.destroy();this.player=null;
  this.video.pause();this.video.removeAttribute('src');this.video.load();
 }
 retry(generation){
  if(!this.active||generation!==this.generation||this.timer!==null)return;
  this.status.textContent='Waiting for local stream / renewal…';
  this.timer=this.deps.setTimeout(()=>{this.timer=null;if(this.active&&generation===this.generation)this.start();},5000);
 }
 async start(){
  this.stop();this.active=true;const generation=this.generation;
  this.status.textContent='Connecting…';this.request=new AbortController();
  try{
   const response=await this.deps.prepare(this.id,this.request.signal);
   if(!this.active||generation!==this.generation)return;
   if(!response.ok){this.retry(generation);return;}
   const url=`/api/preview/${encodeURIComponent(this.id)}/index.m3u8`,Hls=this.deps.Hls;
   const play=()=>{if(this.active&&generation===this.generation)this.video.play().catch(()=>{
    if(this.active&&generation===this.generation)this.status.textContent='Press play to watch.';
   });};
   if(Hls&&Hls.isSupported()){
    this.player=new Hls({enableWorker:false,lowLatencyMode:false,backBufferLength:0,maxBufferLength:8});
    this.player.on(Hls.Events.MANIFEST_PARSED,play);
    this.player.on(Hls.Events.ERROR,(_,data)=>{if(data.fatal)this.retry(generation);});
    this.player.loadSource(url);this.player.attachMedia(this.video);
   }else if(this.video.canPlayType('application/vnd.apple.mpegurl')){
    this.video.src=url;play();
   }else{this.stop();this.status.textContent='HLS playback is not supported by this browser.';}
  }catch(error){if(error.name!=='AbortError')this.retry(generation);}
 }
}
function multiViewColumns(count){return count<=2?1:Math.ceil(Math.sqrt(count));}
if(typeof module!=='undefined')module.exports={MultiViewPlayer,multiViewColumns};
if(typeof document!=='undefined'){
 let players=new Map(),generation=0,signature='';
 const choices=new Set();
 window.stopMultiView=(message='View stopped. Bridge streams keep running.')=>{
  generation++;for(const player of players.values())player.stop();players.clear();
  $('multiview-grid').replaceChildren();$('multiview-status').textContent=message;
  $('multiview-stop').disabled=true;$('multiview-start').disabled=busy||!choices.size;
 };
 window.renderMultiView=()=>{
  const cameras=state?.cameras||[],ids=new Set(cameras.map(c=>c.id));
  for(const id of choices)if(!ids.has(id))choices.delete(id);
  if([...players.keys()].some(id=>!ids.has(id)))stopMultiView('Camera list changed. Select cameras and launch again.');
  const next=JSON.stringify(cameras.map(c=>[c.id,c.name,c.running,c.phase]));
  if(next!==signature){signature=next;$('multiview-choices').replaceChildren();
   for(const camera of cameras){
    const label=document.createElement('label');label.className='check';
    const input=document.createElement('input');input.type='checkbox';input.checked=choices.has(camera.id);
    input.onchange=()=>{if(input.checked)choices.add(camera.id);else choices.delete(camera.id);
     $('multiview-start').disabled=busy||!choices.size;
    };
    label.append(input,document.createTextNode(`${camera.name} · ${camera.running?camera.phase:'stopped'}`));
    $('multiview-choices').append(label);
   }
   $('multiview-empty').hidden=cameras.length>0;
  }
  $('multiview-start').disabled=busy||!choices.size;
  $('multiview-stop').disabled=!players.size;
 };
 $('multiview-start').onclick=async()=>{
  stopMultiView();const run=generation;
  const cameras=state.cameras.filter(c=>choices.has(c.id)),grid=$('multiview-grid');
  grid.dataset.count=String(cameras.length);grid.style.setProperty('--view-columns',multiViewColumns(cameras.length));
  $('multiview-status').textContent=`${cameras.length} selected · local streams · a few seconds behind`;
  $('multiview-stop').disabled=false;
  for(const camera of cameras){
   if(run!==generation)return;
   const tile=document.createElement('section');tile.className='multiview-tile';
   const heading=document.createElement('h2');heading.textContent=camera.name;
   const video=document.createElement('video');video.muted=true;video.playsInline=true;video.controls=true;
   video.setAttribute('aria-label',`${camera.name} live preview`);
   const status=document.createElement('p');status.className='caption';status.setAttribute('role','status');
   tile.append(heading,video,status);grid.append(tile);
   const player=new MultiViewPlayer(video,status,camera.id,{Hls:window.Hls,setTimeout:(fn,ms)=>setTimeout(fn,ms),clearTimeout:id=>clearTimeout(id),
    prepare:(id,signal)=>fetch('/api/preview-start',{method:'POST',signal,
     headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify({id})})});
   players.set(camera.id,player);await player.start();
  }
 };
 $('multiview-stop').onclick=()=>stopMultiView();
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stopMultiView('View stopped while this tab is hidden. Launch to resume.');});
 window.addEventListener('pagehide',()=>stopMultiView());
}
