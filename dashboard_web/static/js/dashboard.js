/* =====================================================================
   SegmentIQ — laporan segmentasi pengguna (gaya Power BI / Looker)
   Semua angka & narasi dihitung dari tabel hasil analisis di PostgreSQL.
   ===================================================================== */
'use strict';

/* ---------- util ---------- */
const $ = id => document.getElementById(id);
const cv = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const num = v => (v == null || isNaN(v)) ? 0 : Number(v);
const nf = (n, d = 0) => num(n).toLocaleString('id-ID', {minimumFractionDigits: d, maximumFractionDigits: d});
const compact = n => {
  const a = Math.abs(num(n));
  if (a >= 1e9) return nf(n / 1e9, 1) + ' M';
  if (a >= 1e6) return nf(n / 1e6, 1) + ' jt';
  if (a >= 1e4) return nf(n / 1e3, 1) + ' rb';
  return nf(n, a < 10 && a % 1 ? 2 : 0);
};
/* aturan pembulatan persen yang sama di semua visual & tabel:
   < 1% → 2 desimal, selain itu 1 desimal */
const pct = (v, d) => { const x = num(v); return nf(x, d ?? (x !== 0 && Math.abs(x) < 1 ? 2 : 1)) + '%'; };
const ratio = (a, b) => num(b) ? num(a) / num(b) : 0;
const CUR = () => (D.meta.currency === 'USD' ? '$' : D.meta.currency + ' ');
const money = (n, d = 2) => CUR() + nf(n, d);
const moneyC = n => CUR() + compact(n);
const ico = () => window.lucide && lucide.createIcons();
const sum = (a, f) => a.reduce((t, r) => t + num(typeof f === 'function' ? f(r) : r[f]), 0);
const by = (arr, s) => (arr || []).find(r => r.segmen === s) || {};
const hh = h => String(((h % 24) + 24) % 24).padStart(2, '0') + '.00';
let toastT;
function toast(msg) { const t = $('tip'); t.textContent = msg; t.classList.remove('hide'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.add('hide'), 2400); }
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage diblokir */ } },
};

/* ---------- state ---------- */
let D = null;                 // payload /api/data
let SEL = new Set();          // filter segmen (kosong = semua)
let STAT = 'mean';            // profil: mean | med
let PICK = null;              // fokus segmen untuk brand/kategori/produk
let PAGE = 'ringkasan';
let TZ = 'src';               // 'src' = UTC+3 (zona analisis) | 'wib' = UTC+7
const WI = {pp: 1, val: null, react: 10};   // parameter simulasi (what-if)
const CH = {};
const TV = new Set();

const ORDER = () => D.meta.order;
const segs = () => ORDER().filter(s => !SEL.size || SEL.has(s));
const PAL = () => ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7', '--s8'].map(cv);
const colorOf = s => { const i = ORDER().indexOf(s); return PAL()[(i < 0 ? ORDER().length : i) % 8]; };
const isF = () => SEL.size > 0;
const econF = () => D.econ.filter(r => segs().includes(r.segmen));

/* nama tampilan segmen (nama di database tidak diubah) */
const RENAME = {'Browser Aktif': 'Pengunjung Aktif'};
/* zona waktu tabel aktivitas (analisis_marketing.py: TZ_OFFSET = 3) */
const SRC_TZ = 3, WIB = 7;
const tzShift = () => TZ === 'wib' ? WIB - SRC_TZ : 0;
const tzName = () => TZ === 'wib' ? 'WIB' : `UTC+${SRC_TZ}`;

const SRC = {
  econ: 'analisis_lanjutan.py', funnel: 'analisis_lanjutan.py', funnel_seg: 'analisis_lanjutan.py',
  corr: 'analisis_lanjutan.py', sil: 'analisis_lanjutan.py', stab: 'analisis_lanjutan.py',
  seed: 'analisis_lanjutan.py', sens: 'analisis_lanjutan.py',
  brand: 'analisis_marketing.py', category: 'analisis_marketing.py', product: 'analisis_marketing.py',
  price: 'analisis_marketing.py', hour: 'analisis_marketing.py', day: 'analisis_marketing.py',
  churn: 'analisis_marketing.py', sim: 'analisis_marketing.py', assume: 'analisis_marketing.py',
  ksel: 'validasi_kmeans.py', val: 'validasi_kmeans.py', purity: 'validasi_kmeans.py', kcmp: 'banding_k4_k5.py',
  bench: 'benchmark.py', spec: 'benchmark.py', profile: 'pipeline.py',
};

/* ---------- definisi metrik (dipakai tooltip ⓘ dan halaman Metodologi) ---------- */
const DEF = {
  users: ['Total pengguna unik', 'Jumlah user_id unik yang memiliki minimal satu event (view, cart, remove, purchase) selama periode data.', 'COUNT(DISTINCT user_id)', 'segment_economics'],
  buyers: ['Pembeli unik', 'Pengguna yang memiliki minimal satu event purchase selama periode data.', 'COUNT(user_id) WHERE purchase_count > 0', 'segment_economics'],
  rate: ['Tingkat pembelian', 'Proporsi pengguna yang pernah membeli. Pada segmen yang dibentuk dari riwayat belanja, nilainya tinggi karena cara segmentasi, bukan karena efektivitas pemasaran.', 'pembeli unik ÷ pengguna unik × 100', 'segment_economics'],
  revenue: ['Total pendapatan transaksi', 'Jumlah harga pada event purchase. Dataset tidak memuat kuantitas, diskon, ongkir, maupun biaya, sehingga ini pendapatan kotor, bukan laba.', 'SUM(price) WHERE event_type = purchase', 'segment_economics'],
  spb: ['Pendapatan kumulatif rata-rata per pembeli', 'Total pendapatan selama periode dibagi pembeli unik. Bukan AOV (dataset tidak memiliki ID pesanan) dan bukan CLV.', 'total pendapatan ÷ pembeli unik', 'segment_economics'],
  items: ['Item dibeli per pembeli', 'Rata-rata jumlah event purchase per pembeli. Satu event = satu baris produk yang dibeli, bukan satu pesanan.', 'SUM(purchase_count) ÷ pembeli unik', 'segment_economics'],
  ppi: ['Pendapatan per item', 'Rata-rata harga per event purchase. Dipakai untuk memisahkan efek frekuensi dan efek harga pada nilai pembeli.', 'pendapatan per pembeli ÷ item per pembeli', 'turunan segment_economics'],
  topshare: ['Kontribusi pendapatan segmen terbesar', 'Porsi pendapatan dari segmen dengan pendapatan tertinggi terhadap total pendapatan.', 'pendapatan segmen ÷ total pendapatan × 100', 'segment_economics'],
  inactive: ['Pembeli berisiko tidak aktif', 'Pembeli yang tidak memiliki aktivitas apa pun (bukan hanya pembelian) selama ≥ 60 hari sampai tanggal terakhir dataset. Indikasi risiko, bukan churn aktual (tidak ada label churn).', 'COUNT(pembeli) WHERE days_since_last_event ≥ 60', 'churn_risk_segment'],
  revrisk: ['Pendapatan historis pembeli berisiko', 'Total pendapatan masa lalu dari pembeli yang berisiko tidak aktif. Menggambarkan nilai yang dipertaruhkan, bukan kerugian yang pasti terjadi.', 'SUM(total_spend) WHERE berisiko = 1', 'churn_risk_segment'],
  funnel: ['Corong konversi', 'Pengguna unik yang pernah melakukan tiap tahap pada periode data. Rasio antar-tahap berbasis pengguna, bukan sesi.', 'pengguna tahap n ÷ pengguna tahap n-1', 'funnel_customer, funnel_segment'],
  cartleak: ['Keranjang tanpa pembelian', 'Proporsi pengguna yang pernah menambahkan ke keranjang tetapi tidak pernah membeli.', 'pengguna (cart > 0 dan purchase = 0) ÷ pengguna (cart > 0)', 'cluster_purity'],
  conc: ['Konsentrasi pendapatan', 'Berapa persen pengguna yang menghasilkan sebagian besar (≥ 90%) pendapatan, dihitung per segmen berurutan dari pendapatan terbesar.', 'kumulatif % pendapatan vs kumulatif % pengguna', 'segment_economics'],
  recency: ['Hari sejak aktivitas terakhir', 'Selisih hari antara tanggal event terakhir pengguna dan tanggal event terakhir di seluruh dataset.', 'DATEDIFF(max(event_time) dataset, max(event_time) pengguna)', 'customer_segments'],
};
const info = k => DEF[k] ? `<span class="inf" tabindex="0" title="${esc(DEF[k][0] + ': ' + DEF[k][1] + '\nRumus: ' + DEF[k][2])}"><i data-lucide="info"></i></span>` : '';

const FEATS = [['avg_views', 'Melihat'], ['avg_carts', 'Keranjang'], ['avg_removes', 'Hapus'], ['avg_purchases', 'Item dibeli'],
  ['avg_sessions', 'Sesi'], ['avg_spend', 'Pendapatan'], ['avg_recency', 'Hari tidak aktif']];

/* asumsi nilai pembeli baru untuk simulasi (dari marketing_assumptions, fallback rata-rata) */
function baseSpb() {
  const a = (D.assume || []).find(r => /nilai belanja per pembeli/i.test(r.parameter));
  const v = a ? parseFloat(String(a.nilai).replace(',', '.')) : NaN;
  return isFinite(v) && v > 0 ? v : ratio(sum(D.econ, 'segment_revenue'), sum(D.econ, 'buyers'));
}
const churnDays = () => { const a = (D.assume || []).find(r => /ambang/i.test(r.parameter)); const m = a && String(a.nilai).match(/\d+/); return m ? +m[0] : 60; };

/* ---------- Chart.js defaults ---------- */
function base(extra = {}) {
  Chart.defaults.font.family = '"Segoe UI", Inter, system-ui, sans-serif';
  Chart.defaults.color = cv('--muted');
  const o = {
    responsive: true, maintainAspectRatio: false, animation: {duration: 300},
    interaction: {mode: 'nearest', intersect: true},
    plugins: {
      legend: {display: false},
      tooltip: {backgroundColor: cv('--card'), titleColor: cv('--ink'), bodyColor: cv('--ink2'), borderColor: cv('--line2'),
        borderWidth: 1, padding: 10, cornerRadius: 3, titleFont: {weight: '600', size: 12}, bodyFont: {size: 12}, boxPadding: 4, usePointStyle: true},
    },
    scales: {
      x: {grid: {display: false}, border: {color: cv('--line2')}, ticks: {font: {size: 11}}},
      y: {grid: {color: cv('--line')}, border: {display: false}, ticks: {font: {size: 11}}},
    },
  };
  return deep(o, extra);
}
function deep(a, b) {
  for (const k in b) {
    if (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && typeof a[k] === 'object' && a[k]) a[k] = deep({...a[k]}, b[k]);
    else a[k] = b[k];
  }
  return a;
}
const legend = (pos = 'top') => ({display: true, position: pos, align: 'start',
  labels: {boxWidth: 9, boxHeight: 9, usePointStyle: true, pointStyle: 'rectRounded', font: {size: 11}, padding: 12, color: cv('--ink2')}});
const catAxis = () => ({grid: {display: false}, border: {color: cv('--line2')},
  ticks: {font: {size: 11}, autoSkip: false, maxRotation: 0,
    callback(v) { const l = String(this.getLabelForValue(v)); return l.length > (window.innerWidth < 760 ? 9 : 18) ? l.split(' ') : l; }}});
const hAxisX = (f = compact) => ({grid: {color: cv('--line')}, border: {display: false}, ticks: {maxTicksLimit: 5, maxRotation: 0, callback: v => f(v)}});
const hAxisY = () => ({grid: {display: false}, border: {color: cv('--line2')}, ticks: {font: {size: 11},
  callback(v) { const l = String(this.getLabelForValue(v)); return l.length > 24 ? l.slice(0, 23) + '…' : l; }}});

