from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Segmentasi Pelanggan E-Commerce Kosmetik", layout="wide")
st.markdown("""
<style>
#MainMenu {visibility:hidden;} footer {visibility:hidden;}
.block-container {padding-top:2rem; padding-bottom:3rem; max-width:1400px;}
div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.25);
background:rgba(128,128,128,.06); padding:14px 18px; border-radius:8px;}
</style>
""", unsafe_allow_html=True)

DATA = Path(__file__).resolve().parent / "data"
PROFILE_FILE = DATA / "profile.csv"
SAMPLE_FILE = DATA / "sample.csv"
K_FILE = DATA / "k_selection.csv"

COLORS = {
    "Pembeli Aktif Bernilai Tinggi": "#1B7F4C",
    "Browsers & Calon Pembeli": "#D9822B",
    "Pengunjung Terbaru": "#1F5FBF",
    "Pelanggan Pasif": "#8A94A0",
}
FEATURES = {
    "avg_views": "View", "avg_carts": "Cart", "avg_removes": "Remove",
    "avg_purchases": "Purchase events", "avg_sessions": "Sesi",
    "avg_spend": "Spend (USD)", "avg_recency_days": "Hari sejak aktif terakhir",
}
STRATEGY = {
    "Pembeli Aktif Bernilai Tinggi": (
        "Program loyalitas, penawaran eksklusif, dan rekomendasi produk pelengkap.",
        "Rata-rata purchase events dan nilai belanja tertinggi. Fokus pada retensi dan pembelian ulang.",
    ),
    "Browsers & Calon Pembeli": (
        "Pengingat keranjang, informasi produk, voucher, dan uji coba promosi checkout.",
        "Aktivitas view/cart relatif tinggi tetapi pembelian rendah. Fokus pada konversi.",
    ),
    "Pengunjung Terbaru": (
        "Rekomendasi produk populer dan penawaran pembelian pertama yang relevan.",
        "Aktivitas terakhir relatif baru, tetapi rata-rata pembelian rendah.",
    ),
    "Pelanggan Pasif": (
        "Uji kampanye reaktivasi dan rekomendasi produk populer.",
        "Aktivitas rendah dan aktivitas terakhir relatif lama.",
    ),
}

@st.cache_data
def load_data():
    if not PROFILE_FILE.exists() or not SAMPLE_FILE.exists():
        raise FileNotFoundError(
            f"Pastikan file berikut ada di repositori: {PROFILE_FILE} dan {SAMPLE_FILE}"
        )
    p = pd.read_csv(PROFILE_FILE)
    s = pd.read_csv(SAMPLE_FILE)
    required_p = {
        "cluster", "customers", "buyers", "avg_views", "avg_carts", "avg_removes",
        "avg_purchases", "avg_sessions", "avg_spend", "avg_recency_days",
        "sum_views", "sum_carts", "sum_purchases", "sum_spend", "med_views",
        "med_carts", "med_purchases", "med_spend", "med_recency_days",
    }
    required_s = {
        "user_id", "cluster", "view_count", "cart_count", "remove_count",
        "purchase_count", "session_count", "total_spend", "days_since_last_event",
    }
    if required_p - set(p.columns) or required_s - set(s.columns):
        raise ValueError(
            f"Kolom profile.csv kurang: {sorted(required_p-set(p.columns))}; "
            f"kolom sample.csv kurang: {sorted(required_s-set(s.columns))}"
        )
    for df in (p, s):
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    p["cluster"] = p["cluster"].astype(int)
    s["cluster"] = s["cluster"].astype(int)
    return p, s

