import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans, BisectingKMeans
from pyspark.ml.evaluation import ClusteringEvaluator

spark = (SparkSession.builder.appName("validasi_kmeans")
         .config("spark.sql.shuffle.partitions", "8")
         .config("spark.sql.adaptive.enabled", "true")
         .getOrCreate())
spark.sparkContext.setLogLevel("WARN")

FEATURES_PATH = "hdfs://namenode:9000/data/processed/customer_features"
SEGMENTS_PATH = "hdfs://namenode:9000/data/processed/customer_segments"
JDBC = "jdbc:postgresql://postgres:5432/segmentasi"
PROPS = {"user": "bigdata", "password": "bigdata",
         "driver": "org.postgresql.Driver", "batchsize": "10000"}

# sama persis dengan kmeans_pipeline.py
FEATS = ["view_count", "cart_count", "remove_count", "purchase_count",
         "total_spend", "session_count", "days_since_last_event"]
K_FINAL = 4
MAX_ITER, TOL = 20, 0.01
SEEDS = [42, 1, 2, 3, 4, 5]


def to_pg(pdf, table):
    spark.createDataFrame(pdf).write.jdbc(JDBC, table, mode="overwrite", properties=PROPS)


# ---------- baca fitur + diagnosis nilai tidak wajar
raw = spark.read.parquet(FEATURES_PATH).select("user_id", *FEATS)
print("\n=== DIAGNOSIS NULL / NEGATIF ===")
raw.agg(
    *[F.sum(F.col(c).isNull().cast("int")).alias(f"null_{c}") for c in FEATS],
    *[F.sum((F.col(c) < 0).cast("int")).alias(f"neg_{c}") for c in FEATS],
).show(vertical=True)

# ---------- fitur: potong negatif ke 0 -> log1p -> StandardScaler (sama dengan dashboard)
for c in FEATS:
    raw = raw.withColumn(f"log_{c}", F.log1p(F.greatest(F.col(c).cast("double"), F.lit(0.0))))

vec = VectorAssembler(inputCols=[f"log_{c}" for c in FEATS], outputCol="raw_vec",
                      handleInvalid="skip").transform(raw)
data = (StandardScaler(inputCol="raw_vec", outputCol="features", withMean=True, withStd=True)
        .fit(vec).transform(vec)
        .select("user_id", *FEATS, "features").cache())
print("Pelanggan:", f"{data.count():,}")
smp = data.sample(False, 0.1, seed=1).cache()
print("Sample silhouette:", f"{smp.count():,}")


def km(k, seed, pred="prediction"):
    return KMeans(k=k, seed=seed, featuresCol="features", predictionCol=pred,
                  maxIter=MAX_ITER, tol=TOL)


# ---------- A. pemilihan K (elbow + silhouette)
rows = []
for k in range(2, 9):
    m = km(k, 42).fit(data)
    sil = ClusteringEvaluator(featuresCol="features", metricName="silhouette").evaluate(m.transform(smp))
    rows.append({"k": k, "wssse": float(m.summary.trainingCost), "silhouette": float(sil)})
    print(rows[-1])
ksel = pd.DataFrame(rows)
to_pg(ksel, "k_selection")
sil_k = float(ksel.loc[ksel["k"] == K_FINAL, "silhouette"].iloc[0])

# ---------- B. stabilitas antar seed + C. Bisecting K-Means
res = data
for s in SEEDS:
    res = km(K_FINAL, s, pred=f"c{s}").fit(data).transform(res)

bm = BisectingKMeans(k=K_FINAL, seed=42, featuresCol="features", predictionCol="c_bisect",
                     maxIter=MAX_ITER).fit(data)
res = bm.transform(res)
sil_bis = float(ClusteringEvaluator(featuresCol="features", predictionCol="c_bisect",
                                    metricName="silhouette").evaluate(bm.transform(smp)))

# label cluster yang dipakai dashboard (customer_segments di HDFS)
saved = spark.read.parquet(SEGMENTS_PATH).select("user_id", F.col("cluster").alias("c_saved"))
res = res.drop("features").join(saved, "user_id", "left").cache()
print("Baris tergabung:", f"{res.count():,}")


def ari(df, a, b):
    ct = df.groupBy(a, b).count().toPandas()
    comb = lambda x: x * (x - 1) / 2
    n = ct["count"].sum()
    s_ij = sum(comb(x) for x in ct["count"])
    s_a = sum(comb(x) for x in ct.groupby(a)["count"].sum())
    s_b = sum(comb(x) for x in ct.groupby(b)["count"].sum())
    exp = s_a * s_b / comb(n)
    return float((s_ij - exp) / ((s_a + s_b) / 2 - exp))


stab = [ari(res, "c42", f"c{s}") for s in SEEDS[1:]]
ari_bis = ari(res, "c42", "c_bisect")
ari_saved = ari(res, "c42", "c_saved")

# ---------- D. kemurnian cluster (pakai cluster dashboard)
pur = (res.groupBy("c_saved").agg(
    F.count("*").alias("customers"),
    F.round(F.avg((F.col("purchase_count") > 0).cast("double")) * 100, 1).alias("pct_pernah_beli"),
    F.round(F.avg((F.col("cart_count") > 0).cast("double")) * 100, 1).alias("pct_pernah_cart"),
    F.round(F.avg(((F.col("cart_count") > 0) & (F.col("purchase_count") == 0)).cast("double")) * 100, 1)
        .alias("pct_cart_tanpa_beli"),
    F.round(F.avg("view_count"), 2).alias("avg_views"),
    F.round(F.avg("purchase_count"), 2).alias("avg_purchases"),
).orderBy("c_saved").withColumnRenamed("c_saved", "cluster")).toPandas()

# ---------- ringkasan
summary = pd.DataFrame([
    ("K final", float(K_FINAL)),
    ("Silhouette K-Means (K final, sample 10%)", sil_k),
    ("Silhouette Bisecting K-Means (sample 10%)", sil_bis),
    ("ARI stabilitas K-Means, rata-rata 5 seed", sum(stab) / len(stab)),
    ("ARI stabilitas K-Means, minimum", min(stab)),
    ("ARI K-Means vs Bisecting K-Means", ari_bis),
    ("ARI validasi vs model dashboard (reproduksi)", ari_saved),
], columns=["metrik", "nilai"])

print("\n=== PEMILIHAN K ===");        print(ksel.to_string(index=False))
print("\n=== RINGKASAN VALIDASI ==="); print(summary.to_string(index=False))
print("\n=== KEMURNIAN CLUSTER ===");  print(pur.to_string(index=False))

to_pg(summary, "model_validation")
to_pg(pur, "cluster_purity")
print("\nSELESAI: k_selection, model_validation, cluster_purity ditulis ke PostgreSQL")
spark.stop()