chrome.runtime.onMessage.addListener((message,sender)=>{
 if(sender.tab?.id===undefined||sender.origin!=='https://fantasy.premierleague.com'||message.type!=='pair')return;
 if(!/^[a-f0-9]{64}$/.test(message.token||'')||!Number.isInteger(message.port)||message.port<1024||message.port>65535)return;
 chrome.storage.session.set({[String(sender.tab.id)]:{token:message.token,port:message.port,prices:message.prices===true}});
});
chrome.tabs.onRemoved.addListener(tabId=>chrome.storage.session.remove(String(tabId)));
