'use strict';
let previewCamera=null, previewPlayer=null, previewRetry=null, previewGeneration=0;
const video=$('live-video');
function stopPreview(message='Preview stopped. The bridge stream keeps running.'){
 previewGeneration++;clearTimeout(previewRetry);previewRetry=null;previewCamera=null;
 if(previewPlayer){previewPlayer.destroy();previewPlayer=null;}
 video.pause();video.removeAttribute('src');video.load();show('live-video',false);
 show('picture-placeholder',true);show('picture',false);
 $('watch-live').textContent='Watch live';$('preview-status').textContent=message;
}
function connectPreview(generation){
 if(generation!==previewGeneration||!previewCamera)return;
 const url=`/api/preview/${encodeURIComponent(previewCamera)}/index.m3u8`;
 $('preview-status').textContent='Connecting to local video…';
 if(previewPlayer){previewPlayer.destroy();previewPlayer=null;}
 if(window.Hls&&Hls.isSupported()){
  previewPlayer=new Hls({enableWorker:false,lowLatencyMode:false,backBufferLength:0,maxBufferLength:8});
  previewPlayer.on(Hls.Events.MANIFEST_PARSED,()=>video.play().catch(()=>{$('preview-status').textContent='Press play to watch.';}));
  previewPlayer.on(Hls.Events.ERROR,(_,data)=>{if(data.fatal)retryPreview(generation);});
  previewPlayer.loadSource(url);previewPlayer.attachMedia(video);
 }else if(video.canPlayType('application/vnd.apple.mpegurl')){
  video.src=url;video.play().catch(()=>{$('preview-status').textContent='Press play to watch.';});
 }else stopPreview('This browser does not support HLS video. Use VLC or Protect.');
}
function retryPreview(generation){
 if(generation!==previewGeneration||previewRetry)return;
 $('preview-status').textContent='Waiting for video / session renewal…';
 previewRetry=setTimeout(()=>{previewRetry=null;connectPreview(generation);},5000);
}
$('watch-live').onclick=async()=>{
 if(previewCamera){stopPreview();return;}
 const id=selected,generation=++previewGeneration;previewCamera=id;
 $('watch-live').textContent='Stop preview';$('preview-status').textContent='Preparing local preview…';
 try{
  const response=await fetch('/api/preview-start',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify({id})});
  if(!response.ok)throw Error('Start the bridge stream before watching live.');
  if(generation!==previewGeneration||selected!==id)return;
  show('picture',false);show('picture-placeholder',false);show('live-video',true);
  connectPreview(generation);
 }catch(error){if(generation===previewGeneration)stopPreview(error.message);}
};
video.addEventListener('playing',()=>{$('preview-status').textContent='Live local preview · a few seconds behind · audio off';});
video.addEventListener('waiting',()=>{if(previewCamera)$('preview-status').textContent='Buffering / waiting for session renewal…';});
video.addEventListener('error',()=>{if(previewCamera)retryPreview(previewGeneration);});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&previewCamera)stopPreview('Preview stopped while this tab is hidden.');});
window.addEventListener('pagehide',()=>stopPreview());
