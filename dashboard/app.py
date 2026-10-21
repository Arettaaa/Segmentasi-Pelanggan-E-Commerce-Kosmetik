import os
import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

st.set_page_config(page_title="Segmentasi Pelanggan E-Commerce Kosmetik", layout="wide")

st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px;}
    h1 {font-weight: 700; letter-spacing: -0.01em; margin-bottom: 0.2rem;}
    h2, h3 {font-weight: 600;}
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,0.25);
        background: rgba(128,128,128,0.06);
        padding: 14px 18px;
        border-radius: 8px;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.05em; opacity: 0.75;
    }
    button[role="tab"] {font-weight: 600;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ konfigurasi
PG = dict(
    host=os.getenv("PG_HOST", "postgres"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "segmentasi"),
    user=os.getenv("PG_USER", "bigdata"),
    password=os.getenv("PG_PASSWORD", "bigdata"),
)

WARNA = {
    "Loyal High-Value": "#1B7F4C",
    "Pembeli Reguler": "#1F5FBF",
    "Cart Abandoner": "#D9822B",
    "Pengunjung Kasual": "#8A94A0",
}

STRATEGI = {
    "Loyal High-Value": (
        "Program loyalitas, penawaran eksklusif, benefit prioritas.",
        "Nilai transaksi dan frekuensi pembelian tertinggi. Fokus: mempertahankan pelanggan agar tidak berhenti bertransaksi.",
    ),
    "Pembeli Reguler": (
        "Cross-sell dan upsell, bundling produk, dorongan repeat purchase.",
        "Sudah membeli secara berkala dengan nilai menengah. Fokus: meningkatkan nilai dan frekuensi pembelian.",
    ),
    "Cart Abandoner": (
        "Pengingat keranjang, voucher, promo gratis ongkir.",
        "Aktif melihat produk dan memasukkan ke keranjang, tetapi hampir tidak membeli. Fokus: mendorong checkout.",
    ),
    "Pengunjung Kasual": (
        "Promo pembelian pertama, rekomendasi produk populer.",
        "Aktivitas sangat rendah dan tidak melakukan pembelian. Fokus: konversi pembelian pertama.",
    ),
}

FEAT_LABEL = {
    "avg_views": "View",
    "avg_carts": "Cart",
    "avg_removes": "Remove",
    "avg_purchases": "Purchase",
    "avg_sessions": "Sesi",
    "avg_spend": "Spend (USD)",
    "avg_recency_days": "Hari sejak aktif terakhir",
}


# ------------------------------------------------------------------ database
def get_conn():
    try:
        return psycopg2.connect(**PG, connect_timeout=5)
    except psycopg2.OperationalError:
        if PG["host"] != "localhost":
            return psycopg2.connect(**{**PG, "host": "localhost"}, connect_timeout=5)
        raise


def q(sql, params=None):
    conn = get_conn()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def beri_nama(p):
    if len(p) != 4:
        return {int(c): f"Cluster {int(c)}" for c in p["cluster"]}
    urut = p.sort_values("avg_spend", ascending=False)
    nama = {
        int(urut.iloc[0]["cluster"]): "Loyal High-Value",
        int(urut.iloc[1]["cluster"]): "Pembeli Reguler",
    }
    sisa = urut.iloc[2:].sort_values("avg_carts", ascending=False)
    nama[int(sisa.iloc[0]["cluster"])] = "Cart Abandoner"
    nama[int(sisa.iloc[1]["cluster"])] = "Pengunjung Kasual"
    return nama


@st.cache_data(ttl=3600, show_spinner="Mengambil profil segmen dari PostgreSQL...")
def load_profile():
    df = q(
        """
        SELECT cluster,
               COUNT(*)                                   AS customers,
               COUNT(*) FILTER (WHERE purchase_count > 0) AS buyers,
               AVG(view_count)             AS avg_views,
               AVG(cart_count)             AS avg_carts,
               AVG(remove_count)           AS avg_removes,
               AVG(purchase_count)         AS avg_purchases,
               AVG(session_count)          AS avg_sessions,
               AVG(total_spend)            AS avg_spend,
               AVG(days_since_last_event)  AS avg_recency_days,
               SUM(view_count)             AS sum_views,
               SUM(cart_count)             AS sum_carts,
               SUM(purchase_count)         AS sum_purchases,
               SUM(total_spend)            AS sum_spend,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY view_count)            AS med_views,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cart_count)            AS med_carts,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY purchase_count)        AS med_purchases,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_spend)           AS med_spend,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_since_last_event) AS med_recency_days
        FROM customer_segments
        GROUP BY cluster
        ORDER BY cluster
        """
    )
    df = df.apply(pd.to_numeric)
    df["cluster"] = df["cluster"].astype(int)
    df["segmen"] = df["cluster"].map(beri_nama(df))
    df["pct"] = df["customers"] / df["customers"].sum() * 100
    return df


@st.cache_data(ttl=3600, show_spinner="Mengambil sample pelanggan...")
def load_sample(n_per_cluster=5000):
    df = q(
        """
        SELECT user_id, cluster, view_count, cart_count, remove_count,
               purchase_count, session_count, total_spend, days_since_last_event
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY cluster ORDER BY random()) AS rn
            FROM customer_segments
        ) t
        WHERE rn <= %s
        """,
        params=(n_per_cluster,),
    )
    return df.apply(pd.to_numeric)


@st.cache_data(ttl=3600)
def load_k():
    try:
        return q("SELECT * FROM k_selection ORDER BY k")
    except Exception:
        pass
    if os.path.exists("k_selection_metrics.csv"):
        return pd.read_csv("k_selection_metrics.csv")
    return None


# ------------------------------------------------------------------ load
try:
    profile = load_profile()
    sample = load_sample()
except Exception as e:
    st.error("Dashboard belum dapat membaca data dari PostgreSQL.")
    st.code(str(e))
    st.info(
        "Periksa: (1) container postgres aktif, (2) tabel customer_segments sudah terisi, "
        "(3) jika dashboard dijalankan di laptop (bukan di Docker), port 5432 PostgreSQL harus di-publish."
    )
    st.stop()

nama_map = dict(zip(profile["cluster"], profile["segmen"]))
sample["segmen"] = sample["cluster"].map(nama_map)
urutan = profile.sort_values("avg_spend", ascending=False)["segmen"].tolist()

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Segmentasi Pelanggan")
    st.caption("K-Means, Apache Spark MLlib")
    st.caption("HDFS > Spark > PostgreSQL > Streamlit")
    st.divider()
    pilih_segmen = st.multiselect("Filter segmen (tab Eksplorasi)", urutan, default=urutan)
    if st.button("Muat ulang data"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption(
        "Data historis Oktober 2019 sampai Februari 2020. "
        "Segmentasi berdasarkan perilaku, bukan bukti dampak strategi."
    )

# ------------------------------------------------------------------ header + KPI
st.title("Segmentasi Pelanggan E-Commerce Kosmetik")
st.caption("Pengelompokan pelanggan berdasarkan kemiripan perilaku aktivitas dan transaksi")

total = int(profile["customers"].sum())
buyers = int(profile["buyers"].sum())
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total pelanggan", f"{total:,}")
c2.metric("Pernah membeli", f"{buyers:,}", help=f"{buyers / total * 100:.1f}% dari seluruh pelanggan")
c3.metric("Event purchase", f"{int(profile['sum_purchases'].sum()):,}")
c4.metric("Total nilai transaksi", f"${profile['sum_spend'].sum():,.0f}")
c5.metric("Jumlah cluster (K)", len(profile))

st.write("")
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Ringkasan", "Profil Segmen", "Eksplorasi", "Rekomendasi Strategi", "Metodologi"]
)

# ------------------------------------------------------------------ tab 1
with tab1:
    a, b = st.columns(2)
    fig = px.pie(
        profile, names="segmen", values="customers", hole=0.55,
        color="segmen", color_discrete_map=WARNA, category_orders={"segmen": urutan},
        title="Komposisi seluruh pelanggan",
    )
    fig.update_traces(textinfo="percent")
    a.plotly_chart(fig, use_container_width=True)

    aktif = profile[profile["segmen"] != "Pengunjung Kasual"]
    fig = px.bar(
        aktif, x="segmen", y="customers", color="segmen", text="customers",
        color_discrete_map=WARNA, category_orders={"segmen": urutan},
        title="Segmen aktif (tanpa Pengunjung Kasual)",
        labels={"segmen": "", "customers": "Jumlah pelanggan"},
    )
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(showlegend=False)
    b.plotly_chart(fig, use_container_width=True)

    a, b = st.columns(2)
    fig = go.Figure(
        go.Funnel(
            y=["View", "Cart", "Purchase"],
            x=[profile["sum_views"].sum(), profile["sum_carts"].sum(), profile["sum_purchases"].sum()],
            textinfo="value+percent initial",
            marker={"color": ["#8A94A0", "#D9822B", "#1B7F4C"]},
        )
    )
    fig.update_layout(title="Funnel event (total seluruh pelanggan)")
    a.plotly_chart(fig, use_container_width=True)

    conv = profile.set_index("segmen").loc[urutan].reset_index()
    conv["Cart per view (%)"] = conv["sum_carts"] / conv["sum_views"] * 100
    conv["Purchase per cart (%)"] = conv["sum_purchases"] / conv["sum_carts"] * 100
    conv = conv.replace([np.inf, -np.inf], np.nan)
    long = conv.melt(
        id_vars="segmen", value_vars=["Cart per view (%)", "Purchase per cart (%)"],
        var_name="rasio", value_name="persen",
    )
    fig = px.bar(
        long, x="segmen", y="persen", color="rasio", barmode="group",
        title="Rasio event per segmen", labels={"segmen": "", "persen": "Persen", "rasio": "Rasio"},
    )
    b.plotly_chart(fig, use_container_width=True)
    st.caption("Rasio dihitung dari jumlah event, bukan jumlah pesanan unik.")

# ------------------------------------------------------------------ tab 2
with tab2:
    w = profile["customers"]
    overall = {c: (profile[c] * w).sum() / w.sum() for c in FEAT_LABEL}
    idx = pd.DataFrame({FEAT_LABEL[c]: profile[c] / overall[c] for c in FEAT_LABEL})
    idx.index = profile["segmen"]
    idx = idx.loc[urutan]

    a, b = st.columns(2)
    fig = px.imshow(
        idx, text_auto=".2f", aspect="auto", color_continuous_scale="Blues",
        title="Indeks terhadap rata-rata keseluruhan (1,00 = sama dengan rata-rata)",
    )
    a.plotly_chart(fig, use_container_width=True)

    norm = profile.set_index("segmen")[list(FEAT_LABEL)]
    norm = norm / norm.max()
    labels = list(FEAT_LABEL.values())
    fig = go.Figure()
    for seg in urutan:
        vals = norm.loc[seg].tolist()
        fig.add_trace(
            go.Scatterpolar(
                r=vals + [vals[0]], theta=labels + [labels[0]], fill="toself", name=seg,
                line_color=WARNA.get(seg),
            )
        )
    fig.update_layout(
        title="Radar profil (dinormalisasi per fitur)",
        polar={"radialaxis": {"visible": True, "range": [0, 1]}},
    )
    b.plotly_chart(fig, use_container_width=True)

    metrik = st.multiselect(
        "Bandingkan rata-rata fitur",
        list(FEAT_LABEL),
        default=["avg_views", "avg_carts", "avg_purchases"],
        format_func=lambda c: FEAT_LABEL[c],
    )
    if metrik:
        long = profile.melt(id_vars="segmen", value_vars=metrik, var_name="fitur", value_name="rata-rata")
        long["fitur"] = long["fitur"].map(FEAT_LABEL)
        fig = px.bar(
            long, x="fitur", y="rata-rata", color="segmen", barmode="group",
            color_discrete_map=WARNA, category_orders={"segmen": urutan},
            labels={"fitur": "", "segmen": "Segmen"},
        )
        st.plotly_chart(fig, use_container_width=True)

    t1, t2 = st.tabs(["Rata-rata", "Median"])
    avg_tbl = profile.set_index("segmen").loc[urutan][["customers", "pct"] + list(FEAT_LABEL)]
    avg_tbl = avg_tbl.rename(columns={**FEAT_LABEL, "customers": "Pelanggan", "pct": "% Pelanggan"}).round(2)
    t1.dataframe(avg_tbl, use_container_width=True)
    med_tbl = profile.set_index("segmen").loc[urutan][
        ["med_views", "med_carts", "med_purchases", "med_spend", "med_recency_days"]
    ].rename(columns={
        "med_views": "View", "med_carts": "Cart", "med_purchases": "Purchase",
        "med_spend": "Spend (USD)", "med_recency_days": "Hari sejak aktif terakhir",
    }).round(2)
    t2.dataframe(med_tbl, use_container_width=True)
    st.caption("Median lebih tahan terhadap pelanggan ekstrem dibandingkan rata-rata.")

# ------------------------------------------------------------------ tab 3
with tab3:
    sm = sample[sample["segmen"].isin(pilih_segmen)].copy()
    st.caption(f"Sample acak per cluster (maksimal 5.000 pelanggan tiap cluster). {len(sm):,} titik ditampilkan.")

    sm["x"] = sm["view_count"] + 1
    sm["y"] = sm["total_spend"] + 1
    a, b = st.columns(2)
    fig = px.scatter(
        sm, x="x", y="y", color="segmen", color_discrete_map=WARNA, log_x=True, log_y=True,
        opacity=0.45, hover_data=["user_id", "cart_count", "purchase_count"],
        labels={"x": "view_count + 1 (skala log)", "y": "total_spend + 1 (skala log)", "segmen": "Segmen"},
        title="View terhadap total belanja",
    )
    a.plotly_chart(fig, use_container_width=True)
    fig = px.box(
        sm, x="segmen", y="days_since_last_event", color="segmen", color_discrete_map=WARNA,
        category_orders={"segmen": urutan}, title="Hari sejak aktivitas terakhir",
        labels={"segmen": "", "days_since_last_event": "Hari"},
    )
    fig.update_layout(showlegend=False)
    b.plotly_chart(fig, use_container_width=True)

    st.subheader("Cari pelanggan")
    uid = st.text_input("Masukkan user_id")
    if uid.strip():
        if uid.strip().isdigit():
            r = q("SELECT * FROM customer_segments WHERE user_id = %s", params=(int(uid.strip()),))
            if r.empty:
                st.warning("user_id tidak ditemukan.")
            else:
                r["segmen"] = r["cluster"].map(nama_map)
                st.success(f"Segmen: {r.iloc[0]['segmen']}")
                st.dataframe(r, use_container_width=True, hide_index=True)
        else:
            st.warning("user_id harus berupa angka.")

    st.subheader("Data sample")
    st.dataframe(sm.drop(columns=["x", "y"]).head(1000), use_container_width=True, hide_index=True)
    st.download_button(
        "Unduh sample (CSV)",
        sm.drop(columns=["x", "y"]).to_csv(index=False).encode("utf-8"),
        file_name="sample_pelanggan_segmen.csv",
        mime="text/csv",
    )

# ------------------------------------------------------------------ tab 4
with tab4:
    st.info("Rekomendasi berikut merupakan hipotesis yang perlu diuji (misalnya melalui A/B test), bukan hasil terbukti dari model.")
    cols = st.columns(2)
    for i, seg in enumerate(urutan):
        r = profile[profile["segmen"] == seg].iloc[0]
        aksi, alasan = STRATEGI.get(seg, ("-", "-"))
        with cols[i % 2]:
            with st.container(border=True):
                st.subheader(seg)
                st.caption(f"{int(r['customers']):,} pelanggan, {r['pct']:.1f}% dari total")
                m1, m2, m3 = st.columns(3)
                m1.metric("Rata-rata purchase", f"{r['avg_purchases']:.2f}")
                m2.metric("Rata-rata spend", f"${r['avg_spend']:.2f}")
                m3.metric("Hari sejak aktif", f"{r['avg_recency_days']:.0f}")
                st.markdown(f"**Strategi:** {aksi}")
                st.write(alasan)

# ------------------------------------------------------------------ tab 5
with tab5:
    st.subheader("Arsitektur")
    st.code(
        "CSV (5 file, Oktober 2019 - Februari 2020)\n"
        "   > HDFS (data lake: raw dan processed)\n"
        "   > Apache Spark (agregasi fitur per user_id)\n"
        "   > Spark MLlib K-Means (log1p dan StandardScaler)\n"
        "   > PostgreSQL (serving layer)\n"
        "   > Streamlit (dashboard)",
        language="text",
    )
    st.subheader("Fitur per pelanggan")
    st.write(
        "Jumlah view, cart, remove_from_cart, purchase, jumlah sesi, total nilai transaksi "
        "(hanya dari event purchase), dan hari sejak aktivitas terakhir. "
        "user_id hanya digunakan sebagai kunci pengelompokan, bukan sebagai fitur."
    )
    st.subheader("Pemilihan jumlah cluster (K)")
    ks = load_k()
    if ks is not None:
        a, b = st.columns(2)
        a.plotly_chart(px.line(ks, x="k", y="wssse", markers=True, title="Elbow (WSSSE)"), use_container_width=True)
        b.plotly_chart(px.line(ks, x="k", y="silhouette", markers=True, title="Silhouette score"), use_container_width=True)
        st.caption("K=4 dipilih berdasarkan elbow, silhouette (puncak lokal), dan kebutuhan strategi bisnis.")
    else:
        st.caption("Data pemilihan K belum tersedia (tabel k_selection atau file k_selection_metrics.csv).")
    st.subheader("Catatan interpretasi")
    st.markdown(
        "- Nama segmen dan strategi merupakan interpretasi dari profil cluster, bukan keluaran model.\n"
        "- Event purchase tidak sama dengan jumlah pesanan unik.\n"
        "- Data bersifat historis (2019-2020); hasil menggambarkan periode tersebut.\n"
        "- Mayoritas pelanggan berada pada satu cluster pasif, yang wajar pada e-commerce."
    )