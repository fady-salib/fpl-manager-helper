const icons={home:'<path d="m3 10 9-7 9 7v10H3z"/><path d="M9 20v-7h6v7"/>',team:'<path d="m4 5 5-2 3 3 3-3 5 2 3 5-5 3v8H6v-8l-5-3z"/>',players:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M17 4a3 3 0 0 1 0 6M19 21v-3a6 6 0 0 0-3-5"/>',calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18M7 15h3M14 15h3"/>',chart:'<path d="M4 3v17h17M8 16v-5M13 16V7M18 16V4"/>',settings:'<circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 3 2 3-1 3 3 2 3-1 3 2 3-2 3-1v-4l2-3-2-3-4-1-2-3z"/>',arrow:'<path d="M4 12h16M14 6l6 6-6 6"/>',refresh:'<path d="M20 7v5h-5M4 17v-5h5M19 11a7 7 0 0 0-12-6L4 8M5 13a7 7 0 0 0 12 6l3-3"/>',search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',bolt:'<path d="m13 2-9 12h7l-1 8L21 9h-8z"/>',check:'<path d="m5 12 4 4L20 5"/>',info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',transfer:'<path d="M3 7h17l-4-4M21 17H4l4 4M20 7l-4 4M4 17l4-4"/>',crown:'<path d="m3 6 4 4 5-7 5 7 4-4-2 13H5z"/>',download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',lock:'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4"/>',chevron:'<path d="m9 5 7 7-7 7"/>',save:'<path d="M5 3h12l4 4v14H3V3zM7 3v6h9V3M7 21v-8h10v8"/>'};
const icon=(name)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||icons.info}</svg>`;
const e=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(n,d=1)=>Number.isFinite(Number(n))?Number(n).toFixed(d):'—';
const money=(v)=>`£${fmt(Number(v)/10)}m`;
const positions={1:'GKP',2:'DEF',3:'MID',4:'FWD'};
const chipNames={wildcard:'Wildcard',freehit:'Free Hit',bboost:'Bench Boost','3xc':'Triple Captain'};
const colors={ARS:['#dc243b','#fff'],AVL:['#7e2941','#78b9e9'],BOU:['#d72c34','#151b25'],BRE:['#ed2334','#fff'],BHA:['#1e6fca','#fff'],BUR:['#782a42','#69b7dc'],CHE:['#2455c8','transparent'],CRY:['#2867b9','#e9314c'],EVE:['#264db9','transparent'],FUL:['#eee','#222'],LEE:['#eee','#ffcd2d'],LIV:['#d32137','transparent'],MCI:['#73b9dc','transparent'],MUN:['#d52c37','transparent'],NEW:['#eee','#25262b'],NFO:['#e53942','transparent'],SUN:['#e33c4d','#fff'],TOT:['#f0f0f0','#262957'],WHU:['#7a2846','#80bee5'],WOL:['#f8b62d','#25262b']};
let data={players:[],events:[],teams:[],chips:[],report:{},rules:{}},byId=new Map(),horizon=3,weekIndex=0,playerPage=1,playerSearch='',positionFilter=0,maxPrice=200,sortKey='projected',sortDesc=true,job=null,optimizeRoute=null,busy=false;
let plans={team:null,builder:null,transfer:null},lastContext=null,searchTimer,toastTimer;
const defaults={owned:[],sale_prices:{},bank:0,free_transfers:1,max_transfers:2,confirmed:false,available_chip_ids:[],previous_chip:'',team_reference:'',team_name:'My team',team_manager:'',team_league_url:'',risk_mode:'aggressive',locked:[],excluded:[]};
let prefs={...defaults};try{const saved=JSON.parse(localStorage.getItem('fpl-manager-native-v1')||'{}');Object.assign(prefs,saved);if(!prefs.team_reference&&saved.team_id)prefs.team_reference=String(saved.team_id);delete prefs.team_id;}catch{}
const desktop=new URLSearchParams(location.search).get('desktop')==='1'&&Boolean(window.chrome?.webview);
let teamNameQuery=prefs.team_reference?String(prefs.team_name||''):'',teamManagerQuery=String(prefs.team_manager||''),teamMatches=null,teamSearchGeneration=0,teamLoadGeneration=0,priceImport=null,transferReviewPending=false;
const normaliseTeamName=v=>String(v||'').trim().replace(/\s+/g,' ').toLowerCase();

const riskLabels={aggressive:'Aggressive',balanced:'Balanced',conservative:'Conservative'};
if(!riskLabels[prefs.risk_mode])prefs.risk_mode='aggressive';
function riskControls(){return ['overview','team','builder','transfers','captaincy','players'].includes(route())?`<section class="risk-controls" aria-label="Playing style"><strong>Playing style</strong><div>${Object.entries(riskLabels).map(([key,label])=>`<button class="pill ${prefs.risk_mode===key?'active':''}" data-risk="${key}" aria-pressed="${prefs.risk_mode===key}">${label}</button>`).join('')}</div><p>${{aggressive:'Chase recent upside, weighted by expected minutes.',balanced:'Maximize the model’s expected points.',conservative:'Prefer steadier historical returns.'}[prefs.risk_mode]} Style scores are preferences, not extra predicted points.</p></section>`:'';}
function styleScore(p,k=0){return p.risk_scores?.[prefs.risk_mode]?.[k]??p.weeks[k]?.points??0;}
function styleHorizon(p){return p.weeks.slice(0,horizon).reduce((sum,_,k)=>sum+styleScore(p,k),0);}

function save(){try{localStorage.setItem('fpl-manager-native-v1',JSON.stringify(prefs));}catch{toast('Browser storage is unavailable. Your choices will last for this session.',true);}}
function toast(message,error=false){const t=document.getElementById('toast');t.textContent=message;t.className=`visible${error?' error':''}`;clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.className='',6500);}
async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});let result;try{result=await response.json();}catch{throw Error('The local server returned an unreadable response.');}if(!response.ok)throw Error(result.error||`Request failed (${response.status})`);return result;}
async function load(){data=await api('/api/state');data.players ||= [];data.events ||= [];data.chips ||= [];data.teams ||= [];data.report ||= {};byId=new Map(data.players.map(p=>[p.id,p]));horizon=Math.min(horizon,data.events.length||3);prefs.owned=(prefs.owned||[]).filter(i=>byId.has(i));prefs.locked=(prefs.locked||[]).filter(i=>byId.has(i));prefs.excluded=(prefs.excluded||[]).filter(i=>byId.has(i));}
const route=()=>location.hash.replace(/^#\/?/,'').split('?')[0]||'overview';
function navigate(name){if(route()===name)render();else location.hash=`/${name}`;}
function projected(p){return p.weeks.slice(0,horizon).reduce((n,w)=>n+w.points,0);}
const nextPoints=(p)=>p.weeks[0]?.points||0;
function shirt(p,large=false){let [color,stripe]=colors[p?.club]||['#805192','transparent'];if(p?.position===1){color='#e1b342';stripe='transparent';}return `<span class="shirt${large?' large':''}" style="--shirt:${color};--stripe:${stripe}" aria-hidden="true"></span>`;}
const mark=(club)=>`<span class="club-mark">${e(club)}</span>`;
function spark(p){let values=p.last_points||[];if(!values.length)return '<span class="muted small">—</span>';let max=Math.max(...values,6);return `<span class="spark" title="Last five match points: ${e(values.join(', '))}">${values.map(v=>`<i class="${v>=5?'good':''}" style="height:${Math.max(12,v/max*100)}%"></i>`).join('')}</span>`;}
function playerCell(p,rank=''){return `<div class="player-cell">${rank!==''?`<span class="rank">${rank}</span>`:''}${shirt(p)}<div><strong>${e(p.name)}${p.status!=='a'?'<span class="state-dot flagged" title="Availability flag"></span>':''}</strong><small>${e(p.club)} <span aria-hidden="true">·</span> ${positions[p.position]}</small></div></div>`;}
function heading(title,description,actions=''){return riskControls()+ `<div class="page-heading"><div><h1>${e(title)}</h1><p>${description}</p></div><div class="heading-actions">${actions}</div></div>`;}
function horizonSelect(){return `<select id="horizon" aria-label="Planning horizon">${[1,3,5,8].filter(n=>n<=data.events.length||n===horizon).map(n=>`<option value="${n}" ${horizon===n?'selected':''}>${n} gameweek${n===1?'':'s'}</option>`).join('')}</select>`;}
function subnav(active){return `<div class="subtabs">${[['team','Pick team'],['transfers','Transfers'],['captaincy','Captaincy'],['chips','Chips'],['builder','New team builder']].map(([r,t])=>`<a href="#/${r}" class="${r===active?'active':''}">${t}</a>`).join('')}</div>`;}
function notice(message,type=''){return `<div class="notice ${type}">${icon('info')}<span>${message}</span></div>`;}
function modelReady(){return data.model_version && data.model_version!=='Form baseline'&&data.model_version!=='No model';}
function shell(content){let r=route(),teamRoutes=['team','transfers','builder','captaincy','chips'];return `<header class="topbar"><div class="brand-row"><a class="brand" href="#/overview"><span class="brand-icon">F</span><span>FPL <em>Manager</em></span></a><div class="brand-tools"><span class="snapshot-status">Your game. Your local intelligence.</span><span class="local-pill"><i class="dot"></i> Rust engine</span></div></div></header><div class="nav-wrap"><nav class="navigation" aria-label="Main navigation">${[['overview','home','Overview'],['team','team','My team'],['players','players','Players'],['fixtures','calendar','Fixtures'],['models','chart','Local ML']].map(([path,i,label])=>`<a href="#/${path}" class="nav-link ${(r===path||(path==='team'&&teamRoutes.includes(r)))?'active':''}">${icon(i)}${label}</a>`).join('')}<span class="nav-spacer"></span><a href="#/settings" class="nav-link ${r==='settings'?'active':''}">${icon('settings')}Settings</a></nav></div><main class="container">${data.error?notice(e(data.error),'warning'):''}<div data-job-panel>${job?jobPanel():''}</div>${content}</main><footer class="footer"><div><strong>FPL Manager</strong> &nbsp;·&nbsp; Independent analytics. Not affiliated with the Premier League.<br>Predictions are estimates, not guaranteed returns.</div><div><span class="engine-indicator"><i class="dot"></i>Native inference · ${fmt(data.compute_ms,0)} ms for all players</span><span>Public data saved ${dateTime(data.snapshot_at)} · <button class="sort" data-action="refresh">Refresh</button></span></div></footer>`;}
function dateTime(value){let d=new Date(value);return Number.isNaN(d.getTime())?'not yet':d.toLocaleString('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'UTC'})+' UTC';}
function topPlayers(){return [...data.players].filter(p=>p.purchasable).sort((a,b)=>styleScore(b)-styleScore(a));}
function tableRows(players,compact=false){return players.map((p,i)=>`<tr data-player="${p.id}" tabindex="0" role="button" aria-label="View ${e(p.name)}"><td>${playerCell(p,compact?i+1:'')}</td><td class="number">${money(p.cost)}</td><td class="number ${compact?'':'mobile-hide'}">${fmt(p.ownership)}%</td>${compact?'':`<td class="number mobile-hide">${fmt(p.expected_minutes,0)}</td>`}<td class="number points">${fmt(nextPoints(p))}</td>${compact?'':`<td class="number points">${fmt(projected(p))}</td>`}<td class="mobile-hide">${spark(p)}</td></tr>`).join('');}
function countdown(event){if(!event)return '';let seconds=Math.max(0,(new Date(event.deadline)-Date.now())/1000),days=Math.floor(seconds/86400),hours=Math.floor(seconds%86400/3600),mins=Math.floor(seconds%3600/60);return `<div class="countdown"><span>${String(days).padStart(2,'0')}<small>DAYS</small></span><span>${String(hours).padStart(2,'0')}<small>HRS</small></span><span>${String(mins).padStart(2,'0')}<small>MINS</small></span></div>`;}
function overview(){let next=data.events[0],top=topPlayers(),date=next?new Date(next.deadline):null,flags=data.players.filter(p=>p.status!=='a'&&p.ownership>5),fixtures=uniqueFixtures(next?.id).slice(0,4);return heading('Your gameweek, at a glance.','Less guesswork. More informed decisions.',`<button class="btn" data-action="refresh">${icon('refresh')}Refresh data</button>`)+`<section class="hero"><div class="hero-copy"><div class="eyebrow"><i class="dot"></i>${next?`GAMEWEEK ${next.id} IS NEXT`:'YOUR LOCAL WORKSPACE'}</div><h2>A little more insight.<br>A better next move.</h2><p>Your squad, fixtures and local model in one place.<br>Powered by your own locally trained model.</p><a class="btn green" href="#/team">Manage my team ${icon('arrow')}</a></div><div class="deadline-block"><div class="divider"></div><div><div class="eyebrow">NEXT DEADLINE · UTC</div><div class="deadline-time">${date?date.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'}):'—'}</div><div class="deadline-date">${date?date.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',timeZone:'UTC'}):'No scheduled gameweek'}</div>${countdown(next)}</div></div></section><div class="metrics"><div class="metric"><div class="metric-icon">${icon('team')}</div><div><div class="metric-label">Your squad</div><div class="metric-value">${prefs.owned.length} / 15<span class="metric-note">${prefs.owned.length===15?e(prefs.team_name):'Ready when you are'}</span></div></div></div><div class="metric"><div class="metric-icon">${icon('bolt')}</div><div><div class="metric-label">Local prediction model</div><div class="metric-value">${modelReady()?'Ready':'Baseline'}<span class="metric-note">${modelReady()?'Trained · runs in Rust':'Train in Local ML'}</span></div></div></div><div class="metric"><div class="metric-icon">${icon('players')}</div><div><div class="metric-label">Players in your pool</div><div class="metric-value">${data.players.length}<span class="metric-note">Official FPL data</span></div></div></div></div><div class="grid-main"><div><section class="card"><div class="card-head"><div><h2>On the radar</h2><p>Ranked by your selected style for ${next?`Gameweek ${next.id}`:'the next gameweek'}</p></div><a class="text-link" href="#/players">All players ${icon('chevron')}</a></div><div class="table-wrap"><table><thead><tr><th>Player</th><th class="number">Price</th><th class="number">Selected</th><th class="number">Projected</th><th class="mobile-hide">Recent points</th></tr></thead><tbody>${tableRows(top.slice(0,6),true)}</tbody></table></div><div class="card-footer">${icon('info')} Model estimates include minutes and rotation risk in historical data. Check availability before the deadline.</div></section><section class="card"><div class="card-head"><div><h2>Availability watch</h2><p>Flagged players selected by more than 5% of managers</p></div><span class="badge amber">${flags.length} players</span></div><div class="card-body">${flags.slice(0,3).map(p=>`<div class="list-item" data-player="${p.id}">${playerCell(p)}<span class="small muted" style="max-width:54%;font-size:10px;line-height:1.6">${e(p.news||'Check availability on FPL')}</span></div>`).join('')||'<p class="small muted">No popular flagged players in this snapshot.</p>'}</div></section></div><aside><section class="card"><div class="card-head"><div><h2>Fixture focus</h2><p>${next?`Gameweek ${next.id}`:'Upcoming games'}</p></div><a class="text-link" href="#/fixtures">${icon('arrow')}</a></div><div class="card-body">${fixtures.map(f=>`<div class="fixture-line"><span class="fixture-club">${mark(f.home)}<b>${e(f.home)}</b></span><span class="fixture-vs">vs</span><span class="fixture-club away"><b>${e(f.away)}</b>${mark(f.away)}</span></div>`).join('')}</div></section><div class="callout"><div class="eyebrow muted" style="margin-bottom:12px">MAKE IT YOURS</div><h3>${prefs.owned.length===15?'Your next move starts here.':'Your squad. In the picture.'}</h3><p>${prefs.owned.length===15?'See your best XI, captain and bench. Then compare transfers using your actual selling prices.':'Find your FPL team by name to see your squad on the pitch. Starting fresh? Build a new team within the £100m budget.'}</p><a class="btn primary full" href="#/${prefs.owned.length===15?'team':'settings'}">${prefs.owned.length===15?'Open my team':'Connect my team'} ${icon('arrow')}</a><a href="#/builder" class="text-link mt16">Or build a new squad ${icon('chevron')}</a></div><p class="small muted" style="line-height:1.8;margin:18px 3px">Saved public data: ${dateTime(data.snapshot_at)}. Refresh before making a transfer on the official FPL website.</p></aside></div>`;}
function uniqueFixtures(event){let seen=new Set(),rows=[];for(let p of data.players){let w=p.weeks.find(w=>w.event===event);if(!w)continue;for(let f of w.fixtures){if(!f.home)continue;let key=`${p.club}-${f.opponent}-${f.kickoff}`;if(seen.has(key))continue;seen.add(key);rows.push({home:p.club,away:f.opponent,kickoff:f.kickoff});}}return rows.sort((a,b)=>a.kickoff.localeCompare(b.kickoff));}
function teamSearchResults(){
 if(!teamMatches)return '';
 if(teamMatches.desktopWaiting)return '<p class="small muted" role="status">Waiting for official FPL sign-in…</p>';
 if(teamMatches.error)return `<div class="inline-error" role="alert">${e(teamMatches.error)}</div>`;
 if(teamMatches.waiting)return `<div class="notice mt16"><span>Waiting for your browser helper. <a href="${e(teamMatches.url)}" target="_blank" rel="noopener noreferrer">Open official FPL</a>, then click the helper and Continue with FPL. Keep this page open. Connection expires after five minutes.</span></div>`;
 return `<div class="team-search-results">${(teamMatches.candidates||[]).map(c=>`<div class="list-item"><span>${e(c.name)} · ${e(c.manager)}</span><button class="btn small" type="button" data-team-candidate="${c.reference}">Load squad</button></div>`).join('')}</div>`;
}
function loadTeamForm(){return `<form id="load-team-form"><div class="field"><label for="team-name">FPL team name</label><input class="input" id="team-name" type="text" maxlength="80" value="${e(teamNameQuery)}" required autocomplete="off"></div><div class="field"><label for="team-manager">Manager name</label><input class="input" id="team-manager" type="text" maxlength="80" value="${e(teamManagerQuery)}" placeholder="Full name shown on FPL" required autocomplete="name"></div><button class="btn primary full" type="submit" ${desktop&&teamMatches?.desktopWaiting?'disabled':''}>Connect my team</button><div id="team-search-results">${teamSearchResults()}</div>${desktop?'':`<details class="mt16"><summary>First connection: install the browser helper</summary><p class="small muted">In Chrome open chrome://extensions, or Edge edge://extensions. Enable Developer mode, choose Load unpacked, and select this app’s browser-connector folder. Pin FPL Manager Local Connector. Click Connect here, sign in only on official FPL, then click the helper’s Continue with FPL button. If login changes the link, click Connect here again.</p><p class="small muted">FPL has no global name-search API. The helper verifies your account once; later connections use both names. The helper shares your public team reference when connecting. A selling-price import shares only the squad IDs and their prices with this local manager. Public picks are from the last deadline.</p></details>`}<button class="text-link sort mt16" type="button" data-action="manual-team-name">Or select my 15 players manually</button></form>`;}

function teamAside(){return `<section class="card"><div class="card-head"><div><div class="eyebrow muted" style="margin-bottom:8px">YOUR SQUAD</div><h2>${e(prefs.team_name||'My team')}</h2></div>${prefs.owned.length===15?'<span class="badge green">15 / 15</span>':''}</div><div class="card-body">${prefs.owned.length===15?`<div class="budget-strip"><div><small>Squad value</small><strong>${money(prefs.owned.reduce((s,id)=>s+(byId.get(id)?.cost||0),0))}</strong></div><div><small>Confirmed bank</small><strong>${prefs.confirmed?money(prefs.bank):'—'}</strong></div></div><div class="list-item"><span class="small muted">Free transfers</span><strong class="small">${prefs.confirmed?prefs.free_transfers:'Not confirmed'}</strong></div><a class="btn full mt16" href="#/settings">${icon('settings')}Confirm team details</a>`:loadTeamForm()}</div></section><div class="callout"><h3>A fresh start?</h3><p>Build a legal 15-player squad for £100m, with a starting XI and captain across your chosen horizon.</p><a class="text-link" href="#/builder">Open new team builder ${icon('arrow')}</a></div>`;}
function pitch(plan,empty=false){let week=plan?.weeks[Math.min(weekIndex,plan.weeks.length-1)],xi=week?.xi.map(i=>byId.get(i)).filter(Boolean)||[],bench=week?.bench.map(i=>byId.get(i)).filter(Boolean)||[];let groups=empty?[[0],[0,0,0,0],[0,0,0,0],[0,0]]:[1,2,3,4].map(pos=>xi.filter(p=>p.position===pos));return `<div class="pitch ${empty?'empty':''}"><div class="pitch-lines"></div><div class="box-top"></div><div class="box-bottom"></div>${groups.map(group=>`<div class="pitch-row">${group.map(p=>`<div class="pitch-player" ${p?`data-player="${p.id}" tabindex="0" role="button" aria-label="View ${e(p.name)}"`:''}>${shirt(p)}${p?.id===week?.captain?'<span class="captain-marker">C</span>':p?.id===week?.vice_captain?'<span class="captain-marker">V</span>':''}<div class="pitch-name">${p?e(p.name):'Player'}</div><div class="pitch-points">${p?fmt(p.weeks.find(w=>w.event===week.event)?.points):'0.0'} pts</div></div>`).join('')}</div>`).join('')}${empty?`<div class="pitch-overlay"><div>${icon('team')}<h3>Your squad belongs here.</h3><p>Load your FPL team to reveal your starting XI, bench and captain.</p><button class="btn primary" data-action="focus-team">Enter my team name ${icon('arrow')}</button></div></div>`:''}</div>${!empty?`<div class="bench">${bench.map((p,i)=>`<div class="bench-player" data-player="${p.id}"><span class="bench-label">${i===0?'Reserve GK':`Bench ${i}`}</span>${shirt(p)}<b>${e(p.name)}</b><small>${fmt(p.weeks.find(w=>w.event===week.event)?.points)} pts</small></div>`).join('')}</div>`:''}`;}
function planCard(plan,title='Your starting XI'){let w=plan?.weeks[Math.min(weekIndex,plan.weeks.length-1)];return `<section class="card"><div class="card-head"><div><h2>${title}</h2><p>${w?`GW${w.event} · ${e(riskLabels[plan.risk_mode]||'Balanced')} formation · style score ${fmt(w.selection_score)}`:'Load your squad to get started'}</p></div>${w?`<span class="badge green">${fmt(w.points)} projected pts</span>`:''}</div>${plan?.weeks.length>1?`<div class="toolbar"><div class="table-filter">${plan.weeks.map((w,i)=>`<button class="pill ${weekIndex===i?'active':''}" data-week="${i}">GW${w.event}</button>`).join('')}</div><span class="small muted">Captain points included</span></div>`:''}${pitch(plan,!plan)}${plan?`<div class="card-footer">${plan.optimal?`${icon('check')} Proven optimal for this objective`:`${icon('clock')} Feasible plan · solver time limit reached`} · ${fmt(plan.elapsed_ms,0)} ms &nbsp;·&nbsp; ${money(plan.bank)} remaining</div>`:''}</section>`;}
function team(){let has=prefs.owned.length===15;return heading('My team',has?e(prefs.team_name)+' · Your next XI, captain and bench.':'Bring your team into focus.',horizonSelect())+subnav('team')+`<div class="team-layout"><div>${has&&!plans.team?`<section class="card"><div class="empty-state">${icon('bolt')}<h2>Your 15 are ready.</h2><p>Calculate your best legal starting XI and captain. Native Rust enumerates valid formations without starting Python.</p><button class="btn primary" data-action="lineup">Pick my best XI ${icon('arrow')}</button></div></section>`:planCard(plans.team)}${plans.team?notice('XI, captain, vice-captain and bench follow your selected playing style. Displayed points remain model means; autosub probabilities are not modeled.'):''}</div><aside>${teamAside()}</aside></div>`;}
function builder(){let plan=plans.builder;return heading('A new squad. A fresh start.','15 players. £100m. Built around your next gameweeks.',horizonSelect())+subnav('builder')+`<div class="team-layout"><div>${plan?planCard(plan,'Your recommended squad'):`<section class="card"><div class="card-head"><div><h2>Your draft pitch</h2><p>Your players appear here after building your squad.</p></div><span class="badge">£100m budget</span></div>${pitch(null,true)}</section>`}${plan?`<div class="flex" style="margin-bottom:20px"><button class="btn primary" data-action="use-draft">${icon('check')}Use as my local squad</button><button class="btn" data-action="download-squad">${icon('download')}Download CSV</button></div>`:''}</div><aside><section class="card"><div class="card-head"><div><h2>Build your squad</h2><p>Local predictions. Official squad constraints.</p></div></div><div class="card-body"><div class="budget-strip"><div><small>Starting budget</small><strong>£100.0m</strong></div><div><small>Club limit</small><strong>3 players</strong></div></div><div class="list-item"><span class="small muted">Squad composition</span><b class="small">2 GK · 5 DEF · 5 MID · 3 FWD</b></div><div class="field mt16"><label>Locked players <span class="pill-count">${prefs.locked.length}</span></label><div class="lock-list">${prefs.locked.map(i=>`<button class="lock-item" data-unlock="${i}" title="Remove lock">${e(byId.get(i)?.name)} ×</button>`).join('')||'<span class="small muted">No locks. Add them from a player profile.</span>'}</div></div><p class="small muted" style="line-height:1.8">${prefs.excluded.length} excluded player${prefs.excluded.length===1?'':'s'}. Find a player in Players and choose Lock or Exclude.</p><button class="btn primary full" data-action="build">${icon('bolt')}Build my squad</button><a class="text-link mt16" href="#/players">Find players to lock ${icon('arrow')}</a></div></section>${notice('Native MILP has a 10-second solve budget. A feasible result that is not proven optimal is labeled clearly. Formation, budget and club rules are never relaxed.')}</aside></div>`;}
function players(){let list=data.players.filter(p=>(!positionFilter||p.position===positionFilter)&&p.cost<=maxPrice&&(`${p.name} ${p.full_name} ${p.club}`).toLowerCase().includes(playerSearch.toLowerCase()));const value=p=>sortKey==='projected'?styleHorizon(p):p[sortKey];list.sort((a,b)=>{let av=value(a),bv=value(b);return (typeof av==='string'?av.localeCompare(bv):av-bv)*(sortDesc?-1:1);});let pages=Math.max(1,Math.ceil(list.length/25));playerPage=Math.max(1,Math.min(playerPage,pages));let shown=list.slice((playerPage-1)*25,playerPage*25);return heading('Find your next difference-maker.','Compare local projections, minutes and value. Click a player for the full picture.',horizonSelect())+`<section class="card"><div class="card-head"><div><h2>Player pool <span class="pill-count">${list.length}</span></h2><p>Projected points include the fixtures in your planning horizon.</p></div><button class="btn small" data-action="download-players">${icon('download')}<span class="mobile-hide"> Export CSV</span></button></div><div class="toolbar"><div class="search-wrap">${icon('search')}<input class="input" id="player-search" type="search" aria-label="Search players or clubs" placeholder="Search players or clubs…" value="${e(playerSearch)}"></div><div class="table-filter">${[[0,'All'],[1,'GKP'],[2,'DEF'],[3,'MID'],[4,'FWD']].map(([n,p])=>`<button class="pill ${positionFilter===n?'active':''}" data-position="${n}">${p}</button>`).join('')}</div><select id="max-price" aria-label="Maximum player price">${[200,150,120,100,80,60,50,45].map(p=>`<option value="${p}" ${maxPrice===p?'selected':''}>${p===200?'Any price':`Up to ${money(p)}`}</option>`).join('')}</select></div><div class="table-wrap"><table><thead><tr><th><button class="sort" data-sort="name">Player ↕</button></th><th class="number"><button class="sort" data-sort="cost">Price ↕</button></th><th class="number mobile-hide"><button class="sort" data-sort="ownership">Selected ↕</button></th><th class="number mobile-hide"><button class="sort" data-sort="expected_minutes">xMins / fixture ↕</button></th><th class="number">Next GW</th><th class="number"><button class="sort" data-sort="projected">${horizon} GW points · style order ↓</button></th><th class="mobile-hide">Last 5 points</th></tr></thead><tbody>${tableRows(shown)||'<tr><td colspan="7" class="muted">No players match these filters.</td></tr>'}</tbody></table></div><div class="pagination"><span>${list.length?(playerPage-1)*25+1:0}–${Math.min(playerPage*25,list.length)} of ${list.length} players</span><div><button class="btn small" data-action="previous-page" ${playerPage===1?'disabled':''}>Previous</button><button class="btn small" data-action="next-page" ${playerPage===pages?'disabled':''}>Next</button></div></div></section>`;}
function transfers(){let plan=plans.transfer,eligible=transferDetailsReady();return heading('Make the next move count.','Compare transfers using your real selling prices and free transfers.',horizonSelect())+subnav('transfers')+`${!eligible?notice(prefs.owned.length!==15?'Load all 15 players in Settings before comparing transfers.':`${salePriceStatus()}. Check your selling prices, bank and free transfers in Settings, then confirm and save.`,'warning'):''}<div class="team-layout"><div>${plan?`<section class="card"><div class="card-head"><div><h2>${plan.transfers_in.length?`${plan.transfers_in.length} recommended transfer${plan.transfers_in.length===1?'':'s'}`:'Keep your squad. Roll the transfer.'}</h2><p>${fmt(plan.expected_points)} projected horizon points, after ${plan.hit} hit points</p></div><span class="badge ${plan.optimal?'green':'amber'}">${plan.optimal?'Optimal for '+e(riskLabels[plan.risk_mode]||'Balanced'):'Feasible · time limit'}</span></div><div class="card-body">${plan.transfers_in.map((id,i)=>`<div class="transfer-pair"><div><div class="eyebrow muted" style="margin-bottom:12px">TRANSFER OUT</div>${playerCell(byId.get(plan.transfers_out[i]))}</div>${icon('arrow')}<div><div class="eyebrow" style="color:#009e69;margin-bottom:12px">TRANSFER IN</div>${playerCell(byId.get(id))}</div></div>`).join('')||'<p class="small muted">No transfers improve this solution within your constraints.</p>'}<div class="budget-strip"><div><small>Points cost</small><strong>${plan.hit?'-'+plan.hit:'0'} pts</strong></div><div><small>Bank after transfers</small><strong>${money(plan.bank)}</strong></div></div>${transferReviewControl(plan)}</div><div class="card-footer">${e(riskLabels[plan.risk_mode]||'Balanced')} · Style score ${fmt(plan.selection_score)} · ${e(plan.method)}</div></section>${planCard(plan,'XI after these transfers')}`:`<section class="card"><div class="empty-state">${icon('transfer')}<h2>A move should earn its place.</h2><p>The optimizer compares projected points across your horizon, with official budget, club limits and transfer hits.</p><a class="btn ${eligible?'':'primary'}" href="#/settings">${eligible?'Review financial details':'Set up my team'} ${icon('arrow')}</a></div></section>`}</div><aside><section class="card"><div class="card-head"><div><h2>Transfer planner</h2><p>One immediate transfer set held across the horizon.</p></div></div><div class="card-body"><div class="budget-strip"><div><small>Bank</small><strong>${prefs.confirmed?money(prefs.bank):'—'}</strong></div><div><small>Free transfers</small><strong>${prefs.confirmed?prefs.free_transfers:'—'}</strong></div></div>${priceImportControl()}<div class="field"><label for="max-transfers">Maximum transfers now</label><select id="max-transfers">${[0,1,2,3,4].map(n=>`<option value="${n}" ${prefs.max_transfers===n?'selected':''}>${n} transfer${n===1?'':'s'}</option>`).join('')}</select><small>Each transfer beyond your free allowance costs 4 points.</small></div><div class="field"><label for="transfer-chip">Chip for the next gameweek</label><select id="transfer-chip"><option value="">No chip</option>${data.chips.filter(c=>prefs.available_chip_ids.includes(c.id)).map(c=>`<option value="${e(c.name)}">${e(chipNames[c.name]||c.name)} · GW${c.start_event}–${c.stop_event}</option>`).join('')}</select><small>Only chip instances you confirmed unused are listed.</small></div><button class="btn primary full" data-action="transfers" ${eligible?'':'disabled'}>${icon('transfer')}Compare transfers</button></div></section>${desktop?'':notice('Review current prices and availability on FPL before acting.')}</aside></div>`;}
function captaincy(){let pool=prefs.owned.length===15?prefs.owned.map(i=>byId.get(i)):[...data.players];pool.sort((a,b)=>styleScore(b)-styleScore(a));return heading('Give the armband a second thought.','Ranked by your playing style. Projected points stay separate.')+subnav('captaincy')+(!prefs.owned.length?notice('Showing the full player pool. Load your team to restrict the shortlist to players you own.'):'')+`<div class="captain-grid">${pool.slice(0,3).map((p,i)=>`<section class="captain-card" data-player="${p.id}"><span class="badge ${i===0?'green':''}">${i===0?'Leading candidate':i===1?'Alternative':'One to consider'}</span>${shirt(p)}<h2>${e(p.name)}</h2><p>${e(p.club)} · ${positions[p.position]} · ${money(p.cost)}</p><div class="captain-score">${fmt(nextPoints(p))}<small>projected next-GW points</small><small>Style score ${fmt(styleScore(p))}</small></div></section>`).join('')}</div><section class="card"><div class="card-head"><div><h2>Captain shortlist</h2><p>Only a player in your starting XI can receive the armband.</p></div></div><div class="table-wrap"><table><thead><tr><th>Player</th><th class="number">Price</th><th class="number mobile-hide">Selected</th><th class="number mobile-hide">xMins / fixture</th><th class="number">Next GW</th><th class="number">${horizon} GW projection</th><th class="mobile-hide">Recent points</th></tr></thead><tbody>${tableRows(pool.slice(0,15))}</tbody></table></div></section>`;}
function fixtures(){let teams=[...data.teams].sort((a,b)=>a.short_name.localeCompare(b.short_name));return heading('See the run ahead.','Home and away. Doubles and blanks. Fixture difficulty from FPL.',horizonSelect())+`<section class="card"><div class="card-head"><div><h2>Fixture planner</h2><p>Each fixture is retained in a double gameweek. Unscheduled weeks are left blank.</p></div><span class="badge">${horizon} gameweek horizon</span></div><div class="table-wrap"><table class="fixture-grid"><thead><tr><th>Club</th>${data.events.slice(0,horizon).map(ev=>`<th>GW${ev.id}</th>`).join('')}</tr></thead><tbody>${teams.map(t=>{let p=data.players.find(p=>p.team===t.id);return `<tr><td><span class="flex">${mark(t.short_name)}${e(t.short_name)}</span></td>${data.events.slice(0,horizon).map(ev=>{let week=p?.weeks.find(w=>w.event===ev.id);return `<td>${week?.fixtures.length?week.fixtures.map(f=>`<span class="fixture-tag fdr-${f.difficulty}" title="${e(f.opponent)} · ${f.home?'Home':'Away'} · ${dateTime(f.kickoff)}">${e(f.opponent)} ${f.home?'(H)':'(A)'}</span>`).join(''):'<span class="fixture-tag fdr-0">—</span>'}</td>`;}).join('')}</tr>`;}).join('')}</tbody></table></div><div class="card-footer flex" style="flex-wrap:wrap"><span>FPL difficulty</span>${[1,2,3,4,5].map(n=>`<span class="fixture-tag fdr-${n}">${n}</span>`).join('')}<span>Easy → Difficult · Fixture difficulty is not a trained effect in the current model.</span></div></section>`;}
function chips(){let descriptions={wildcard:'Make unlimited permanent transfers without points hits.',freehit:'Change your squad for one gameweek, then revert to your original squad.',bboost:'Count points from all 15 players for one gameweek.','3xc':'Triple your captain’s points for one gameweek.'};return heading('Use your chips with purpose.','Review the official windows. Confirm what you have left in Settings.')+subnav('chips')+`<div class="two-col">${Object.entries(chipNames).map(([name,label])=>`<section class="chip-card" style="margin-bottom:20px"><div class="flex space-between"><div class="chip-icon">${icon(name==='3xc'?'crown':'bolt')}</div><span class="badge">${data.chips.filter(c=>c.name===name&&prefs.available_chip_ids.includes(c.id)).length} confirmed unused</span></div><h2>${label}</h2><p>${descriptions[name]}</p>${data.chips.filter(c=>c.name===name).map(c=>`<div class="list-item"><span class="small muted">GW ${c.start_event}–${c.stop_event}</span><span class="badge ${prefs.available_chip_ids.includes(c.id)?'green':''}">${prefs.available_chip_ids.includes(c.id)?'Confirmed unused':'Not confirmed'}</span></div>`).join('')}</section>`).join('')}</div>${notice('Chip choices are validated for the relevant season, gameweek, confirmed unused instances and consecutive Free Hit rules. The native planner compares a chip now; it does not choose a future activation date.')}<a class="btn primary" href="#/settings">Confirm unused chips ${icon('arrow')}</a>`;}
function models(){let r=data.report||{},targets=r.targets||{},points=targets.total_points,minutes=targets.minutes,candidates=Object.entries(points?.validation||{});let max=Math.max(...candidates.map(([,v])=>v.mae),1);return heading('Local intelligence. Measured honestly.','Your saved model, evaluation and retraining tools.',`<button class="btn" data-action="download-report">${icon('download')}Export report</button>`)+`<div class="model-feature"><div class="flex space-between"><div><div class="eyebrow muted" style="margin-bottom:10px">SAVED MODEL</div><h2>${modelReady()?'Trained. Exported. Running in Rust.':'Using the transparent form baseline.'}</h2><p>${e(data.model_version||'No model')}<br>${r.trained_at?`Trained ${dateTime(r.trained_at)} · Seasons ${(r.seasons||[]).map(e).join(', ')} · CPU`:'Train a model to enable saved tree-based inference.'}</p></div><span class="badge green">${modelReady()?'Native inference':'Local baseline'}</span></div></div><div class="grid-main"><div><section class="card"><div class="card-head"><div><h2>Held-out performance</h2><p>Chronological test period. No random train/test split.</p></div><span class="badge">${r.rows?.test?.toLocaleString()||'—'} test rows</span></div><div class="card-body"><div class="two-col">${[['Points per fixture',points],['Minutes per fixture',minutes]].map(([label,item])=>`<div class="report-metric"><small>${label} · Test MAE</small><strong class="metric-big">${fmt(item?.test?.mae,3)}</strong><span>RMSE ${fmt(item?.test?.rmse,3)} · Bias ${fmt(item?.test?.bias,3)}</span><span>Selected: ${e(item?.winner||'No report')}</span></div>`).join('')}</div><p class="small muted mt16" style="line-height:1.8">Results include zero-minute and zero-point player-fixture rows. They are not a starting-XI accuracy estimate or a guarantee of future performance.</p></div></section><section class="card"><div class="card-head"><div><h2>Points model comparison</h2><p>Validation MAE · lower is better</p></div></div><div class="card-body">${candidates.map(([name,item])=>`<div class="bar-row"><span>${e(name.replaceAll('_',' '))}</span><div class="bar-track"><div class="${name===points?.winner?'best':''}" style="width:${item.mae/max*100}%"></div></div><b>${fmt(item.mae,3)}</b></div>`).join('')||'<p class="small muted">No evaluation report is available yet.</p>'}</div></section><section class="card"><div class="card-head"><div><h2>Probability models</h2><p>Brier score on the held-out test set</p></div></div><div class="card-body">${['starts','goals_scored','assists','clean_sheets'].map(key=>`<div class="list-item"><span class="small">${({starts:'Starting',goals_scored:'Scoring a goal',assists:'Providing an assist',clean_sheets:'Keeping a clean sheet'})[key]}</span><b class="small">${fmt(targets[key]?.test_brier,4)}</b></div>`).join('')}</div></section></div><aside><section class="card"><div class="card-head"><div><h2>Local training</h2><p>Run only when you choose. Browsing stays responsive.</p></div></div><div class="card-body"><p class="small muted" style="line-height:1.8">Training uses the existing Python ML tools on your PC, then exports fitted trees for native Rust inference. No paid AI APIs.</p><button class="btn primary full" data-task="train">${icon('bolt')}Retrain local models</button><button class="btn full mt16" data-task="download">${icon('download')}Update historical data</button><button class="btn full mt16" data-task="histories">${icon('refresh')}Update player histories</button><p class="small muted mt16" style="line-height:1.8">Retraining needs Python dependencies. Use SETUP_LOCAL_TRAINING.bat once. Model serving and squad optimization do not need Python.</p></div></section>${notice('Historical features exclude the entire target gameweek. Retrospectively corrected statistics and approximate availability cutoffs remain limitations.')}<section class="card"><div class="card-head"><h3 class="mb0">Model details</h3></div><div class="card-body"><details><summary class="small muted" style="cursor:pointer">Features, calibration and full evaluation</summary><pre class="report-json">${e(JSON.stringify(r,null,2))}</pre></details></div></section></aside></div>`;}
function transferReviewControl(plan){
 if(!desktop||!plan.transfers_in.length||!plan.reference)return '';
 if(plan.chip)return '<p class="small muted">Review chip plans on the official FPL Transfers page.</p>';
 return `<button class="btn primary" type="button" data-action="review-fpl-transfers" ${transferReviewPending?'disabled':''}>Review and apply on FPL</button>`;
}
function reviewFplTransfers(){
 const plan=plans.transfer;
 if(!desktop||!plan?.transfers_in.length||plan.chip||transferReviewPending)return;
 if(!transferDetailsReady()||plan.reference!==prefs.team_reference||
    plan.originalSquad.length!==prefs.owned.length||plan.originalSquad.some(id=>!prefs.owned.includes(id))){
  toast('Sync your current FPL squad and recalculate transfers.',true);
  return;
 }
 transferReviewPending=true;
 const webview=window.chrome.webview;
 const finished=event=>{
  if(event.data?.type!=='fpl-transfer-review-finished')return;
  webview.removeEventListener('message',finished);
  transferReviewPending=false;
  if(event.data.verified&&plan.reference===prefs.team_reference){
   plans.transfer=null;
   toast('FPL saved your transfers. Syncing your squad.');
   void connectDesktop(teamNameQuery,teamManagerQuery);
  }else{
   render();
   if(event.data.message)toast(event.data.message,true);
  }
 };
 webview.addEventListener('message',finished);
 webview.postMessage({type:'fpl-review-transfers',plan:{
  reference:Number(plan.reference),event:plan.weeks[0].event,owned:plan.originalSquad,
  incoming:plan.transfers_in,outgoing:plan.transfers_out,
 }});
 render();
}
function priceImportContent(){
 const message=desktop
  ? e(teamMatches?.desktopWaiting?'Syncing with official FPL…':teamMatches?.error||'')
  : priceImport?.url
  ? `Open the connector on the <a href="${e(priceImport.url)}" target="_blank" rel="noopener noreferrer">official FPL tab</a> and choose <b>Continue with FPL</b>.`
  : e(priceImport?.message||'');
 return `<button class="btn" type="button" data-action="import-selling-prices" ${desktop&&teamMatches?.desktopWaiting?'disabled':''}>${priceImport?.waiting?'Restart price import':desktop?'Sync with FPL':'Load squad and selling prices from FPL'}</button><div class="small muted" role="status">${message}</div>`;
}
function priceImportControl(){
 return /^[1-9]\d*$/.test(prefs.team_reference)?`<div id="price-import" class="field">${priceImportContent()}</div>`:'';
}
function showPriceImport(){
 const control=document.getElementById('price-import');
 if(control)control.innerHTML=priceImportContent();
}
function salePriceProblem(player, price){
 if(!Number.isInteger(price)||price<0)return 'Enter the selling price shown on FPL.';
 if(price>player.cost)return `This is above the local market price (${money(player.cost)}). Check the FPL selling price or refresh local FPL data.`;
 return '';
}
function saveSaleInput(input){
 const id=Number(input.dataset.sale),value=input.valueAsNumber;
 if(Number.isFinite(value)&&value>=0&&!input.validity.stepMismatch){
  prefs.sale_prices[id]=Math.round(value*10);
 }else{
  delete prefs.sale_prices[id];
 }
 return input.validity.stepMismatch?'Use increments of £0.1m.':salePriceProblem(byId.get(id),prefs.sale_prices[id]);
}
function readySalePriceCount(){
 return prefs.owned.filter(id=>!salePriceProblem(byId.get(id),prefs.sale_prices[id])).length;
}
function salePriceStatus(){
 return `${readySalePriceCount()} of 15 selling prices ready`;
}
function transferDetailsReady(){
 return prefs.confirmed&&prefs.owned.length===15&&readySalePriceCount()===15;
}
function settings(){let selected=prefs.owned.map(i=>byId.get(i)).filter(Boolean),value=selected.reduce((s,p)=>s+p.cost,0);return heading('Your team, your details.','Public picks do not reveal your current selling prices or bank.','<button class="btn" type="button" data-open-tutorial>App tutorial</button>')+`<div class="two-col"><section class="card"><div class="card-head"><div><h2>Connect your FPL team</h2><p>${desktop?'Connect your current squad and transfer details through official FPL.':'Verify on official FPL. Read-only public squad loading.'}</p></div></div><div class="card-body">${loadTeamForm()}${prefs.owned.length?`<div class="notice mt16 mb0">${icon('check')}<span>${prefs.owned.length} players loaded · ${e(prefs.team_name)}<br>Market value ${money(value)}. Confirm any transfers since the last deadline.</span></div>`:''}</div></section><section class="card"><div class="card-head"><div><h2>Financial information</h2><p>Used only for transfer recommendations.</p></div></div><div class="card-body"><form id="finance-form"><div class="field-row"><div class="field"><label for="bank">Current bank (£m)</label><input id="bank" class="input" type="number" min="0" max="1000" step="0.1" value="${fmt(prefs.bank/10)}" required></div><div class="field"><label for="free-transfers">Free transfers</label><select id="free-transfers">${[0,1,2,3,4,5].map(n=>`<option value="${n}" ${prefs.free_transfers===n?'selected':''}>${n}</option>`).join('')}</select></div></div><p class="small muted"><a id="sale-price-status" href="#selling-prices" data-action="show-selling-prices">${salePriceStatus()}</a></p><label class="check-row"><input id="confirmed" type="checkbox" ${prefs.confirmed?'checked':''}><span>I confirmed my squad, bank, free transfers and all 15 selling prices against FPL.</span></label><button class="btn primary" type="submit">${icon('save')}Save team details</button><p id="finance-error" class="inline-error" role="alert" hidden></p></form><div class="mt16">${priceImportControl()}</div></div></section></div><div class="two-col"><section class="card" id="selling-prices"><div class="card-head"><div><h2>Your 15 and their selling prices</h2><p>Copy each player's selling price from <a href="https://fantasy.premierleague.com/transfers" target="_blank" rel="noopener noreferrer">official FPL Transfers</a>.</p></div><span class="badge">${selected.length} players</span></div><div class="card-body"><div class="field"><label for="manual-search">Add or remove players manually</label><input class="input" type="search" id="manual-search" placeholder="Find a player to add…"><div id="manual-results"></div></div></div>${selected.length?`<div class="table-wrap"><table><thead><tr><th>Player</th><th class="number">Sell (£m)</th><th></th></tr></thead><tbody>${selected.sort((a,b)=>a.position-b.position).map(p=>`<tr><td>${playerCell(p)}</td><td class="number"><input class="input sale-input" aria-label="Selling price for ${e(p.name)}" type="number" min="0" step="0.1" data-sale="${p.id}" aria-describedby="sale-error-${p.id}" value="${prefs.sale_prices[p.id]!==undefined?fmt(prefs.sale_prices[p.id]/10):''}" placeholder="£m"><small id="sale-error-${p.id}" class="muted" hidden></small></td><td><button class="sort" data-remove="${p.id}" aria-label="Remove ${e(p.name)}">${icon('close')}</button></td></tr>`).join('')}</tbody></table></div>`:'<div class="card-body"><p class="small muted">Load a public squad, select players manually, or create a new team in the builder.</p></div>'}<div class="card-footer">Private financial inputs stay in this browser’s local storage. They are not sent to FPL.</div></section><div><section class="card"><div class="card-head"><div><h2>Unused chips</h2><p>Confirm the chip instances still available in your account.</p></div></div><div class="card-body">${data.chips.map(c=>`<label class="check-row"><input type="checkbox" data-chip="${c.id}" ${prefs.available_chip_ids.includes(c.id)?'checked':''}><span><b>${e(chipNames[c.name]||c.name)}</b> · GW${c.start_event}–${c.stop_event}</span></label>`).join('')}<div class="field mt16"><label for="previous-chip">Chip used last gameweek</label><select id="previous-chip"><option value="">None</option>${Object.entries(chipNames).map(([key,name])=>`<option value="${key}" ${prefs.previous_chip===key?'selected':''}>${name}</option>`).join('')}</select></div></div></section><section class="card"><div class="card-head"><div><h2>Local backup</h2><p>Keep your squad and confirmed details between devices.</p></div></div><div class="card-body"><div class="flex"><button class="btn" data-action="export-team">${icon('download')}Export JSON</button><label class="btn" for="import-team">Import JSON<input class="hidden" id="import-team" type="file" accept="application/json"></label></div><p class="small muted mt16" style="line-height:1.8">Your backup contains private team financial inputs. Keep it on your own computer.</p></div></section></div></div>`;}
function jobPanel(){if(!job||(job.kind==='optimize'&&job.status!=='running'&&route()!==optimizeRoute))return '';return `<section class="job-panel"><div class="flex space-between"><div class="flex">${icon(job.status==='running'?'bolt':job.status==='done'?'check':'info')}<b class="small">${e(({'team-search':'Team name search',optimize:'Squad optimization',train:'Local model training',download:'Historical data',histories:'Player history refresh',refresh:'Official data refresh'})[job.kind]||job.kind)}</b></div><div class="flex"><span class="badge ${job.status==='failed'?'amber':'green'}">${e(job.status)}</span>${job.status!=='running'?'<button class="sort" data-action="dismiss-job" aria-label="Dismiss task">'+icon('close')+'</button>':''}</div></div><div class="progress"><div style="width:${job.progress}%"></div></div><span class="small muted">${job.status==='running'?'Running in the background. You can continue using other pages.':job.status==='done'?`Completed in ${fmt(job.elapsed_ms/1000)} seconds.`:e(job.error)}</span>${job.kind!=='optimize'?`<details ${job.status==='failed'?'open':''}><summary class="small muted mt16">Training / download log</summary><div class="logs">${e(job.logs?.join('\n')||'')}</div></details>`:''}</section>`;}
function render(){const pages={overview,team,builder,players,transfers,captaincy,fixtures,chips,models,settings};document.getElementById('app').innerHTML=shell((pages[route()]||overview)());document.title=`${({overview:'Overview',team:'My Team',builder:'New Team Builder',players:'Players',transfers:'Transfers',captaincy:'Captaincy',fixtures:'Fixtures',chips:'Chips',models:'Local ML',settings:'Settings'})[route()]||'Overview'} · FPL Manager`;}
function modal(id){const p=byId.get(Number(id));if(!p)return;let modal=document.getElementById('modal-root');modal.innerHTML=`<div class="modal-backdrop" data-action="close-modal"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="player-title"><div class="modal-title"><button class="modal-close" data-action="close-modal" aria-label="Close player details">${icon('close')}</button><div class="eyebrow" style="margin-bottom:15px;color:#d1b9d8">${e(p.club)} · ${positions[p.position]}</div><h2 id="player-title">${e(p.name)}</h2><p class="small" style="margin:0;color:#d1b9d8">${e(p.full_name)}</p></div><div class="modal-body"><div class="modal-stats">${[['Price',money(p.cost)],['Next GW',fmt(nextPoints(p))+' pts'],['xMins / fixture',fmt(p.expected_minutes,0)]].map(([label,value])=>`<div class="modal-stat"><small>${label}</small><strong>${value}</strong></div>`).join('')}</div>${p.news?notice(e(p.news),'warning'):''}<h3>Per-fixture probabilities</h3>${[['starts','Starting'],['goals_scored','Scoring a goal'],['assists','Providing an assist'],['clean_sheets','Keeping a clean sheet']].map(([key,label])=>`<div class="prob-row"><span>${label}</span><b>${p.probabilities[key]===undefined?'Not available':fmt(p.probabilities[key]*100,0)+'%'}</b></div>`).join('')}<div class="field mt24"><label>Upcoming fixtures</label>${p.weeks.slice(0,horizon).map(w=>`<div class="list-item"><b class="small">GW${w.event}</b><span>${w.fixtures.map(f=>`<span class="fixture-tag fdr-${f.difficulty}">${e(f.opponent)} ${f.home?'(H)':'(A)'}</span>`).join('')||'<span class="muted small">Blank</span>'}</span><b class="small">${fmt(w.points)} pts</b></div>`).join('')}</div><p class="small muted" style="line-height:1.8">${p.history_samples} completed match records in this season’s feature history. ${p.history_samples<3?'Sparse history: predictions rely heavily on imputation. ':''}Probabilities and minutes are per fixture; they are not weekly totals for doubles.</p><div class="flex"><button class="btn primary" data-toggle-lock="${p.id}">${icon('lock')}${prefs.locked.includes(p.id)?'Unlock player':'Lock in new squad'}</button><button class="btn" data-toggle-exclude="${p.id}">${prefs.excluded.includes(p.id)?'Include player':'Exclude from builder'}</button></div></div></section></div>`;document.body.style.overflow='hidden';modal.querySelector('.modal-close').focus();}
function closeModal(){document.getElementById('modal-root').innerHTML='';document.body.style.overflow='';}
async function poll(id){for(;;){job=await api(`/api/jobs/${id}`);const panel=document.querySelector('[data-job-panel]');if(panel)panel.innerHTML=jobPanel();if(job.status!=='running'){if(job.status==='failed')throw Error(job.error);return job.result;}await new Promise(resolve=>setTimeout(resolve,500));}}
async function optimize(mode,request){request={...request,risk_mode:prefs.risk_mode};if(busy){toast('A local task is already being started.');return;}busy=true;const origin=route();try{const response=await api('/api/optimize',request);optimizeRoute=origin;job={id:response.job,kind:'optimize',status:'running',progress:5,logs:[]};render();const result=await poll(response.job);if((mode==='team'||mode==='transfer')&&JSON.stringify([...(request.owned||[])].sort((a,b)=>a-b))!==JSON.stringify([...prefs.owned].sort((a,b)=>a-b))){toast('Your team changed while solving. Recalculate for the selected squad.');render();return;}if(request.risk_mode!==prefs.risk_mode||request.horizon!==horizon){toast('Style or horizon changed. Calculate again.');return;}plans[mode]=mode==='transfer'?{...result,chip:request.chip,originalSquad:[...request.owned],reference:prefs.team_reference}:result;lastContext={mode,horizon};weekIndex=0;toast(mode==='team'?'Your starting XI is ready.':'Your recommended squad is ready.');render();}catch(error){toast(error.message,true);render();}finally{busy=false;}}
async function task(kind){try{let response=await api('/api/tasks',{kind});job={id:response.job,kind,status:'running',progress:0,logs:[]};render();await poll(response.job);await load();plans={team:null,builder:null,transfer:null};toast(kind==='train'?'Model trained, exported and reloaded in Rust.':'Local data updated.');render();}catch(error){toast(error.message,true);render();}}
async function searchTeams(form=null){
 const name=(form?.querySelector('#team-name')?.value??teamNameQuery).trim();
 const manager=(form?.querySelector('#team-manager')?.value??teamManagerQuery).trim();
 teamNameQuery=name;teamManagerQuery=manager;
 if(!name||!manager){toast('Enter your team name and full manager name.',true);return;}
 if(desktop){if(!teamMatches?.desktopWaiting)await connectDesktop(name,manager);return;}
 const generation=++teamSearchGeneration;teamLoadGeneration++;
 // Open synchronously so browsers do not block the official FPL tab.
 const official=window.open('about:blank','_blank');if(official)official.opener=null;
 try{
  let result=await api('/api/connect/start',{name,manager,known_entry_id:/^\d+$/.test(String(prefs.team_reference))?Number(prefs.team_reference):null});
  if(generation!==teamSearchGeneration){official?.close();return;}
  if(!result.candidate){
   teamMatches={waiting:true,url:result.url};render();
   if(official)official.location=result.url;
   const until=Date.now()+result.expires_seconds*1000;
   while(Date.now()<until){
    await new Promise(resolve=>setTimeout(resolve,1500));
    if(generation!==teamSearchGeneration)return;
    const status=await api('/api/connect/status',{token:result.token});
    if(status.candidate){result=status;break;}
   }
   if(!result.candidate)throw Error('Connection expired. Click Connect again to open a new FPL tab.');
  }else official?.close();
  if(generation!==teamSearchGeneration)return;
  teamMatches={candidates:[result.candidate]};render();
  await loadCandidate(result.candidate.reference);
 }catch(error){official?.close();if(generation===teamSearchGeneration){teamMatches={error:error.message};render();toast(error.message,true);}}
}
async function connectDesktop(name,manager){
 const generation=++teamSearchGeneration;
 teamLoadGeneration++;
 teamMatches={desktopWaiting:true};
 prefs.confirmed=false;
 render();
 let closed=false;
 const webview=window.chrome.webview;
 const onMessage=event=>{
  if(event.data?.type==='fpl-sign-in-error'&&event.data.generation===generation){
   closed=true;
   if(generation===teamSearchGeneration){
    teamMatches={error:event.data.message};
    render();
   }
  }
 };
 webview.addEventListener('message',onMessage);
 try{
  const {token,url,expires_seconds}=await api('/api/connect/start',{name,manager,desktop:true});
  if(generation!==teamSearchGeneration)return;
  webview.postMessage({type:'fpl-sign-in',url,generation});
  const until=Date.now()+expires_seconds*1000;
  while(!closed&&generation===teamSearchGeneration&&Date.now()<until){
   await new Promise(resolve=>setTimeout(resolve,1200));
   if(closed||generation!==teamSearchGeneration)return;
   const {account}=await api('/api/connect/status',{token});
   if(closed||generation!==teamSearchGeneration)return;
   if(!account)continue;
   const owned=Object.keys(account.sale_prices).map(Number);
   if(owned.some(id=>!byId.has(id)||salePriceProblem(byId.get(id),account.sale_prices[id]))){
    await task('refresh');
    if(generation!==teamSearchGeneration)return;
   }
   if(owned.some(id=>!byId.has(id)))throw Error('The current FPL squad includes players missing from local data. Refresh FPL data and connect again.');
   const sameTeam=String(prefs.team_reference)===String(account.candidate.reference);
   const haveFinances=Number.isInteger(account.bank)&&Number.isInteger(account.free_transfers);
   prefs={...prefs,owned,sale_prices:account.sale_prices,
    team_reference:String(account.candidate.reference),team_name:account.candidate.name,
    team_manager:account.candidate.manager,bank:account.bank??(sameTeam?prefs.bank:0),
    free_transfers:account.free_transfers??(sameTeam?prefs.free_transfers:1),
    available_chip_ids:sameTeam?prefs.available_chip_ids:[],
    previous_chip:sameTeam?prefs.previous_chip:'',
    confirmed:haveFinances&&owned.every(id=>!salePriceProblem(byId.get(id),account.sale_prices[id])),
   };
   teamNameQuery=prefs.team_name;
   teamManagerQuery=prefs.team_manager;
   teamMatches=null;
   plans={team:null,builder:plans.builder,transfer:null};
   save();
   navigate(prefs.confirmed?'transfers':'settings');
   toast(prefs.confirmed?'Current FPL squad and transfer details loaded.':'Squad and selling prices loaded. Review the remaining transfer details in Settings.');
   return;
  }
  if(!closed&&generation===teamSearchGeneration)throw Error('FPL sign-in expired. Click Connect to try again.');
 }catch(error){
  if(generation===teamSearchGeneration){teamMatches={error:error.message};render();}
 }finally{
  webview.removeEventListener('message',onMessage);
 }
}
async function loadCandidate(reference){
 const candidate=teamMatches?.candidates?.find(c=>c.reference===Number(reference));if(!candidate)return;
 const generation=++teamLoadGeneration;
 try{
  const team=await api(`/api/team/${candidate.reference}?expected_name=${encodeURIComponent(candidate.name)}&expected_manager=${encodeURIComponent(candidate.manager)}`);
  if(generation!==teamLoadGeneration)return;
  const sameReference=String(prefs.team_reference)===String(team.id);
  const sameSquad=sameReference&&team.owned.length===prefs.owned.length&&team.owned.every(id=>prefs.owned.includes(id));
  prefs={...prefs,bank:sameReference?prefs.bank:0,free_transfers:sameReference?prefs.free_transfers:1,owned:team.owned,team_reference:String(team.id),team_name:team.name||candidate.name,team_manager:candidate.manager,confirmed:sameSquad&&prefs.confirmed,sale_prices:sameSquad?prefs.sale_prices:{}};
  teamNameQuery=prefs.team_name;save();plans={team:null,builder:plans.builder,transfer:null};closeModal();navigate('team');toast(prefs.confirmed?'Squad loaded with your saved transfer details.':'Squad loaded by name. Confirm your transfer details in Settings.');
  await optimize('team',{owned:prefs.owned,horizon,max_transfers:0});
 }catch(error){if(generation===teamLoadGeneration)toast(error.message,true);}
}
async function importSellingPrices(){
 const reference=Number(prefs.team_reference),generation=teamLoadGeneration;
 const pending={waiting:true,message:'Opening official FPL…'};
 priceImport=pending;
 const official=window.open('about:blank','_blank');
 if(official)official.opener=null;
 showPriceImport();
 try{
  const {token,url,expires_seconds}=await api('/api/connect/prices',{reference});
  if(priceImport!==pending){official?.close();return;}
  pending.url=url;
  if(official)official.location=url;
  showPriceImport();
  const expires=Date.now()+expires_seconds*1000;
  while(priceImport===pending&&Date.now()<expires){
   await new Promise(resolve=>setTimeout(resolve,1500));
   if(priceImport!==pending)return;
   const result=await api('/api/connect/status',{token});
   if(priceImport!==pending)return;
   if(!result.sale_prices)continue;
   if(generation!==teamLoadGeneration||Number(prefs.team_reference)!==reference){
    throw Error('The connected team changed. Start a new price import for that team.');
   }
   const owned=Object.keys(result.sale_prices).map(Number);
   if(owned.some(id=>!byId.has(id))){
    throw Error('Refresh local FPL data to load the latest squad, then try the price import again.');
   }
   const sameSquad=owned.length===prefs.owned.length&&owned.every(id=>prefs.owned.includes(id));
   const bank=document.getElementById('bank')?.value;
   const free=document.getElementById('free-transfers')?.value;
   prefs.owned=owned;
   prefs.sale_prices=result.sale_prices;
   prefs.confirmed=false;
   if(!sameSquad)plans.team=null;
   plans.transfer=null;
   save();
   const message=owned.some(id=>salePriceProblem(byId.get(id),prefs.sale_prices[id]))
    ? 'Loaded all 15 selling prices. Refresh local FPL data to update market prices before confirming.'
    : 'Loaded all 15 selling prices. Review your bank and free transfers, then confirm and save in Settings.';
   priceImport={message};
   render();
   if(bank!==undefined)document.getElementById('bank').value=bank;
   if(free!==undefined)document.getElementById('free-transfers').value=free;
   toast(message);
   return;
  }
  if(priceImport===pending)throw Error('The price import expired. Start it again after signing in to FPL.');
 }catch(error){
  if(!pending.url)official?.close();
  if(priceImport!==pending)return;
  priceImport={message:error.message};
  showPriceImport();
  toast(error.message,true);
 }
}
function download(name,content,type='application/json'){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csv(rows){return rows.map(row=>row.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');}
function fixedRequest(){return {owned:prefs.owned,horizon,max_transfers:0};}
document.addEventListener('click',event=>{const target=event.target.closest('button,a,[data-player]');if(!target)return;const action=target.dataset.action;
if(action==='close-modal'&&event.target.closest('.modal')&&!event.target.closest('.modal-close'))return;
if(action){if(action==='unused'){}else if(action==='manual-team-name'){const name=document.getElementById('team-name')?.value.trim()||teamNameQuery;if(!name){toast('Enter your team name first.',true);return;}teamLoadGeneration++;prefs={...prefs,team_name:name,team_reference:'',team_manager:teamManagerQuery,confirmed:false};plans={team:null,builder:plans.builder,transfer:null};save();navigate('settings');toast('Local team name saved. Select your 15 players manually; no official squad was downloaded.');}else if(action==='review-fpl-transfers')reviewFplTransfers();else if(action==='import-selling-prices'){if(desktop)searchTeams();else importSellingPrices();}else if(action==='show-selling-prices'){event.preventDefault();document.getElementById('selling-prices').scrollIntoView({block:'start'});}else if(action==='refresh')task('refresh');else if(action==='close-modal')closeModal();else if(action==='dismiss-job'){job=null;render();}else if(action==='focus-team'){if(route()==='builder'){navigate('settings');setTimeout(()=>document.getElementById('team-name')?.focus(),0);}else{document.getElementById('team-name')?.scrollIntoView({behavior:'smooth',block:'center'});document.getElementById('team-name')?.focus();}}else if(action==='lineup')optimize('team',fixedRequest());else if(action==='build')optimize('builder',{horizon,locked:prefs.locked,excluded:prefs.excluded});else if(action==='transfers'){if(!transferDetailsReady()){toast('Confirm your team finances in Settings.',true);return;}optimize('transfer',{...prefs,horizon,chip:document.getElementById('transfer-chip')?.value||null});}else if(action==='use-draft'){teamLoadGeneration++;prefs={...prefs,owned:plans.builder.squad,team_name:'My local draft',team_reference:'',team_manager:'',confirmed:false,sale_prices:{}};plans.team=plans.builder;save();navigate('team');toast('Draft saved locally. Nothing was sent to FPL.');}else if(action==='previous-page'){playerPage--;render();}else if(action==='next-page'){playerPage++;render();}else if(action==='download-report')download('fpl-model-report.json',JSON.stringify(data.report,null,2));else if(action==='download-players')download('fpl-player-projections.csv',csv([['ID','Name','Club','Position','Price (£m)','Next GW','Horizon points','Style score','Playing style','Expected minutes per fixture'],...data.players.map(p=>[p.id,p.name,p.club,positions[p.position],p.cost/10,nextPoints(p),projected(p),styleHorizon(p),prefs.risk_mode,p.expected_minutes])]),'text/csv');else if(action==='download-squad'&&plans.builder)download('fpl-draft-squad.csv',csv([['ID','Name','Club','Position','Price (£m)','Horizon points'],...plans.builder.squad.map(i=>{let p=byId.get(i);return [i,p.name,p.club,positions[p.position],p.cost/10,projected(p)];})]),'text/csv');else if(action==='export-team')download('my-fpl-local-team.json',JSON.stringify({schema:3,...prefs},null,2));return;}
if(target.dataset.risk){prefs.risk_mode=target.dataset.risk;plans={team:null,builder:null,transfer:null};weekIndex=0;save();render();return;}if(target.dataset.teamCandidate){loadCandidate(target.dataset.teamCandidate);return;}if(target.dataset.player){modal(target.dataset.player);return;}if(target.dataset.position!==undefined){positionFilter=Number(target.dataset.position);playerPage=1;render();}if(target.dataset.sort){sortDesc=sortKey===target.dataset.sort?!sortDesc:true;sortKey=target.dataset.sort;render();}if(target.dataset.week!==undefined){weekIndex=Number(target.dataset.week);render();}if(target.dataset.task){task(target.dataset.task);}if(target.dataset.unlock){prefs.locked=prefs.locked.filter(i=>i!==Number(target.dataset.unlock));save();render();}if(target.dataset.toggleLock){let id=Number(target.dataset.toggleLock);if(!prefs.locked.includes(id)&&prefs.locked.length>=15){toast('At most 15 players can be locked.',true);return;}prefs.locked=prefs.locked.includes(id)?prefs.locked.filter(i=>i!==id):[...prefs.locked,id];prefs.excluded=prefs.excluded.filter(i=>i!==id);save();modal(id);}if(target.dataset.toggleExclude){let id=Number(target.dataset.toggleExclude);prefs.excluded=prefs.excluded.includes(id)?prefs.excluded.filter(i=>i!==id):[...prefs.excluded,id];prefs.locked=prefs.locked.filter(i=>i!==id);save();modal(id);}if(target.dataset.remove){let id=Number(target.dataset.remove);prefs.owned=prefs.owned.filter(i=>i!==id);delete prefs.sale_prices[id];prefs.confirmed=false;plans.team=null;save();render();}if(target.dataset.add){let id=Number(target.dataset.add);if(prefs.owned.length>=15){toast('Remove a player before adding another.',true);return;}if(!prefs.owned.includes(id))prefs.owned.push(id);prefs.confirmed=false;plans.team=null;save();render();}
});
document.addEventListener('click',event=>{if(event.target.classList.contains('modal-backdrop'))closeModal();});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeModal();if(event.key==='Enter'&&event.target.matches('[data-player]'))modal(event.target.dataset.player);});
document.addEventListener('submit',event=>{
 if(event.target.id==='load-team-form'){
  event.preventDefault();
  searchTeams(event.target);
 }
 if(event.target.id!=='finance-form')return;
 event.preventDefault();
 const bank=document.getElementById('bank').valueAsNumber;
 const free=Number(document.getElementById('free-transfers').value);
 if(!Number.isFinite(bank)||bank<0||bank>1000){toast('Enter a valid bank amount.',true);return;}
 const confirm=document.getElementById('confirmed').checked;
 const error=document.getElementById('finance-error');
 const issues=[...document.querySelectorAll('[data-sale]')].map(input=>({
  input,player:byId.get(Number(input.dataset.sale)),message:saveSaleInput(input),
 })).filter(issue=>issue.message);
 prefs.bank=Math.round(bank*10);
 prefs.free_transfers=free;
 prefs.confirmed=confirm&&prefs.owned.length===15&&!issues.length;
 plans.transfer=null;
 save();
 if(confirm&&!prefs.confirmed){
  error.textContent=issues.length?`Check the selling prices for ${issues.map(issue=>issue.player.name).join(', ')}.`:'Select all 15 players to confirm the transfer details.';
  error.hidden=false;
  for(const {input,player,message} of issues){
   input.setAttribute('aria-invalid','true');
   const detail=document.getElementById(`sale-error-${player.id}`);
   detail.textContent=message;
   detail.hidden=false;
  }
  if(issues.length)issues[0].input.focus();
  toast(error.textContent,true);
  return;
 }
 toast('Team details saved in this browser.');
 render();
});
document.addEventListener('input',event=>{let input=event.target;if(input.id==='team-name'||input.id==='team-manager'){if(input.id==='team-name')teamNameQuery=input.value;else teamManagerQuery=input.value;teamSearchGeneration++;teamLoadGeneration++;teamMatches=null;const box=document.getElementById('team-search-results');if(box)box.innerHTML='';}if(input.id==='player-search'){playerSearch=input.value;playerPage=1;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{let start=input.selectionStart;render();let next=document.getElementById('player-search');next.focus();next.setSelectionRange(start,start);},140);}if(input.id==='manual-search'){let q=input.value.toLowerCase().trim(),list=q?data.players.filter(p=>!prefs.owned.includes(p.id)&&`${p.name} ${p.full_name} ${p.club}`.toLowerCase().includes(q)).slice(0,6):[];document.getElementById('manual-results').innerHTML=list.map(p=>`<div class="list-item">${playerCell(p)}<button class="btn small" data-add="${p.id}">Add</button></div>`).join('');}});
document.addEventListener('change',async event=>{let input=event.target;if(input.id==='horizon'){horizon=Number(input.value);plans={team:null,builder:null,transfer:null};weekIndex=0;render();}if(input.id==='max-price'){maxPrice=Number(input.value);playerPage=1;render();}if(input.id==='max-transfers'){prefs.max_transfers=Number(input.value);save();}if(input.dataset.sale){
 const problem=saveSaleInput(input);
 const detail=document.getElementById(`sale-error-${input.dataset.sale}`);
 detail.textContent=problem;
 detail.hidden=!problem;
 if(problem)input.setAttribute('aria-invalid','true');
 else input.removeAttribute('aria-invalid');
 document.getElementById('sale-price-status').textContent=salePriceStatus();
 const error=document.getElementById('finance-error');
 error.hidden=true;
 prefs.confirmed=false;
 document.getElementById('confirmed').checked=false;
 plans.transfer=null;
 save();
}if(input.dataset.chip){let id=Number(input.dataset.chip);prefs.available_chip_ids=input.checked?[...new Set([...prefs.available_chip_ids,id])]:prefs.available_chip_ids.filter(i=>i!==id);save();}if(input.id==='previous-chip'){prefs.previous_chip=input.value;save();}if(input.id==='import-team'&&input.files[0]){try{let imported=JSON.parse(await input.files[0].text());if(!Array.isArray(imported.owned)||imported.owned.length>15||new Set(imported.owned).size!==imported.owned.length||imported.owned.some(i=>!byId.has(i)))throw Error('Invalid squad IDs in backup.');let next={...defaults};if(imported.team_id&&!imported.team_reference)imported.team_reference=String(imported.team_id);for(let key of Object.keys(defaults))if(imported[key]!==undefined)next[key]=imported[key];if(!Number.isInteger(next.bank)||next.bank<0||!Number.isInteger(next.free_transfers)||next.free_transfers<0||next.free_transfers>5)throw Error('Invalid financial values in backup.');if(!Array.isArray(next.available_chip_ids)||!Array.isArray(next.locked)||!Array.isArray(next.excluded)||typeof next.sale_prices!=='object'||next.sale_prices===null)throw Error('Invalid backup structure.');next.confirmed=false;teamLoadGeneration++;prefs=next;teamNameQuery=prefs.team_reference?String(prefs.team_name):'';teamManagerQuery=String(prefs.team_manager||'');teamMatches=null;save();plans={team:null,builder:null,transfer:null};render();toast('Backup imported. Confirm the details against your account again.');}catch(error){toast(error.message,true);}}});

