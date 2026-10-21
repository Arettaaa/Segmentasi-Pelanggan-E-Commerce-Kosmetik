import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans

spark = (SparkSession.builder.appName("kmeans_best")
         .config("spark.sql.shuffle.partitions", "8")
         .config("spark.sql.adaptive.enabled", "true").getOrCreate())
spark.sparkContext.setLogLevel("WARN")

FEATURES_PATH = "hdfs://namenode:9000/data/processed/customer_features"
SEGMENTS_PATH = "hdfs://namenode:9000/data/processed/customer_segments"
BEST_PATH = "hdfs://namenode:9000/data/processed/customer_segments_best"

FEATS = ["view_count", "cart_count", "remove_count", "purchase_count",
         "total_spend", "session_count", "days_since_last_event"]
OUTPUT_COLS = ["user_id", "total_events", *FEATS[:3], "purchase_count", "total_spend",
               "session_count", "days_since_last_event", "cluster"]
OUTPUT_COLS = ["user_id", "total_events", "view_count", "cart_count", "remove_count",
               "purchase_count", "total_spend", "session_count", "days_since_last_event", "cluster"]
K, SEEDS, MAX_ITER, TOL = 4, [42, 1, 2, 3, 4, 5], 100, 1e-6

df = spark.read.parquet(FEATURES_PATH)
for c in FEATS:
    df = df.withColumn(f"{c}_log", F.log1p(F.greatest(F.col(c).cast("double"), F.lit(0.0))))
vec = VectorAssembler(inputCols=[f"{c}_log" for c in FEATS], outputCol="features_raw",
                      handleInvalid="skip").transform(df)
data = (StandardScaler(inputCol="features_raw", outputCol="features", withMean=True, withStd=True)
        .fit(vec).transform(vec).cache())
print("Pelanggan:", f"{data.count():,}")

best = None
for s in SEEDS:
    m = KMeans(k=K, seed=s, featuresCol="features", predictionCol="cluster",
               maxIter=MAX_ITER, tol=TOL).fit(data)
    cost = float(m.summary.trainingCost)
    print(f"seed={s} | WSSSE={cost:,.1f} | iterasi={m.summary.numIter}")
    if best is None or cost < best[0]:
        best = (cost, s, m)

cost, seed, model = best
print(f"\nTERBAIK: seed={seed}, WSSSE={cost:,.1f}")
result = model.transform(data).select(*OUTPUT_COLS).cache()
result.write.mode("overwrite").parquet(BEST_PATH)

# bandingkan dengan hasil dashboard
saved = spark.read.parquet(SEGMENTS_PATH).select("user_id", F.col("cluster").alias("c_saved"))
cmp = result.join(saved, "user_id")

ct = cmp.groupBy("cluster", "c_saved").count().toPandas()
comb = lambda x: x * (x - 1) / 2
n = ct["count"].sum()
s_ij = sum(comb(x) for x in ct["count"])
s_a = sum(comb(x) for x in ct.groupby("cluster")["count"].sum())
s_b = sum(comb(x) for x in ct.groupby("c_saved")["count"].sum())
exp = s_a * s_b / comb(n)
print(f"\nARI model terbaik vs model dashboard: {(s_ij - exp) / ((s_a + s_b) / 2 - exp):.4f}")


def profil(d, col):
    return (d.groupBy(col).agg(
        F.count("*").alias("customers"),
        F.round(F.avg("purchase_count"), 2).alias("avg_purchases"),
        F.round(F.avg("total_spend"), 2).alias("avg_spend"),
        F.round(F.avg("view_count"), 2).alias("avg_views"),
        F.round(F.avg("cart_count"), 2).alias("avg_carts"),
        F.round(F.avg("days_since_last_event"), 1).alias("avg_recency"),
    ).orderBy(col).toPandas().to_string(index=False))


print("\n=== PROFIL MODEL TERBAIK ===");   print(profil(cmp, "cluster"))
print("\n=== PROFIL MODEL DASHBOARD ==="); print(profil(cmp, "c_saved"))
spark.stop()