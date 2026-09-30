// Deterministic layer renderer. Imports SVG data only, never the source HTML's scripts.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{pathToFileURL,fileURLToPath}=require('url'),{spawn}=require('child_process'),{once}=require('events');
const {chromium}=require('playwright');
function args(argv){const a={};for(let i=0;i<argv.length;i+=2){if(!argv[i].startsWith('--')||argv[i+1]===undefined)throw Error('Expected --key value');a[argv[i].slice(2)]=argv[i+1]}return a}
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const esc=s=>s.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');

function svgData(source,approvedPng){
 const raw=fs.readFileSync(source,'utf8'),m=raw.match(/<svg\b[\s\S]*<\/svg>/i);
 if(!m)throw Error('Editable source needs reconstructed SVG layers: '+source);
 let svg=m[0];
 if(/<script\b|<foreignObject\b|\son\w+\s*=|javascript:|<animate\b|<set\b/i.test(svg))throw Error('Active source content refused; rebuild as passive layers');
 if(!/data-at=/.test(svg))throw Error('Source has no semantic absolute event anchors; agent must annotate a new source copy');
 svg=svg.replace(/\b(?:xlink:)?href="([^"]+)"/g,(all,value)=>{
  if(value.startsWith('#'))return all;
  const url=new URL(value,pathToFileURL(source));
  if(url.protocol!=='file:')throw Error('Only local SVG assets supported: '+value);
  if(!fs.existsSync(fileURLToPath(url)))throw Error('Missing SVG asset: '+value);
  if(approvedPng&&path.resolve(fileURLToPath(url))===path.resolve(approvedPng))throw Error('Flattened approved PNG cannot be used as an animation layer');
  return 'href="'+esc(url.href)+'"';
 });
 for(const m of svg.matchAll(/url\(['"]?([^)'"\s]+)['"]?\)/g))if(/^https?:/.test(m[1]))throw Error('Remote font/style refused; save verified local dependency');
 return svg;
}

// Serialized into our own generated viewer, independent of all original source scripts.
function installMotion(shot){
 const svg=document.querySelector('svg'),ns='http://www.w3.org/2000/svg';
 const groups=[...svg.querySelectorAll('g[data-at]')];
 if(!groups.length)throw Error('No semantic groups');
 const ids=new Set();for(const g of groups){if(!g.id||ids.has(g.id))throw Error('Groups require unique semantic ids');ids.add(g.id)}
 for(const g of groups)g.style.display='inline';
 const ends=new Set(groups.filter(g=>g.dataset.until).map(g=>+g.dataset.until));
 const defs=document.createElementNS(ns,'defs');svg.prepend(defs);
 const events=groups.map(g=>{
  const at=+g.dataset.at,until=g.dataset.until?+g.dataset.until:null;
  if(!Number.isFinite(at)||(until!==null&&until<=at)||at>=shot.end_ms)throw Error('Invalid event '+g.id);
  const duration=(g.dataset.motion==='hold'||at<=shot.start_ms||ends.has(at))?0:Number(g.dataset.duration||240);
  if(!Number.isFinite(duration)||duration<0)throw Error('Invalid duration');
  const brushes=[...g.querySelectorAll('[data-role="emphasis"]')].filter(e=>e.closest('g[data-at]')===g).map((e,i)=>{
   const b=e.getBBox(),clip=document.createElementNS(ns,'clipPath'),rect=document.createElementNS(ns,'rect');clip.id='motion-'+g.id+'-'+i;clip.setAttribute('clipPathUnits','userSpaceOnUse');
   rect.setAttribute('x',b.x-1);rect.setAttribute('y',b.y-1);rect.setAttribute('height',b.height+2);clip.append(rect);defs.append(clip);
   return {e,rect,width:b.width+2,clip:clip.id,original:e.getAttribute('clip-path')};
  });
  const lines=[...g.querySelectorAll('line[data-role="connectors"],path[data-role="chart-line"]')].filter(e=>e.closest('g[data-at]')===g).map(e=>({e,length:e.getTotalLength(),dash:e.getAttribute('stroke-dasharray'),offset:e.getAttribute('stroke-dashoffset')}));
  return {g,at,until,duration,brushes,lines,opacity:g.style.opacity};
 });
 function attr(e,k,v){if(v===null)e.removeAttribute(k);else e.setAttribute(k,v)}
 window.renderSourceTime=async t=>{
  for(const x of events){
   const visible=t>=x.at&&(x.until===null||t<x.until),p=x.duration?Math.max(0,Math.min(1,(t-x.at)/x.duration)):1;
   x.g.style.display=visible?'inline':'none';x.g.style.opacity=visible&&p<1?String(p):x.opacity;
   for(const b of x.brushes){const q=x.at<=shot.start_ms?1:Math.max(0,Math.min(1,(t-x.at)/450));if(q===1)attr(b.e,'clip-path',b.original);else{b.e.setAttribute('clip-path','url(#'+b.clip+')');b.rect.setAttribute('width',b.width*q)}}
   for(const l of x.lines){if(p===1){attr(l.e,'stroke-dasharray',l.dash);attr(l.e,'stroke-dashoffset',l.offset)}else{l.e.setAttribute('stroke-dasharray',l.length);l.e.setAttribute('stroke-dashoffset',l.length*(1-p))}}
  }
  window.sourceTime=t;
  return events.map(x=>({id:x.g.id,visible:x.g.style.display!=='none',progress:x.duration?Math.max(0,Math.min(1,(t-x.at)/x.duration)):1}));
 };
 window.motionEvents=events.map(x=>({id:x.g.id,at:x.at,until:x.until,duration:x.duration,brushes:x.brushes.length}));
}

