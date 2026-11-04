"""Cek keputusan K=3 vs K=4:
1) WSSSE & silhouette tiap seed -> apakah seed 42 solusi terbaik (WSSSE terendah)?
2) Profil solusi terbaik tiap K + tabulasi silang terhadap 4 segmen dashboard
   -> segmen mana yang digabung bila memakai K=3."""
import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator

spark = (SparkSession.builder.appName("cek_k3_k4")
         .config("spark.sql.shuffle.partitions", "8")
         .config("spark.sql.adaptive.enabled", "true").getOrCreate())
spark.sparkContext.setLogLevel("ERROR")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

FEATURES_PATH = "hdfs://namenode:9000/data/processed/customer_features"
SEGMENTS_PATH = "hdfs://namenode:9000/data/processed/customer_segments"
# sama dengan kmeans_pipeline.py (6 fitur, tanpa recency)
FEATS = ["view_count", "cart_count", "remove_count", "purchase_count",
         "session_count", "total_spend"]
SEEDS = [42, 1, 2, 3, 4]
MAX_ITER, TOL = 50, 1e-4

raw = spark.read.parquet(FEATURES_PATH)
for c in FEATS:
    raw = raw.withColumn(f"log_{c}", F.log1p(F.greatest(F.col(c).cast("double"), F.lit(0.0))))
vec = VectorAssembler(inputCols=[f"log_{c}" for c in FEATS], outputCol="raw_vec",
                      handleInvalid="skip").transform(raw)
data = (StandardScaler(inputCol="raw_vec", outputCol="features", withMean=True, withStd=True)
        .fit(vec).transform(vec)
        .select("user_id", *FEATS, "days_since_last_event", "features").cache())
n = data.count()
smp = data.sample(False, 0.1, seed=1).cache()
ev = ClusteringEvaluator(featuresCol="features", metricName="silhouette")

# ---------- 1. tiap seed
rows, best = [], {}
for k in (3, 4):
    for sd in SEEDS:
        m = KMeans(k=k, seed=sd, featuresCol="features", maxIter=MAX_ITER, tol=TOL,
                   initMode="k-means||").fit(data)
        w = float(m.summary.trainingCost)
        s = float(ev.evaluate(m.transform(smp)))
        rows.append(dict(k=k, seed=sd, wssse=round(w), silhouette=round(s, 4),
                         cluster_terkecil_pct=round(min(m.summary.clusterSizes) / n * 100, 2)))
        if k not in best or w < best[k][1]:
            best[k] = (m, w, sd)
        print(rows[-1])

tab = pd.DataFrame(rows)
print("\n=== 1. HASIL PER SEED ===")
print(tab.to_string(index=False))
for k in (3, 4):
    t = tab[tab.k == k]
    b = t.loc[t.wssse.idxmin()]
    print(f"K={k}: WSSSE terendah di seed {int(b.seed)} (silhouette {b.silhouette:.4f}); "
          f"seed 42 {'ADALAH' if int(b.seed) == 42 else 'BUKAN'} solusi terbaik")

# ---------- 2. profil solusi terbaik + tabulasi silang vs segmen dashboard
seg = spark.read.parquet(SEGMENTS_PATH).select("user_id", F.col("cluster").alias("seg4"))
for k in (3, 4):
    m, w, sd = best[k]
    p = m.transform(data).withColumnRenamed("prediction", f"c{k}")
    prof = (p.groupBy(f"c{k}").agg(
        F.count("*").alias("pengguna"),
        F.round(F.avg((F.col("purchase_count") > 0).cast("double")) * 100, 1).alias("pct_beli"),
        F.round(F.avg(((F.col("cart_count") > 0) & (F.col("purchase_count") == 0)).cast("double")) * 100, 1).alias("pct_keranjang_tanpa_beli"),
        F.round(F.avg("view_count"), 1).alias("avg_view"),
        F.round(F.avg("cart_count"), 1).alias("avg_cart"),
        F.round(F.avg("purchase_count"), 2).alias("avg_item"),
        F.round(F.avg("total_spend"), 2).alias("avg_belanja"),
    ).orderBy(F.desc("avg_belanja")).toPandas())
    print(f"\n=== 2. PROFIL K={k} (seed {sd}, WSSSE {w:,.0f}) ===")
    print(prof.to_string(index=False))
    if k == 3:
        ct = (p.join(seg, "user_id").groupBy("c3").pivot("seg4").count().orderBy("c3").toPandas().fillna(0))
        print("\n=== TABULASI SILANG: cluster K=3 (baris) vs cluster dashboard K=4 (kolom) ===")
        print(ct.to_string(index=False))
        print("Kolom = nomor cluster dashboard. Cocokkan dengan tabel kemurnian (cluster_purity) untuk nama segmennya.")

spark.stop()
