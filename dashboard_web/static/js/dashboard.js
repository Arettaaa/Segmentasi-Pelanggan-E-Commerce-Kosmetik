const fm=(n,d=0)=>Number(n).toLocaleString('id-ID',{minimumFractionDigits:d,maximumFractionDigits:d});
const cv=v=>getComputedStyle(document.body).getPropertyValue(v).trim();
const c=id=>document.getElementById(id);
const row=(arr,s)=>(arr||[]).find(r=>r.segmen===s)||{};
const ico=()=>window.lucide&&lucide.createIcons();
const ch={}; let D=null, STAT='mean';

const SEGC=()=>[cv('--p1'),cv('--p3'),cv('--warn'),cv('--p4')];
const colorOf=s=>{const i=D.kpi.order.indexOf(s);return SEGC()[i<0?3:i];};
const FEATS=[['avg_views','View'],['avg_carts','Cart'],['avg_removes','Remove'],
 ['avg_purchases','Purchase'],['avg_sessions','Sesi'],['avg_spend','Nilai'],['avg_recency','Recency']];
const STRAT={
 'Pembeli Bernilai Tinggi':['Retensi','crown','VIP membership, reward pembelian, bundling premium, dan early access produk baru.'],
 'Pembeli Menengah':['Pertumbuhan','trending-up','Rekomendasi produk pelengkap, promo pembelian berikutnya, dan program repeat purchase.'],
 'Browser Aktif':['Konversi','shopping-cart','Retargeting produk yang dilihat, pengingat keranjang, ulasan pelanggan, dan penawaran terbatas.'],
 'Pengunjung Kasual':['Akuisisi','user-plus','Welcome coupon, promo pembelian pertama, dan pengenalan produk terlaris.']};

function opts(extra={}){
  Chart.defaults.font.family="'Plus Jakarta Sans',sans-serif";
  Chart.defaults.color=cv('--muted');
  return Object.assign({responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:false},tooltip:{backgroundColor:cv('--card'),titleColor:cv('--ink'),
      bodyColor:cv('--ink'),borderColor:cv('--line'),borderWidth:1,padding:11,cornerRadius:10,
      titleFont:{weight:'700',size:12},bodyFont:{size:12},boxPadding:4}},
    scales:{x:{grid:{display:false},border:{display:false},ticks:{font:{size:10.5,weight:'600'}}},
      y:{grid:{color:cv('--line')},border:{display:false},ticks:{font:{size:10.5}}}}},extra);
}
const legend=()=>({display:true,position:'bottom',labels:{boxWidth:8,boxHeight:8,usePointStyle:true,
  pointStyle:'circle',font:{size:11,weight:'600'},padding:14,color:cv('--muted')}});
const catX=()=>({grid:{display:false},border:{display:false},
  ticks:{font:{size:9.5,weight:'600'},maxRotation:18,autoSkip:false,
    callback(v){const l=String(this.getLabelForValue(v));return l.length>16?l.slice(0,15)+'…':l;}}});

function kpi(el,items){
  c(el).innerHTML=items.map(([ic,val,lab,bdg,col])=>`
   <div class="kpi"><div class="r"><div class="ic" style="background:${col}1f;color:${col}">
   <i data-lucide="${ic}"></i></div>
   <div class="tx"><div class="lab">${lab}</div><div class="val">${val}</div></div></div>
   ${bdg?`<div class="bdg" style="background:${col}17;color:${col}">${bdg}</div>`:''}</div>`).join('');
  ico();
}
function table(id,head,rows){
  c(id).innerHTML=`<thead><tr>${head.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>`+
   rows.map(r=>`<tr>${r.map(x=>typeof x==='object'
    ?`<td class="sg" style="--sc:${x.c}">${x.v}</td>`:`<td>${x}</td>`).join('')}</tr>`).join('')+'</tbody>';
}
function heatGrid(el,rowLabels,colLabels,values,fmt=2,zmax=3){
  const g=c(el);
  const w=window.innerWidth<600?92:126;
  g.style.gridTemplateColumns=`${w}px repeat(${colLabels.length},minmax(0,1fr))`;
  let h='<div></div>'+colLabels.map(x=>`<div class="hh">${x}</div>`).join('');
  rowLabels.forEach((r,i)=>{
    h+=`<div class="hl">${r}</div>`;
    values[i].forEach(v=>{
      const t=Math.max(-1,Math.min(1,v.t/zmax));
      const bg=t>=0?`color-mix(in srgb, ${cv('--p1')} ${t*80}%, transparent)`
                   :`color-mix(in srgb, ${cv('--warn')} ${-t*70}%, transparent)`;
      h+=`<div class="hc" style="background:${bg};color:${t>.5?'#fff':cv('--ink')}">${v.v.toFixed(fmt)}</div>`;
    });
  });
  g.innerHTML=h;
}

