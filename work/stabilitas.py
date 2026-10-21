import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans

spark = (SparkSession.builder.appName("stabilitas")
         .config("spark.sql.shuffle.partitions", "8").getOrCreate())
spark.sparkContext.setLogLevel("WARN")

FEATURES_PATH = "hdfs://namenode:9000/data/processed/customer_features"
FEATS = ["view_count", "cart_count", "remove_count", "purchase_count",
         "total_spend", "session_count", "days_since_last_event"]
K = 4
SEEDS = [42, 1, 2, 3, 4, 5]
SETTINGS = {
    "longgar (maxIter=20, tol=0.01)": (20, 0.01),
    "ketat (maxIter=100, tol=1e-6)": (100, 1e-6),
}

raw = spark.read.parquet(FEATURES_PATH).select("user_id", *FEATS)
for c in FEATS:
    raw = raw.withColumn(f"log_{c}", F.log1p(F.greatest(F.col(c).cast("double"), F.lit(0.0))))
vec = VectorAssembler(inputCols=[f"log_{c}" for c in FEATS], outputCol="raw_vec",
                      handleInvalid="skip").transform(raw)
data = (StandardScaler(inputCol="raw_vec", outputCol="features", withMean=True, withStd=True)
        .fit(vec).transform(vec).select("user_id", *FEATS, "features")
        .sample(False, 0.2, seed=7).cache())
print("Pelanggan (sample 20%):", f"{data.count():,}")


def ari(df, a, b):
    ct = df.groupBy(a, b).count().toPandas()
    comb = lambda x: x * (x - 1) / 2
    n = ct["count"].sum()
    s_ij = sum(comb(x) for x in ct["count"])
    s_a = sum(comb(x) for x in ct.groupby(a)["count"].sum())
    s_b = sum(comb(x) for x in ct.groupby(b)["count"].sum())
    exp = s_a * s_b / comb(n)
    return float((s_ij - exp) / ((s_a + s_b) / 2 - exp))


for name, (mi, tol) in SETTINGS.items():
    res, wss, iters = data, {}, {}
    for s in SEEDS:
        m = KMeans(k=K, seed=s, featuresCol="features", predictionCol=f"c{s}",
                   maxIter=mi, tol=tol).fit(data)
        wss[s] = round(float(m.summary.trainingCost), 1)
        iters[s] = int(m.summary.numIter)
        res = m.transform(res)
    res = res.drop("features").cache()
    res.count()
    aris = [ari(res, "c42", f"c{s}") for s in SEEDS[1:]]
    print(f"\n=== {name} ===")
    print("WSSSE per seed   :", wss)
    print("Iterasi per seed :", iters)
    print("ARI vs seed 42   :", [round(a, 3) for a in aris])
    print(f"ARI rata-rata {sum(aris)/len(aris):.3f} | minimum {min(aris):.3f}")
    res.unpersist()

spark.stop()