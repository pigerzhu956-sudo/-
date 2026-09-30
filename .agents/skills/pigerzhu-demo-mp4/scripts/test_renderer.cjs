// Synthetic behavioral checks; does not use any previous project or private template.
const assert=require('assert'),{chromium}=require('playwright'),{installMotion}=require('./render.cjs');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:process.argv[2]||process.env.PIGERZHU_CHROME||undefined});
 try{
  const p=await b.newPage({viewport:{width:640,height:360}});
  await p.setContent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#c9dce5"/><g id="retained" data-at="0"><text x="30" y="60">Retained</text></g><g id="new" data-at="1000"><path data-role="emphasis" d="M30 80H230V120H30Z" fill="#e6f01f"/><text x="30" y="110">New</text></g><g id="before-swap" data-at="1500" data-until="2000"><text x="30" y="180">Before</text></g><g id="after-swap" data-at="2000"><text x="30" y="180">After</text></g></svg>');
  await p.evaluate(installMotion,{start_ms:0,end_ms:3000});
  const at=t=>p.evaluate(t=>window.renderSourceTime(t),t);
  let s=await at(999);assert(s[0].visible&&!s[1].visible);
  s=await at(1225);assert(s[0].progress===1&&s[1].progress>0);const a=await p.screenshot();
  const width=await p.locator('clipPath rect').first().getAttribute('width');assert(Math.abs(+width-101)<.001);
  await at(2999);await at(0);await at(1225);assert(a.equals(await p.screenshot()),'Absolute seek must be history-independent');
  s=await at(2000);assert(!s[2].visible&&s[3].visible&&s[3].progress===1,'Swap must have no blank interval');
  await at(2500);assert.equal(await p.locator('[data-role="emphasis"]').getAttribute('clip-path'),null,'Completed brush removes clip');
  console.log('5 renderer checks passed: pre-event, retained state, half brush, repeatable seeking, gapless swap/stable brush.');
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exit(1)});