/* ══ TAB BISNIS ══ */
function drawBisnis(){
  const e=D.econ,P=D.profile,k=D.kpi,ord=k.order,hi=e[0];
  kpi('kpi-bisnis',[
    ['users-round',fm(k.total),'Total pelanggan',`${k.k} segmen terbentuk`,cv('--p1')],
    ['badge-check',fm(k.buyers),'Pernah membeli',`buyer rate ${(k.buyers/k.total*100).toFixed(1)}%`,cv('--ok')],
    ['wallet',fm(k.revenue),'Total nilai transaksi',`${fm(k.revenue/k.buyers,2)} per pembeli`,cv('--p3')],
    ['trending-up',hi.revenue_share.toFixed(1)+'%','Revenue segmen teratas',
     `dari ${hi.pct_customers.toFixed(1)}% pelanggan`,cv('--warn')]]);

  ch.share=new Chart(c('c-share'),{type:'bar',
    data:{labels:ord,datasets:[
      {label:'Customer share',data:ord.map(s=>row(e,s).pct_customers),backgroundColor:cv('--p4'),
       borderRadius:7,maxBarThickness:38},
      {label:'Revenue share',data:ord.map(s=>row(e,s).revenue_share),backgroundColor:cv('--p1'),
       borderRadius:7,maxBarThickness:38}]},
    options:opts({plugins:{legend:legend(),tooltip:{callbacks:{
      label:x=>` ${x.dataset.label}: ${x.raw.toFixed(1)}%`}}},
      scales:{x:catX(),y:{grid:{color:cv('--line')},border:{display:false},
        ticks:{callback:v=>v+'%',font:{size:10.5}}}}})});

  ch.pie=new Chart(c('c-pie'),{type:'doughnut',
    data:{labels:ord,datasets:[{data:ord.map(s=>row(e,s).customers),
      backgroundColor:ord.map(colorOf),borderWidth:4,borderColor:cv('--card'),hoverOffset:7}]},
    options:opts({cutout:'70%',scales:{},plugins:{legend:legend(),
      tooltip:{callbacks:{label:x=>` ${fm(x.raw)} (${(x.raw/k.total*100).toFixed(1)}%)`}}}})});

  const fu=D.funnel,mx=Math.max(...fu.map(r=>r.customers));
  c('funnel').innerHTML=fu.map((r,i)=>
   `<div class="fs" style="width:${Math.max(r.customers/mx*100,40)}%;
     background:${[cv('--p4'),cv('--warn'),cv('--p1')][i]}">
    <b>${r.tahap}</b><em>${fm(r.customers)} · ${r.pct_of_total.toFixed(1)}%</em></div>`).join('');

  ch.conv=new Chart(c('c-conv'),{type:'bar',
    data:{labels:ord,datasets:[['pct_view','View',cv('--p4')],['pct_cart','Cart',cv('--warn')],
      ['pct_purchase','Purchase',cv('--p1')]].map(([f,l,cc])=>({label:l,backgroundColor:cc,
      borderRadius:6,maxBarThickness:22,data:ord.map(s=>row(D.funnel_seg,s)[f]||0)}))},
    options:opts({plugins:{legend:legend(),tooltip:{callbacks:{
      label:x=>` ${x.dataset.label}: ${x.raw.toFixed(1)}%`}}},
      scales:{x:catX(),y:{grid:{color:cv('--line')},border:{display:false},
        ticks:{callback:v=>v+'%'}}}})});

  const tot=P.reduce((a,r)=>a+r.customers,0),ov={};
  FEATS.forEach(([f])=>ov[f]=P.reduce((a,r)=>a+r[f]*r.customers,0)/tot);
  heatGrid('heat',ord,FEATS.map(x=>x[1]),ord.map(s=>{const p=row(P,s);
    return FEATS.map(([f])=>{const i=ov[f]?p[f]/ov[f]:0;
      return{v:i,t:Math.log2(Math.max(i,.01))};});}));

  const pr=D.price,pmax=Math.max(...pr.map(r=>r.p75_price));
  c('pricebars').innerHTML=ord.map(s=>{const r=row(pr,s);if(!r.p75_price)return'';
    const l=r.p25_price/pmax*100,w=(r.p75_price-r.p25_price)/pmax*100,m=r.median_price/pmax*100;
    return `<div class="pb"><div class="pbl"><span>${s}</span><em>median ${fm(r.median_price,2)}</em></div>
     <div class="track"><div class="fill" style="left:${l}%;width:${w}%;background:${colorOf(s)}"></div>
     <div class="med" style="left:${m}%"></div></div></div>`;}).join('');

  renderProfileTable();

  const bseg=ord.slice(0,2),bd=D.brand.filter(r=>bseg.includes(r.segmen));
  const items=[...new Set(bd.map(r=>r.item))];
  ch.brand=new Chart(c('c-brand'),{type:'bar',
    data:{labels:items,datasets:bseg.map(s=>({label:s,backgroundColor:colorOf(s),borderRadius:6,
      data:items.map(i=>{const f=bd.find(r=>r.segmen===s&&r.item===i);return f?f.purchase_events:0;})}))},
    options:opts({indexAxis:'y',plugins:{legend:legend()},
      scales:{x:{grid:{color:cv('--line')},border:{display:false}},
        y:{grid:{display:false},border:{display:false},ticks:{font:{size:10,weight:'600'}}}}})});

  ch.hour=new Chart(c('c-hour'),{type:'line',
    data:{labels:[...Array(24).keys()],datasets:ord.map(s=>({label:s,borderColor:colorOf(s),
      borderWidth:2.4,pointRadius:0,tension:.4,
      data:[...Array(24).keys()].map(h=>{
        const f=D.hour.find(r=>r.segmen===s&&r.jam===h);return f?f.pct_events:0;})}))},
    options:opts({plugins:{legend:legend()},
      scales:{x:{grid:{display:false},border:{display:false},ticks:{stepSize:3,font:{size:10}}},
        y:{grid:{color:cv('--line')},border:{display:false},ticks:{callback:v=>v+'%'}}}})});

  const cr=[...D.churn].sort((a,b)=>a.revenue_at_risk-b.revenue_at_risk);
  ch.churn=new Chart(c('c-churn'),{type:'bar',
    data:{labels:cr.map(r=>r.segmen),datasets:[{data:cr.map(r=>r.revenue_at_risk),
      backgroundColor:cr.map(r=>colorOf(r.segmen)),borderRadius:7,maxBarThickness:28}]},
    options:opts({indexAxis:'y',plugins:{tooltip:{callbacks:{
      label:x=>` ${fm(x.raw)} · ${cr[x.dataIndex].pct_at_risk.toFixed(0)}% pembeli berisiko`}}},
      scales:{x:{grid:{color:cv('--line')},border:{display:false}},
        y:{grid:{display:false},border:{display:false},ticks:{font:{size:10,weight:'600'}}}}})});

  ch.sim=new Chart(c('c-sim'),{type:'bar',
    data:{labels:ord,datasets:[1,3,5].map((p,i)=>({label:p+'%',
      backgroundColor:[cv('--p4'),cv('--p3'),cv('--p1')][i],borderRadius:6,maxBarThickness:22,
      data:ord.map(s=>{const f=D.sim.find(r=>r.segmen===s&&r.skenario_pct===p);
        return f?f.estimasi_revenue:0;})}))},
    options:opts({plugins:{legend:legend(),tooltip:{callbacks:{
      label:x=>` ${x.dataset.label}: ${fm(x.raw)}`}}},
      scales:{x:catX(),y:{grid:{color:cv('--line')},border:{display:false},
        ticks:{callback:v=>fm(v/1000)+'rb'}}}})});

  c('cards-strategi').innerHTML=ord.map(s=>{const r=row(e,s);
    const [f,icon,a]=STRAT[s]||['Segmen','users','—'];
    return `<div class="scard" style="--sc:${colorOf(s)}">
     <div class="sh"><div class="si"><i data-lucide="${icon}"></i></div><b>${s}</b></div>
     <div class="pills"><span class="pl hi">${f}</span>
     <span class="pl">${fm(r.customers)} pelanggan</span>
     <span class="pl">${r.revenue_share.toFixed(1)}% revenue</span>
     <span class="pl">buyer rate ${r.buyer_rate.toFixed(1)}%</span></div><p>${a}</p></div>`;}).join('');
  ico();

  table('t-assume',['Parameter','Nilai'],D.assume.map(r=>[r.parameter,r.nilai]));
}

