// Offline protocol checks; no signed-in account or browser session is used.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const picks=Array.from({length:15},(_,i)=>({element:i+1,selling_price:42+i,purchase_price:900}));
async function popup({squad=picks,url='https://fantasy.premierleague.com/',reference=123,saved={token:'a'.repeat(64),port:7878},ok=true}={}){
 let click,posted,removed;const status={textContent:''},button={disabled:false,addEventListener:(_,cb)=>click=cb};
 const chrome={tabs:{query:async()=>[{id:7,url}]},storage:{session:{get:async()=>({'7':saved}),remove:async key=>removed=key}},scripting:{executeScript:async request=>{
  assert.equal(request.world,'MAIN');
  // Exercise the injected function with a synthetic /api/me/ response and check it only returns entry.
  const injected=vm.runInNewContext('('+request.func.toString()+')',{fetch:async(path,options)=>{
   assert.equal(options.credentials,'same-origin');
   if(path==='/api/me/')return {ok:true,json:async()=>({player:{entry:reference,email:'must-not-leave-official-page'}})};
   assert.equal(path,`/api/my-team/${reference}/`);
   return {ok:true,json:async()=>({picks:squad,transfers:{bank:5}})};
  }});
  return [{result:await injected(...request.args)}];
 }}};
 const sandbox={URL,URLSearchParams,chrome,document:{getElementById:id=>id==='connect'?button:status},fetch:async(url,request)=>{
  posted={url,body:JSON.parse(request.body)};return {ok,json:async()=>ok?{connected:true}:{error:'Manager name did not match'}};
 }};
 vm.runInNewContext(fs.readFileSync('browser-connector/popup.js','utf8'),sandbox);
 await click();return {posted,removed,message:status.textContent,disabled:button.disabled};
}
(async()=>{
 const good=await popup();assert.deepEqual(good.posted.body,{token:'a'.repeat(64),reference:123});
 assert.equal(good.posted.url,'http://127.0.0.1:7878/api/connect/complete');assert.equal(good.removed,'7');assert.match(good.message,/Verified/);assert.equal(good.disabled,false);
 assert.equal((await popup({url:'https://evil.test/'})).posted,undefined);
 assert.equal((await popup({saved:{token:'bad',port:7878}})).posted,undefined);
 assert.equal((await popup({reference:null})).posted,undefined);
 assert.match((await popup({ok:false})).message,/Manager name did not match/);
 const priceLink={token:'a'.repeat(64),port:7878,prices:true};
 const imported=await popup({saved:priceLink});
 assert.deepEqual(imported.posted.body,{token:priceLink.token,reference:123,sale_prices:Object.fromEntries(picks.map(p=>[p.element,p.selling_price]))});
 assert.match(imported.message,/Selling prices sent/);
 for(const squad of [picks.slice(1),[...picks.slice(1),picks[1]]]){
  const invalid=await popup({saved:priceLink,squad});
  assert.equal(invalid.posted,undefined);
  assert.match(invalid.message,/all 15 selling prices/);
 }
 let listener,stored;vm.runInNewContext(fs.readFileSync('browser-connector/background.js','utf8'),{chrome:{runtime:{onMessage:{addListener:cb=>listener=cb}},storage:{session:{set:value=>stored=value,remove:()=>{}}},tabs:{onRemoved:{addListener:()=>{}}}}});
 listener({type:'pair',token:'a'.repeat(64),port:7878},{origin:'https://evil.test',tab:{id:7}});assert.equal(stored,undefined);
 listener({type:'pair',token:'a'.repeat(64),port:7878,prices:true},{origin:'https://fantasy.premierleague.com',tab:{id:7}});assert.equal(stored['7'].port,7878);assert.equal(stored['7'].prices,true);
 let captured,replaced;vm.runInNewContext(fs.readFileSync('browser-connector/capture.js','utf8'),{URLSearchParams,location:{hash:'#fpl-local='+'a'.repeat(64)+'&port=7878&prices=1',pathname:'/',search:''},history:{replaceState:(_,__,value)=>replaced=value},chrome:{runtime:{sendMessage:value=>captured=value}}});assert.equal(captured.token,'a'.repeat(64));assert.equal(replaced,'/');assert.equal(captured.prices,true);
 console.log('Browser helper: verification and selling-price protocol checks passed; live account/Windows browser not tested.');
})().catch(error=>{console.error(error);process.exit(1);});