def segment_names(p):
    ids = p["cluster"].astype(int).tolist()
    if len(ids) != 4:
        return {i: f"Cluster {i}" for i in ids}
    x = p.set_index("cluster")
    high = int((x["avg_spend"].fillna(0) + x["avg_purchases"].fillna(0)).idxmax())
    other = [i for i in ids if i != high]
    rest = x.loc[other]
    candidate = int((rest["avg_carts"].fillna(0) + .25*rest["avg_views"].fillna(0)
                     - 2*rest["avg_purchases"].fillna(0)).idxmax())
    other = [i for i in other if i != candidate]
    recent_first = x.loc[other].sort_values("avg_recency_days")
    recent, passive = int(recent_first.index[0]), int(recent_first.index[-1])
    return {
        high: "Pembeli Aktif Bernilai Tinggi",
        candidate: "Browsers & Calon Pembeli",
        recent: "Pengunjung Terbaru",
        passive: "Pelanggan Pasif",
    }

st.title("Segmentasi Pelanggan E-Commerce Kosmetik")
st.caption("Pengelompokan pelanggan berdasarkan kemiripan perilaku aktivitas dan transaksi")
try:
    profile, sample = load_data()
    name_map = segment_names(profile)
    profile["segmen"] = profile["cluster"].map(name_map)
    profile["pct"] = profile["customers"] / profile["customers"].sum() * 100
    sample["segmen"] = sample["cluster"].map(name_map)
except Exception as e:
    st.error("Dashboard belum dapat membaca file CSV.")
    st.code(str(e))
    st.info("Periksa dashboard/data/profile.csv dan dashboard/data/sample.csv di GitHub.")
    st.stop()