/* label nilai di ujung bar */
const VL = {
  id: 'vl',
  afterDatasetsDraw(chart, _a, opt) {
    if (!opt || !opt.fmt) return;
    const {ctx} = chart, hz = chart.options.indexAxis === 'y';
    ctx.save(); ctx.font = '600 10.5px "Segoe UI", Inter, sans-serif'; ctx.fillStyle = cv('--ink2');
    chart.data.datasets.forEach((ds, di) => {
      const m = chart.getDatasetMeta(di); if (m.hidden || ds.type === 'line' || ds.noLabel) return;
      m.data.forEach((el, i) => {
        const v = ds.data[i]; if (v == null || (!v && opt.skipZero)) return;
        const t = opt.fmt(v, ds);
        if (hz) { ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(t, el.x + 5, el.y); }
        else { ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'; ctx.fillText(t, el.x, el.y - 3); }
      });
    });
    ctx.restore();
  },
};
const xf = key => (ev, els, chart) => {
  if (!els.length) return;
  const e = els[0];
  const s = key === 'dataset' ? chart.data.datasets[e.datasetIndex].label : chart.data.labels[e.index];
  if (ORDER().includes(s)) toggleSeg(s, ev.native && (ev.native.ctrlKey || ev.native.metaKey));
};
const hoverPtr = (ev, els) => { ev.native.target.style.cursor = els.length ? 'pointer' : 'default'; };

/* ---------- tabel matriks ---------- */
function matrix(cols, rows, opt = {}) {
  const mx = {};
  cols.forEach(c => { if (c.bar) mx[c.k] = Math.max(...rows.map(r => Math.abs(num(r[c.k]))), 1e-9); });
  const sortK = opt.sort, dir = opt.dir || -1;
  if (sortK) rows = [...rows].sort((a, b) => (num(a[sortK]) - num(b[sortK])) * dir || String(a[sortK]).localeCompare(String(b[sortK])) * dir);
  const th = cols.map(c => `<th class="${c.n ? 'n' : ''}" data-k="${c.k}">${esc(c.l)}${c.i ? info(c.i) : ''}${sortK === c.k ? `<span class="ar">${dir > 0 ? '▲' : '▼'}</span>` : ''}</th>`).join('');
  const td = r => cols.map(c => {
    const v = r[c.k], txt = c.f ? c.f(v, r) : esc(v);
    if (c.seg) return `<td class="sg" style="--sc:${colorOf(v)}">${esc(v)}</td>`;
    if (c.bar) return `<td class="n bar" style="--w:${Math.abs(num(v)) / mx[c.k]};--bc:${c.bc ? c.bc(r) : cv('--accent')}"><span>${txt}</span></td>`;
    return `<td class="${c.n ? 'n' : ''}">${txt}</td>`;
  }).join('');
  const body = rows.map(r => `<tr class="${opt.click && ORDER().includes(r.segmen) ? 'click' : ''}" data-s="${esc(r.segmen || '')}">${td(r)}</tr>`).join('');
  const foot = opt.total ? `<tfoot><tr>${cols.map((c, i) => `<td class="${c.n ? 'n' : ''}">${i === 0 ? 'Total' : (opt.total[c.k] != null ? (c.f ? c.f(opt.total[c.k], opt.total) : opt.total[c.k]) : '')}</td>`).join('')}</tr></tfoot>` : '';
  return `<table class="mx"><thead><tr>${th}</tr></thead><tbody>${body}</tbody>${foot}</table>`;
}
function bindMatrix(el, v) {
  el.querySelectorAll('th[data-k]').forEach(th => th.onclick = () => {
    const k = th.dataset.k; v._dir = v._sort === k ? -(v._dir || -1) : -1; v._sort = k; drawVisual(v);
  });
  el.querySelectorAll('tr.click').forEach(tr => tr.onclick = ev => toggleSeg(tr.dataset.s, ev.ctrlKey || ev.metaKey));
}

/* ---------- heatmap ---------- */
function heat(rowL, colL, vals, o = {}) {
  const w = window.innerWidth < 600 ? 86 : (o.lw || 140);
  const cell = ({v, t}) => {
    const k = Math.max(-1, Math.min(1, t));
    const bg = k >= 0 ? `color-mix(in srgb, var(--heat-pos) ${Math.round(k * 85)}%, transparent)`
                      : `color-mix(in srgb, var(--heat-neg) ${Math.round(-k * 80)}%, transparent)`;
    return `<div class="hc" style="background:${bg};color:${Math.abs(k) > .55 ? '#fff' : 'var(--ink)'}" title="${esc(o.tip ? o.tip(v) : v)}">${o.fmt ? o.fmt(v) : nf(v, 2)}</div>`;
  };
  let h = '<div></div>' + colL.map(c => `<div class="hh">${esc(c)}</div>`).join('');
  rowL.forEach((r, i) => { h += `<div class="hl" title="${esc(r)}">${esc(r)}</div>` + vals[i].map(cell).join(''); });
  return `<div class="heat ${o.dense ? 'dense' : ''}" style="grid-template-columns:${w}px repeat(${colL.length},minmax(0,1fr))">${h}</div>` +
    (o.legend ? `<div class="legend-scale"><span>${o.legend[0]}</span><i></i><span>${o.legend[1]}</span></div>` : '');
}

/* =====================================================================
   ANALITIK TURUNAN (semua dihitung dari data, tidak ada angka tertulis)
   ===================================================================== */
function funnelRows() {
  if (!isF()) return D.funnel.map(r => ({tahap: r.tahap, customers: num(r.customers), pct: num(r.pct_of_total)}));
  const f = (D.funnel_seg || []).filter(r => segs().includes(r.segmen)), tot = sum(f, 'customers');
  return [['Pernah view', 'pct_view'], ['Pernah cart', 'pct_cart'], ['Pernah purchase', 'pct_purchase']].map(([t, k]) => {
    const c = sum(f, r => r.customers * r[k] / 100); return {tahap: t, customers: Math.round(c), pct: ratio(c, tot) * 100};
  });
}
const STAGE = {'Pernah view': 'Melihat produk', 'Pernah cart': 'Menambahkan ke keranjang', 'Pernah purchase': 'Menyelesaikan pembelian'};

function funnelMetrics() {
  const r = funnelRows(); if (r.length < 3) return null;
  const [v, c, p] = r.map(x => x.customers);
  const pur = (D.purity || []).filter(x => segs().includes(x.segmen));
  const cartUsers = sum(pur, x => x.customers * x.pct_pernah_cart / 100);
  const leak = pur.length && cartUsers ? sum(pur, x => x.customers * x.pct_cart_tanpa_beli / 100) / cartUsers * 100 : (1 - ratio(p, c)) * 100;
  return {v2c: ratio(c, v) * 100, c2p: ratio(p, c) * 100, v2p: ratio(p, v) * 100, leak, leakExact: !!(pur.length && cartUsers)};
}

function concentration() {
  const e = [...econF()].sort((a, b) => b.segment_revenue - a.segment_revenue);
  const U = sum(e, 'customers'), R = sum(e, 'segment_revenue');
  let cu = 0, cr = 0;
  const rows = e.map(r => { cu += num(r.customers); cr += num(r.segment_revenue);
    return {segmen: r.segmen, pu: ratio(r.customers, U) * 100, pr: ratio(r.segment_revenue, R) * 100, cu: ratio(cu, U) * 100, cr: ratio(cr, R) * 100}; });
  const k = rows.findIndex(r => r.cr >= 90);
  return {rows, top: k >= 0 ? rows.slice(0, k + 1) : rows, U, R};
}

function valueRows() {
  return econF().filter(r => r.buyers > 0).map(r => ({segmen: r.segmen, buyers: r.buyers, spend_per_buyer: r.spend_per_buyer,
    purchase_per_buyer: r.purchase_per_buyer, ppi: ratio(r.spend_per_buyer, r.purchase_per_buyer)}));
}

function whatIfConv() {
  const spb = WI.val ?? baseSpb();
  return econF().map(r => {
    const non = num(r.customers) - num(r.buyers), add = Math.min(Math.round(num(r.customers) * WI.pp / 100), non);
    return {segmen: r.segmen, customers: r.customers, buyers: r.buyers, rate: r.buyer_rate, new_rate: ratio(num(r.buyers) + add, r.customers) * 100,
      add_buyers: add, add_revenue: add * spb};
  });
}
function whatIfReact() {
  return (D.churn || []).filter(r => segs().includes(r.segmen)).map(r => {
    const n = Math.round(num(r.at_risk) * WI.react / 100), per = ratio(r.revenue_at_risk, r.at_risk);
    return {segmen: r.segmen, at_risk: r.at_risk, reactivated: n, per_buyer: per, revenue: n * per};
  }).sort((a, b) => b.revenue - a.revenue);
}

/* Insight: temuan (fakta data) → implikasi (makna bisnis) → tindakan */
function insights() {
  const e = econF(), it = [];
  if (!e.length) return it;
  const U = sum(e, 'customers'), R = sum(e, 'segment_revenue');

  const c = concentration();
  if (c.rows.length >= 2 && R > 0) {
    const t = c.top, last = t[t.length - 1], restU = 100 - last.cu, restR = 100 - last.cr;
    it.push({i: 'pie-chart', tone: 's2', h: 'Pendapatan sangat terkonsentrasi', k: `${pct(last.cu)} pengguna → ${pct(last.cr)} pendapatan`,
      f: `${t.length === 1 ? 'Segmen' : t.length + ' segmen'} <b>${t.map(x => esc(x.segmen)).join(' + ')}</b> mencakup <b>${pct(last.cu)}</b> pengguna, tetapi menghasilkan <b>${pct(last.cr)}</b> pendapatan (${moneyC(R * last.cr / 100)}). ${restU > 0 ? `Sisanya, ${pct(restU)} pengguna, hanya menyumbang ${pct(restR)}.` : ''}`,
      m: 'Ketergantungan pada basis pembeli kecil membuat pendapatan rentan. Retensi segmen ini adalah prioritas pertama; kehilangan sebagian kecil pembelinya berdampak besar.'});
  }

  const opp = [...e].map(r => ({...r, non: r.customers - r.buyers})).sort((a, b) => b.non - a.non)[0];
  if (opp && opp.non > 0) {
    const add = Math.min(Math.round(opp.customers / 100), opp.non);
    it.push({i: 'target', tone: 'ok', h: `Peluang konversi: ${opp.segmen}`, k: `+1 pp ≈ ${nf(add)} pembeli baru`,
      f: `<b>${esc(opp.segmen)}</b> berisi <b>${nf(opp.customers)}</b> pengguna, tetapi baru <b>${nf(opp.buyers)}</b> yang membeli (tingkat pembelian ${pct(opp.buyer_rate)}). Kenaikan 1 poin persentase setara ±<b>${nf(add)}</b> pembeli baru atau ±<b>${moneyC(add * baseSpb())}</b> (asumsi).`,
      m: 'Identifikasi hambatan pembelian (harga, halaman produk, kepercayaan) dan uji promosi pembelian pertama dengan grup kontrol sebelum diperluas.'});
  }

  const fm = funnelMetrics();
  if (fm) it.push({i: 'filter', tone: 's3', h: 'Kebocoran terbesar setelah keranjang', k: `${pct(fm.leak)} keranjang tanpa pembelian`,
    f: `Dari pengguna yang melihat produk, <b>${pct(fm.v2c)}</b> menambahkan ke keranjang, tetapi hanya <b>${pct(fm.c2p)}</b> dari mereka yang membeli. <b>${pct(fm.leak)}</b> pengguna yang memakai keranjang tidak pernah menyelesaikan pembelian.`,
    m: 'Area yang perlu diperiksa adalah proses setelah keranjang: total harga, ongkir, langkah checkout, dan metode pembayaran. Ini hipotesis; penyebabnya perlu diuji dengan data sesi/checkout.'});

  /* hanya bandingkan segmen pembeli (tingkat pembelian >= 50%); segmen pengunjung punya sedikit pembeli */
  const buyerSegs = new Set(e.filter(r => num(r.buyer_rate) >= 50).map(r => r.segmen));
  const vr = valueRows().filter(r => buyerSegs.has(r.segmen)).sort((a, b) => b.spend_per_buyer - a.spend_per_buyer);
  if (vr.length >= 2 && vr[1].spend_per_buyer > 0) {
    const [a, b] = vr, rs = ratio(a.spend_per_buyer, b.spend_per_buyer), ri = ratio(a.purchase_per_buyer, b.purchase_per_buyer), rp = ratio(a.ppi, b.ppi);
    it.push({i: 'gem', tone: 's6', h: `Nilai pembeli didorong ${ri >= rp ? 'frekuensi' : 'harga'}`, k: `${nf(rs, 1)}× pendapatan per pembeli`,
      f: `Pendapatan per pembeli <b>${esc(a.segmen)}</b> (${money(a.spend_per_buyer)}) <b>${nf(rs, 1)}×</b> lebih besar dari <b>${esc(b.segmen)}</b> (${money(b.spend_per_buyer)}). Selisih ini berasal dari jumlah item dibeli (${nf(ri, 1)}×), sedangkan pendapatan per item ${nf(rp, 1)}×.`,
      m: ri >= rp ? 'Strategi peningkatan nilai sebaiknya mendorong pembelian berulang (pengingat restock, langganan, bundling), bukan sekadar menaikkan harga produk.'
                  : 'Pembeli bernilai tinggi memilih produk lebih mahal; perkuat penawaran premium dan rekomendasi produk kelas atas.'});
  }

  const ch = (D.churn || []).filter(r => segs().includes(r.segmen)).sort((a, b) => b.revenue_at_risk - a.revenue_at_risk)[0];
  if (ch) it.push({i: 'user-minus', tone: 'bad', h: `Risiko tidak aktif: ${ch.segmen}`, k: `${pct(ch.pct_at_risk)} pembeli tidak aktif`,
    f: `<b>${pct(ch.pct_at_risk)}</b> pembeli <b>${esc(ch.segmen)}</b> (${nf(ch.at_risk)} orang) tidak beraktivitas ≥ ${churnDays()} hari. Pendapatan historis kelompok ini <b>${moneyC(ch.revenue_at_risk)}</b>, nilai terbesar di antara segmen.`,
    m: 'Jalankan kampanye reaktivasi bertahap dan analisis penurunan frekuensi. Status ini indikasi risiko, belum churn terkonfirmasi.'});

  const hr = (D.hour || []).filter(r => segs().includes(r.segmen));
  if (hr.length) {
    const agg = {}; hr.forEach(r => agg[r.jam] = (agg[r.jam] || 0) + num(r.events));
    const pk = +Object.entries(agg).sort((a, b) => b[1] - a[1])[0][0];
    it.push({i: 'clock', tone: 's1', h: 'Jam aktivitas puncak', k: `${hh(pk)} UTC+${SRC_TZ} · ${hh(pk + WIB - SRC_TZ)} WIB`,
      f: `Event paling ramai sekitar pukul <b>${hh(pk)} UTC+${SRC_TZ}</b> (setara ${hh(pk + WIB - SRC_TZ)} WIB).`,
      m: `Gunakan sebagai kandidat waktu kirim promo, lalu validasi dengan uji A/B. Zona UTC+${SRC_TZ} adalah asumsi analisis (data asli UTC).`});
  }
  return it;
}

/* rekomendasi per segmen: aksi + metrik pantau + peluang terukur */
function recommendations() {
  const spb = baseSpb(), e = econF(), out = [];
  e.forEach(r => {
    const ch = by(D.churn, r.segmen), non = r.customers - r.buyers, add1 = Math.min(Math.round(r.customers / 100), non);
    const retain = r.revenue_share >= 15 || r.buyer_rate >= 50;
    const rec = retain
      ? {goal: 'Retensi', icon: 'shield-check', act: 'Loyalitas bertingkat, penawaran personal, dan reaktivasi pembeli pasif.',
         kpi: '% pembeli berisiko tidak aktif, frekuensi pembelian', val: num(ch.revenue_at_risk), valTxt: `${moneyC(ch.revenue_at_risk)} berisiko`}
      : r.buyer_rate < 1 && num(by(D.profile, r.segmen).avg_carts) >= 2
      ? {goal: 'Konversi', icon: 'shopping-cart', act: 'Pengingat keranjang, retargeting, dan total harga yang jelas.',
         kpi: 'Tingkat pembelian, rasio keranjang → pembelian', val: add1 * spb, valTxt: `+1 pp ≈ ${moneyC(add1 * spb)}`}
      : {goal: 'Akuisisi', icon: 'user-plus', act: 'Promo pembelian pertama dan sorotan produk terlaris.',
         kpi: 'Tingkat pembelian pertama, rasio melihat → keranjang', val: add1 * spb, valTxt: `+1 pp ≈ ${moneyC(add1 * spb)}`};
    out.push({segmen: r.segmen, ...rec, r});
  });
  const ranked = [...out].sort((a, b) => b.val - a.val);
  out.forEach(o => o.prio = 'Prioritas ' + (ranked.indexOf(o) + 1));
  return out;
}

/* =====================================================================
   DEFINISI HALAMAN & VISUAL
   ===================================================================== */
const kpiCards = list => list.map(k => `
  <div class="kpi" style="--span:${k.span || 2};--kc:${k.c || cv('--accent')}">
    <div class="kl"><i data-lucide="${k.i}"></i><span>${esc(k.l)}</span>${info(k.d)}</div>
    <div class="kv" title="${esc(k.tip || '')}">${k.v}</div><div class="ks">${k.s || '&nbsp;'}</div></div>`).join('');

const PAGES = [
/* ================= 1. RINGKASAN EKSEKUTIF ================= */
{id: 'ringkasan', t: 'Ringkasan Eksekutif', i: 'layout-dashboard', sub: 'Apa yang terjadi, di mana nilai terkonsentrasi, dan di mana peluangnya',
 kpi() {
   const e = econF(), tot = sum(e, 'customers'), buy = sum(e, 'buyers'), rev = sum(e, 'segment_revenue');
   const top = [...e].sort((a, b) => b.segment_revenue - a.segment_revenue)[0] || {};
   const ch = (D.churn || []).filter(r => segs().includes(r.segmen)), risk = sum(ch, 'at_risk');
   return [
     {i: 'users', l: 'Total pengguna unik', d: 'users', v: compact(tot), s: `<b>${nf(tot)}</b> pengguna`, tip: nf(tot)},
     {i: 'badge-check', l: 'Pembeli unik', d: 'buyers', v: compact(buy), s: `tingkat pembelian <b>${pct(ratio(buy, tot) * 100)}</b>`, c: cv('--ok'), tip: nf(buy)},
     {i: 'wallet', l: 'Total pendapatan transaksi', d: 'revenue', v: moneyC(rev), s: 'pendapatan kotor', c: cv('--s2'), tip: money(rev)},
     {i: 'receipt', l: 'Pendapatan rata-rata per pembeli', d: 'spb', v: money(ratio(rev, buy)), s: 'kumulatif periode data', c: cv('--s6')},
     {i: 'trophy', l: 'Kontribusi segmen terbesar', d: 'topshare', v: pct(ratio(top.segment_revenue, rev) * 100), s: `${esc(top.segmen || '—')} · ${pct(ratio(top.customers, tot) * 100)} pengguna`, c: cv('--s3')},
     {i: 'user-minus', l: 'Pembeli berisiko tidak aktif', d: 'inactive', v: compact(risk), s: `${pct(ratio(risk, sum(ch, 'buyers')) * 100)} pembeli · ≥ ${churnDays()} hari`, c: cv('--bad'), tip: nf(risk)},
   ];
 },
 vis: [
  {id: 'insight', t: 'Temuan utama', s: 'Klik kartu untuk melihat implikasi', span: 12, kind: 'html', src: ['econ'], filt: true,
   note: 'Estimasi memakai asumsi pendapatan per pembeli baru dari marketing_assumptions. Bukan prediksi model.',
   data: () => ({cols: [{k: 'h', l: 'Temuan'}, {k: 'k', l: 'Angka kunci'}, {k: 'f', l: 'Fakta'}, {k: 'm', l: 'Implikasi'}],
     rows: insights().map(x => ({h: x.h, k: x.k, f: x.f.replace(/<[^>]+>/g, ''), m: x.m}))}),
   draw(el) {
     el.innerHTML = `<div class="insg">${insights().map(x => `<details class="insc" style="--ic:var(--${x.tone})">
       <summary><i data-lucide="${x.i}"></i><div><b>${esc(x.k)}</b><span>${esc(x.h)}</span></div><i data-lucide="chevron-down" class="cv"></i></summary>
       <div class="ib"><p class="if">${x.f}</p><p class="im"><span>Implikasi</span>${esc(x.m)}</p></div></details>`).join('')}</div>`;
   }},
  {id: 'pareto', t: 'Konsentrasi pendapatan', s: 'Urut dari pendapatan terbesar', span: 7, h: 300, kind: 'chart', src: ['econ'], filt: true, info: 'conc',
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'pu', l: '% pengguna', n: 1, bar: 1, f: v => pct(v)}, {k: 'pr', l: '% pendapatan', n: 1, bar: 1, bc: () => cv('--s2'), f: v => pct(v)},
     {k: 'cu', l: 'Kumulatif pengguna', n: 1, f: v => pct(v)}, {k: 'cr', l: 'Kumulatif pendapatan', n: 1, f: v => pct(v)}], rows: concentration().rows}),
   draw(cx) {
     const r = concentration().rows;
     return new Chart(cx, {type: 'bar', plugins: [VL],
       data: {labels: r.map(x => x.segmen), datasets: [
         {label: '% pengguna', data: r.map(x => x.pu), backgroundColor: cv('--s1'), maxBarThickness: 44, order: 2},
         {label: '% pendapatan', data: r.map(x => x.pr), backgroundColor: cv('--s2'), maxBarThickness: 44, order: 2},
         {type: 'line', label: 'Kumulatif % pendapatan', data: r.map(x => x.cr), borderColor: cv('--s3'), backgroundColor: cv('--s3'),
          borderWidth: 2, pointRadius: 4, tension: 0, order: 1}]},
       options: base({onClick: xf(), onHover: hoverPtr, layout: {padding: {top: 18}},
         plugins: {legend: deep(legend(), {labels: {sort: (a, b) => a.datasetIndex - b.datasetIndex}}), vl: {fmt: v => pct(v)}, tooltip: {callbacks: {label: x => ` ${x.dataset.label}: ${pct(x.raw)}`}}},
         scales: {x: catAxis(), y: {beginAtZero: true, max: 105, ticks: {stepSize: 25, callback: v => v <= 100 ? v + '%' : ''}}}})});
   }},
  {id: 'pie', t: 'Distribusi pengguna per segmen', s: 'Jumlah pengguna unik', span: 5, h: 300, kind: 'chart', src: ['econ'], filt: true, info: 'users',
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'customers', l: 'Pengguna', n: 1, bar: 1, f: v => nf(v)},
     {k: 'pct_customers', l: '% pengguna', n: 1, f: v => pct(v)}], rows: econF()}),
   draw(cx) {
     const e = econF(), tot = sum(e, 'customers');
     const center = {id: 'ctr', afterDraw(c) {
       const {ctx, chartArea: a} = c, x = (a.left + a.right) / 2, y = (a.top + a.bottom) / 2;
       ctx.save(); ctx.textAlign = 'center'; ctx.fillStyle = cv('--ink'); ctx.font = '600 20px "Segoe UI", Inter, sans-serif';
       ctx.fillText(compact(tot), x, y + 2); ctx.fillStyle = cv('--muted'); ctx.font = '11px "Segoe UI", Inter, sans-serif';
       ctx.fillText('pengguna', x, y + 18); ctx.restore(); }};
     return new Chart(cx, {type: 'doughnut', plugins: [center],
       data: {labels: e.map(r => r.segmen), datasets: [{data: e.map(r => r.customers), backgroundColor: e.map(r => colorOf(r.segmen)),
         borderWidth: 2, borderColor: cv('--card'), hoverOffset: 6}]},
       options: base({cutout: '66%', scales: {x: {display: false}, y: {display: false}}, onClick: xf(), onHover: hoverPtr,
         plugins: {legend: legend('bottom'), tooltip: {callbacks: {label: x => ` ${nf(x.raw)} (${pct(ratio(x.raw, tot) * 100)})`}}}})});
   }},
  {id: 'funnel', t: 'Corong konversi pengguna', s: 'Pengguna unik per tahap', span: 5, kind: 'html', src: ['funnel'], filt: true, info: 'funnel',
   data: () => ({cols: [{k: 'tahap', l: 'Tahap'}, {k: 'customers', l: 'Pengguna', n: 1, bar: 1, f: v => nf(v)}, {k: 'pct', l: '% seluruh pengguna', n: 1, f: v => pct(v)}],
     rows: funnelRows().map(r => ({...r, tahap: STAGE[r.tahap] || r.tahap}))}),
   draw(el) {
     const r = funnelRows(), m = funnelMetrics(), mx = Math.max(...r.map(x => x.customers), 1), col = [cv('--s1'), cv('--s6'), cv('--s2')];
     el.innerHTML = `<div class="funnel">${r.map((x, i) => `
       ${i ? `<div class="fd"><i data-lucide="corner-down-right"></i>${pct(ratio(x.customers, r[i - 1].customers) * 100)} lanjut</div>` : ''}
       <div class="fs"><div class="fn">${esc(STAGE[x.tahap] || x.tahap)}</div><div class="ft">
         <div class="ff" style="width:${Math.max(x.customers / mx * 100, 2)}%;background:${col[i]}">${compact(x.customers)} · ${pct(x.pct)}</div></div></div>`).join('')}</div>
       ${m ? `<div class="mstrip">
         <div><span>Melihat → Keranjang</span><b>${pct(m.v2c)}</b></div>
         <div><span>Keranjang → Pembelian</span><b>${pct(m.c2p)}</b></div>
         <div><span>Melihat → Pembelian</span><b>${pct(m.v2p)}</b></div>
         <div class="bad"><span>Keranjang tanpa pembelian ${info('cartleak')}</span><b>${pct(m.leak)}</b></div></div>` : ''}`;
   }},
  {id: 'conv', t: 'Tahap konversi per segmen', s: '% pengguna per tahap', span: 7, h: 290, kind: 'chart', src: ['funnel_seg'], filt: true,
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'pct_view', l: 'Melihat', n: 1, f: v => pct(v)}, {k: 'pct_cart', l: 'Keranjang', n: 1, f: v => pct(v)},
     {k: 'pct_purchase', l: 'Membeli', n: 1, f: v => pct(v)}, {k: 'cart_to_purchase', l: 'Keranjang → Membeli', n: 1, bar: 1, f: v => pct(v)}],
     rows: D.funnel_seg.filter(r => segs().includes(r.segmen))}),
   draw(cx) {
     const s = segs();
     return new Chart(cx, {type: 'bar',
       data: {labels: s, datasets: [['pct_view', 'Melihat', '--s1'], ['pct_cart', 'Keranjang', '--s6'], ['pct_purchase', 'Membeli', '--s2']].map(([f, l, c]) =>
         ({label: l, backgroundColor: cv(c), maxBarThickness: 26, data: s.map(x => num(by(D.funnel_seg, x)[f]))}))},
       options: base({onClick: xf(), onHover: hoverPtr, plugins: {legend: legend(), tooltip: {callbacks: {label: x => ` ${x.dataset.label}: ${pct(x.raw)}`}}},
         scales: {x: catAxis(), y: {beginAtZero: true, max: 100, ticks: {callback: v => v + '%'}}}})});
   }},
  {id: 'econ', t: 'Ekonomi segmen', s: 'Klik baris untuk filter', span: 12, h: 300, kind: 'html', src: ['econ'], filt: true,
   note: 'Tingkat pembelian ≈ 100% pada segmen pembeli adalah konsekuensi segmentasi berbasis riwayat belanja, bukan ukuran efektivitas pemasaran.',
   cols: () => [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'customers', l: 'Pengguna', n: 1, bar: 1, f: v => nf(v)},
     {k: 'pct_customers', l: '% pengguna', n: 1, f: v => pct(v)}, {k: 'buyers', l: 'Pembeli unik', n: 1, f: v => nf(v)},
     {k: 'buyer_rate', l: 'Tingkat pembelian', i: 'rate', n: 1, bar: 1, bc: () => cv('--ok'), f: v => pct(v)},
     {k: 'segment_revenue', l: 'Pendapatan', n: 1, bar: 1, bc: () => cv('--s2'), f: v => money(v, 0)}, {k: 'revenue_share', l: '% pendapatan', n: 1, f: v => pct(v)},
     {k: 'spend_per_buyer', l: 'Pendapatan/pembeli', i: 'spb', n: 1, f: v => money(v)}, {k: 'purchase_per_buyer', l: 'Item/pembeli', i: 'items', n: 1, f: v => nf(v, 2)}],
   data() { return {cols: this.cols(), rows: econF()}; },
   draw(el, v) {
     const e = econF(), tot = {customers: sum(e, 'customers'), buyers: sum(e, 'buyers'), segment_revenue: sum(e, 'segment_revenue'), pct_customers: sum(e, 'pct_customers'), revenue_share: sum(e, 'revenue_share')};
     tot.buyer_rate = ratio(tot.buyers, tot.customers) * 100; tot.spend_per_buyer = ratio(tot.segment_revenue, tot.buyers);
     tot.purchase_per_buyer = ratio(sum(e, r => r.purchase_per_buyer * r.buyers), tot.buyers);
     el.innerHTML = matrix(this.cols(), e, {sort: v._sort, dir: v._dir, click: 1, total: tot}); bindMatrix(el, v);
   }},
 ]},

