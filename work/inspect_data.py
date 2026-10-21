from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("InspectEcommerceData") \
    .config("spark.sql.shuffle.partitions", "8") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

path = "hdfs://namenode:9000/data/raw/*.csv"

df = spark.read \
    .option("header", "true") \
    .option("inferSchema", "false") \
    .csv(path)

print("\n=== KOLOM DATA ===")
print(df.columns)

print("\n=== STRUKTUR DATA ===")
df.printSchema()

print("\n=== CONTOH 5 BARIS ===")
df.show(5, truncate=False)

print("\n=== JUMLAH KOLOM ===")
print(len(df.columns))

spark.stop()
