import pandas as pd
from pyspark.sql import SparkSession, functions as F, Window
from penamaan import beri_nama

spark = (SparkSession.builder.appName("analisis_marketing")
         .config("spark.sql.shuffle.partitions", "8")
         .config("spark.sql.adaptive.enabled", "true")
         .config("spark.sql.autoBroadcastJoinThreshold", "-1").getOrCreate())   # cegah error memori saat join besar
spark.sparkContext.setLogLevel("WARN")

EVENTS = "hdfs://namenode:9000/data/processed/events_parquet"
FEATURES = "hdfs://namenode:9000/data/processed/customer_features"
SEGMENTS = "hdfs://namenode:9000/data/processed/customer_segments"
JDBC = "jdbc:postgresql://postgres:5432/segmentasi"
PROPS = {"user": "bigdata", "password": "bigdata",
         "driver": "org.postgresql.Driver", "batchsize": "10000"}

TZ_OFFSET = 3           # dataset UTC; toko diasumsikan UTC+3 (Moskow)
CHURN_DAYS = 60         # ambang "berisiko churn"
TOP_N = 5


def to_pg(df, table):
    (df.toPandas() if hasattr(df, "toPandas") else df)
    pdf = df.toPandas() if hasattr(df, "toPandas") else df
    spark.createDataFrame(pdf).write.jdbc(JDBC, table, mode="overwrite", properties=PROPS)


# ---------- label segmen (ranking: spend -> cart), konsisten dengan dashboard
feat = spark.read.parquet(FEATURES)
lab = spark.read.parquet(SEGMENTS).select("user_id", "cluster")
seg = feat.join(lab, "user_id").cache()
print("Pelanggan:", f"{seg.count():,}")

peta = beri_nama(seg)   # penamaan berbasis data, sama dengan analisis_lanjutan.py
rec = spark.createDataFrame([(c, n) for c, n in peta.items()], ["cluster", "segmen"])

ev = (spark.read.parquet(EVENTS)
      .join(lab, "user_id")
      .withColumn("local_ts", F.col("event_time") + F.expr(f"INTERVAL {TZ_OFFSET} HOURS"))
      .cache())
buys = ev.filter(F.col("event_type") == "purchase").cache()
print("Event purchase:", f"{buys.count():,}")


def topn(df, col, nama_tabel, judul):
    """Top N nilai kolom per cluster berdasarkan jumlah event purchase."""
    d = df.filter(F.col(col).isNotNull() & (F.col(col) != ""))
    agg = d.groupBy("cluster", col).agg(
        F.count("*").alias("purchase_events"),
        F.round(F.sum("price"), 2).alias("revenue"),
        F.countDistinct("user_id").alias("buyers"),
    )
    w = Window.partitionBy("cluster").orderBy(F.desc("purchase_events"))
    out = (agg.withColumn("rank", F.row_number().over(w)).filter(F.col("rank") <= TOP_N)
           .join(rec, "cluster")
           .select("cluster", "segmen", "rank", F.col(col).alias("item"),
                   "purchase_events", "revenue", "buyers")
           .orderBy("cluster", "rank"))
    print(f"\n=== {judul} (top {TOP_N} per segmen) ===")
    out.show(40, truncate=False)
    to_pg(out, nama_tabel)
    return out


# ---------- 1. brand, kategori, produk favorit
topn(buys, "brand", "top_brand_segment", "BRAND FAVORIT")
topn(buys.withColumn("category_code",
                     F.coalesce(F.col("category_code"), F.lit("(tanpa kategori)"))),
     "category_code", "top_category_segment", "KATEGORI FAVORIT")
topn(buys.withColumn("product_id", F.col("product_id").cast("string")),
     "product_id", "top_product_segment", "PRODUK FAVORIT")

# ---------- 2. rentang harga produk yang dibeli
harga = (buys.groupBy("cluster").agg(
    F.count("*").alias("purchase_events"),
    F.round(F.avg("price"), 2).alias("avg_price"),
    F.round(F.expr("percentile_approx(price, 0.25, 10000)"), 2).alias("p25_price"),
    F.round(F.expr("percentile_approx(price, 0.5, 10000)"), 2).alias("median_price"),
    F.round(F.expr("percentile_approx(price, 0.75, 10000)"), 2).alias("p75_price"),
    F.round(F.min("price"), 2).alias("min_price"),
    F.round(F.max("price"), 2).alias("max_price"),
).join(rec, "cluster").select(
    "cluster", "segmen", "purchase_events", "avg_price",
    "p25_price", "median_price", "p75_price", "min_price", "max_price").orderBy("cluster"))
print("\n=== RENTANG HARGA PRODUK DIBELI ===")
harga.show(truncate=False)
to_pg(harga, "price_range_segment")

# ---------- 3. waktu aktif (jam & hari), semua event
jam = (ev.groupBy("cluster", F.hour("local_ts").alias("jam"))
       .agg(F.count("*").alias("events"))
       .join(rec, "cluster"))