/* ================= 2. PROFIL & NILAI SEGMEN ================= */
{id: 'profil', t: 'Profil & Nilai Segmen', i: 'fingerprint', sub: 'Mengapa segmen berbeda: perilaku, nilai pembeli, harga, dan produk',
 vis: [
  {id: 'heat', t: 'Indeks perilaku segmen', s: '1,00 = rata-rata semua pengguna', span: 7, kind: 'html', src: ['profile'], filt: true,
   rows() {
     const P = D.profile, tot = sum(P, 'customers'), ov = {};
     FEATS.forEach(([f]) => ov[f] = ratio(sum(P, r => r[f] * r.customers), tot));
     return segs().map(s => { const p = by(P, s), o = {segmen: s}; FEATS.forEach(([f, l]) => o[l] = ov[f] ? p[f] / ov[f] : 0); return o; });
   },
   data() { return {cols: [{k: 'segmen', l: 'Segmen', seg: 1}, ...FEATS.map(([, l]) => ({k: l, l, n: 1, f: v => nf(v, 2)}))], rows: this.rows()}; },
   draw(el) {
     const r = this.rows();
     el.innerHTML = heat(r.map(x => x.segmen), FEATS.map(x => x[1]), r.map(x => FEATS.map(([, l]) => ({v: x[l], t: Math.log2(Math.max(x[l], .01)) / 3}))),
       {legend: ['di bawah rata-rata', 'di atas rata-rata'], tip: v => `indeks ${nf(v, 2)}× rata-rata`});
   }},
  {id: 'price', t: 'Rentang harga produk dibeli', s: 'Kuartil 25–75 & median', span: 5, kind: 'html', src: ['price'], filt: true,
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'p25_price', l: 'Kuartil 1', n: 1, f: v => money(v)}, {k: 'median_price', l: 'Median', n: 1, f: v => money(v)},
     {k: 'p75_price', l: 'Kuartil 3', n: 1, f: v => money(v)}, {k: 'avg_price', l: 'Rata-rata', n: 1, f: v => money(v)}], rows: D.price.filter(r => segs().includes(r.segmen))}),
   draw(el) {
     const pr = D.price.filter(r => segs().includes(r.segmen)), mx = Math.max(...pr.map(r => num(r.p75_price)), 1) * 1.1;
     el.innerHTML = `<div class="ranges">${segs().map(s => { const r = by(pr, s); if (!r.p75_price) return '';
       return `<div class="rg"><div class="rl"><span>${esc(s)}</span><em>${money(r.p25_price)} – ${money(r.p75_price)} · median ${money(r.median_price)}</em></div>
         <div class="track"><div class="fill" style="left:${r.p25_price / mx * 100}%;width:${(r.p75_price - r.p25_price) / mx * 100}%;background:${colorOf(s)}"></div>
         <div class="med" style="left:${r.median_price / mx * 100}%"></div></div></div>`; }).join('')}
       <div class="axis"><span>${money(0, 0)}</span><span>${money(mx / 2)}</span><span>${money(mx)}</span></div></div>`;
   }},
  {id: 'value', t: 'Dekomposisi nilai pembeli', s: 'Item per pembeli × pendapatan per item', note: 'Nilai historis selama periode data, bukan CLV.', span: 12, h: 250, kind: 'html', src: ['econ'], filt: true, info: 'spb',
   cols: () => [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'buyers', l: 'Pembeli unik', n: 1, f: v => nf(v)},
     {k: 'spend_per_buyer', l: 'Pendapatan/pembeli', i: 'spb', n: 1, bar: 1, bc: () => cv('--s2'), f: v => money(v)},
     {k: 'purchase_per_buyer', l: 'Item/pembeli', i: 'items', n: 1, bar: 1, bc: () => cv('--s1'), f: v => nf(v, 2)},
     {k: 'ppi', l: 'Pendapatan/item', i: 'ppi', n: 1, bar: 1, bc: () => cv('--s3'), f: v => money(v)}],
   data() { return {cols: this.cols(), rows: valueRows()}; },
   draw(el, v) {
     const r = valueRows().sort((a, b) => b.spend_per_buyer - a.spend_per_buyer);
     el.innerHTML = matrix(this.cols(), r, {sort: v._sort, dir: v._dir, click: 1}); bindMatrix(el, v);
   }},
  {id: 'profile', t: 'Karakteristik segmen', s: '', note: 'Nilai asli hasil agregasi, bukan hasil standardisasi.', span: 12, h: 260, kind: 'html', src: ['profile', 'econ'], filt: true,
   head: () => `<div class="seg" data-ctl="stat"><button data-v="mean" class="${STAT === 'mean' ? 'on' : ''}">Rata-rata</button><button data-v="med" class="${STAT === 'med' ? 'on' : ''}">Median</button></div>`,
   cols() {
     return STAT === 'mean'
       ? [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'customers', l: 'Pengguna', n: 1, bar: 1, f: v => nf(v)}, {k: 'avg_views', l: 'Melihat', n: 1, bar: 1, f: v => nf(v, 1)},
          {k: 'avg_carts', l: 'Keranjang', n: 1, bar: 1, f: v => nf(v, 1)}, {k: 'avg_removes', l: 'Hapus', n: 1, f: v => nf(v, 1)}, {k: 'avg_purchases', l: 'Item dibeli', n: 1, bar: 1, f: v => nf(v, 2)},
          {k: 'avg_sessions', l: 'Sesi', n: 1, f: v => nf(v, 1)}, {k: 'avg_spend', l: 'Pendapatan', n: 1, bar: 1, bc: () => cv('--s2'), f: v => money(v)},
          {k: 'avg_recency', l: 'Hari tidak aktif', i: 'recency', n: 1, bar: 1, bc: () => cv('--warn'), f: v => nf(v, 1)}]
       : [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'customers', l: 'Pengguna', n: 1, bar: 1, f: v => nf(v)}, {k: 'med_views', l: 'Melihat', n: 1, bar: 1, f: v => nf(v, 1)},
          {k: 'med_carts', l: 'Keranjang', n: 1, bar: 1, f: v => nf(v, 1)}, {k: 'med_purchases', l: 'Item dibeli', n: 1, f: v => nf(v, 1)},
          {k: 'med_spend', l: 'Pendapatan', n: 1, bar: 1, bc: () => cv('--s2'), f: v => money(v)}, {k: 'med_recency', l: 'Hari tidak aktif', i: 'recency', n: 1, bar: 1, bc: () => cv('--warn'), f: v => nf(v, 1)}];
   },
   rows: () => segs().map(s => by(D.profile, s)).filter(r => r.segmen),
   data() { return {cols: this.cols(), rows: this.rows()}; },
   draw(el, v) { el.innerHTML = matrix(this.cols(), this.rows(), {sort: v._sort, dir: v._dir, click: 1}); bindMatrix(el, v); }},
  ...[['brand', 'Brand terlaris', 'Brand'], ['category', 'Kategori terlaris', 'Kategori']].map(([key, t, l]) => ({
   id: key, t, s: 'Top 5 · item dibeli', span: 4, h: 250, kind: 'chart', src: [key], filt: true, picker: true,
   data: () => ({cols: [{k: 'rank', l: '#', n: 1}, {k: 'item', l}, {k: 'purchase_events', l: 'Item dibeli', n: 1, bar: 1, f: v => nf(v)},
     {k: 'revenue', l: 'Pendapatan', n: 1, f: v => money(v, 0)}, {k: 'buyers', l: 'Pembeli', n: 1, f: v => nf(v)}], rows: D[key].filter(r => r.segmen === PICK)}),
   draw(cx) {
     const r = D[key].filter(x => x.segmen === PICK).sort((a, b) => a.rank - b.rank);
     return new Chart(cx, {type: 'bar', plugins: [VL],
       data: {labels: r.map(x => x.item), datasets: [{label: 'Item dibeli', data: r.map(x => x.purchase_events), backgroundColor: colorOf(PICK), maxBarThickness: 22}]},
       options: base({indexAxis: 'y', layout: {padding: {right: 46}}, plugins: {vl: {fmt: v => compact(v)}}, scales: {x: hAxisX(), y: hAxisY()}})});
   }})),
  {id: 'product', t: 'Produk terlaris', s: 'Top 5 · item dibeli', span: 4, h: 250, kind: 'html', src: ['product'], filt: true, picker: true,
   cols: () => [{k: 'rank', l: '#', n: 1}, {k: 'item', l: 'Product ID'}, {k: 'purchase_events', l: 'Item dibeli', n: 1, bar: 1, bc: () => colorOf(PICK), f: v => nf(v)},
     {k: 'revenue', l: 'Pendapatan', n: 1, f: v => money(v, 0)}],
   data() { return {cols: this.cols(), rows: D.product.filter(r => r.segmen === PICK)}; },
   draw(el, v) { el.innerHTML = matrix(this.cols(), D.product.filter(r => r.segmen === PICK), {sort: v._sort || 'rank', dir: v._dir || 1}); bindMatrix(el, v); }},
 ]},

