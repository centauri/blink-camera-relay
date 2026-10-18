const {test}=require('node:test');
const assert=require('node:assert/strict');
const {MultiViewPlayer,multiViewColumns}=require('../bridge/static/multiview.js');
function fixture(id='camera'){
 const timers=new Map(),instances=[];let serial=0;
 class Hls{
  static isSupported(){return true;}
  static Events={MANIFEST_PARSED:'manifest',ERROR:'error'};
  constructor(){this.handlers={};instances.push(this);}
  on(event,handler){this.handlers[event]=handler;}
  loadSource(url){this.url=url;}
  attachMedia(video){this.video=video;}
  destroy(){this.destroyed=true;}
 }
 const video={listeners:{},addEventListener(k,f){this.listeners[k]=f;},play(){return Promise.resolve();},
  pause(){this.paused=true;},removeAttribute(){delete this.src;},load(){},canPlayType(){return 'probably';}};
 const status={textContent:''};
 const deps={Hls,prepare:async()=>({ok:true}),setTimeout:f=>{timers.set(++serial,f);return serial;},clearTimeout:id=>timers.delete(id)};
 return {player:new MultiViewPlayer(video,status,id,deps),video,status,deps,instances,timers};
}
test('layouts provide stacked two, two-column three/four and growing grids',()=>{
 assert.deepEqual([1,2,3,4,5,9,10].map(multiViewColumns),[1,1,2,2,3,3,4]);
});
test('each camera owns a distinct player and stopping one leaves the other running',async()=>{
 const a=fixture('one'),b=fixture('two');await a.player.start();await b.player.start();
 assert.match(a.instances[0].url,/\/one\/index.m3u8$/);assert.match(b.instances[0].url,/\/two\/index.m3u8$/);
 a.player.stop();assert.equal(a.instances[0].destroyed,true);assert.equal(b.instances[0].destroyed,undefined);
 assert.equal(b.player.active,true);
});
test('fatal errors schedule a single retry and stop cancels it',async()=>{
 const f=fixture();await f.player.start();const error=f.instances[0].handlers.error;
 error(null,{fatal:true});error(null,{fatal:true});assert.equal(f.timers.size,1);
 f.player.stop();assert.equal(f.timers.size,0);error(null,{fatal:true});assert.equal(f.timers.size,0);
});
test('renewal retry replaces and destroys the old HLS instance',async()=>{
 const f=fixture();await f.player.start();f.instances[0].handlers.error(null,{fatal:true});
 const callback=[...f.timers.values()][0];f.timers.clear();callback();await new Promise(setImmediate);
 assert.equal(f.instances.length,2);assert.equal(f.instances[0].destroyed,true);
 f.instances[0].handlers.error(null,{fatal:true});assert.equal(f.timers.size,0);
});
test('late preparation cannot restart a stopped view',async()=>{
 const f=fixture();let resolve;f.deps.prepare=()=>new Promise(r=>resolve=r);
 const pending=f.player.start();f.player.stop();resolve({ok:true});await pending;
 assert.equal(f.instances.length,0);assert.equal(f.player.active,false);
});
test('stopped stream can retry without creating a Blink session',async()=>{
 const f=fixture();f.deps.prepare=async()=>({ok:false});await f.player.start();
 assert.equal(f.instances.length,0);assert.equal(f.timers.size,1);
 f.player.stop();assert.equal(f.timers.size,0);
});
test('native HLS fallback and unsupported browsers clean up',async()=>{
 const f=fixture();f.deps.Hls=null;await f.player.start();assert.match(f.video.src,/index.m3u8$/);
 f.player.stop();assert.equal(f.video.src,undefined);
 f.video.canPlayType=()=>'';await f.player.start();assert.equal(f.player.active,false);
 assert.match(f.status.textContent,/not supported/);
});

