const state={rows:[],sort:"pe",direction:"asc",query:"",type:"all",quality:"all",profitable:false};
const $=s=>document.querySelector(s);
const fmt=(value,digits=1)=>value==null?"—":new Intl.NumberFormat("en-US",{maximumFractionDigits:digits,minimumFractionDigits:digits}).format(value);
const won=value=>value==null?"—":"₩"+new Intl.NumberFormat("en-US",{maximumFractionDigits:0}).format(value);
const multiple=value=>value==null?"—":fmt(value,2)+"×";
const pct=value=>value==null?"—":fmt(value*100,1)+"%";
const compact=value=>value==null?"—":new Intl.NumberFormat("en-US",{notation:"compact",maximumFractionDigits:2}).format(value);
const median=values=>{const a=values.filter(v=>v!=null&&v>0).sort((x,y)=>x-y);if(!a.length)return null;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2};
const escapeHtml=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));

function filtered(){
  return state.rows.filter(r=>{
    const q=(r.company+" "+r.ticker).toLowerCase();
    return (!state.query||q.includes(state.query))&&(state.type==="all"||r.type===state.type)&&(state.quality==="all"||r.quality===state.quality)&&(!state.profitable||r.common_income_ttm>0);
  }).sort((a,b)=>{
    let av=a[state.sort],bv=b[state.sort];
    if(av==null&&bv==null)return 0;if(av==null)return 1;if(bv==null)return -1;
    if(typeof av==="string")return av.localeCompare(bv,"ko")*(state.direction==="asc"?1:-1);
    return (av-bv)*(state.direction==="asc"?1:-1);
  });
}

function render(){
  const rows=filtered();
  $("#result-count").textContent=rows.length+" of "+state.rows.length+" companies";
  document.querySelectorAll("th").forEach(th=>{th.classList.toggle("sorted",th.dataset.key===state.sort);th.classList.toggle("asc",th.dataset.key===state.sort&&state.direction==="asc")});
  $("#rows").innerHTML=rows.length?rows.map(r=>`<tr data-ticker="${escapeHtml(r.ticker)}" tabindex="0">
    <td class="company"><strong>${escapeHtml(r.company)}</strong><span>${escapeHtml(r.ticker)} · ${escapeHtml(r.exchange||r.type)}</span></td>
    <td>${won(r.price)}</td><td class="${r.pe==null?"muted":""}">${multiple(r.pe)}</td>
    <td class="${r.ex_cash_pe==null?"muted":""}">${multiple(r.ex_cash_pe)}</td>
    <td class="${r.pb==null?"muted":""}">${multiple(r.pb)}</td>
    <td class="${r.roe<0?"negative":r.roe==null?"muted":""}">${pct(r.roe)}</td>
    <td class="${r.net_cash_pct<0?"negative":r.net_cash_pct==null?"muted":""}">${pct(r.net_cash_pct)}</td>
    <td class="${r.ev_ebit<0?"negative":r.ev_ebit==null?"muted":""}">${multiple(r.ev_ebit)}</td>
    <td><span class="badge ${escapeHtml(r.quality)}">${r.quality==="review"?"Review":escapeHtml(r.quality)}</span></td>
  </tr>`).join(""):'<tr><td colspan="9" class="empty">No companies match these filters.</td></tr>';
  document.querySelectorAll("#rows tr[data-ticker]").forEach(tr=>{
    const open=()=>showDetail(state.rows.find(r=>r.ticker===tr.dataset.ticker));
    tr.addEventListener("click",open);tr.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();open()}});
  });
}

