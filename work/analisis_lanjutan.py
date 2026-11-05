import pandas as pd
from pyspark.sql import SparkSession, functions as F, Window
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.stat import Correlation
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator
from penamaan import beri_nama

spark = (SparkSession.builder.appName("analisis_lanjutan")
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

# 6 fitur perilaku & belanja (sama dengan notebook Colab). Recency TIDAK masuk K-Means;
# dipakai terpisah untuk profil dan analisis risiko tidak aktif.
FEATS = ["view_count", "cart_count", "remove_count", "purchase_count",
         "session_count", "total_spend"]
K, SEEDS, MAX_ITER, TOL = 3, [42, 1, 2, 3, 4, 5, 6, 7, 8, 9], 50, 1e-4   # sama dengan model final Colab


def to_pg(pdf, table):
    spark.createDataFrame(pdf).write.jdbc(JDBC, table, mode="overwrite", properties=PROPS)


seg = (spark.read.parquet(FEATURES)
       .join(spark.read.parquet(SEGMENTS).select("user_id", "cluster"), "user_id").cache())
total = seg.count()
print("Pelanggan:", f"{total:,}")

# ---------- A. penamaan segmen berbasis data (lihat penamaan.py)
peta = beri_nama(seg)
rec = spark.createDataFrame([(c, n) for c, n in peta.items()], ["cluster", "segmen"])

# ---------- B. revenue share + buyer rate + spending per buyer
grand = seg.agg(F.sum("total_spend")).first()[0]
w = Window.partitionBy()
econ = (seg.groupBy("cluster").agg(
    F.count("*").alias("customers"),
    F.sum((F.col("purchase_count") > 0).cast("int")).alias("buyers"),
    F.sum("total_spend").alias("segment_revenue"),
    F.sum("purchase_count").alias("purchase_events"),
).join(rec, "cluster")
    .withColumn("pct_customers", F.round(F.col("customers") / F.sum("customers").over(w) * 100, 2))
    .withColumn("buyer_rate", F.round(F.col("buyers") / F.col("customers") * 100, 2))
    .withColumn("revenue_share", F.round(F.col("segment_revenue") / F.lit(grand) * 100, 2))
    .withColumn("spend_per_customer", F.round(F.col("segment_revenue") / F.col("customers"), 2))
    .withColumn("spend_per_buyer",
                F.round(F.col("segment_revenue") / F.greatest(F.col("buyers"), F.lit(1)), 2))
    .withColumn("purchase_per_buyer",
                F.round(F.col("purchase_events") / F.greatest(F.col("buyers"), F.lit(1)), 2))
    .select("cluster", "segmen", "customers", "pct_customers", "buyers", "buyer_rate",
            F.round("segment_revenue", 2).alias("segment_revenue"), "revenue_share",
            "spend_per_customer", "spend_per_buyer", "purchase_per_buyer")
    .orderBy(F.desc("revenue_share")))
print("\n=== EKONOMI SEGMEN (revenue share & buyer rate) ===")
econ.show(truncate=False)
to_pg(econ.toPandas(), "segment_economics")

# ---------- C. funnel berbasis PELANGGAN UNIK (bukan total event)
ev = spark.read.parquet(EVENTS).select("user_id", "event_type")
flag = (ev.groupBy("user_id").agg(
    F.max((F.col("event_type") == "view").cast("int")).alias("f_view"),
    F.max((F.col("event_type") == "cart").cast("int")).alias("f_cart"),
    F.max((F.col("event_type") == "purchase").cast("int")).alias("f_purchase"),
).join(spark.read.parquet(SEGMENTS).select("user_id", "cluster"), "user_id"))

glob = flag.agg(F.sum("f_view").alias("n_view"), F.sum("f_cart").alias("n_cart"),
                F.sum("f_purchase").alias("n_purchase")).first()
funnel = pd.DataFrame([
    ("Pernah view", int(glob["n_view"])),
    ("Pernah cart", int(glob["n_cart"])),
    ("Pernah purchase", int(glob["n_purchase"])),
], columns=["tahap", "customers"])
funnel["pct_of_total"] = (funnel["customers"] / total * 100).round(2)
print("\n=== FUNNEL PELANGGAN UNIK ===")
print(funnel.to_string(index=False))
to_pg(funnel, "funnel_customer")

fseg = (flag.groupBy("cluster").agg(
    F.count("*").alias("customers"),
    F.round(F.avg("f_view") * 100, 2).alias("pct_view"),
    F.round(F.avg("f_cart") * 100, 2).alias("pct_cart"),
    F.round(F.avg("f_purchase") * 100, 2).alias("pct_purchase"),
).join(rec, "cluster")
    .withColumn("cart_to_purchase",
                F.round(F.col("pct_purchase") / F.greatest(F.col("pct_cart"), F.lit(0.01)) * 100, 2))
    .select("cluster", "segmen", "customers", "pct_view", "pct_cart", "pct_purchase",
            "cart_to_purchase").orderBy("cluster"))
print("\n=== FUNNEL PER SEGMEN (% pelanggan) ===")
fseg.show(truncate=False)
to_pg(fseg.toPandas(), "funnel_segment")

# ---------- D. fitur terskala (dipakai korelasi, silhouette, stabilitas)
df = spark.read.parquet(FEATURES)
for c in FEATS:
    df = df.withColumn(f"{c}_log", F.log1p(F.greatest(F.col(c).cast("double"), F.lit(0.0))))
vec = VectorAssembler(inputCols=[f"{c}_log" for c in FEATS], outputCol="features_raw",
                      handleInvalid="skip").transform(df)
data = (StandardScaler(inputCol="features_raw", outputCol="features", withMean=True, withStd=True)
        .fit(vec).transform(vec).select("user_id", *FEATS, "features").cache())
data.count()

# korelasi antar fitur setelah transformasi
cm = Correlation.corr(data, "features", "pearson").head()[0].toArray()
corr = pd.DataFrame(cm.round(3), index=FEATS, columns=FEATS)
print("\n=== KORELASI FITUR (setelah log1p + scaling) ===")
print(corr.to_string())
to_pg(corr.reset_index().rename(columns={"index": "fitur"}), "feature_correlation")
tinggi = [(FEATS[i], FEATS[j], round(float(cm[i][j]), 3))
          for i in range(len(FEATS)) for j in range(i + 1, len(FEATS)) if abs(cm[i][j]) > 0.8]
print("Pasangan korelasi > 0.8:", tinggi if tinggi else "tidak ada")

# ---------- E. silhouette per cluster (squared Euclidean, default Spark)
smp = data.sample(False, 0.1, seed=1).cache()
ev_sil = ClusteringEvaluator(featuresCol="features", predictionCol="cluster",
                             metricName="silhouette", distanceMeasure="squaredEuclidean")
labeled = (smp.join(spark.read.parquet(SEGMENTS).select("user_id", "cluster"), "user_id")).cache()
print("\nSample silhouette:", f"{labeled.count():,}")
sil_all = float(ev_sil.evaluate(labeled))
rows = [("Keseluruhan (sample 10%)", round(sil_all, 4))]
# silhouette tiap cluster: bandingkan cluster itu vs sisanya
for c in sorted(peta):
    sub = labeled.withColumn("cluster", F.when(F.col("cluster") == c, 0).otherwise(1))
    rows.append((f"{peta[c]} vs lainnya", round(float(ev_sil.evaluate(sub)), 4)))
sil_df = pd.DataFrame(rows, columns=["cakupan", "silhouette"])
print("\n=== SILHOUETTE (squaredEuclidean) ===")
print(sil_df.to_string(index=False))
to_pg(sil_df, "silhouette_detail")

# ---------- F. stabilitas PER CLUSTER (10 seed, Jaccard terhadap seed 42)
res = data.select("user_id", "features")
wss = {}
for s in SEEDS:
    m = KMeans(k=K, seed=s, featuresCol="features", predictionCol=f"c{s}",
               maxIter=MAX_ITER, tol=TOL).fit(data)
    wss[s] = round(float(m.summary.trainingCost), 1)
    res = m.transform(res)
res = res.drop("features").cache()
res.count()
print("\nWSSSE per seed:", wss)
best_seed = min(wss, key=wss.get)
print("Seed dengan WSSSE terendah:", best_seed)

base_map = {}
for c in sorted(peta):
    base_map[peta[c]] = c
stab_rows = []
for nama, c42 in base_map.items():
    jac = []
    for s in SEEDS[1:]:
        ct = res.filter(F.col("c42") == c42).groupBy(f"c{s}").count().toPandas()
        if ct.empty:
            continue
        top = ct.sort_values("count", ascending=False).iloc[0]
        inter = float(top["count"])
        size_other = res.filter(F.col(f"c{s}") == int(top[f"c{s}"])).count()
        size_base = float(ct["count"].sum())
        jac.append(inter / (size_base + size_other - inter))
    stab_rows.append((nama, round(sum(jac) / len(jac), 3), round(min(jac), 3), round(max(jac), 3)))
stab = pd.DataFrame(stab_rows, columns=["segmen", "jaccard_mean", "jaccard_min", "jaccard_max"])
print("\n=== STABILITAS PER CLUSTER (Jaccard vs seed 42, 9 pembanding) ===")
print(stab.to_string(index=False))
to_pg(stab, "cluster_stability")

wss_df = pd.DataFrame(sorted(wss.items()), columns=["seed", "wssse"])
to_pg(wss_df, "seed_wssse")

# ---------- G. sensitivitas fitur: tanpa session_count
alt = [f for f in FEATS if f != "session_count"]
v2 = VectorAssembler(inputCols=[f"{c}_log" for c in alt], outputCol="fr2",
                     handleInvalid="skip").transform(df)
d2 = (StandardScaler(inputCol="fr2", outputCol="f2", withMean=True, withStd=True)
      .fit(v2).transform(v2).select("user_id", "f2").cache())
m2 = KMeans(k=K, seed=42, featuresCol="f2", predictionCol="c_alt",
            maxIter=MAX_ITER, tol=TOL).fit(d2)
sil2 = float(ClusteringEvaluator(featuresCol="f2", predictionCol="c_alt",
                                 metricName="silhouette").evaluate(
    m2.transform(d2).sample(False, 0.1, seed=1)))
cmp = m2.transform(d2).select("user_id", "c_alt").join(res.select("user_id", "c42"), "user_id")
ct = cmp.groupBy("c42", "c_alt").count().toPandas()
comb = lambda x: x * (x - 1) / 2
n = ct["count"].sum()
s_ij = sum(comb(x) for x in ct["count"])
s_a = sum(comb(x) for x in ct.groupby("c42")["count"].sum())
s_b = sum(comb(x) for x in ct.groupby("c_alt")["count"].sum())
exp = s_a * s_b / comb(n)
ari_alt = (s_ij - exp) / ((s_a + s_b) / 2 - exp)
sens = pd.DataFrame([
    ("Model 1: 6 fitur (utama)", round(sil_all, 4), 1.0),
    ("Model 2: tanpa session_count", round(sil2, 4), round(float(ari_alt), 4)),
], columns=["model", "silhouette", "ari_vs_model_utama"])
print("\n=== SENSITIVITAS FITUR ===")
print(sens.to_string(index=False))
to_pg(sens, "feature_sensitivity")

print("\nSELESAI. Tabel baru di PostgreSQL: segment_economics, funnel_customer, funnel_segment,")
print("feature_correlation, silhouette_detail, cluster_stability, seed_wssse, feature_sensitivity")
spark.stop()