tot_jam = jam.groupBy("cluster").agg(F.sum("events").alias("tot"))
jam = (jam.join(tot_jam, "cluster")
       .withColumn("pct_events", F.round(F.col("events") / F.col("tot") * 100, 2))
       .select("cluster", "segmen", "jam", "events", "pct_events").orderBy("cluster", "jam"))
to_pg(jam, "activity_hour_segment")

hari = (ev.groupBy("cluster", F.dayofweek("local_ts").alias("dow"))
        .agg(F.count("*").alias("events")).join(rec, "cluster"))
tot_h = hari.groupBy("cluster").agg(F.sum("events").alias("tot"))
NAMA_HARI = F.when(F.col("dow") == 1, "Minggu").when(F.col("dow") == 2, "Senin") \
    .when(F.col("dow") == 3, "Selasa").when(F.col("dow") == 4, "Rabu") \
    .when(F.col("dow") == 5, "Kamis").when(F.col("dow") == 6, "Jumat").otherwise("Sabtu")
hari = (hari.join(tot_h, "cluster").withColumn("nama_hari", NAMA_HARI)
        .withColumn("pct_events", F.round(F.col("events") / F.col("tot") * 100, 2))
        .select("cluster", "segmen", "dow", "nama_hari", "events", "pct_events")
        .orderBy("cluster", "dow"))
to_pg(hari, "activity_day_segment")

puncak = (jam.withColumn("rk", F.row_number().over(
    Window.partitionBy("cluster").orderBy(F.desc("events")))).filter(F.col("rk") <= 3)
    .select("cluster", "segmen", "jam", "pct_events").orderBy("cluster", F.desc("pct_events")))
print(f"\n=== JAM PUNCAK AKTIVITAS (UTC+{TZ_OFFSET}) ===")
puncak.show(truncate=False)

# ---------- 4. risiko churn (pembeli yang sudah lama tidak aktif)
churn = (seg.filter(F.col("purchase_count") > 0)
         .withColumn("berisiko", (F.col("days_since_last_event") >= CHURN_DAYS).cast("int"))
         .groupBy("cluster").agg(
             F.count("*").alias("buyers"),
             F.sum("berisiko").alias("at_risk"),
             F.round(F.sum(F.when(F.col("berisiko") == 1, F.col("total_spend"))
                           .otherwise(0.0)), 2).alias("revenue_at_risk"),
             F.round(F.avg("days_since_last_event"), 1).alias("avg_recency_buyers"),
         ).join(rec, "cluster")
         .withColumn("pct_at_risk", F.round(F.col("at_risk") / F.col("buyers") * 100, 2))
         .select("cluster", "segmen", "buyers", "at_risk", "pct_at_risk",
                 "revenue_at_risk", "avg_recency_buyers").orderBy(F.desc("revenue_at_risk")))
print(f"\n=== RISIKO CHURN (pembeli tidak aktif >= {CHURN_DAYS} hari) ===")
churn.show(truncate=False)
to_pg(churn, "churn_risk_segment")

# ---------- 5. simulasi potensi konversi (bukan prediksi model)
non = seg.join(rec, "cluster").filter(F.col("purchase_count") == 0) \
    .groupBy("segmen").agg(F.count("*").alias("non_buyers")).toPandas()
spb = (seg.filter(F.col("purchase_count") > 0)
       .agg((F.sum("total_spend") / F.count("*")).alias("v")).first()["v"])
rows = []
for _, r in non.iterrows():
    for p in (1, 3, 5):
        conv = r["non_buyers"] * p / 100
        rows.append((r["segmen"], p, int(r["non_buyers"]), int(round(conv)),
                     round(conv * spb, 2)))
sim = pd.DataFrame(rows, columns=["segmen", "skenario_pct", "non_buyers",
                                  "estimasi_pembeli_baru", "estimasi_revenue"])
print(f"\n=== SIMULASI KONVERSI (asumsi belanja/pembeli = {spb:,.2f}) ===")
print(sim.to_string(index=False))
to_pg(sim, "conversion_simulation")

asumsi = pd.DataFrame([
    ("Zona waktu analisis", f"UTC+{TZ_OFFSET} (dataset asli UTC)"),
    ("Ambang berisiko churn", f"{CHURN_DAYS} hari sejak aktivitas terakhir"),
    ("Top N produk/brand/kategori", f"{TOP_N}, diurutkan jumlah event purchase"),
    ("Harga", "harga pada event purchase, disajikan median dan kuartil"),
    ("Asumsi nilai belanja per pembeli (simulasi)", f"{spb:.2f}"),
    ("Status churn", "berisiko churn, bukan churn aktual (tidak ada label)"),
    ("Simulasi konversi", "skenario 1%, 3%, 5% — bukan prediksi model"),
], columns=["parameter", "nilai"])
to_pg(asumsi, "marketing_assumptions")
print("\n=== ASUMSI ===")
print(asumsi.to_string(index=False))

print("\nSELESAI. Tabel baru: top_brand_segment, top_category_segment, top_product_segment,")
print("price_range_segment, activity_hour_segment, activity_day_segment,")
print("churn_risk_segment, conversion_simulation, marketing_assumptions")
spark.stop()