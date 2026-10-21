from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("TestHDFS").getOrCreate()

path = spark._jvm.org.apache.hadoop.fs.Path("hdfs://namenode:9000/data/raw")
fs = path.getFileSystem(spark._jsc.hadoopConfiguration())

for f in fs.listStatus(path):
    print(f.getPath().getName(), f.getLen())

spark.stop()
