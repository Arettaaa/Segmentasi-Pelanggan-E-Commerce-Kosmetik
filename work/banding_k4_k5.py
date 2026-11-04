"""Bandingkan beberapa K (default 3, 4, 5) secara adil: silhouette multi-seed & multi-sampel,
stabilitas antar seed (ARI), dan ukuran cluster terkecil.
Hasil disimpan ke tabel PostgreSQL `k_compare`."""
import itertools
import statistics as st

import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator

spark = (SparkSession.builder.appName("banding_k4_k5")
         .config("spark.sql.shuffle.partitions", "8")
         .config("spark.sql.adaptive.enabled", "true").getOrCreate())
spark.sparkContext.setLogLevel("WARN")

FEATURES_PATH = "hdfs://namenode:9000/data/processed/customer_features"
JDBC = "jdbc:postgresql://postgres:5432/segmentasi"
PROPS = {"user": "bigdata", "password": "bigdata", "driver": "org.postgresql.Driver"}

# sama persis dengan validasi_kmeans.py (6 fitur, tanpa recency)
# 6 fitur perilaku & belanja (sama dengan notebook Colab). Recency TIDAK masuk K-Means;
# dipakai terpisah untuk profil dan analisis risiko tidak aktif.
FEATS = ["view_count", "cart_count", "remove_count", "purchase_count",
         "session_count", "total_spend"]
KS = [3, 4, 5]
SEEDS = [42, 1, 2, 3, 4]          # seed K-Means
SAMPLE_SEEDS = [1, 2, 3]          # seed sampel 10% untuk silhouette
MAX_ITER, TOL = 30, 1e-4   # sama dengan Colab (pemilihan K)

raw = spark.read.parquet(FEATURES_PATH).select("user_id", *FEATS)
for c in FEATS:
    raw = raw.withColumn(f"log_{c}", F.log1p(F.greatest(F.col(c).cast("double"), F.lit(0.0))))
vec = VectorAssembler(inputCols=[f"log_{c}" for c in FEATS], outputCol="raw_vec",
                      handleInvalid="skip").transform(raw)
data = (StandardScaler(inputCol="raw_vec", outputCol="features", withMean=True, withStd=True)
        .fit(vec).transform(vec).select("user_id", "features").cache())
n = data.count()
print(f"Pengguna: {n:,}")
samples = {s: data.sample(False, 0.1, seed=s).cache() for s in SAMPLE_SEEDS}
ev = ClusteringEvaluator(featuresCol="features", metricName="silhouette")


def ari(df, a, b):
    ct = df.groupBy(a, b).count().toPandas()
    comb = lambda x: x * (x - 1) / 2
    tot = ct["count"].sum()
    s_ij = sum(comb(x) for x in ct["count"])
    s_a = sum(comb(x) for x in ct.groupby(a)["count"].sum())
    s_b = sum(comb(x) for x in ct.groupby(b)["count"].sum())
    exp = s_a * s_b / comb(tot)
    return float((s_ij - exp) / ((s_a + s_b) / 2 - exp))


rows = []
for k in KS:
    sils, mins, res = [], [], data.select("user_id", "features")
    for sd in SEEDS:
        m = KMeans(k=k, seed=sd, featuresCol="features", predictionCol=f"c{sd}",
                   maxIter=MAX_ITER, tol=TOL).fit(data)
        for smp in samples.values():
            sils.append(float(ev.evaluate(m.transform(smp).withColumnRenamed(f"c{sd}", "prediction"))))
        sizes = m.summary.clusterSizes
        mins.append(min(sizes) / n * 100)
        res = m.transform(res)
    res = res.drop("features").cache()
    aris = [ari(res, f"c{a}", f"c{b}") for a, b in itertools.combinations(SEEDS, 2)]
    rows.append(dict(
        k=k,
        silhouette_mean=round(st.mean(sils), 4),
        silhouette_std=round(st.stdev(sils), 4),
        silhouette_min=round(min(sils), 4),
        silhouette_max=round(max(sils), 4),
        ari_mean=round(st.mean(aris), 4),
        ari_min=round(min(aris), 4),
        min_cluster_pct=round(st.mean(mins), 3),
        n_eval=len(sils),
    ))
    res.unpersist()
    print(rows[-1])

out = pd.DataFrame(rows).sort_values("k").reset_index(drop=True)
print("\n=== PERBANDINGAN K ===")
print(out.to_string(index=False))

# bandingkan setiap pasangan K berurutan
for i in range(len(out) - 1):
    a, b = out.iloc[i], out.iloc[i + 1]
    diff = b.silhouette_mean - a.silhouette_mean
    noise = max(a.silhouette_std, b.silhouette_std)
    status = "dalam variasi seed/sampel" if abs(diff) <= 2 * noise else "berbeda bermakna"
    print(f"K={int(b.k)} - K={int(a.k)}: selisih silhouette {diff:+.4f} (std terbesar {noise:.4f}) -> {status}")

top = out.sort_values(["silhouette_mean", "ari_mean"], ascending=False).iloc[0]
stab = out.sort_values("ari_mean", ascending=False).iloc[0]
print(f"\nSilhouette rata-rata tertinggi: K={int(top.k)} ({top.silhouette_mean:.4f}, std {top.silhouette_std:.4f})")
print(f"Paling stabil antar seed (ARI): K={int(stab.k)} ({stab.ari_mean:.4f})")
print("Keputusan akhir tetap mempertimbangkan profil segmen (lihat cek_k3_k4.py).")

spark.createDataFrame(out).write.jdbc(JDBC, "k_compare", mode="overwrite", properties=PROPS)
print("\nTersimpan ke tabel PostgreSQL: k_compare")
spark.stop()
