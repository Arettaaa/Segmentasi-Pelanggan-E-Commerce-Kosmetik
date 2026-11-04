import time
import pandas as pd
from pyspark.sql import SparkSession, functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans

spark = (SparkSession.builder.appName("benchmark")
         .config("spark.sql.shuffle.partitions", "8")
         .config("spark.sql.adaptive.enabled", "true").getOrCreate())
spark.sparkContext.setLogLevel("WARN")

RAW = "hdfs://namenode:9000/data/raw/*.csv"
BENCH = "hdfs://namenode:9000/data/processed/bench_events"
BENCH_F = "hdfs://namenode:9000/data/processed/bench_features"
JDBC = "jdbc:postgresql://postgres:5432/segmentasi"
PROPS = {"user": "bigdata", "password": "bigdata", "driver": "org.postgresql.Driver"}
# 6 fitur perilaku & belanja (sama dengan notebook Colab). Recency TIDAK masuk K-Means;
# dipakai terpisah untuk profil dan analisis risiko tidak aktif.
FEATS = ["view_count", "cart_count", "remove_count", "purchase_count",
         "session_count", "total_spend"]

sc = spark.sparkContext
log = []


def t(nama, fn):
    s = time.perf_counter()
    out = fn()
    d = time.perf_counter() - s
    print(f"{nama:38s} {d:8.1f} detik")
    log.append((nama, round(d, 1)))
    return out


# 1. baca + bersihkan CSV dari HDFS
def step1():
    df = (spark.read.option("header", "true").csv(RAW)
          .withColumn("event_time", F.to_timestamp(
              F.regexp_replace("event_time", " UTC$", ""), "yyyy-MM-dd HH:mm:ss"))
          .withColumn("price", F.col("price").cast("double"))
          .withColumn("user_id", F.col("user_id").cast("long"))
          .filter(F.col("user_id").isNotNull() & F.col("event_time").isNotNull()
                  & F.col("event_type").isin("view", "cart", "remove_from_cart", "purchase")))
    df.write.mode("overwrite").parquet(BENCH)
    return spark.read.parquet(BENCH)


ev = t("1. Baca CSV HDFS + cleaning -> Parquet", step1)
n_event = t("2. Hitung jumlah event", lambda: ev.count())


# 3. agregasi fitur
def step3():
    mx = ev.agg(F.max("event_time")).first()[0]
    f = (ev.groupBy("user_id").agg(
        F.count("*").alias("total_events"),
        F.sum((F.col("event_type") == "view").cast("int")).alias("view_count"),
        F.sum((F.col("event_type") == "cart").cast("int")).alias("cart_count"),
        F.sum((F.col("event_type") == "remove_from_cart").cast("int")).alias("remove_count"),
        F.sum((F.col("event_type") == "purchase").cast("int")).alias("purchase_count"),
        F.sum(F.when(F.col("event_type") == "purchase",
                     F.coalesce(F.col("price"), F.lit(0.0))).otherwise(0.0)).alias("total_spend"),
        F.countDistinct("user_session").alias("session_count"),
        F.max("event_time").alias("last_event_time"),
    ).withColumn("days_since_last_event",
                 F.datediff(F.lit(mx).cast("date"), F.col("last_event_time").cast("date"))))
    f.write.mode("overwrite").parquet(BENCH_F)
    return spark.read.parquet(BENCH_F)


feat = t("3. Agregasi fitur per user_id", step3)
n_cust = t("4. Hitung jumlah pelanggan", lambda: feat.count())


def step5():
    d = feat
    for c in FEATS:
        d = d.withColumn(f"{c}_log", F.log1p(F.greatest(F.col(c).cast("double"), F.lit(0.0))))
    v = VectorAssembler(inputCols=[f"{c}_log" for c in FEATS], outputCol="fr",
                        handleInvalid="skip").transform(d)
    out = (StandardScaler(inputCol="fr", outputCol="features", withMean=True, withStd=True)
           .fit(v).transform(v).select("user_id", *FEATS, "features").cache())
    out.count()
    return out


data = t("5. Transformasi log1p + StandardScaler", step5)
model = t("6. Training K-Means (K=4)",
          lambda: KMeans(k=3, seed=42, featuresCol="features", predictionCol="cluster",
                         maxIter=50, tol=1e-4).fit(data))


def step7():
    r = model.transform(data).select("user_id", *FEATS, "cluster")
    r.write.mode("overwrite").jdbc(JDBC, "bench_segments", mode="overwrite", properties=PROPS)


t("7. Tulis hasil ke PostgreSQL", step7)

def step8():
    jvm = spark._jvm
    p = jvm.org.apache.hadoop.fs.Path("hdfs://namenode:9000/data/raw")
    fs = p.getFileSystem(spark._jsc.hadoopConfiguration())
    return fs.getContentSummary(p).getLength()


size = t("8. Ukur ukuran data di HDFS", step8)

conf = sc.getConf()
spek = [
    ("Spark version", sc.version),
    ("Mode", conf.get("spark.master", "local[*]")),
    ("Driver memory", conf.get("spark.driver.memory", "default")),
    ("Default parallelism", str(sc.defaultParallelism)),
    ("Shuffle partitions", conf.get("spark.sql.shuffle.partitions")),
    ("Adaptive execution", conf.get("spark.sql.adaptive.enabled", "false")),
    ("HDFS replication", "1"),
    ("Ukuran data mentah (HDFS)", f"{size / 1024**3:.2f} GB"),
    ("Jumlah file CSV", "5"),
    ("Jumlah event", f"{n_event:,}"),
    ("Jumlah pelanggan", f"{n_cust:,}"),
]

bench = pd.DataFrame(log, columns=["tahap", "detik"])
bench["persen"] = (bench["detik"] / bench["detik"].sum() * 100).round(1)
info = pd.DataFrame(spek, columns=["parameter", "nilai"])

print("\n=== BENCHMARK PIPELINE ===")
print(bench.to_string(index=False))
print(f"\nTotal: {bench['detik'].sum():.1f} detik "
      f"({bench['detik'].sum() / 60:.1f} menit)")
print(f"Throughput: {n_event / bench['detik'].sum():,.0f} event/detik")
print("\n=== SPESIFIKASI LINGKUNGAN ===")
print(info.to_string(index=False))

spark.createDataFrame(bench).write.jdbc(JDBC, "pipeline_benchmark", mode="overwrite", properties=PROPS)
spark.createDataFrame(info).write.jdbc(JDBC, "pipeline_spec", mode="overwrite", properties=PROPS)
print("\nSELESAI. Tabel: pipeline_benchmark, pipeline_spec")
spark.stop()