const tutorialSteps = [
  ['Welcome to FPL Manager', 'Start in Overview to check the next deadline, review projected points and refresh public FPL data.'],
  ['Load your squad', 'Open My Team and enter your FPL team name and manager name. Follow the official FPL sign-in prompt if it appears. You can also select your squad manually in Settings.'],
  ['Set your playing style', 'Choose Conservative, Balanced or Aggressive for recommendations that suit how much risk you want to take. Use Players and Fixtures to compare options over your chosen gameweeks.'],
  ['Plan your lineup and transfers', 'In My Team, optimize your starting XI, bench and captain. Before comparing transfers, confirm your selling prices, money in the bank and free transfers in Settings. Review any recommended changes on the official FPL site.'],
  ['Check the local model', 'Open Local ML to see which model is loaded, review its evaluation and find the local training options. You can reopen this tutorial any time in Settings.'],
];
const tutorialStorageKey = 'fpl-manager-tutorial-seen';
const tutorial = document.getElementById('tutorial');
const tutorialTitle = document.getElementById('tutorial-title');
const tutorialCopy = document.getElementById('tutorial-copy');
const tutorialProgress = document.getElementById('tutorial-progress');
const tutorialBack = document.getElementById('tutorial-back');
const tutorialNext = document.getElementById('tutorial-next');
let tutorialStep = 0;
let tutorialSeen = false;
try { tutorialSeen = localStorage.getItem(tutorialStorageKey) === 'true'; } catch {}