function showDetail(r){
  $("#detail-ticker").textContent=[r.ticker,r.exchange,r.type].filter(Boolean).join(" · ");
  $("#detail-company").textContent=r.company;
  const auditFlags=r.flags||[];
  const flags=auditFlags.length?auditFlags:(r.warnings||[]).map(message=>({level:"low",message}));
  $("#detail-content").innerHTML=`
    <div class="detail-grid">
      <div><span>Price</span><strong>${won(r.price)}</strong></div><div><span>Market cap</span><strong>${r.market_cap==null?"—":"₩"+compact(r.market_cap)}</strong></div><div><span>TTM P/E</span><strong>${multiple(r.pe)}</strong></div>
      <div><span>TTM revenue</span><strong>${r.currency==="KRW"?"₩":r.currency+" "}${compact(r.revenue_ttm)}</strong></div><div><span>Operating profit</span><strong>${compact(r.operating_profit_ttm)}</strong></div><div><span>Common income</span><strong>${compact(r.common_income_ttm)}</strong></div>
      <div><span>Cash-like</span><strong>${compact(r.cash_like)}</strong></div><div><span>Debt</span><strong>${compact(r.debt)}</strong></div><div><span>Net cash</span><strong>${compact(r.net_cash)}</strong></div>
      <div><span>P/B</span><strong>${multiple(r.pb)}</strong></div><div><span>EV / EBIT</span><strong>${multiple(r.ev_ebit)}</strong></div><div><span>Operating margin</span><strong>${pct(r.operating_margin)}</strong></div>
    </div>
    <div class="detail-section"><h3>Calculation basis</h3><p>${escapeHtml(r.basis||"Unavailable")} · ${escapeHtml(r.fs_div||"")} · ${escapeHtml(r.currency||"")} statements<br>Debt: ${escapeHtml((r.debt_status||"unavailable").replaceAll("_"," "))} · Cash: ${escapeHtml((r.cash_review||"face statement view").replaceAll("_"," "))}</p></div>
    <div class="detail-section"><h3>Review notes</h3>${flags.length?flags.map(f=>`<div class="flag ${escapeHtml(f.level)}">${escapeHtml(f.message)}</div>`).join(""):'<div class="flag low">No current extraction or methodology flags. Earnings may still require normalization.</div>'}</div>
    ${r.filing_url?`<a class="source-link" href="${escapeHtml(r.filing_url)}" target="_blank" rel="noopener">Open latest DART filing ↗</a>`:""}`;
  $("#detail-dialog").showModal();
}

async function init(){
  try{
    const response=await fetch("dashboard-data.json",{cache:"no-store"});if(!response.ok)throw new Error("HTTP "+response.status);
    const data=await response.json();state.rows=data.results||[];
    const date=new Date(data.generated_at_kst);
    $("#updated").textContent="Data reviewed "+new Intl.DateTimeFormat("en-GB",{dateStyle:"medium",timeStyle:"short",timeZone:"Asia/Seoul"}).format(date)+" KST";
    $("#company-count").textContent=data.company_count;
    $("#median-pe").textContent=multiple(median(state.rows.map(r=>r.pe)));
    $("#net-cash-count").textContent=state.rows.filter(r=>r.net_cash>0).length;
    $("#high-count").textContent=data.flag_counts?.high??"—";
    render();
  }catch(error){$("#rows").innerHTML='<tr><td colspan="9" class="empty">The valuation feed could not be loaded. Please refresh shortly.</td></tr>';$("#updated").textContent="Data unavailable"}
}

$("#search").addEventListener("input",e=>{state.query=e.target.value.trim().toLowerCase();render()});
$("#type-filter").addEventListener("change",e=>{state.type=e.target.value;render()});
$("#quality-filter").addEventListener("change",e=>{state.quality=e.target.value;render()});
$("#profitable-filter").addEventListener("change",e=>{state.profitable=e.target.checked;render()});
$("#reset").addEventListener("click",()=>{state.query="";state.type="all";state.quality="all";state.profitable=false;$("#search").value="";$("#type-filter").value="all";$("#quality-filter").value="all";$("#profitable-filter").checked=false;render()});
document.querySelectorAll("th[data-key]").forEach(th=>th.addEventListener("click",()=>{if(state.sort===th.dataset.key)state.direction=state.direction==="asc"?"desc":"asc";else{state.sort=th.dataset.key;state.direction=th.dataset.key==="company"?"asc":"asc"}render()}));
$("#method-button").addEventListener("click",()=>$("#method-dialog").showModal());
$("#close-method").addEventListener("click",()=>$("#method-dialog").close());
$("#close-detail").addEventListener("click",()=>$("#detail-dialog").close());
for(const dialog of document.querySelectorAll("dialog"))dialog.addEventListener("click",e=>{if(e.target===dialog)dialog.close()});
init();