function renderProfileTable(){
  const ord=D.kpi.order;
  if(STAT==='mean')
    table('t-profile',['Segmen','Pelanggan','% Plg','Buyer rate','Revenue share','View','Cart',
      'Purchase','Nilai/pembeli','Recency'],
      ord.map(s=>{const p=row(D.profile,s),e2=row(D.econ,s);
        return [{v:s,c:colorOf(s)},fm(e2.customers),e2.pct_customers.toFixed(2)+'%',
          e2.buyer_rate.toFixed(1)+'%',e2.revenue_share.toFixed(1)+'%',fm(p.avg_views,1),
          fm(p.avg_carts,1),fm(p.avg_purchases,2),fm(e2.spend_per_buyer,2),fm(p.avg_recency,1)];}));
  else
    table('t-profile',['Segmen','Median view','Median cart','Median purchase','Median nilai','Median recency'],
      ord.map(s=>{const p=row(D.profile,s);
        return [{v:s,c:colorOf(s)},fm(p.med_views,1),fm(p.med_carts,1),fm(p.med_purchases,1),
          fm(p.med_spend,2),fm(p.med_recency,1)];}));
}

/* ══ TAB MODEL ══ */
function drawModel(){
  const v=D.val||[],g=s=>{const r=v.find(x=>x.metrik.includes(s));return r?r.nilai:null;};
  const sk=g('Silhouette K-Means'),sb=g('Silhouette Bisecting'),ar=g('rata-rata');
  kpi('kpi-model',[
    ['git-branch','4','Jumlah cluster','elbow + silhouette',cv('--p1')],
    ['diamond',sk?sk.toFixed(3):'—','Silhouette K-Means','squared Euclidean',cv('--ok')],
    ['git-compare',sb?sb.toFixed(3):'—','Silhouette Bisecting','metode pembanding',cv('--p3')],
    ['waves',ar?ar.toFixed(2):'—','ARI antar seed','stabilitas sedang',cv('--warn')]]);

  const ks=D.ksel||[],kl=ks.map(r=>r.k),iK=kl.indexOf(4);
  const vline={id:'vl',afterDraw(c2){
    if(iK<0)return;
    const x=c2.scales.x.getPixelForValue(iK),a=c2.chartArea,t=c2.ctx;
    t.save();t.setLineDash([4,4]);t.strokeStyle=cv('--muted');t.lineWidth=1.3;
    t.beginPath();t.moveTo(x,a.top);t.lineTo(x,a.bottom);t.stroke();
    t.setLineDash([]);t.fillStyle=cv('--muted');t.font="700 10px 'Plus Jakarta Sans'";
    t.textAlign='center';t.fillText('K = 4',x,a.top+11);t.restore();}};
  [['c-elbow','wssse',cv('--p1')],['c-silk','silhouette',cv('--p3')]].forEach(([id,f,cc])=>{
    ch[id]=new Chart(c(id),{type:'line',plugins:[vline],
      data:{labels:kl,datasets:[{data:ks.map(r=>r[f]),borderColor:cc,borderWidth:2.8,tension:.35,
        pointRadius:5,pointBackgroundColor:cc,pointBorderColor:cv('--card'),pointBorderWidth:2,
        fill:true,backgroundColor:cc+'14'}]},options:opts()});});

  const sd=D.sil||[];
  ch.sild=new Chart(c('c-sildetail'),{type:'bar',
    data:{labels:sd.map(r=>r.cakupan.replace(' vs lainnya','')),
      datasets:[{data:sd.map(r=>r.silhouette),borderRadius:7,maxBarThickness:24,
        backgroundColor:sd.map(r=>r.cakupan.includes('Keseluruhan')?cv('--muted')
          :colorOf(r.cakupan.replace(' vs lainnya','')))}]},
    options:opts({indexAxis:'y',scales:{x:{max:1,grid:{color:cv('--line')},border:{display:false}},
      y:{grid:{display:false},border:{display:false},ticks:{font:{size:10,weight:'600'}}}}})});

  c('stab').innerHTML=(D.stab||[]).map(r=>
   `<div class="sb"><div class="sbl"><span>${r.segmen}</span><span>${r.jaccard_mean.toFixed(2)}</span></div>
    <div class="track"><div class="rng" style="left:${r.jaccard_min*100}%;
      width:${(r.jaccard_max-r.jaccard_min)*100}%"></div>
    <div class="dot" style="left:${r.jaccard_mean*100}%;background:${colorOf(r.segmen)}"></div></div></div>`).join('');

  const sw=D.seed||[];
  if(sw.length){
    const mn=Math.min(...sw.map(r=>r.wssse)),mxw=Math.max(...sw.map(r=>r.wssse));
    ch.seed=new Chart(c('c-seed'),{type:'bar',
      data:{labels:sw.map(r=>'s'+r.seed),datasets:[{data:sw.map(r=>r.wssse),borderRadius:6,
        maxBarThickness:26,backgroundColor:sw.map(r=>r.wssse<=mn*1.001?cv('--p1'):cv('--p4'))}]},
      options:opts({plugins:{tooltip:{callbacks:{label:x=>` WSSSE ${fm(x.raw,0)}`}}},
        scales:{x:{grid:{display:false},border:{display:false}},
          y:{min:mn*.97,max:mxw*1.01,grid:{color:cv('--line')},border:{display:false},
            ticks:{callback:x=>(x/1e6).toFixed(2)+'M'}}}})});
  }

  table('t-val',['Metrik','Nilai'],v.map(r=>[r.metrik,r.nilai.toFixed(3)]));

  const co=D.corr||[];
  if(co.length){
    const keys=Object.keys(co[0]).filter(x=>x!=='fitur');
    heatGrid('corr',co.map(r=>r.fitur.replace(/_/g,' ')),
      keys.map(x=>x==='days_since_last_event'?'recency':x.replace(/_count|_spend/g,'')),
      co.map(r=>keys.map(x=>({v:r[x],t:r[x]*3}))),2,3);
  }

  table('t-sens',['Model','Silhouette','ARI vs utama'],
    (D.sens||[]).map(r=>[r.model,r.silhouette.toFixed(4),r.ari_vs_model_utama.toFixed(4)]));

  if((D.bench||[]).length){
    const b=D.bench,tt=b.reduce((a,r)=>a+r.detik,0);
    c('bench-sub').textContent=`Total ${tt.toFixed(0)} detik`;
    ch.bench=new Chart(c('c-bench'),{type:'bar',
      data:{labels:b.map(r=>r.tahap.replace(/^\d+\.\s*/,'')),datasets:[{data:b.map(r=>r.detik),
        backgroundColor:cv('--p1'),borderRadius:6,maxBarThickness:20}]},
      options:opts({indexAxis:'y',plugins:{tooltip:{callbacks:{label:x=>` ${x.raw.toFixed(1)} detik`}}},
        scales:{x:{grid:{color:cv('--line')},border:{display:false}},
          y:{grid:{display:false},border:{display:false},ticks:{font:{size:9.5,weight:'600'}}}}})});
    table('t-spec',['Parameter','Nilai'],(D.spec||[]).map(r=>[r.parameter,r.nilai]));
  }else{
    c('bench-sub').textContent='Jalankan benchmark.py terlebih dahulu';
  }
}