/* ================= 3. POLA AKTIVITAS ================= */
{id: 'aktivitas', t: 'Pola Aktivitas', i: 'clock-3', sub: 'Kapan tiap segmen aktif · zona waktu dapat diganti di visual',
 vis: [
  {id: 'hour', t: 'Distribusi event per jam', s: '% event per jam', span: 8, h: 290, kind: 'chart', src: ['hour'], filt: true, tz: true,
   note: `Data asli berstempel UTC; analisis memakai asumsi zona toko UTC+${SRC_TZ}. WIB = UTC+${SRC_TZ} + 4 jam.`,
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'jam', l: `Jam (UTC+${SRC_TZ})`, n: 1}, {k: 'events', l: 'Event', n: 1, f: v => nf(v)}, {k: 'pct_events', l: '% event', n: 1, bar: 1, f: v => pct(v)}],
     rows: D.hour.filter(r => segs().includes(r.segmen))}),
   draw(cx) {
     const H = [...Array(24).keys()], sh = tzShift();
     return new Chart(cx, {type: 'line',
       data: {labels: H.map(h => hh(h).slice(0, 2)), datasets: segs().map(s => ({label: s, borderColor: colorOf(s), backgroundColor: colorOf(s),
         borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: .35,
         data: H.map(h => num((D.hour.find(r => r.segmen === s && r.jam === ((h - sh) % 24 + 24) % 24) || {}).pct_events))}))},
       options: base({interaction: {mode: 'index', intersect: false}, onClick: xf('dataset'),
         plugins: {legend: legend(), tooltip: {callbacks: {title: x => `Pukul ${x[0].label}.00 ${tzName()}`, label: x => ` ${x.dataset.label}: ${pct(x.raw)}`}}},
         scales: {x: {title: {display: true, text: `Jam (${tzName()})`, font: {size: 11}}, ticks: {maxTicksLimit: 12}}, y: {beginAtZero: true, ticks: {callback: v => v + '%'}}}})});
   }},
  {id: 'day', t: 'Aktivitas per hari', s: '% event per hari', note: `Batas hari memakai UTC+${SRC_TZ}.`, span: 4, h: 290, kind: 'chart', src: ['day'], filt: true,
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'nama_hari', l: 'Hari'}, {k: 'events', l: 'Event', n: 1, f: v => nf(v)}, {k: 'pct_events', l: '% event', n: 1, bar: 1, f: v => pct(v)}],
     rows: D.day.filter(r => segs().includes(r.segmen))}),
   draw(cx) {
     const days = [...new Map(D.day.map(r => [r.dow, r.nama_hari])).entries()].sort((a, b) => a[0] - b[0]);
     return new Chart(cx, {type: 'bar',
       data: {labels: days.map(d => String(d[1]).slice(0, 3)), datasets: segs().map(s => ({label: s, backgroundColor: colorOf(s),
         data: days.map(([d]) => num((D.day.find(r => r.segmen === s && r.dow === d) || {}).pct_events))}))},
       options: base({onClick: xf('dataset'), onHover: hoverPtr, plugins: {legend: legend(), tooltip: {callbacks: {label: x => ` ${x.dataset.label}: ${pct(x.raw)}`}}},
         scales: {y: {beginAtZero: true, ticks: {callback: v => v + '%'}}}})});
   }},
  {id: 'hourheat', t: 'Heatmap jam × segmen', s: 'Biru = lebih ramai dari rata-rata', note: 'Indeks terhadap distribusi merata (4,17% per jam).', span: 12, kind: 'html', src: ['hour'], filt: true, tz: true,
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'jam', l: `Jam (UTC+${SRC_TZ})`, n: 1}, {k: 'pct_events', l: '% event', n: 1, f: v => pct(v)}],
     rows: D.hour.filter(r => segs().includes(r.segmen))}),
   draw(el) {
     const H = [...Array(24).keys()], u = 100 / 24, sh = tzShift();
     el.innerHTML = heat(segs(), H.map(h => hh(h).slice(0, 2)), segs().map(s => H.map(h => {
       const v = num((D.hour.find(r => r.segmen === s && r.jam === ((h - sh) % 24 + 24) % 24) || {}).pct_events); return {v, t: Math.log2(Math.max(v / u, .01)) / 1.5};
     })), {dense: 1, lw: 150, fmt: v => nf(v, 1), tip: v => pct(v) + ' event', legend: ['lebih sepi', 'lebih ramai']});
   }},
 ]},

