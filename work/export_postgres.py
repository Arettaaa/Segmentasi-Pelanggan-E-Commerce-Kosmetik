
from pyspark.sql import SparkSession, functions as F

spark = (
    SparkSession.builder
    .appName("ExportSegmentsToPostgres")
    .config("spark.sql.shuffle.partitions", "8")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

SOURCE = "hdfs://namenode:9000/data/processed/customer_segments_best"

JDBC_URL = "jdbc:postgresql://postgres:5432/segmentasi"
CONNECTION = {
    "user": "bigdata",
    "password": "bigdata",
    "driver": "org.postgresql.Driver"
}

df = spark.read.parquet(SOURCE)

# Simpan detail segmentasi pelanggan
(
    df.write
    .mode("overwrite")
    .option("batchsize", "5000")
    .jdbc(
        JDBC_URL,
        "customer_segments",
        mode="overwrite",
        properties=CONNECTION
    )
)

# Buat ringkasan profil cluster di Spark
profile = (
    df.groupBy("cluster")
    .agg(
        F.count("*").alias("customers"),
        F.avg("purchase_count").alias("avg_purchases"),
        F.avg("total_spend").alias("avg_spend"),
        F.avg("view_count").alias("avg_views"),
        F.avg("cart_count").alias("avg_carts"),
        F.avg("days_since_last_event").alias("avg_recency_days")
    )
)

(
    profile.write
    .mode("overwrite")
    .jdbc(
        JDBC_URL,
        "cluster_profile",
        mode="overwrite",
        properties=CONNECTION
    )
)

print("Ekspor selesai.")
print("Tabel: customer_segments dan cluster_profile")

spark.stop()
