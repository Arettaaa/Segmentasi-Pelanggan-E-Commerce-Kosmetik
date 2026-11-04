import os
import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")
st.set_page_config(page_title="Customer Segmentation", layout="wide",
                   initial_sidebar_state="expanded")

MINT, MINT_D, MINT_L = "#2FB89A", "#1C7F6B", "#A8E3D4"
INDIGO, SKY, AMBER, SLATE = "#5B6CFF", "#56C8E8", "#F4B740", "#9BA8BE"
INK, MUTED, CARD, BG, LINE = "#0F2A3D", "#7A8BA3", "#FFFFFF", "#F2F8F7", "#E6EFEE"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp {{ font-family:'Plus Jakarta Sans',sans-serif; }}
#MainMenu, footer, header {{visibility:hidden;}}
.stApp {{background:{BG};}}
.block-container {{padding:1.6rem 2.2rem 3rem; max-width:1560px;}}
h1,h2,h3,h4,p,span,div,label,li {{color:{INK};}}

section[data-testid="stSidebar"] {{background:{CARD}; border-right:1px solid {LINE};}}
section[data-testid="stSidebar"] .block-container {{padding-top:1.6rem;}}
.logo {{display:flex;gap:11px;align-items:center;margin-bottom:6px;}}
.logo .mark {{width:38px;height:38px;border-radius:12px;
  background:linear-gradient(140deg,{MINT} 0%,{MINT_D} 100%);
  box-shadow:0 6px 14px rgba(47,184,154,.3);}}
.logo b {{font-size:16px;font-weight:800;letter-spacing:-.02em;display:block;line-height:1.15;}}
.logo small {{color:{MUTED};font-size:11px;font-weight:500;}}
.sideq {{background:{BG};border-radius:14px;padding:14px 16px;margin-top:14px;
  font-size:12px;color:{MUTED};line-height:1.55;}}
.sideq b {{display:block;color:{INK};font-size:12px;margin-bottom:5px;}}

.hello {{color:{MUTED};font-size:13px;font-weight:500;margin-bottom:2px;}}
.ttl {{font-size:30px;font-weight:800;letter-spacing:-.03em;line-height:1.15;}}
.sub {{color:{MUTED};font-size:13px;margin-top:5px;}}
.daterange {{background:{CARD};border:1px solid {LINE};border-radius:12px;
  padding:11px 18px;font-size:12.5px;font-weight:600;text-align:center;}}

.kpi {{background:{CARD};border-radius:18px;padding:17px 19px;
  box-shadow:0 4px 16px rgba(15,42,61,.055);height:100%;}}
.kpi .row {{display:flex;align-items:center;gap:13px;}}
.kpi .ic {{width:46px;height:46px;border-radius:14px;flex:none;display:flex;
  align-items:center;justify-content:center;font-size:19px;font-weight:700;}}
.kpi .v {{font-size:23px;font-weight:800;letter-spacing:-.025em;line-height:1.1;}}
.kpi .l {{color:{MUTED};font-size:12px;font-weight:500;margin-top:1px;}}
.kpi .tag {{display:inline-block;margin-top:11px;background:{MINT_L}22;color:{MINT_D};
  border-radius:20px;padding:3px 11px;font-size:11px;font-weight:700;}}

div[data-testid="stVerticalBlockBorderWrapper"]:has(div.cardtag) {{
  background:{CARD};border:none !important;border-radius:20px;padding:6px 14px 2px;
  box-shadow:0 4px 16px rgba(15,42,61,.055);}}
.cardtag {{display:none;}}
.ch {{font-size:14.5px;font-weight:700;letter-spacing:-.01em;padding:11px 2px 2px;}}
.chs {{color:{MUTED};font-size:11.5px;font-weight:500;margin:-1px 0 7px;}}
.note {{color:{MUTED};font-size:11.5px;line-height:1.55;padding:2px 2px 9px;}}
.sect {{font-size:11px;font-weight:800;letter-spacing:.12em;color:{MUTED};
  text-transform:uppercase;margin:26px 0 11px;}}