/* ================= 4. RISIKO & PELUANG ================= */
{id: 'risiko', t: 'Risiko & Peluang', i: 'triangle-alert', sub: 'Berapa nilai yang dipertaruhkan, berapa peluangnya, dan tindakan yang diprioritaskan',
 kpi() {
   const c = (D.churn || []).filter(r => segs().includes(r.segmen)), b = sum(c, 'buyers'), a = sum(c, 'at_risk');
   const w = whatIfConv(), ad = sum(w, 'add_buyers'), ar = sum(w, 'add_revenue');
   return [
     {span: 3, i: 'user-minus', l: 'Pembeli berisiko tidak aktif', d: 'inactive', v: compact(a), s: `dari ${nf(b)} pembeli unik`, c: cv('--bad'), tip: nf(a)},
     {span: 3, i: 'percent', l: '% pembeli berisiko', d: 'inactive', v: pct(ratio(a, b) * 100), s: `tidak beraktivitas ≥ ${churnDays()} hari`, c: cv('--warn')},
     {span: 3, i: 'wallet', l: 'Pendapatan historis berisiko', d: 'revrisk', v: moneyC(sum(c, 'revenue_at_risk')), s: 'nilai historis', c: cv('--s4')},
     {span: 3, i: 'rocket', l: `Potensi konversi +${nf(WI.pp, 1)} pp`, v: moneyC(ar), s: `+${nf(ad)} pembeli baru`, c: cv('--ok')},
   ];
 },
 vis: [
  {id: 'churn', t: 'Pembeli berisiko tidak aktif per segmen', s: 'Pendapatan historis · ≥ 60 hari tanpa aktivitas', span: 6, h: 260, kind: 'chart', src: ['churn'], filt: true, info: 'revrisk',
   note: 'Indikasi risiko ketidakaktifan, bukan churn aktual: dataset tidak memiliki label churn dan periode hanya 5 bulan.',
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'buyers', l: 'Pembeli', n: 1, f: v => nf(v)}, {k: 'at_risk', l: 'Berisiko', n: 1, f: v => nf(v)},
     {k: 'pct_at_risk', l: '% berisiko', n: 1, bar: 1, bc: () => cv('--warn'), f: v => pct(v)}, {k: 'revenue_at_risk', l: 'Pendapatan historis', n: 1, bar: 1, bc: () => cv('--bad'), f: v => money(v, 0)},
     {k: 'avg_recency_buyers', l: 'Rata-rata hari tidak aktif', n: 1, f: v => nf(v, 1)}], rows: D.churn.filter(r => segs().includes(r.segmen))}),
   draw(cx) {
     const c = D.churn.filter(r => segs().includes(r.segmen)).sort((a, b) => b.revenue_at_risk - a.revenue_at_risk);
     return new Chart(cx, {type: 'bar', plugins: [VL],
       data: {labels: c.map(r => r.segmen), datasets: [{label: 'Pendapatan historis berisiko', data: c.map(r => r.revenue_at_risk), backgroundColor: c.map(r => colorOf(r.segmen)), maxBarThickness: 30}]},
       options: base({indexAxis: 'y', onClick: xf(), onHover: hoverPtr, layout: {padding: {right: 92}},
         plugins: {vl: {fmt: (v, ds) => moneyC(v)}, tooltip: {callbacks: {label: x => ` ${money(x.raw, 0)} · ${pct(c[x.dataIndex].pct_at_risk)} pembeli berisiko`}}},
         scales: {x: hAxisX(moneyC), y: hAxisY()}})});
   }},
  {id: 'react', t: 'Simulasi reaktivasi', s: 'Jika pembeli berisiko aktif kembali', span: 6, h: 210, kind: 'html', src: ['churn'], filt: true, notable: false,
   note: 'Asumsi: pembeli yang aktif kembali menghasilkan nilai setara rata-rata historisnya. Skenario, bukan prediksi.',
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'at_risk', l: 'Pembeli berisiko', n: 1, f: v => nf(v)}, {k: 'reactivated', l: 'Aktif kembali', n: 1, f: v => nf(v)},
     {k: 'per_buyer', l: 'Nilai historis/pembeli', n: 1, f: v => money(v)}, {k: 'revenue', l: 'Potensi pendapatan', n: 1, bar: 1, bc: () => cv('--ok'), f: v => money(v, 0)}], rows: whatIfReact()}),
   draw(el, v) {
     const r = whatIfReact();
     el.innerHTML = `<div class="wi"><label>Tingkat reaktivasi <output>${nf(WI.react)}%</output>
       <input type="range" min="1" max="50" step="1" value="${WI.react}" data-wi="react"></label>
       <div class="wis"><b>${moneyC(sum(r, 'revenue'))}</b><span>${nf(sum(r, 'reactivated'))} pembeli aktif kembali</span></div></div><div class="wic"><canvas></canvas></div>`;
     const mk = () => new Chart(el.querySelector('canvas'), {type: 'bar', plugins: [VL],
       data: {labels: r.map(x => x.segmen), datasets: [{data: r.map(x => x.revenue), backgroundColor: r.map(x => colorOf(x.segmen)), maxBarThickness: 26}]},
       options: base({indexAxis: 'y', layout: {padding: {right: 60}}, plugins: {vl: {fmt: x => moneyC(x)}, tooltip: {callbacks: {label: x => ` ${money(x.raw, 0)}`}}},
         scales: {x: hAxisX(moneyC), y: hAxisY()}})});
     CH[v.id] = mk();
     bindWI(el, v);
   }},
  {id: 'whatif', t: 'Simulasi peningkatan konversi', s: 'Geser untuk mengubah skenario', span: 12, h: 230, kind: 'html', src: ['econ'], filt: true,
   note: 'Kenaikan dalam poin persentase (pp) dari total pengguna segmen, dibatasi jumlah non-pembeli. Nilai default pembeli baru dari marketing_assumptions. Skenario, bukan prediksi model.',
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'customers', l: 'Pengguna', n: 1, f: v => nf(v)}, {k: 'rate', l: 'Tingkat pembelian kini', n: 1, f: v => pct(v)},
     {k: 'new_rate', l: 'Setelah skenario', n: 1, f: v => pct(v)}, {k: 'add_buyers', l: 'Pembeli baru', n: 1, f: v => nf(v)},
     {k: 'add_revenue', l: 'Potensi pendapatan', n: 1, bar: 1, bc: () => cv('--ok'), f: v => money(v, 0)}], rows: whatIfConv()}),
   draw(el, v) {
     const r = whatIfConv().filter(x => x.add_buyers > 0), tot = sum(D.econ.filter(x => segs().includes(x.segmen)), 'segment_revenue');
     const add = sum(r, 'add_revenue');
     el.innerHTML = `<div class="wi">
       <label>Kenaikan tingkat pembelian <output>+${nf(WI.pp, 1)} pp</output>
         <input type="range" min="0.5" max="5" step="0.5" value="${WI.pp}" data-wi="pp"></label>
       <label>Pendapatan per pembeli baru (${esc(D.meta.currency)})
         <input type="number" min="0" step="0.5" value="${nf(WI.val ?? baseSpb(), 2).replace(/\./g, '').replace(',', '.')}" data-wi="val"></label>
       <div class="wis"><b>+${moneyC(add)}</b><span>+${nf(sum(r, 'add_buyers'))} pembeli · +${pct(ratio(add, tot) * 100)} dari pendapatan saat ini</span></div></div>
       <div class="wic"><canvas></canvas></div>`;
     CH[v.id] = new Chart(el.querySelector('canvas'), {type: 'bar', plugins: [VL],
       data: {labels: r.map(x => x.segmen), datasets: [{label: 'Potensi pendapatan', data: r.map(x => x.add_revenue), backgroundColor: r.map(x => colorOf(x.segmen)), maxBarThickness: 44}]},
       options: base({onClick: xf(), onHover: hoverPtr, layout: {padding: {top: 18}}, plugins: {vl: {fmt: x => moneyC(x)},
         tooltip: {callbacks: {label: x => ` ${money(x.raw, 0)} · +${nf(r[x.dataIndex].add_buyers)} pembeli`}}},
         scales: {x: catAxis(), y: {beginAtZero: true, ticks: {callback: x => moneyC(x)}}}})});
     bindWI(el, v);
   }},
  {id: 'strat', t: 'Rekomendasi tindakan per segmen', s: 'Urut berdasarkan nilai peluang', span: 12, kind: 'html', src: ['econ'], filt: true,
   note: 'Estimasi +1 pp memakai asumsi nilai pembeli baru. Arahkan kursor ke kartu untuk metrik pantau. Validasi dengan uji A/B sebelum diperluas.',
   data: () => ({cols: [{k: 'prio', l: 'Prioritas'}, {k: 'segmen', l: 'Segmen', seg: 1}, {k: 'goal', l: 'Tujuan'}, {k: 'act', l: 'Tindakan'}, {k: 'kpi', l: 'Metrik pantau'}, {k: 'valTxt', l: 'Nilai terukur'}],
     rows: recommendations().sort((a, b) => a.prio.localeCompare(b.prio))}),
   draw(el) {
     el.innerHTML = `<div class="strat">${recommendations().sort((a, b) => a.prio.localeCompare(b.prio)).map(o => `
       <div class="sc" style="--sc:${colorOf(o.segmen)}" title="Metrik pantau: ${esc(o.kpi)}"><div class="sch"><i data-lucide="${o.icon}"></i>${esc(o.segmen)}<span class="pr">${o.prio}</span></div>
       <div class="scm"><span class="hi">${o.goal}</span><span class="val">${esc(o.valTxt)}</span></div>
       <p>${esc(o.act)}</p></div>`).join('')}</div>`;
   }},
  {id: 'assume', t: 'Asumsi analisis', s: 'Parameter dari analisis_marketing.py', span: 12, h: 260, kind: 'html', src: ['assume'],
   cols: () => [{k: 'parameter', l: 'Parameter'}, {k: 'nilai', l: 'Nilai'}],
   data() { return {cols: this.cols(), rows: D.assume}; },
   draw(el) { el.innerHTML = matrix(this.cols(), D.assume); }},
 ]},