async function main(a){
 if(!a.manifest||!a.out||!['frames','video'].includes(a.mode||'video'))throw Error('Usage: --manifest parsed.json --out new-directory --mode frames|video [--chrome path] [--ffmpeg path] [--times seconds,...]');
 const manifest=path.resolve(a.manifest),m=JSON.parse(fs.readFileSync(manifest));
 for(const [f,h] of [[m.document,m.document_sha256],[m.audio,m.audio_sha256],[m.srt,m.srt_sha256]])if(hash(f)!==h)throw Error('Source changed since parse: '+f);
 const root=path.resolve(a.out);if(fs.existsSync(root))throw Error('Output exists; use a new directory');fs.mkdirSync(root,{recursive:true});fs.mkdirSync(path.join(root,'source'));
 const selected=m.shots.filter(s=>s.end_ms>m.range.start_ms&&s.start_ms<m.range.end_ms),wrappers=new Map();
 for(const s of selected){
  let html;
  if(s.video){
   const v=s.video;html=`<!doctype html><meta charset="utf-8"><style>body{margin:0}video{display:block;width:1920px;height:1080px;object-fit:cover}</style><video muted preload="auto" src="${esc(pathToFileURL(v.file).href)}"></video><script>window.motionEvents=[];window.renderSourceTime=async t=>{const v=document.querySelector('video');v.pause();v.muted=true;if(v.readyState<1)await new Promise((r,j)=>{v.addEventListener('loadedmetadata',r,{once:true});v.addEventListener('error',j,{once:true})});const target=(${v.in_ms}+t-${s.start_ms})/1000;if(target>=v.duration)throw Error('Footage out of bounds');if(Math.abs(v.currentTime-target)>.000001)await new Promise(r=>{v.addEventListener('seeked',r,{once:true});v.currentTime=target});return [{video:true,time:v.currentTime,muted:v.muted}]};</script>`;
  }else{
   const svg=svgData(s.editable,s.png);
   html=`<!doctype html><meta charset="utf-8"><style>body{margin:0}svg{display:block}*{animation:none!important;transition:none!important}</style>${svg}<script>(${installMotion.toString()})(${JSON.stringify({start_ms:s.start_ms,end_ms:s.end_ms})});</script>`;
  }
  const dest=path.join(root,'source','shot-'+s.id+'.html');fs.writeFileSync(dest,html);wrappers.set(s.id,dest);
 }
 const browser=await chromium.launch({headless:true,executablePath:a.chrome||process.env.PIGERZHU_CHROME||undefined,args:['--allow-file-access-from-files','--disable-gpu']});
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});await page.route(/^https?:/,r=>r.abort());
 let current=null;const events={},errors=[];page.on('pageerror',e=>errors.push(e.message));
 async function frame(t){
  const s=selected.find(x=>x.start_ms<=t&&t<x.end_ms);if(!s)throw Error('No shot at '+t);
  if(current!==s.id){await page.goto(pathToFileURL(wrappers.get(s.id)).href,{waitUntil:'load'});await page.evaluate(()=>document.fonts.ready);current=s.id;events[s.id]=await page.evaluate(()=>window.motionEvents)}
  const state=await page.evaluate(t=>window.renderSourceTime(t),t);if(errors.length)throw Error(errors.join('\n'));
  return {image:await page.screenshot({animations:'disabled'}),shot:s.id,state};
 }
 let encoder=null,encoderDone=null;const report={manifest,range:m.range,frames:[],events,engine:'absolute-time SVG/Chromium + FFmpeg',width:1920,height:1080,fps:m.fps};
 try{
  for(const s of selected){await frame(Math.max(s.start_ms,m.range.start_ms))}
  if((a.mode||'video')==='frames'){
   let times=a.times?a.times.split(',').map(v=>Math.round(Number(v)*1000)):selected.flatMap(s=>[Math.max(s.start_ms,m.range.start_ms),s.end_ms-1,...events[s.id].flatMap(e=>[e.at-1,e.at+Math.max(e.duration,450)/2,e.at+Math.max(e.duration,450)+1])]);
   times=[...new Set(times)].filter(t=>t>=m.range.start_ms&&t<m.range.end_ms).sort((a,b)=>a-b);
   for(const t of times){const f=await frame(t),file=path.join(root,`frame-${String(Math.round(t)).padStart(9,'0')}.png`);fs.writeFileSync(file,f.image);report.frames.push({source_ms:t,file,shot:f.shot,state:f.state})}
  }else{
   const duration=(m.range.end_ms-m.range.start_ms)/1000,n=Math.ceil(duration*m.fps),output=path.join(root,'animation.mp4');let stderr='';
   encoder=spawn(a.ffmpeg||'ffmpeg',['-hide_banner','-loglevel','error','-n','-f','image2pipe','-framerate',String(m.fps),'-vcodec','png','-i','pipe:0','-ss',String(m.range.start_ms/1000),'-t',String(duration),'-i',m.audio,'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r',String(m.fps),'-c:a','aac','-b:a','192k','-t',String(duration),'-movflags','+faststart',output],{windowsHide:true});
   encoder.stderr.on('data',d=>stderr+=d);encoder.stdin.on('error',()=>{});
   encoderDone=new Promise((resolve,reject)=>{encoder.on('error',reject);encoder.on('close',code=>code===0?resolve():reject(Error('FFmpeg '+code+': '+stderr)))});encoderDone.catch(()=>{});
   for(let i=0;i<n;i++){const t=m.range.start_ms+i*1000/m.fps,f=await frame(t);if(!encoder.stdin.write(f.image))await Promise.race([once(encoder.stdin,'drain'),encoderDone.then(()=>{throw Error('Encoder closed early')})]);if(i===0||i===n-1){const file=path.join(root,`frame-${i}.png`);fs.writeFileSync(file,f.image);report.frames.push({frame:i,source_ms:t,file,shot:f.shot,state:f.state})}if(i%30===0)console.log(`Frame ${i}/${n}`)}
   encoder.stdin.end();await encoderDone;report.output=output;report.frame_count=n;report.quantization_ms=n*1000/m.fps-(m.range.end_ms-m.range.start_ms);
  }
 }finally{await browser.close();if(encoder&&encoder.exitCode===null)encoder.kill()}
 fs.writeFileSync(path.join(root,'render-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({out:root,frames:report.frame_count||report.frames.length,output:report.output}));
}
if(require.main===module)main(args(process.argv.slice(2))).catch(e=>{console.error(e);process.exit(1)});
module.exports={svgData,installMotion};