function redraw(){
  Object.values(ch).forEach(x=>x&&x.destroy());
  for(const k in ch)delete ch[k];
  drawBisnis();drawModel();ico();
}

async function load(){
  c('loader').classList.remove('hide');
  try{
    const res=await fetch('/api/data'),j=await res.json();
    if(!res.ok)throw new Error(j.error||res.statusText);
    D=j;c('loader').classList.add('hide');c('app').classList.remove('hide');
    c('h-k').textContent='K = '+D.kpi.k;redraw();
  }catch(e){
    c('loader').classList.add('hide');
    const f=c('fatal');f.classList.remove('hide');
    f.innerHTML=`<b>Dashboard belum dapat membaca data.</b>
     <p style="margin-top:9px;font-size:13px">Pastikan container postgres aktif dan tabel hasil analisis sudah terisi.</p>
     <code>${e.message}</code>`;}
}

/* ══ interaksi ══ */
document.querySelectorAll('nav a').forEach(a=>a.onclick=()=>{
  document.querySelectorAll('nav a').forEach(x=>x.classList.remove('on'));
  a.classList.add('on');
  const b=a.dataset.tab==='bisnis';
  c('tab-bisnis').classList.toggle('hide',!b);
  c('tab-model').classList.toggle('hide',b);
  c('h-title').textContent=b?'Hasil Segmentasi':'Evaluasi Model';
  c('h-sub').textContent=b?'Profil, nilai ekonomi, dan strategi tiap segmen pelanggan'
    :'Validitas, stabilitas, dan performa pipeline K-Means';
  document.body.classList.remove('open');
  setTimeout(()=>Object.values(ch).forEach(x=>x&&x.resize()),60);
  window.scrollTo({top:0,behavior:'smooth'});
});
c('tab-stat').onclick=ev=>{
  if(ev.target.tagName!=='BUTTON')return;
  document.querySelectorAll('#tab-stat button').forEach(b=>b.classList.remove('on'));
  ev.target.classList.add('on');STAT=ev.target.dataset.t;renderProfileTable();};
c('toggle').onclick=()=>{
  if(window.innerWidth<=900)document.body.classList.toggle('open');
  else document.body.classList.toggle('mini');
  setTimeout(()=>Object.values(ch).forEach(x=>x&&x.resize()),280);};
c('scrim').onclick=()=>document.body.classList.remove('open');
c('theme').onclick=()=>{
  const d=document.body.classList.toggle('dark');
  c('theme').innerHTML=`<i data-lucide="${d?'sun':'moon'}"></i><span>${d?'Mode terang':'Mode gelap'}</span>`;
  ico();if(D)redraw();};
c('reload').onclick=load;
let rt;
window.addEventListener('resize',()=>{
  if(window.innerWidth>900)document.body.classList.remove('open');
  clearTimeout(rt);rt=setTimeout(()=>{if(D)redraw();},250);});
ico();
load();