/* ================= 5. EVALUASI MODEL ================= */
{id: 'model', t: 'Evaluasi Model', i: 'activity', sub: 'Apakah segmentasi K-Means valid, stabil, dan tidak bergantung pada satu fitur',
 kpi() {
   const g = s => { const r = (D.val || []).find(x => x.metrik.includes(s)); return r ? r.nilai : null; };
   const sk = g('Silhouette K-Means'), sb = g('Silhouette Bisecting'), ar = g('rata-rata'), rp = g('reproduksi');
   const lvl = (v, hi, md) => v == null ? '' : v >= hi ? 'tinggi' : v >= md ? 'sedang' : 'rendah';
   return [
     {span: 3, i: 'git-branch', l: 'Jumlah cluster (K)', v: D.meta.k, s: (D.kcmp || []).length ? 'silhouette & stabilitas multi-seed' : 'dipilih via elbow + silhouette'},
     {span: 3, i: 'diamond', l: 'Silhouette K-Means', v: sk != null ? nf(sk, 3) : '—', s: sk != null ? `kualitas pemisahan <b>${lvl(sk, .7, .5)}</b> (rentang −1 s.d. 1)` : 'jalankan validasi_kmeans.py', c: cv('--ok')},
     {span: 3, i: 'git-compare', l: 'Silhouette Bisecting K-Means', v: sb != null ? nf(sb, 3) : '—', s: sk != null && sb != null ? `K-Means ${sk >= sb ? 'lebih tinggi' : 'lebih rendah'} ${nf(Math.abs(sk - sb), 3)}` : 'metode pembanding', c: cv('--s6')},
     {span: 3, i: 'waves', l: 'ARI antar seed', v: ar != null ? nf(ar, 2) : '—', s: ar != null ? `stabilitas <b>${lvl(ar, .8, .5)}</b>${rp != null ? ` · reproduksi ${nf(rp, 2)}` : ''}` : '', c: cv('--warn')},
   ];
 },
 vis: [
  ...[['elbow', 'Metode elbow (WSSSE)', 'wssse', '--s1', v => compact(v)], ['silk', 'Silhouette per K', 'silhouette', '--s6', v => nf(v, 3)]].map(([id, t, f, c, fm]) => ({
   id, t, s: 'Garis putus-putus = K terpilih', span: 6, h: 240, kind: 'chart', src: ['ksel'],
   data: () => ({cols: [{k: 'k', l: 'K', n: 1}, {k: 'wssse', l: 'WSSSE', n: 1, f: v => nf(v)}, {k: 'silhouette', l: 'Silhouette', n: 1, bar: 1, f: v => nf(v, 4)}], rows: D.ksel}),
   draw(cx) {
     const ks = D.ksel, iK = ks.findIndex(r => r.k === D.meta.k);
     const vline = {id: 'kline', afterDraw(ch) { if (iK < 0) return;
       const x = ch.scales.x.getPixelForValue(iK), a = ch.chartArea, t = ch.ctx;
       t.save(); t.setLineDash([4, 4]); t.strokeStyle = cv('--muted'); t.beginPath(); t.moveTo(x, a.top); t.lineTo(x, a.bottom); t.stroke();
       t.setLineDash([]); t.fillStyle = cv('--ink2'); t.font = '600 10.5px "Segoe UI", Inter, sans-serif'; t.textAlign = 'left'; t.fillText(`K = ${D.meta.k}`, x + 5, a.top + 10); t.restore(); }};
     return new Chart(cx, {type: 'line', plugins: [vline],
       data: {labels: ks.map(r => r.k), datasets: [{label: t, data: ks.map(r => r[f]), borderColor: cv(c), borderWidth: 2.2, tension: .3,
         pointRadius: ks.map((_, i) => i === iK ? 6 : 3.5), pointBackgroundColor: cv(c), pointBorderColor: cv('--card'), pointBorderWidth: 2,
         fill: true, backgroundColor: cv(c) + '1A'}]},
       options: base({plugins: {tooltip: {callbacks: {title: x => `K = ${x[0].label}`, label: x => ` ${fm(x.raw)}`}}},
         scales: {x: {title: {display: true, text: 'Jumlah cluster (K)', font: {size: 11}}}, y: {ticks: {callback: v => fm(v)}}}})});
   }})),
  {id: 'kcmp', t: 'Perbandingan K multi-seed', s: '5 seed × 3 sampel per K · baris tebal = K terpilih', span: 12, h: 200, kind: 'html', src: ['kcmp'],
   note: 'Silhouette dihitung pada 15 kombinasi seed K-Means dan sampel 10%. Std kecil dan ARI tinggi berarti hasil tidak bergantung pada seed tertentu.',
   cols: () => [{k: 'k', l: 'K', n: 1}, {k: 'silhouette_mean', l: 'Silhouette rata-rata', n: 1, bar: 1, f: v => nf(v, 3)},
     {k: 'silhouette_std', l: 'Std', n: 1, f: v => nf(v, 3)}, {k: 'silhouette_min', l: 'Terburuk', n: 1, f: v => nf(v, 3)},
     {k: 'silhouette_max', l: 'Terbaik', n: 1, f: v => nf(v, 3)}, {k: 'ari_mean', l: 'ARI antar seed', n: 1, bar: 1, bc: () => cv('--ok'), f: v => nf(v, 3)},
     {k: 'min_cluster_pct', l: 'Cluster terkecil', n: 1, f: v => pct(v)}],
   data() { return {cols: this.cols(), rows: D.kcmp}; },
   draw(el, v) {
     el.innerHTML = matrix(this.cols(), D.kcmp, {sort: v._sort, dir: v._dir});
     el.querySelectorAll('tbody tr').forEach((tr, i) => { if (num(D.kcmp[i] && D.kcmp[i].k) === D.meta.k && !v._sort) tr.classList.add('pick'); });
     bindMatrix(el, v);
   }},
  {id: 'sildetail', t: 'Silhouette per segmen', s: 'Segmen vs semua segmen lain', span: 6, h: 250, kind: 'chart', src: ['sil'], filt: true,
   rows: () => (D.sil || []).filter(r => r.cakupan.includes('Keseluruhan') || segs().includes(r.cakupan.replace(' vs lainnya', ''))),
   data() { return {cols: [{k: 'cakupan', l: 'Cakupan'}, {k: 'silhouette', l: 'Silhouette', n: 1, bar: 1, f: v => nf(v, 4)}], rows: this.rows()}; },
   draw(cx) {
     const sd = this.rows(), nm = r => r.cakupan.replace(' vs lainnya', '');
     return new Chart(cx, {type: 'bar', plugins: [VL],
       data: {labels: sd.map(nm), datasets: [{data: sd.map(r => r.silhouette), maxBarThickness: 24,
         backgroundColor: sd.map(r => r.cakupan.includes('Keseluruhan') ? cv('--muted') : colorOf(nm(r)))}]},
       options: base({indexAxis: 'y', onClick: xf(), onHover: hoverPtr, layout: {padding: {right: 40}}, plugins: {vl: {fmt: v => nf(v, 3)}},
         scales: {x: {min: 0, max: 1, grid: {color: cv('--line')}, border: {display: false}}, y: hAxisY()}})});
   }},
  {id: 'stab', t: 'Stabilitas per segmen', s: 'Jaccard vs seed 42', note: 'Titik = rata-rata, bar = rentang min–maks dari 9 seed pembanding.', span: 6, kind: 'html', src: ['stab'], filt: true,
   data: () => ({cols: [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'jaccard_mean', l: 'Rata-rata', n: 1, bar: 1, f: v => nf(v, 3)}, {k: 'jaccard_min', l: 'Min', n: 1, f: v => nf(v, 3)},
     {k: 'jaccard_max', l: 'Maks', n: 1, f: v => nf(v, 3)}], rows: D.stab.filter(r => segs().includes(r.segmen))}),
   draw(el) {
     el.innerHTML = `<div class="ranges">${D.stab.filter(r => segs().includes(r.segmen)).map(r => `
       <div class="rg"><div class="rl"><span>${esc(r.segmen)}</span><em>${nf(r.jaccard_mean, 2)} (${nf(r.jaccard_min, 2)}–${nf(r.jaccard_max, 2)})</em></div>
       <div class="track"><div class="fill" style="left:${r.jaccard_min * 100}%;width:${(r.jaccard_max - r.jaccard_min) * 100}%;background:${colorOf(r.segmen)};opacity:.35"></div>
       <div class="dot" style="left:${r.jaccard_mean * 100}%;background:${colorOf(r.segmen)}"></div></div></div>`).join('')}
       <div class="axis"><span>0</span><span>0,5</span><span>1,0</span></div></div>`;
   }},
  {id: 'seed', t: 'WSSSE per seed', s: 'Biru tua = WSSSE terendah', span: 6, h: 230, kind: 'chart', src: ['seed'],
   data: () => ({cols: [{k: 'seed', l: 'Seed', n: 1}, {k: 'wssse', l: 'WSSSE', n: 1, bar: 1, f: v => nf(v)}], rows: D.seed}),
   draw(cx) {
     const sw = D.seed, mn = Math.min(...sw.map(r => r.wssse)), mx = Math.max(...sw.map(r => r.wssse));
     return new Chart(cx, {type: 'bar',
       data: {labels: sw.map(r => 'seed ' + r.seed), datasets: [{data: sw.map(r => r.wssse), maxBarThickness: 28,
         backgroundColor: sw.map(r => r.wssse <= mn * 1.001 ? cv('--s2') : cv('--s1') + '99')}]},
       options: base({plugins: {tooltip: {callbacks: {label: x => ` WSSSE ${nf(x.raw)}`}}},
         scales: {y: {min: mn * .97, max: mx * 1.01, ticks: {maxTicksLimit: 5, callback: v => nf(v / 1e6, 2) + ' jt'}}}})});
   }},
  {id: 'corr', t: 'Korelasi fitur', s: 'Pearson, setelah log1p + scaling', note: '|r| > 0,8 menandakan fitur redundan.', span: 6, kind: 'html', src: ['corr'],
   data: () => ({cols: [{k: 'fitur', l: 'Fitur'}, ...D.corr.map(r => ({k: r.fitur, l: r.fitur, n: 1, f: v => nf(v, 3)}))], rows: D.corr}),
   draw(el) {
     const co = D.corr, keys = co.map(r => r.fitur);
     const nm = x => x === 'days_since_last_event' ? 'recency' : x.replace(/_count|total_/g, '');
     el.innerHTML = heat(co.map(r => nm(r.fitur)), keys.map(nm), co.map(r => keys.map(k => ({v: r[k], t: r[k]}))),
       {lw: 90, fmt: v => nf(v, 2), legend: ['negatif', 'positif']});
   }},
  ...[['val', 'Ringkasan validasi', [{k: 'metrik', l: 'Metrik'}, {k: 'nilai', l: 'Nilai', n: 1, f: v => nf(v, 3)}]],
      ['sens', 'Sensitivitas fitur', [{k: 'model', l: 'Model'}, {k: 'silhouette', l: 'Silhouette', n: 1, f: v => nf(v, 4)}, {k: 'ari_vs_model_utama', l: 'ARI vs model utama', n: 1, bar: 1, f: v => nf(v, 4)}]],
      ['purity', 'Kemurnian cluster', [{k: 'segmen', l: 'Segmen', seg: 1}, {k: 'pct_pernah_beli', l: '% membeli', n: 1, bar: 1, bc: () => cv('--ok'), f: v => pct(v)},
        {k: 'pct_pernah_cart', l: '% keranjang', n: 1, f: v => pct(v)}, {k: 'pct_cart_tanpa_beli', l: '% keranjang tanpa beli', n: 1, bar: 1, bc: () => cv('--warn'), f: v => pct(v)}]]]
    .map(([id, t, cols]) => ({id, t, s: '', span: 4, h: 240, kind: 'html', src: [id], filt: id === 'purity',
      rows: () => id === 'purity' ? D.purity.filter(r => segs().includes(r.segmen)) : D[id],
      data() { return {cols, rows: this.rows()}; },
      draw(el, v) { el.innerHTML = matrix(cols, this.rows(), {sort: v._sort, dir: v._dir, click: id === 'purity'}); bindMatrix(el, v); }})),
 ]},

