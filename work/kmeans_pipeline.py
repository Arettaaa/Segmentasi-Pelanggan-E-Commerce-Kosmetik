
from pyspark.sql import SparkSession, functions as F
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.ml.clustering import KMeans
from pyspark.ml import Pipeline

spark = (
    SparkSession.builder
    .appName("EcommerceKMeans")
    .config("spark.sql.shuffle.partitions", "8")
    .config("spark.sql.adaptive.enabled", "true")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

FEATURES_PATH = "hdfs://namenode:9000/data/processed/customer_features"
RESULT_PATH = "hdfs://namenode:9000/data/processed/customer_segments"

# Fitur yang digunakan untuk mengelompokkan pelanggan
feature_cols = [
    "view_count",
    "cart_count",
    "remove_count",
    "purchase_count",
    "total_spend",
    "session_count",
    "days_since_last_event"
]

df = spark.read.parquet(FEATURES_PATH)

# Mengurangi kemencengan distribusi fitur
for c in feature_cols:
    df = df.withColumn(
        c + "_log",
        F.log1p(F.greatest(F.col(c).cast("double"), F.lit(0.0)))
    )

log_cols = [c + "_log" for c in feature_cols]

assembler = VectorAssembler(
    inputCols=log_cols,
    outputCol="features_raw",
    handleInvalid="skip"
)

scaler = StandardScaler(
    inputCol="features_raw",
    outputCol="features",
    withMean=True,
    withStd=True
)

kmeans = KMeans(
    k=4,
    seed=42,
    featuresCol="features",
    predictionCol="cluster",
    maxIter=20,
    tol=0.01
)

pipeline = Pipeline(stages=[assembler, scaler, kmeans])
model = pipeline.fit(df)
result = model.transform(df)

# Simpan hasil segmentasi tanpa kolom vector agar mudah digunakan
output_cols = [
    "user_id", "total_events", "view_count", "cart_count",
    "remove_count", "purchase_count", "total_spend",
    "session_count", "days_since_last_event", "cluster"
]

(
    result.select(*output_cols)
    .write
    .mode("overwrite")
    .parquet(RESULT_PATH)
)

print("\n=== JUMLAH PELANGGAN PER CLUSTER ===")
result.groupBy("cluster").count().orderBy("cluster").show()

print("\n=== PROFIL RATA-RATA CLUSTER ===")
result.groupBy("cluster").agg(
    F.count("*").alias("customers"),
    F.avg("purchase_count").alias("avg_purchases"),
    F.avg("total_spend").alias("avg_spend"),
    F.avg("view_count").alias("avg_views"),
    F.avg("cart_count").alias("avg_carts"),
    F.avg("days_since_last_event").alias("avg_recency_days")
).orderBy("cluster").show(truncate=False)

print("K-Means selesai. Hasil disimpan ke:", RESULT_PATH)

spark.stop()
