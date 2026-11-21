document.getElementById('connect').addEventListener('click',async()=>{
 const status=document.getElementById('status'),button=document.getElementById('connect');button.disabled=true;
 try{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  const url=new URL(tab.url);
  if(url.origin!=='https://fantasy.premierleague.com')throw Error('Open the official FPL tab from the local manager first.');
  const params=new URLSearchParams(url.hash.slice(1));
  const saved=(await chrome.storage.session.get(String(tab.id)))[String(tab.id)];
  const token=params.get('fpl-local')||saved?.token,port=Number(params.get('port')||saved?.port);
  if(!/^[a-f0-9]{64}$/.test(token||'')||!Number.isInteger(port)||port<1024||port>65535)throw Error('Pairing link missing. Sign in to FPL, then click Connect again in the local manager and use the new FPL tab.');
  status.textContent='Checking your signed-in account…';
  const prices=params.has('prices')?params.get('prices')==='1':saved?.prices===true;
  const results=await chrome.scripting.executeScript({target:{tabId:tab.id},world:'MAIN',args:[prices],func:async(includePrices)=>{
   // The session stays on the official website. Never return the /me response.
   const response=await fetch('/api/me/',{credentials:'same-origin',cache:'no-store'});
   if(!response.ok)return null;
   const value=await response.json();
   const reference=value?.player?.entry;
   if(!Number.isSafeInteger(reference)||reference<=0)return null;
   if(!includePrices)return reference;

   const team=await fetch(`/api/my-team/${reference}/`,{credentials:'same-origin',cache:'no-store'});
   if(!team.ok)return {reference};
   const squad=await team.json();
   if(!Array.isArray(squad.picks)||squad.picks.length!==15)return {reference};
   const salePrices={};
   for(const {element,selling_price} of squad.picks){
    if(!Number.isSafeInteger(element)||element<=0||!Number.isSafeInteger(selling_price)||selling_price<=0||element in salePrices)return {reference};
    salePrices[element]=selling_price;
   }
   return {reference,sale_prices:salePrices};
  }});
  const account=results[0]?.result;
  const reference=prices?account?.reference:account;
  if(!Number.isInteger(reference)||reference<=0)throw Error('Sign in on the official FPL site and create a team first. Then restart Connect in your local manager.');
  if(prices&&!account.sale_prices)throw Error('FPL did not return all 15 selling prices. Make sure your current squad is set up on FPL.');
  const payload=prices?{token,reference,sale_prices:account.sale_prices}:{token,reference};
  const response=await fetch(`http://127.0.0.1:${port}/api/connect/complete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const value=await response.json();if(!response.ok)throw Error(value.error||'Connection failed');
  await chrome.storage.session.remove(String(tab.id));
  status.textContent=prices?'Selling prices sent. Return to your local FPL Manager.':'Verified. Return to your local FPL Manager; your squad will load there.';
 }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
});