/* ================= 6. PIPELINE DATA ================= */
{id: 'pipeline', t: 'Pipeline Data', i: 'server', sub: 'Performa batch processing Spark + HDFS di Docker',
 kpi() {
   const b = D.bench || [], tt = sum(b, 'detik'), sl = [...b].sort((x, y) => y.detik - x.detik)[0];
   const sp = k => ((D.spec || []).find(r => r.parameter === k) || {}).nilai || '—';
   return [
     {span: 3, i: 'timer', l: 'Total durasi pipeline', v: b.length ? `${nf(tt / 60, 1)} mnt` : '—', s: b.length ? `${nf(tt)} detik` : 'jalankan benchmark.py'},
     {span: 3, i: 'hourglass', l: 'Tahap terlama', v: sl ? `${nf(sl.detik, 0)} dtk` : '—', s: sl ? esc(sl.tahap.replace(/^\d+\.\s*/, '')) : '', c: cv('--warn')},
     {span: 3, i: 'hard-drive', l: 'Data mentah (HDFS)', v: esc(sp('Ukuran data mentah (HDFS)')), s: `${esc(sp('Jumlah file CSV'))} file CSV`, c: cv('--s2')},
     {span: 3, i: 'list-ordered', l: 'Jumlah event', v: esc(sp('Jumlah event')), s: `${esc(sp('Jumlah pelanggan'))} pengguna`, c: cv('--s6')},
   ];
 },
 vis: [
  {id: 'bench', t: 'Durasi per tahap', s: 'Waktu eksekusi (detik)', span: 7, h: 300, kind: 'chart', src: ['bench'],
   data: () => ({cols: [{k: 'tahap', l: 'Tahap'}, {k: 'detik', l: 'Detik', n: 1, bar: 1, f: v => nf(v, 1)}, {k: 'persen', l: '%', n: 1, f: v => v != null ? pct(v) : '—'}], rows: D.bench}),
   draw(cx) {
     const b = D.bench, tt = sum(b, 'detik');
     return new Chart(cx, {type: 'bar', plugins: [VL],
       data: {labels: b.map(r => r.tahap.replace(/^\d+\.\s*/, '')), datasets: [{data: b.map(r => r.detik), backgroundColor: cv('--s1'), maxBarThickness: 20}]},
       options: base({indexAxis: 'y', layout: {padding: {right: 80}}, plugins: {vl: {fmt: v => `${nf(v, 1)} dtk · ${pct(ratio(v, tt) * 100)}`},
         tooltip: {callbacks: {label: x => ` ${nf(x.raw, 1)} detik`}}},
         scales: {x: hAxisX(v => nf(v)), y: hAxisY()}})});
   }},
  {id: 'spec', t: 'Spesifikasi lingkungan', s: '', span: 5, h: 300, kind: 'html', src: ['spec'],
   cols: () => [{k: 'parameter', l: 'Parameter'}, {k: 'nilai', l: 'Nilai'}],
   data() { return {cols: this.cols(), rows: D.spec}; },
   draw(el) { el.innerHTML = matrix(this.cols(), D.spec); }},
 ]},

/* ================= 7. DEFINISI & METODOLOGI ================= */
{id: 'metodologi', t: 'Definisi & Metodologi', i: 'book-open', sub: 'Tujuan, definisi metrik, cara segmentasi dibentuk, dan batasan interpretasi',
 vis: [
  {id: 'tujuan', t: 'Tujuan dashboard', s: '', span: 12, kind: 'html', src: [], notools: true,
   draw(el) {
     el.innerHTML = `<div class="doc"><p><b>Pertanyaan bisnis:</b> segmen pengguna mana yang paling bernilai, di mana peluang pertumbuhan terbesar, dan tindakan apa yang diprioritaskan untuk retensi dan konversi?</p>
       <p><b>Pengguna sasaran:</b> tim marketing/CRM dan analis pelanggan. <b>Jenis analisis:</b> deskriptif dan diagnostik, dengan simulasi skenario (bukan prediksi).</p>
       <div class="callout"><i data-lucide="calendar-clock"></i><div><b>Periode data: ${esc(D.meta.period)} (historis).</b> Waktu "dimuat" di header adalah waktu dashboard membaca PostgreSQL, bukan waktu data.
       Temuan menggambarkan perilaku pada periode tersebut dan tidak otomatis mewakili kondisi bisnis saat ini.</div></div></div>`;
   }},
  {id: 'glossary', t: 'Definisi metrik', s: 'Rumus dan tabel sumber setiap KPI', span: 12, h: 520, kind: 'html', src: [],
   cols: () => [{k: 'n', l: 'Metrik'}, {k: 'd', l: 'Definisi'}, {k: 'f', l: 'Rumus'}, {k: 's', l: 'Tabel sumber'}],
   rows: () => Object.values(DEF).map(([n, d, f, s]) => ({n, d, f, s})),
   data() { return {cols: this.cols(), rows: this.rows()}; },
   draw(el) { el.innerHTML = `<div class="wrap">${matrix(this.cols(), this.rows())}</div>`; }},
  {id: 'method', t: 'Metode segmentasi', s: '', span: 6, kind: 'html', src: [], notools: true,
   draw(el) {
     const sk = ((D.val || []).find(x => x.metrik.includes('Silhouette K-Means')) || {}).nilai;
     el.innerHTML = `<ol class="steps">
       <li><b>Unit analisis:</b> pengguna (user_id) dengan minimal satu event.</li>
       <li><b>6 fitur perilaku & belanja:</b> jumlah view, cart, remove, purchase (item), jumlah sesi, dan total pendapatan. Recency (hari sejak aktivitas terakhir) sengaja tidak dimasukkan ke K-Means; dipakai terpisah untuk profil dan analisis risiko tidak aktif.</li>
       <li><b>Transformasi:</b> log1p untuk meredam skew, lalu StandardScaler (mean 0, std 1) agar fitur berskala besar tidak mendominasi jarak.</li>
       <li><b>Model:</b> K-Means Spark MLlib (init k-means||, maxIter 50, tol 1e-4), K = ${D.meta.k}, seed 42${sk != null ? `, silhouette ${nf(sk, 3)}` : ''}. K dipilih dari silhouette rata-rata dan stabilitas (ARI) pada 5 seed × 3 sampel, bukan dari satu kali run; elbow WSSSE sebagai pendukung.</li>
       <li><b>Validasi:</b> stabilitas 10 seed (ARI, Jaccard), pembanding Bisecting K-Means, uji sensitivitas tanpa session_count, dan perbandingan K=4 vs K=5 multi-seed (banding_k4_k5.py).</li>
       <li><b>Penamaan segmen (otomatis, penamaan.py):</b> cluster dengan tingkat pembelian ≥ 50% menjadi kelompok Pembeli (bila lebih dari satu, diurutkan dari rata-rata pendapatan); cluster lainnya menjadi kelompok Pengunjung, diurutkan dari rata-rata aktivitas keranjang (Aktif → Kasual).</li></ol>`;
   }},
  {id: 'caveat', t: 'Batasan interpretasi', s: '', span: 6, kind: 'html', src: [], notools: true,
   draw(el) {
     el.innerHTML = `<ul class="steps cv">
       <li><b>Tingkat pembelian segmen pembeli ≈ 100%</b> karena segmentasi memakai riwayat belanja. Jangan dibaca sebagai efektivitas pemasaran.</li>
       <li><b>Tidak aktif ≥ ${churnDays()} hari ≠ churn.</b> Tidak ada label churn, dan periode data hanya ±5 bulan.</li>
       <li><b>Pendapatan = jumlah harga event purchase.</b> Tanpa kuantitas, diskon, ongkir, retur, atau biaya, sehingga bukan laba dan bukan margin kontribusi.</li>
       <li><b>Bukan AOV/CLV.</b> Dataset tidak memiliki ID pesanan; nilai per pembeli adalah kumulatif selama periode data.</li>
       <li><b>Zona waktu:</b> data asli UTC, analisis memakai asumsi UTC+${SRC_TZ}. Konversi ke WIB tersedia di halaman Pola Aktivitas.</li>
       <li><b>Mata uang:</b> mengikuti kolom price dataset (ditampilkan sebagai ${esc(D.meta.currency)}). Verifikasi dengan dokumentasi sumber data.</li>
       <li><b>Simulasi</b> adalah skenario berbasis asumsi yang dapat diubah, bukan prediksi model.</li></ul>`;
   }},
  {id: 'roadmap', t: 'Pengembangan berikutnya', s: 'Dari deskriptif ke preskriptif', span: 12, kind: 'html', src: [], notools: true,
   draw(el) {
     const st = [['Deskriptif', 'check', 'tersedia', 'Profil segmen, konsentrasi pendapatan, corong, pola aktivitas.'],
       ['Diagnostik', 'check', 'tersedia', 'Kebocoran corong, dekomposisi nilai pembeli, indeks perilaku, validasi model.'],
       ['Prediktif', 'circle-dashed', 'perlu data/model', 'Skor risiko ketidakaktifan (klasifikasi), prediksi pembelian ulang, CLV (BG/NBD + Gamma-Gamma) dengan train/test berbasis waktu.'],
       ['Preskriptif', 'circle-dashed', 'perlu eksperimen', 'Uji A/B kampanye per segmen, ROAS/CAC dan margin kontribusi bila data biaya tersedia.']];
     el.innerHTML = `<div class="road">${st.map(([t, i, s, d]) => `<div class="rs ${s === 'tersedia' ? 'on' : ''}"><div class="rh"><i data-lucide="${i}"></i><b>${t}</b><span>${s}</span></div><p>${d}</p></div>`).join('')}</div>`;
   }},
 ]},
];

/* =====================================================================
   RENDER
   ===================================================================== */
const page = () => PAGES.find(p => p.id === PAGE) || PAGES[0];
const missing = v => (v.src || []).filter(k => !(D[k] && D[k].length));

function destroyCharts() { for (const k in CH) { CH[k].destroy(); delete CH[k]; } }

function renderPage() {
  destroyCharts();
  closeFocus(true);
  const p = page();
  if (!PICK || !segs().includes(PICK)) PICK = segs()[0];
  const el = $('page');
  el.innerHTML = `<div class="ptitle"><h1>${esc(p.t)}</h1><p>${esc(p.sub)}</p></div>` +
    (p.kpi ? kpiCards(p.kpi()) : '') +
    p.vis.map(v => `<article class="vis" id="v-${v.id}" style="--span:${v.span};--h:${v.h || 260}px"></article>`).join('');
  p.vis.forEach(drawVisual);
  ico();
  document.querySelectorAll('.pagetabs a').forEach(a => a.classList.toggle('on', a.dataset.p === p.id));
}