.pillrow {{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:4px;}}
.pill {{background:{MINT_L}33;color:{MINT_D};border-radius:20px;padding:4px 12px;
  font-size:11.5px;font-weight:700;}}
.pill.g {{background:#EEF1FF;color:{INDIGO};}}
.pill.a {{background:#FEF6E7;color:#B5820C;}}
div[data-testid="stDataFrame"] {{border-radius:12px;overflow:hidden;font-size:12.5px;}}
div[data-testid="stExpander"] {{background:{CARD};border:none;border-radius:16px;
  box-shadow:0 4px 16px rgba(15,42,61,.055);}}
</style>""", unsafe_allow_html=True)

PG = dict(host=os.getenv("PG_HOST", "postgres"), port=int(os.getenv("PG_PORT", "5432")),
          dbname="segmentasi", user="bigdata", password="bigdata")
NAMA = ["Pembeli Bernilai Tinggi", "Pembeli Menengah", "Browser Aktif", "Pengunjung Kasual"]
WARNA = {NAMA[0]: MINT_D, NAMA[1]: MINT, NAMA[2]: AMBER, NAMA[3]: SLATE}
STRATEGI = {
    NAMA[0]: ("Retensi", "VIP membership, reward pembelian, bundling premium, early access produk baru."),
    NAMA[1]: ("Pertumbuhan", "Rekomendasi produk pelengkap, promo pembelian berikutnya, program repeat purchase."),
    NAMA[2]: ("Konversi", "Retargeting produk yang dilihat, pengingat keranjang, ulasan pelanggan, penawaran terbatas."),
    NAMA[3]: ("Akuisisi", "Welcome coupon, promo pembelian pertama, pengenalan produk terlaris."),
}
FEAT = {"avg_views": "View", "avg_carts": "Cart", "avg_removes": "Remove",
        "avg_purchases": "Purchase", "avg_sessions": "Sesi",
        "avg_spend": "Nilai transaksi", "avg_recency": "Recency"}


def q(sql, quiet=False):
    try:
        c = psycopg2.connect(**PG, connect_timeout=5)
    except psycopg2.OperationalError:
        c = psycopg2.connect(**{**PG, "host": "localhost"}, connect_timeout=5)
    try:
        return pd.read_sql_query(sql, c)
    except Exception:
        if quiet:
            return None
        raise
    finally:
        c.close()


@st.cache_data(ttl=1800, show_spinner="Memuat data...")
def load():
    t = {}
    t["econ"] = q("SELECT * FROM segment_economics ORDER BY revenue_share DESC")
    t["prof"] = q("""SELECT cluster, COUNT(*) customers,
        AVG(view_count) avg_views, AVG(cart_count) avg_carts, AVG(remove_count) avg_removes,
        AVG(purchase_count) avg_purchases, AVG(session_count) avg_sessions,
        AVG(total_spend) avg_spend, AVG(days_since_last_event) avg_recency,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY view_count) med_views,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cart_count) med_carts,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY purchase_count) med_purchases,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_spend) med_spend,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_since_last_event) med_recency
        FROM customer_segments GROUP BY cluster""").apply(pd.to_numeric)
    for n, s in [("funnel", "funnel_customer"), ("fseg", "funnel_segment"),
                 ("brand", "top_brand_segment"), ("prod", "top_product_segment"),
                 ("price", "price_range_segment"), ("hour", "activity_hour_segment"),
                 ("day", "activity_day_segment"), ("churn", "churn_risk_segment"),
                 ("sim", "conversion_simulation"), ("asum", "marketing_assumptions"),
                 ("ksel", "k_selection"), ("val", "model_validation"),
                 ("sil", "silhouette_detail"), ("stab", "cluster_stability"),
                 ("seed", "seed_wssse"), ("corr", "feature_correlation"),
                 ("sens", "feature_sensitivity"), ("bench", "pipeline_benchmark"),
                 ("spec", "pipeline_spec")]:
        t[n] = q(f"SELECT * FROM {s}", quiet=True)
    t["smp"] = q("""SELECT cluster, view_count, cart_count, purchase_count, total_spend,
        days_since_last_event FROM (SELECT *, ROW_NUMBER() OVER
        (PARTITION BY cluster ORDER BY random()) rn FROM customer_segments) x WHERE rn<=2500""")
    return t


def S(f, h=270, legend=False):
    f.update_layout(height=h, margin=dict(l=6, r=6, t=8, b=6),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Plus Jakarta Sans", size=11, color=MUTED),
                    showlegend=legend,
                    legend=dict(orientation="h", y=-.2, x=0, font=dict(size=10.5),
                                bgcolor="rgba(0,0,0,0)"),
                    hoverlabel=dict(bgcolor="white", font_size=11,
                                    font_family="Plus Jakarta Sans"))
    f.update_xaxes(gridcolor=LINE, zeroline=False, title=None, linecolor=LINE)
    f.update_yaxes(gridcolor=LINE, zeroline=False, title=None, linecolor=LINE)
    return f


def card(title, sub=None):
    st.markdown('<div class="cardtag"></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="ch">{title}</div>', unsafe_allow_html=True)
    if sub:
        st.markdown(f'<div class="chs">{sub}</div>', unsafe_allow_html=True)


def fm(n, d=0):
    return f"{n:,.{d}f}".replace(",", "~").replace(".", ",").replace("~", ".")


try:
    D = load()
except Exception as e:
    st.error("Dashboard belum dapat membaca data dari PostgreSQL.")
    st.code(str(e))
    st.stop()

econ = D["econ"]
peta = dict(zip(econ["cluster"], econ["segmen"]))
prof = D["prof"]
prof["cluster"] = prof["cluster"].astype(int)
prof["segmen"] = prof["cluster"].map(peta)
urut = econ.sort_values("revenue_share", ascending=False)["segmen"].tolist()
ORD = {"segmen": urut}
D["smp"]["segmen"] = D["smp"]["cluster"].map(peta)
tot = int(econ["customers"].sum())
buyers = int(econ["buyers"].sum())
rev = float(econ["segment_revenue"].sum())

with st.sidebar:
    st.markdown('<div class="logo"><div class="mark"></div><div><b>SegmentIQ</b>'
                '<small>Cosmetics E-Commerce</small></div></div>', unsafe_allow_html=True)
    st.write("")
    tab = st.radio("Navigasi", ["Hasil Segmentasi", "Evaluasi Model"],
                   label_visibility="collapsed")
    st.markdown(f'<div class="sideq"><b>Pipeline</b>HDFS &rarr; Apache Spark &rarr; '
                f'Spark MLlib &rarr; PostgreSQL &rarr; Streamlit</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sideq"><b>Metode</b>K-Means (K=4) pada 7 fitur perilaku, '
                f'{fm(tot)} pelanggan</div>', unsafe_allow_html=True)
    st.write("")
    if st.button("Muat ulang data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

a, b = st.columns([3, 1])
with a:
    st.markdown('<p class="hello">Customer Analytics</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="ttl">{"Hasil Segmentasi Pelanggan" if tab == "Hasil Segmentasi" else "Evaluasi Model Clustering"}</p>',
                unsafe_allow_html=True)
    st.markdown(f'<p class="sub">{"Profil, nilai ekonomi, dan strategi untuk tiap segmen pelanggan" if tab == "Hasil Segmentasi" else "Validitas, stabilitas, dan performa pipeline K-Means"}</p>',
                unsafe_allow_html=True)
with b:
    st.markdown('<div class="daterange">Okt 2019 &ndash; Feb 2020</div>', unsafe_allow_html=True)
st.write("")


def kpi(col, icon, val, lab, tag=None, c1=MINT_L, c2=MINT_D):
    t = f'<div class="tag">{tag}</div>' if tag else ""
    col.markdown(f'<div class="kpi"><div class="row"><div class="ic" '
                 f'style="background:{c1}55;color:{c2}">{icon}</div><div>'
                 f'<div class="v">{val}</div><div class="l">{lab}</div></div></div>{t}</div>',
                 unsafe_allow_html=True)


# ══════════════════════════════════════════ TAB 1
if tab == "Hasil Segmentasi":
    hi = econ.iloc[0]
    br = econ[econ["segmen"] == NAMA[2]].iloc[0]
    k = st.columns(4)
    kpi(k[0], "◉", fm(tot), "Total pelanggan", "4 segmen terbentuk")
    kpi(k[1], "✓", fm(buyers), "Pernah membeli",
        f"buyer rate {buyers / tot * 100:.1f}%", "#D9F2EB", MINT_D)
    kpi(k[2], "≈", fm(rev), "Total nilai transaksi",
        f"{fm(rev / buyers, 2)} per pembeli", "#EEF1FF", INDIGO)
    kpi(k[3], "▲", f"{hi['revenue_share']:.1f}%", f"Revenue dari {hi['segmen']}",
        f"hanya {hi['pct_customers']:.1f}% pelanggan", "#FEF6E7", "#B5820C")

    st.markdown('<div class="sect">01 — Customer Overview</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1.15, 1])
    with c1:
        with st.container(border=True):
            card("Customer share vs revenue share",
                 "Segmen kecil dapat menyumbang sebagian besar nilai transaksi")
            d = econ.melt(id_vars="segmen", value_vars=["pct_customers", "revenue_share"],
                          var_name="jenis", value_name="persen")
            d["jenis"] = d["jenis"].map({"pct_customers": "Customer share",
                                         "revenue_share": "Revenue share"})
            f = px.bar(d, x="segmen", y="persen", color="jenis", barmode="group",
                       text="persen", color_discrete_map={"Customer share": SLATE,
                                                          "Revenue share": MINT},
                       category_orders=ORD)
            f.update_traces(texttemplate="%{text:.1f}%", textposition="outside",
                            textfont_size=10, marker_line_width=0,
                            marker=dict(cornerradius=6))
            f.update_xaxes(tickfont_size=10)
            st.plotly_chart(S(f, 285, True), use_container_width=True)
    with c2:
        with st.container(border=True):
            card("Komposisi pelanggan", "Proporsi jumlah pelanggan tiap segmen")
            f = px.pie(econ, names="segmen", values="customers", hole=.68,
                       color="segmen", color_discrete_map=WARNA, category_orders=ORD)
            f.update_traces(textinfo="none", marker_line_color="white", marker_line_width=3)
            f.add_annotation(text=f"<b>{fm(tot)}</b><br><span style='font-size:10px'>pelanggan</span>",
                             showarrow=False, font=dict(size=16, color=INK))
            st.plotly_chart(S(f, 285, True), use_container_width=True)

    st.markdown('<div class="sect">02 — Customer Conversion</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1.3])
    with c1:
        with st.container(border=True):
            card("Funnel pelanggan unik", "Persentase pelanggan yang pernah melakukan tiap tahap")
            fu = D["funnel"]
            f = go.Figure(go.Funnel(
                y=fu["tahap"], x=fu["customers"], textinfo="value+percent initial",
                textfont=dict(size=11, color="white"),
                marker=dict(color=[SLATE, AMBER, MINT_D])))
            st.plotly_chart(S(f, 265), use_container_width=True)
    with c2:
        with st.container(border=True):
            card("Konversi per segmen", "Persentase pelanggan yang pernah view, cart, dan purchase")
            fs = D["fseg"].copy()
            d = fs.melt(id_vars="segmen", value_vars=["pct_view", "pct_cart", "pct_purchase"],
                        var_name="tahap", value_name="persen")
            d["tahap"] = d["tahap"].map({"pct_view": "View", "pct_cart": "Cart",
                                         "pct_purchase": "Purchase"})
            f = px.bar(d, x="segmen", y="persen", color="tahap", barmode="group",
                       color_discrete_map={"View": SLATE, "Cart": AMBER, "Purchase": MINT_D},
                       category_orders=ORD)
            f.update_traces(marker_line_width=0, marker=dict(cornerradius=5))
            f.update_xaxes(tickfont_size=10)
            st.plotly_chart(S(f, 265, True), use_container_width=True)

    st.markdown('<div class="sect">03 — Customer Profile</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1.35, 1])
    with c1:
        with st.container(border=True):
            card("Indeks perilaku tiap segmen", "1,00 berarti sama dengan rata-rata seluruh pelanggan")
            w = prof["customers"]
            ov = {x: (prof[x] * w).sum() / w.sum() for x in FEAT}
            idx = pd.DataFrame({FEAT[x]: prof[x] / ov[x] for x in FEAT})
            idx.index = prof["segmen"]
            idx = idx.loc[urut]
            f = go.Figure(go.Heatmap(
                z=np.log2(idx.clip(lower=.01)).values, x=list(idx.columns), y=list(idx.index),
                text=idx.round(2).values, texttemplate="%{text}", showscale=False,
                xgap=3, ygap=3, textfont_size=10,
                colorscale=[[0, "#FDEBD3"], [.5, "#FFFFFF"], [1, MINT]], zmid=0, zmin=-3, zmax=3))
            f.update_layout(yaxis=dict(autorange="reversed", tickfont_size=10))
            st.plotly_chart(S(f, 255), use_container_width=True)
    with c2:
        with st.container(border=True):
            card("Rentang harga produk dibeli", "Median dan kuartil harga pada event purchase")
            p = D["price"].set_index("segmen").loc[[s for s in urut if s in set(D["price"]["segmen"])]]
            f = go.Figure()
            for s in p.index:
                r = p.loc[s]
                f.add_trace(go.Bar(y=[s], x=[r["p75_price"] - r["p25_price"]], base=[r["p25_price"]],
                                   orientation="h", marker_color=WARNA[s], marker_line_width=0,
                                   width=.45, hovertemplate=f"P25 {r['p25_price']}<br>"
                                   f"Median {r['median_price']}<br>P75 {r['p75_price']}<extra></extra>"))
                f.add_trace(go.Scatter(y=[s], x=[r["median_price"]], mode="markers",
                                       marker=dict(color="white", size=9, line=dict(color=INK, width=2)),
                                       hoverinfo="skip"))
            f.update_layout(barmode="overlay", yaxis=dict(tickfont_size=10))
            st.plotly_chart(S(f, 255), use_container_width=True)

    with st.container(border=True):
        card("Karakteristik tiap segmen", "Rata-rata dan median dari nilai asli, bukan hasil standardisasi")
        t1, t2 = st.tabs(["Rata-rata", "Median"])
        base = econ.set_index("segmen")[["customers", "pct_customers", "buyer_rate",
                                         "revenue_share", "spend_per_buyer", "purchase_per_buyer"]]
        a1 = prof.set_index("segmen")[list(FEAT)].join(base).loc[urut]
        a1 = a1.rename(columns={**FEAT, "customers": "Pelanggan", "pct_customers": "% Pelanggan",
                                "buyer_rate": "Buyer rate %", "revenue_share": "Revenue share %",
                                "spend_per_buyer": "Belanja/pembeli",
                                "purchase_per_buyer": "Purchase/pembeli"})
        t1.dataframe(a1.round(2), use_container_width=True)
        m = prof.set_index("segmen")[["med_views", "med_carts", "med_purchases",
                                      "med_spend", "med_recency"]].loc[urut]
        m.columns = ["View", "Cart", "Purchase", "Nilai transaksi", "Recency"]
        t2.dataframe(m.round(2), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            card("Brand favorit tiap segmen", "Top 5 berdasarkan jumlah event purchase")
            b = D["brand"]
            b = b[b["segmen"].isin([NAMA[0], NAMA[1]])]
            f = px.bar(b, x="purchase_events", y="item", color="segmen", orientation="h",
                       facet_col="segmen", color_discrete_map=WARNA)
            f.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font_size=11))
            f.update_traces(marker_line_width=0, marker=dict(cornerradius=4))
            f.update_yaxes(matches=None, tickfont_size=9.5)
            st.plotly_chart(S(f, 255), use_container_width=True)
    with c2:
        with st.container(border=True):
            card("Waktu aktif pelanggan", "Distribusi event per jam lokal (UTC+3)")
            h = D["hour"]
            f = px.line(h, x="jam", y="pct_events", color="segmen",
                        color_discrete_map=WARNA, category_orders=ORD, markers=False)
            f.update_traces(line_width=2.4)
            f.update_xaxes(dtick=3, tickfont_size=10)
            st.plotly_chart(S(f, 255, True), use_container_width=True)

    st.markdown('<div class="sect">04 — Risiko & Potensi</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1.25])
    with c1:
        with st.container(border=True):
            card("Pembeli berisiko churn", "Pernah membeli tetapi tidak aktif ≥ 60 hari")
            ch = D["churn"].sort_values("revenue_at_risk", ascending=True)
            f = px.bar(ch, x="revenue_at_risk", y="segmen", orientation="h", text="pct_at_risk",
                       color="segmen", color_discrete_map=WARNA)
            f.update_traces(texttemplate="%{text:.0f}% pembeli", textposition="outside",
                            textfont_size=10, marker_line_width=0, marker=dict(cornerradius=6))
            f.update_yaxes(tickfont_size=10)
            st.plotly_chart(S(f, 240), use_container_width=True)
            st.markdown('<div class="note">Disebut berisiko churn, bukan churn aktual, '
                        'karena dataset tidak memiliki label churn.</div>', unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            card("Simulasi potensi konversi", "Skenario 1%, 3%, 5% non-pembeli menjadi pembeli")
            s = D["sim"]
            f = px.bar(s, x="segmen", y="estimasi_revenue", color="skenario_pct",
                       barmode="group", category_orders=ORD,
                       color_discrete_sequence=[MINT_L, MINT, MINT_D])
            f.update_traces(marker_line_width=0, marker=dict(cornerradius=5))
            f.update_xaxes(tickfont_size=10)
            st.plotly_chart(S(f, 240, True), use_container_width=True)
            st.markdown('<div class="note">Simulasi berbasis asumsi, bukan prediksi model. '
                        'Nilai belanja per pembeli diasumsikan sama dengan rata-rata keseluruhan.</div>',
                        unsafe_allow_html=True)

    st.markdown('<div class="sect">05 — Marketing Recommendations</div>', unsafe_allow_html=True)
    for i in range(0, 4, 2):
        cols = st.columns(2)
        for col, s in zip(cols, urut[i:i + 2]):
            r = econ[econ["segmen"] == s].iloc[0]
            fokus, aksi = STRATEGI[s]
            cls = {"Retensi": "", "Pertumbuhan": "g", "Konversi": "a", "Akuisisi": "g"}[fokus]
            with col:
                with st.container(border=True):
                    st.markdown(
                        f'<div class="ch">{s}</div>'
                        f'<div class="pillrow"><span class="pill {cls}">{fokus}</span>'
                        f'<span class="pill">{fm(r["customers"])} pelanggan</span>'
                        f'<span class="pill">{r["revenue_share"]:.1f}% revenue</span>'
                        f'<span class="pill">buyer rate {r["buyer_rate"]:.1f}%</span></div>'
                        f'<div class="note">{aksi}</div>', unsafe_allow_html=True)

    with st.expander("Asumsi dan catatan analisis"):
        st.dataframe(D["asum"], use_container_width=True, hide_index=True)
        st.markdown('<div class="note">Nama segmen merupakan interpretasi atas profil cluster, '
                    'bukan keluaran model. Event purchase tidak sama dengan jumlah pesanan unik. '
                    'Kolom category_code sebagian besar kosong pada dataset, sehingga analisis '
                    'kategori tidak disajikan.</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════ TAB 2
else:
    val = D["val"]
    gv = lambda s: float(val[val["metrik"].str.contains(s, na=False)].iloc[0]["nilai"]) \
        if val is not None and len(val[val["metrik"].str.contains(s, na=False)]) else None
    sil_km, sil_bis = gv("Silhouette K-Means"), gv("Silhouette Bisecting")
    ari_mean = gv("rata-rata 5 seed")

    k = st.columns(4)
    kpi(k[0], "K", "4", "Jumlah cluster", "elbow + silhouette")
    kpi(k[1], "◆", f"{sil_km:.3f}" if sil_km else "—", "Silhouette K-Means",
        "squared Euclidean", "#D9F2EB", MINT_D)
    kpi(k[2], "◇", f"{sil_bis:.3f}" if sil_bis else "—", "Silhouette Bisecting",
        "metode pembanding", "#EEF1FF", INDIGO)
    kpi(k[3], "~", f"{ari_mean:.2f}" if ari_mean else "—", "ARI antar seed",
        "stabilitas sedang", "#FEF6E7", "#B5820C")

    st.markdown('<div class="sect">01 — Pemilihan jumlah cluster</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    ks = D["ksel"]
    for col, (y, t, c) in zip([c1, c2], [("wssse", "Elbow (WSSSE)", MINT_D),
                                         ("silhouette", "Silhouette per nilai K", INDIGO)]):
        with col:
            with st.container(border=True):
                card(t, "Garis putus menandai K yang dipilih")
                f = px.line(ks, x="k", y=y, markers=True)
                f.update_traces(line_color=c, line_width=2.6, marker_size=7,
                                fill="tozeroy", fillcolor=c + "14")
                f.add_vline(x=4, line_dash="dot", line_color=MUTED, line_width=1.4)
                st.plotly_chart(S(f, 240), use_container_width=True)

    st.markdown('<div class="sect">02 — Kualitas pemisahan cluster</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1.1, 1])
    with c1:
        with st.container(border=True):
            card("Silhouette per cluster", "Tiap cluster dibandingkan terhadap gabungan cluster lain")
            s = D["sil"].copy()
            s["warna"] = [MUTED if "Keseluruhan" in x else
                          WARNA.get(x.replace(" vs lainnya", ""), MINT) for x in s["cakupan"]]
            f = go.Figure(go.Bar(x=s["silhouette"], y=s["cakupan"], orientation="h",
                                 marker_color=list(s["warna"]), marker_line_width=0,
                                 text=s["silhouette"].round(3), textposition="outside",
                                 marker=dict(cornerradius=6)))
            f.update_yaxes(tickfont_size=10, autorange="reversed")
            f.update_xaxes(range=[0, 1])
            st.plotly_chart(S(f, 250), use_container_width=True)
    with c2:
        with st.container(border=True):
            card("Stabilitas tiap cluster", "Jaccard terhadap seed acuan, 9 pembanding")
            sb = D["stab"]
            f = go.Figure()
            for _, r in sb.iterrows():
                f.add_trace(go.Scatter(x=[r["jaccard_min"], r["jaccard_max"]],
                                       y=[r["segmen"]] * 2, mode="lines",
                                       line=dict(color=LINE, width=7)))
                f.add_trace(go.Scatter(x=[r["jaccard_mean"]], y=[r["segmen"]], mode="markers+text",
                                       marker=dict(color=WARNA.get(r["segmen"], MINT), size=13),
                                       text=[f"{r['jaccard_mean']:.2f}"], textposition="top center",
                                       textfont_size=10))
            f.update_xaxes(range=[0, 1.05])
            f.update_yaxes(tickfont_size=10)
            st.plotly_chart(S(f, 250), use_container_width=True)

    c1, c2 = st.columns([1.2, 1])
    with c1:
        with st.container(border=True):
            card("WSSSE per seed", "Nilai berbeda menunjukkan adanya solusi lokal")
            sd = D["seed"].sort_values("seed")
            f = px.bar(sd, x=sd["seed"].astype(str), y="wssse")
            f.update_traces(marker_color=MINT, marker_line_width=0, marker=dict(cornerradius=5))
            f.update_yaxes(range=[sd["wssse"].min() * .97, sd["wssse"].max() * 1.01])
            st.plotly_chart(S(f, 225), use_container_width=True)
            st.markdown('<div class="note">K-Means konvergen ke dua solusi lokal. Model final '
                        'menggunakan seed dengan WSSSE terendah.</div>', unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            card("Validasi model", "Ringkasan metrik evaluasi")
            st.dataframe(val.round(3), use_container_width=True, hide_index=True, height=225)

    st.markdown('<div class="sect">03 — Fitur</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1.3, 1])
    with c1:
        with st.container(border=True):
            card("Korelasi antar fitur", "Setelah transformasi log1p dan standardisasi")
            cr = D["corr"].set_index("fitur")
            f = go.Figure(go.Heatmap(z=cr.values, x=list(cr.columns), y=list(cr.index),
                                     text=cr.round(2).values, texttemplate="%{text}",
                                     textfont_size=9, xgap=2, ygap=2, showscale=False,
                                     colorscale=[[0, "#FDEBD3"], [.5, "#FFFFFF"], [1, MINT]],
                                     zmid=0, zmin=-1, zmax=1))
            f.update_xaxes(tickfont_size=9, tickangle=-30)
            f.update_yaxes(tickfont_size=9)
            st.plotly_chart(S(f, 290), use_container_width=True)
    with c2:
        with st.container(border=True):
            card("Sensitivitas fitur", "Dampak menghapus session_count")
            st.dataframe(D["sens"].round(4), use_container_width=True, hide_index=True, height=110)
            st.markdown('<div class="note">Tiga pasangan fitur berkorelasi di atas 0,8: '
                        'purchase_count dengan total_spend, view_count dengan session_count, '
                        'dan cart_count dengan remove_count. Model tanpa session_count '
                        'menghasilkan silhouette lebih tinggi namun partisi yang cukup berbeda, '
                        'sehingga model tujuh fitur dipertahankan agar profil segmen tetap lengkap.</div>',
                        unsafe_allow_html=True)

    st.markdown('<div class="sect">04 — Performa pipeline</div>', unsafe_allow_html=True)
    if D["bench"] is not None:
        c1, c2 = st.columns([1.3, 1])
        bch = D["bench"]
        with c1:
            with st.container(border=True):
                card("Waktu tiap tahap pipeline", f"Total {bch['detik'].sum():.0f} detik")
                f = px.bar(bch, x="detik", y="tahap", orientation="h", text="detik",
                           color="detik", color_continuous_scale=[MINT_L, MINT_D])
                f.update_traces(texttemplate="%{text:.1f}s", textposition="outside",
                                textfont_size=10, marker_line_width=0, marker=dict(cornerradius=5))
                f.update_yaxes(autorange="reversed", tickfont_size=9.5)
                f.update_layout(coloraxis_showscale=False)
                st.plotly_chart(S(f, 275), use_container_width=True)
        with c2:
            with st.container(border=True):
                card("Spesifikasi lingkungan", "Konfigurasi Spark dan data")
                st.dataframe(D["spec"], use_container_width=True, hide_index=True, height=275)
    else:
        st.info("Tabel pipeline_benchmark belum tersedia. Jalankan benchmark.py terlebih dahulu.")

    with st.expander("Catatan evaluasi"):
        st.markdown(
            '<div class="note">'
            'Silhouette dihitung dengan squared Euclidean distance (default Spark ClusteringEvaluator) '
            'pada sampel 10% data, menggunakan pengaturan yang sama untuk K-Means dan Bisecting K-Means. '
            'Nilai silhouette bukan ukuran akurasi klasifikasi.<br><br>'
            'Buyer rate per segmen merupakan profil deskriptif, bukan ukuran kebenaran model, '
            'karena purchase_count termasuk fitur input clustering.<br><br>'
            'Ditemukan 16 pelanggan dengan total_spend negatif akibat nilai price negatif pada data mentah. '
            'Nilai tersebut dipotong ke nol sebelum transformasi log1p.<br><br>'
            'Keterbatasan: data historis Oktober 2019 sampai Februari 2020, segmentasi menggunakan '
            'agregasi seluruh periode, tidak tersedia label segmen aktual sebagai ground truth, '
            'dan K-Means sensitif terhadap inisialisasi centroid.</div>', unsafe_allow_html=True)