
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = (
    SparkSession.builder
    .appName("EcommerceCustomerSegmentation")
    .config("spark.sql.shuffle.partitions", "8")
    .config("spark.sql.adaptive.enabled", "true")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

RAW_PATH = "hdfs://namenode:9000/data/raw/*.csv"
EVENTS_PATH = "hdfs://namenode:9000/data/processed/events_parquet"
FEATURES_PATH = "hdfs://namenode:9000/data/processed/customer_features"

# 1. Baca kelima file CSV dari HDFS
df = (
    spark.read
    .option("header", "true")
    .option("inferSchema", "false")
    .csv(RAW_PATH)
)

# 2. Bersihkan dan ubah tipe data
df = (
    df.withColumn(
        "event_time",
        F.to_timestamp(
            F.regexp_replace("event_time", " UTC$", ""),
            "yyyy-MM-dd HH:mm:ss"
        )
    )
    .withColumn("price", F.col("price").cast("double"))
    .withColumn("user_id", F.col("user_id").cast("long"))
    .withColumn("product_id", F.col("product_id").cast("long"))
    .filter(
        F.col("user_id").isNotNull()
        & F.col("event_time").isNotNull()
        & F.col("event_type").isin(
            "view", "cart", "remove_from_cart", "purchase"
        )
    )
)

# 3. Simpan data bersih dalam format Parquet
(
    df.write
    .mode("overwrite")
    .parquet(EVENTS_PATH)
)

print("Data bersih berhasil disimpan ke HDFS.")

# 4. Buat fitur perilaku setiap pelanggan
events = spark.read.parquet(EVENTS_PATH)

features = (
    events.groupBy("user_id")
    .agg(
        F.count("*").alias("total_events"),
        F.sum(
            F.when(F.col("event_type") == "view", 1).otherwise(0)
        ).alias("view_count"),
        F.sum(
            F.when(F.col("event_type") == "cart", 1).otherwise(0)
        ).alias("cart_count"),
        F.sum(
            F.when(F.col("event_type") == "remove_from_cart", 1)
             .otherwise(0)
        ).alias("remove_count"),
        F.sum(
            F.when(F.col("event_type") == "purchase", 1).otherwise(0)
        ).alias("purchase_count"),
        F.sum(
            F.when(
                F.col("event_type") == "purchase",
                F.coalesce(F.col("price"), F.lit(0.0))
            ).otherwise(0.0)
        ).alias("total_spend"),
        F.countDistinct("user_session").alias("session_count"),
        F.max("event_time").alias("last_event_time")
    )
)

# 5. Hitung recency berdasarkan waktu event terakhir di dataset
max_time = events.agg(
    F.max("event_time").alias("max_time")
).first()["max_time"]

features = (
    features
    .withColumn(
        "days_since_last_event",
        F.datediff(
            F.lit(max_time).cast("date"),
            F.col("last_event_time").cast("date")
        )
    )
    .fillna(0, subset=[
        "total_events", "view_count", "cart_count",
        "remove_count", "purchase_count", "total_spend",
        "session_count", "days_since_last_event"
    ])
)

# 6. Simpan fitur pelanggan di HDFS
(
    features.write
    .mode("overwrite")
    .parquet(FEATURES_PATH)
)

print("Fitur pelanggan berhasil disimpan:", FEATURES_PATH)
print("Contoh fitur pelanggan:")
features.show(10, truncate=False)

spark.stop()