function drawVisual(v) {
  const box = $('v-' + v.id); if (!box) return;
  if (CH[v.id]) { CH[v.id].destroy(); delete CH[v.id]; }
  const miss = missing(v), asTable = TV.has(v.id) && v.data;
  const foc = box.classList.contains('focus');
  const tools = v.notools ? '' : `<div class="tools">
      ${v.data ? `<button data-a="table" class="${asTable ? 'on' : ''}" title="${asTable ? 'Tampilkan visual' : 'Lihat sebagai tabel'}"><i data-lucide="${asTable ? 'bar-chart-3' : 'table-2'}"></i></button>
      <button data-a="csv" title="Ekspor CSV"><i data-lucide="download"></i></button>` : ''}
      <button data-a="focus" title="${foc ? 'Tutup' : 'Mode fokus'}"><i data-lucide="${foc ? 'minimize-2' : 'maximize-2'}"></i></button></div>`;
  const tz = v.tz && !asTable ? `<div class="seg" data-ctl="tz"><button data-v="src" class="${TZ === 'src' ? 'on' : ''}">UTC+${SRC_TZ}</button><button data-v="wib" class="${TZ === 'wib' ? 'on' : ''}">WIB</button></div>` : '';
  const pills = v.picker ? `<div class="pills">${segs().map(s => `<button class="pill ${s === PICK ? 'on' : ''}" data-pick="${esc(s)}" style="--pc:${colorOf(s)}"><i></i>${esc(s)}</button>`).join('')}</div>` : '';
  const tipTxt = [v.info && DEF[v.info] ? `${DEF[v.info][0]}: ${DEF[v.info][1]}\nRumus: ${DEF[v.info][2]}` : '', v.note || ''].filter(Boolean).join('\n\n');
  const tip = tipTxt ? `<span class="inf" tabindex="0" title="${esc(tipTxt)}"><i data-lucide="info"></i></span>` : '';
  box.innerHTML = `<div class="vh"><div class="vt"><h3>${esc(v.t)}${tip}${v.filt && isF() ? '<span class="fi" title="Visual ini terfilter"><i data-lucide="filter"></i></span>' : ''}</h3>
      ${v.s ? `<p>${esc(v.s)}</p>` : ''}</div><div class="vx">${v.head && !asTable ? v.head() : ''}${tz}${tools}</div></div>${pills}
    ${asTable ? '<div class="vtab"></div>' : `<div class="vb ${v.kind === 'chart' ? 'chart' : ''}"></div>`}
`;
  const body = box.querySelector(asTable ? '.vtab' : '.vb');

  if (miss.length) {
    body.innerHTML = `<div class="empty"><div><b>Data belum tersedia</b><br>Tabel <code>${miss.join(', ')}</code> kosong. Jalankan
      <code>${[...new Set(miss.map(k => SRC[k] || '—'))].join(', ')}</code></div></div>`;
  } else if (asTable) {
    const d = v.data(); body.innerHTML = `<div class="wrap">${matrix(d.cols, d.rows, {sort: v._sort, dir: v._dir, click: 1})}</div>`; bindMatrix(body, v);
  } else if (v.kind === 'chart') {
    body.innerHTML = '<canvas></canvas>'; CH[v.id] = v.draw(body.querySelector('canvas'), v);
  } else {
    v.draw(body, v);
  }

  box.querySelectorAll('.tools button').forEach(b => b.onclick = () => {
    const a = b.dataset.a;
    if (a === 'table') { TV.has(v.id) ? TV.delete(v.id) : TV.add(v.id); drawVisual(v); }
    if (a === 'csv') exportCSV(v);
    if (a === 'focus') toggleFocus(v);
  });
  box.querySelectorAll('[data-ctl="stat"] button').forEach(b => b.onclick = () => { STAT = b.dataset.v; v._sort = null; drawVisual(v); });
  box.querySelectorAll('[data-ctl="tz"] button').forEach(b => b.onclick = () => { TZ = b.dataset.v; page().vis.filter(x => x.tz).forEach(drawVisual); });
  box.querySelectorAll('[data-pick]').forEach(b => b.onclick = () => { PICK = b.dataset.pick; page().vis.filter(x => x.picker).forEach(drawVisual); });
  ico();
}

/* parameter simulasi: perbarui visual simulasi + KPI halaman tanpa render ulang semuanya */
function bindWI(el, v) {
  el.querySelectorAll('[data-wi]').forEach(inp => {
    const k = inp.dataset.wi;
    const apply = () => {
      const x = parseFloat(inp.value);
      if (k === 'val') WI.val = isFinite(x) && x >= 0 ? x : null; else WI[k] = x;
      clearTimeout(v._t);
      v._t = setTimeout(() => {
        const ae = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.wi : null;
        drawVisual(v); refreshKpis();
        if (ae) { const n = $('v-' + v.id).querySelector(`[data-wi="${ae}"]`); if (n) { n.focus(); if (n.type === 'number') { const l = n.value.length; try { n.setSelectionRange(l, l); } catch (e) { /* type number */ } } } }
      }, k === 'val' ? 350 : 60);
    };
    inp.addEventListener(inp.type === 'range' ? 'input' : 'change', apply);
    if (inp.type === 'range') { const o = inp.parentElement.querySelector('output'); inp.addEventListener('input', () => { o.textContent = k === 'pp' ? `+${nf(inp.value, 1)} pp` : `${nf(inp.value)}%`; }); }
  });
}
function refreshKpis() {
  const p = page(); if (!p.kpi) return;
  const old = [...$('page').querySelectorAll('.kpi')]; if (!old.length) return;
  const tmp = document.createElement('div'); tmp.innerHTML = kpiCards(p.kpi());
  [...tmp.children].forEach((n, i) => old[i] && old[i].replaceWith(n)); ico();
}

/* ---------- focus mode ---------- */
let FOCUS = null;
function toggleFocus(v) {
  if (FOCUS) { closeFocus(); return; }
  const box = $('v-' + v.id); FOCUS = v;
  const sc = document.createElement('div'); sc.className = 'scrim'; sc.id = 'scrim'; sc.onclick = () => closeFocus();
  document.body.appendChild(sc); box.classList.add('focus'); document.body.style.overflow = 'hidden'; drawVisual(v);
}
function closeFocus(silent) {
  if (!FOCUS) return;
  const v = FOCUS; FOCUS = null;
  const sc = $('scrim'); if (sc) sc.remove();
  document.body.style.overflow = '';
  const box = $('v-' + v.id); if (box) box.classList.remove('focus');
  if (!silent) drawVisual(v);
}

/* ---------- export CSV ---------- */
function exportCSV(v) {
  const d = v.data(), q = x => { const s = String(x ?? ''); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const csv = [d.cols.map(c => q(c.l)).join(','), ...d.rows.map(r => d.cols.map(c => q(r[c.k])).join(','))].join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + csv], {type: 'text/csv;charset=utf-8'}));
  a.download = `${v.id}${isF() ? '_terfilter' : ''}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast(`${d.rows.length} baris diekspor ke ${a.download}`);
}

/* ---------- slicer / cross-filter ---------- */
function toggleSeg(s, multi) {
  if (multi) { SEL.has(s) ? SEL.delete(s) : SEL.add(s); }
  else if (SEL.size === 1 && SEL.has(s)) SEL.clear();
  else SEL = new Set([s]);
  if (SEL.size === ORDER().length) SEL.clear();
  onFilter();
}
function onFilter() { renderSlicer(); renderPage(); }

function renderSlicer() {
  const all = !SEL.size;
  $('slicer-val').textContent = all ? 'Semua' : SEL.size === 1 ? [...SEL][0] : `${SEL.size} dipilih`;
  $('slicer-pop').innerHTML = `<label><input type="checkbox" data-all ${all ? 'checked' : ''}><b>Pilih semua</b></label><hr>` +
    ORDER().map(s => `<label><input type="checkbox" value="${esc(s)}" ${all || SEL.has(s) ? 'checked' : ''}>
      <span class="sw" style="background:${colorOf(s)}"></span>${esc(s)}</label>`).join('');
  $('slicer-pop').querySelectorAll('input').forEach(i => i.onchange = () => {
    if (i.hasAttribute('data-all')) SEL.clear();
    else {
      if (!SEL.size) SEL = new Set(ORDER());
      i.checked ? SEL.add(i.value) : SEL.delete(i.value);
      if (!SEL.size || SEL.size === ORDER().length) SEL.clear();
    }
    onFilter();
  });
  $('chips').innerHTML = [...SEL].map(s => `<span class="chip"><span class="sw" style="background:${colorOf(s)}"></span>${esc(s)}
    <button data-rm="${esc(s)}" aria-label="Hapus filter ${esc(s)}"><i data-lucide="x"></i></button></span>`).join('');
  $('chips').querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { SEL.delete(b.dataset.rm); onFilter(); });
  $('btn-reset').classList.toggle('hide', all);
  ico();
}
$('slicer-btn').onclick = e => {
  e.stopPropagation();
  const p = $('slicer-pop'), open = p.classList.toggle('hide') === false;
  $('slicer-btn').setAttribute('aria-expanded', open);
};
document.addEventListener('click', e => { if (!$('slicer').contains(e.target)) { $('slicer-pop').classList.add('hide'); $('slicer-btn').setAttribute('aria-expanded', false); } });
$('btn-reset').onclick = () => { SEL.clear(); onFilter(); };
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeFocus(); $('slicer-pop').classList.add('hide'); } });

/* ---------- page tabs ---------- */
function renderTabs() {
  $('pagetabs').innerHTML = PAGES.map(p => `<a href="#${p.id}" data-p="${p.id}" title="${esc(p.sub)}"><i data-lucide="${p.i}"></i>${esc(p.t)}</a>`).join('');
}
window.addEventListener('hashchange', () => {
  const h = location.hash.slice(1);
  if (PAGES.some(p => p.id === h) && h !== PAGE) { PAGE = h; if (D) { renderPage(); window.scrollTo({top: 0}); } }
});

/* ---------- tema ---------- */
function setThemeIcon() {
  const d = document.documentElement.dataset.theme === 'dark';
  $('btn-theme').innerHTML = `<i data-lucide="${d ? 'sun' : 'moon'}"></i>`;
  $('btn-theme').title = d ? 'Mode terang' : 'Mode gelap';
  ico();
}
$('btn-theme').onclick = () => {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t; store.set('siq-theme', t); setThemeIcon();
  if (D) { renderSlicer(); renderPage(); }
};

/* ---------- load data ---------- */
function relabel(d) {
  for (const k of Object.keys(d)) {
    if (!Array.isArray(d[k])) continue;
    d[k].forEach(r => { for (const f in r) {
      const v = r[f]; if (typeof v !== 'string') continue;
      if (RENAME[v]) r[f] = RENAME[v];
      else if (f === 'cakupan') for (const o in RENAME) r[f] = r[f].replace(o, RENAME[o]);
    } });
  }
  d.meta.order = d.meta.order.map(s => RENAME[s] || s);
}

async function load(force) {
  const btn = $('btn-refresh'); btn.classList.add('busy');
  if (!D) $('loader').classList.remove('hide');
  try {
    const res = await fetch('/api/data' + (force ? '?refresh=1' : ''));
    const j = await res.json().catch(() => ({error: res.statusText}));
    if (!res.ok) throw new Error(j.error || res.statusText);
    for (const k of Object.keys(SRC)) if (!Array.isArray(j[k])) j[k] = [];
    relabel(j);
    /* hitung ulang persentase dari angka mentah agar pembulatan KPI, grafik, dan tabel konsisten */
    const U = sum(j.econ, 'customers'), R = sum(j.econ, 'segment_revenue');
    j.econ.forEach(r => { r.pct_customers = ratio(r.customers, U) * 100; r.revenue_share = ratio(r.segment_revenue, R) * 100;
      r.buyer_rate = ratio(r.buyers, r.customers) * 100; });
    D = j;
    [...SEL].forEach(s => { if (!ORDER().includes(s)) SEL.delete(s); });
    const m = D.meta, t = new Date(m.updated_at);
    $('meta-line').textContent = `${nf(sum(D.econ, 'customers'))} pengguna unik · K = ${m.k} · dimuat dari PostgreSQL ${t.toLocaleString('id-ID', {dateStyle: 'medium', timeStyle: 'short'})} (${nf(m.query_ms)} ms)`;
    $('tag-period').textContent = `${m.period} (historis)`;
    if ($('tag-unit')) $('tag-unit').textContent = `Harga: ${m.currency} · Waktu: UTC+${SRC_TZ}`;
    $('loader').classList.add('hide'); $('fatal').classList.add('hide'); $('page').classList.remove('hide');
    renderSlicer(); renderPage();
    if (force) toast('Data dimuat ulang dari PostgreSQL');
    if (m.missing && m.missing.length) toast(`Tabel belum tersedia: ${m.missing.join(', ')}`);
  } catch (e) {
    $('loader').classList.add('hide');
    if (D) toast('Gagal memuat ulang: ' + e.message);
    else {
      const f = $('fatal'); f.classList.remove('hide');
      f.innerHTML = `<div><b>Dashboard belum dapat membaca data.</b>
        <p style="margin-top:8px;color:var(--muted)">Pastikan container postgres aktif dan tabel hasil analisis sudah terisi.</p>
        <code>${esc(e.message)}</code></div>`;
    }
  } finally { btn.classList.remove('busy'); }
}
$('btn-refresh').onclick = () => load(true);

/* ---------- init ---------- */
(function init() {
  const h = location.hash.slice(1);
  if (PAGES.some(p => p.id === h)) PAGE = h;
  renderTabs(); setThemeIcon(); load(false);
})();