order = profile.sort_values("avg_spend", ascending=False)["segmen"].tolist()
with st.sidebar:
    st.header("Segmentasi Pelanggan")
    st.caption("K-Means, Apache Spark MLlib")
    st.caption("HDFS → Spark → PostgreSQL → CSV → Streamlit")
    selected = st.multiselect("Filter segmen (tab Eksplorasi)", order, default=order)
    if st.button("Muat ulang data"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Data historis Oktober 2019–Februari 2020.")

total = int(profile["customers"].sum())
buyers = int(profile["buyers"].sum())
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total pelanggan", f"{total:,}")
k2.metric("Pernah membeli", f"{buyers:,}", help=f"{buyers/total*100:.1f}% dari seluruh pelanggan")
k3.metric("Event purchase", f"{int(profile['sum_purchases'].sum()):,}")
k4.metric("Total nilai belanja", f"${profile['sum_spend'].sum():,.0f}")
k5.metric("Jumlah cluster (K)", len(profile))

t1, t2, t3, t4, t5 = st.tabs(
    ["Ringkasan", "Profil Segmen", "Eksplorasi", "Rekomendasi Strategi", "Metodologi"]
)

with t1:
    a, b = st.columns(2)
    fig = px.pie(profile, names="segmen", values="customers", hole=.55,
                 color="segmen", color_discrete_map=COLORS, title="Komposisi seluruh pelanggan")
    fig.update_traces(textinfo="percent")
    a.plotly_chart(fig, use_container_width=True)
    fig = px.bar(profile, x="segmen", y="customers", color="segmen", text="customers",
                 color_discrete_map=COLORS, title="Jumlah pelanggan per segmen",
                 labels={"segmen": "", "customers": "Jumlah pelanggan"})
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(showlegend=False)
    b.plotly_chart(fig, use_container_width=True)

    a, b = st.columns(2)
    fig = go.Figure(go.Funnel(
        y=["View", "Cart", "Purchase events"],
        x=[profile["sum_views"].sum(), profile["sum_carts"].sum(), profile["sum_purchases"].sum()],
        textinfo="value+percent initial",
        marker={"color": ["#8A94A0", "#D9822B", "#1B7F4C"]}))
    fig.update_layout(title="Funnel event (total seluruh pelanggan)")
    a.plotly_chart(fig, use_container_width=True)
    ratios = profile.copy()
    ratios["Cart per view (%)"] = np.where(ratios["sum_views"] != 0,
                                            ratios["sum_carts"]/ratios["sum_views"]*100, np.nan)
    ratios["Purchase per cart (%)"] = np.where(ratios["sum_carts"] != 0,
                                                ratios["sum_purchases"]/ratios["sum_carts"]*100, np.nan)
    long = ratios.melt(id_vars="segmen", value_vars=["Cart per view (%)", "Purchase per cart (%)"],
                       var_name="rasio", value_name="persen")
    fig = px.bar(long, x="segmen", y="persen", color="rasio", barmode="group",
                 title="Rasio event per segmen", labels={"segmen": "", "persen": "Persen"})
    b.plotly_chart(fig, use_container_width=True)
    st.caption("Rasio dihitung dari jumlah event, bukan jumlah pesanan unik.")

with t2:
    weights = profile["customers"]
    overall = {c: (profile[c].fillna(0)*weights).sum()/weights.sum() for c in FEATURES}
    idx = pd.DataFrame(index=profile["segmen"])
    for c, label in FEATURES.items():
        idx[label] = profile[c] / overall[c] if overall[c] else 0
    idx = idx.reindex(order).replace([np.inf, -np.inf], np.nan).fillna(0)
    a, b = st.columns(2)
    a.plotly_chart(px.imshow(idx, text_auto=".2f", aspect="auto", color_continuous_scale="Blues",
                             title="Indeks terhadap rata-rata (1,00 = rata-rata)"),
                   use_container_width=True)
    norm = profile.set_index("segmen")[list(FEATURES)].reindex(order).fillna(0)
    norm = norm / norm.max().replace(0, 1)
    labels = list(FEATURES.values())
    fig = go.Figure()
    for seg in order:
        vals = norm.loc[seg].tolist()
        fig.add_trace(go.Scatterpolar(r=vals+[vals[0]], theta=labels+[labels[0]],
                                      fill="toself", name=seg, line_color=COLORS.get(seg)))
    fig.update_layout(title="Radar profil (dinormalisasi per fitur)",
                      polar={"radialaxis": {"visible": True, "range": [0, 1]}})
    b.plotly_chart(fig, use_container_width=True)
    metrics = st.multiselect("Bandingkan rata-rata fitur", list(FEATURES),
                             default=["avg_views", "avg_carts", "avg_purchases"],
                             format_func=lambda c: FEATURES[c])
    if metrics:
        long = profile.melt(id_vars="segmen", value_vars=metrics, var_name="fitur", value_name="rata-rata")
        long["fitur"] = long["fitur"].map(FEATURES)
        st.plotly_chart(px.bar(long, x="fitur", y="rata-rata", color="segmen", barmode="group",
                               color_discrete_map=COLORS, labels={"fitur": ""}),
                        use_container_width=True)
    avg = profile.set_index("segmen").loc[order][["customers", "pct"]+list(FEATURES)]
    st.subheader("Rata-rata per segmen")
    st.dataframe(avg.rename(columns={**FEATURES, "customers":"Pelanggan", "pct":"% Pelanggan"}).round(2),
                 use_container_width=True)
    med = profile.set_index("segmen").loc[order][["med_views", "med_carts", "med_purchases", "med_spend", "med_recency_days"]]
    st.subheader("Median per segmen")
    st.dataframe(med.rename(columns={"med_views":"View", "med_carts":"Cart",
                 "med_purchases":"Purchase events", "med_spend":"Spend (USD)",
                 "med_recency_days":"Hari sejak aktif terakhir"}).round(2), use_container_width=True)

with t3:
    sm = sample[sample["segmen"].isin(selected)].copy()
    st.caption(f"Sampel acak, maksimal 5.000 pelanggan per cluster. {len(sm):,} baris ditampilkan.")
    sm["x"] = sm["view_count"].clip(lower=0) + 1
    sm["y"] = sm["total_spend"].clip(lower=0) + 1
    a, b = st.columns(2)
    a.plotly_chart(px.scatter(sm, x="x", y="y", color="segmen", color_discrete_map=COLORS,
        log_x=True, log_y=True, opacity=.45, hover_data=["user_id", "cart_count", "purchase_count"],
        labels={"x":"View count + 1 (skala log)", "y":"Total belanja + 1 (skala log)"},
        title="View terhadap total belanja"), use_container_width=True)
    fig = px.box(sm, x="segmen", y="days_since_last_event", color="segmen",
                 color_discrete_map=COLORS, title="Hari sejak aktivitas terakhir",
                 labels={"segmen":"", "days_since_last_event":"Hari"})
    fig.update_layout(showlegend=False)
    b.plotly_chart(fig, use_container_width=True)
    st.subheader("Cari pelanggan dalam sampel")
    uid = st.text_input("Masukkan user_id")
    if uid.strip():
        if uid.strip().isdigit():
            found = sample[sample["user_id"] == int(uid.strip())]
            if found.empty:
                st.warning("ID tidak ditemukan dalam sampel. CSV ini tidak mencakup semua 1,64 juta pelanggan.")
            else:
                st.success(f"Segmen: {found.iloc[0]['segmen']}")
                st.dataframe(found, use_container_width=True, hide_index=True)
        else:
            st.warning("user_id harus berupa angka.")
    st.subheader("Data sampel")
    cols = [c for c in sm.columns if c not in {"x", "y"}]
    st.dataframe(sm[cols].head(1000), use_container_width=True, hide_index=True)
    st.download_button("Unduh sampel (CSV)", sm[cols].to_csv(index=False).encode("utf-8"),
                       file_name="sample_pelanggan_segmen.csv", mime="text/csv")

with t4:
    st.info("Rekomendasi adalah hipotesis untuk diuji, misalnya melalui A/B test, bukan dampak yang sudah dibuktikan model.")
    columns = st.columns(2)
    for i, seg in enumerate(order):
        row = profile[profile["segmen"] == seg].iloc[0]
        action, reason = STRATEGY.get(seg, ("Analisis lebih lanjut.", "Interpretasi awal profil cluster."))
        with columns[i % 2]:
            with st.container(border=True):
                st.subheader(seg)
                st.caption(f"{int(row['customers']):,} pelanggan ({row['pct']:.1f}%)")
                m1, m2, m3 = st.columns(3)
                m1.metric("Rata-rata purchase", f"{row['avg_purchases']:.2f}")
                m2.metric("Rata-rata spend", f"${row['avg_spend']:.2f}")
                m3.metric("Hari sejak aktif", f"{row['avg_recency_days']:.1f}")
                st.markdown(f"**Strategi:** {action}")
                st.write(reason)

with t5:
    st.subheader("Arsitektur")
    st.code("CSV mentah (Okt 2019–Feb 2020)\n  > HDFS\n  > Apache Spark (agregasi fitur per user_id)\n  > Spark MLlib K-Means (log1p dan StandardScaler)\n  > PostgreSQL (penyimpanan/ekspor)\n  > CSV ringkasan dan sampel\n  > Streamlit Cloud", language="text")
    st.subheader("Fitur per pelanggan")
    st.write("Jumlah view, cart, remove_from_cart, purchase events, jumlah sesi, total nilai belanja dari event purchase, dan hari sejak aktivitas terakhir. user_id menjadi kunci pelanggan, bukan fitur K-Means.")
    st.subheader("Pemilihan jumlah cluster (K)")
    if K_FILE.exists():
        ks = pd.read_csv(K_FILE)
        if {"k", "wssse", "silhouette"}.issubset(ks.columns):
            a, b = st.columns(2)
            a.plotly_chart(px.line(ks, x="k", y="wssse", markers=True, title="Elbow (WSSSE)"), use_container_width=True)
            b.plotly_chart(px.line(ks, x="k", y="silhouette", markers=True, title="Silhouette score"), use_container_width=True)
        else:
            st.caption("Kolom k, wssse, silhouette belum lengkap di k_selection.csv.")
    else:
        st.caption("Metrik pemilihan K belum disertakan. Tambahkan dashboard/data/k_selection.csv jika tersedia.")
    st.subheader("Catatan interpretasi")
    st.markdown("- Nama segmen dan strategi adalah interpretasi dari profil cluster.\n- Purchase events tidak sama dengan jumlah pesanan unik.\n- Data historis 2019–2020; hasil menggambarkan periode tersebut.\n- Mayoritas pelanggan memiliki aktivitas sangat rendah dalam periode data.")