function renderTutorialStep() {
  const [title, copy] = tutorialSteps[tutorialStep];
  tutorialProgress.textContent = 'Step ' + (tutorialStep + 1) + ' of ' + tutorialSteps.length;
  tutorialTitle.textContent = title;
  tutorialCopy.textContent = copy;
  tutorialBack.hidden = tutorialStep === 0;
  tutorialNext.textContent = tutorialStep === tutorialSteps.length - 1 ? 'Finish' : 'Next';
}

function openTutorial() {
  if (tutorial.open) return;
  tutorialStep = 0;
  renderTutorialStep();
  tutorial.showModal();
  tutorialTitle.focus();
}

tutorialBack.addEventListener('click', () => {
  tutorialStep--;
  renderTutorialStep();
  tutorialTitle.focus();
});
tutorialNext.addEventListener('click', () => {
  if (tutorialStep === tutorialSteps.length - 1) {
    tutorial.close();
    return;
  }
  tutorialStep++;
  renderTutorialStep();
  tutorialTitle.focus();
});
document.getElementById('tutorial-skip').addEventListener('click', () => tutorial.close());
tutorial.addEventListener('close', () => {
  tutorialSeen = true;
  try { localStorage.setItem(tutorialStorageKey, 'true'); } catch {}
});
document.addEventListener('click', event => {
  if (event.target.closest('[data-open-tutorial]')) openTutorial();
});

window.addEventListener('hashchange',()=>{closeModal();weekIndex=0;render();window.scrollTo({top:0});});
try{await load();render();if(!tutorialSeen)openTutorial();let active=(await api('/api/jobs')).find(j=>j.status==='running');if(active){job=active;render();poll(active.id).then(async()=>{await load();render();}).catch(error=>toast(error.message,true));}if(desktop&&prefs.team_reference&&teamNameQuery&&teamManagerQuery)void connectDesktop(teamNameQuery,teamManagerQuery);}catch(error){document.getElementById('app').innerHTML=`<div class="boot"><span class="brand-icon">F</span><h1>Could not reach the local server.</h1><p>${e(error.message)}</p><p>Keep the FPL Manager window open, then refresh this page.</p></div>`;}
