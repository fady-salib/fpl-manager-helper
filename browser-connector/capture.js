// Capture only the one-time local pairing fragment before the site's router runs.
const pairingParams=new URLSearchParams(location.hash.slice(1));
const pairingToken=pairingParams.get('fpl-local'),pairingPort=Number(pairingParams.get('port'));
if(/^[a-f0-9]{64}$/.test(pairingToken||'')&&Number.isInteger(pairingPort)&&pairingPort>=1024&&pairingPort<=65535){
 chrome.runtime.sendMessage({type:'pair',token:pairingToken,port:pairingPort,prices:pairingParams.get('prices')==='1'});
 history.replaceState(null,'',location.pathname+location.search);
}