test('selection survives polling and stopping clears tiles without stopping bridge workers',async()=>{
 const vm=require('node:vm'),fs=require('node:fs');
 const elements=new Map(),events={};
 const element=()=>({children:[],style:{setProperty(){}},dataset:{},append(...nodes){this.children.push(...nodes);},replaceChildren(){this.children=[];},setAttribute(){},addEventListener(){},pause(){},removeAttribute(){},load(){}});
 const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
 const document={createElement:element,createTextNode:text=>({text}),addEventListener:(key,fn)=>events[key]=fn};
 const opened=[];const window={addEventListener(){},open(...args){opened.push(args);}};
 const requests=[];
 const context={document,window,$:get,state:{csrf:'demo',cameras:[{id:'one',name:'One',running:true,phase:'streaming'},{id:'two',name:'Two',running:true,phase:'streaming'}]},busy:false,AbortController,URLSearchParams,setTimeout:()=>1,clearTimeout(){},fetch:async(url,options)=>{requests.push([url,JSON.parse(options.body)]);return {ok:false};}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../bridge/static/multiview.js'),'utf8'),context);
 context.stopMultiView=window.stopMultiView;
 window.renderMultiView();
 for(const label of get('multiview-choices').children){label.children[0].checked=true;label.children[0].onchange();}
 get('multiview-window').onclick();
 assert.deepEqual(opened,[['/static/wall.html?camera=one&camera=two','_blank','popup,width=1280,height=720,noopener,noreferrer']]);
 await get('multiview-start').onclick();
 assert.equal(get('multiview-grid').children.length,2);
 assert.equal(get('multiview-grid').dataset.count,'2');
 assert.deepEqual(requests,[['/api/preview-start',{id:'one'}],['/api/preview-start',{id:'two'}]]);
 context.state.cameras[0].phase='renewing';window.renderMultiView();
 assert.ok(get('multiview-choices').children.every(label=>label.children[0].checked));
 assert.equal(get('multiview-stop').disabled,false);
 document.hidden=true;events.visibilitychange();window.renderMultiView();
 assert.equal(get('multiview-grid').children.length,0);
 assert.equal(get('multiview-stop').disabled,true);
 assert.equal(requests.length,2);
});

test('viewing window selects only requested cameras, refreshes CSRF and cleans up on close',async()=>{
 const vm=require('node:vm'),fs=require('node:fs'),elements=new Map(),events={},players=[],requests=[];
 const element=()=>({children:[],dataset:{},style:{setProperty(){}},append(...nodes){this.children.push(...nodes);},replaceChildren(){this.children=[];},setAttribute(){},addEventListener(){}});
 const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id);};
 class Player{constructor(video,status,id,deps){Object.assign(this,{id,deps});players.push(this);}async start(){await this.deps.prepare(this.id);}stop(){this.stopped=true;}}
 const document={getElementById:get,createElement:element,body:{classList:{add(){},remove(){}}},addEventListener(){}};
 let token=0;
 const context={document,location:{search:'?camera=two&camera=two&camera=missing'},URLSearchParams,MultiViewPlayer:Player,multiViewColumns,window:{addEventListener:(k,fn)=>events[k]=fn},setTimeout:()=>1,clearTimeout(){},fetch:async(url,options)=>{
  requests.push([url,options]);return {ok:true,json:async()=>({csrf:`token-${++token}`,cameras:[{id:'one',name:'One'},{id:'two',name:'Two'}]})};
 }};
 vm.createContext(context);vm.runInContext(fs.readFileSync(require.resolve('../bridge/static/wall.js'),'utf8'),context);await new Promise(setImmediate);
 assert.deepEqual(players.map(p=>p.id),['two']);assert.equal(get('wall').children.length,1);
 const post=requests.find(([url])=>url==='/api/preview-start')[1];
 assert.equal(post.headers['X-CSRF-Token'],'token-2');assert.equal(JSON.parse(post.body).id,'two');
 events.pagehide();assert.equal(players[0].stopped,true);assert.equal(get('wall').children.length,0);
});

test('viewing window does not initialize dashboard UI',()=>{
 const vm=require('node:vm'),fs=require('node:fs');
 const context={document:{documentElement:{hasAttribute:()=>true}}};
 vm.createContext(context);
 assert.doesNotThrow(()=>vm.runInContext(fs.readFileSync(require.resolve('../bridge/static/multiview.js'),'utf8'),context));
});
