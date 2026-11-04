"""Penamaan segmen berbasis data, dipakai bersama oleh analisis_lanjutan.py dan
analisis_marketing.py agar nama segmen selalu konsisten untuk K berapa pun.

Aturan:
1. Cluster dengan tingkat pembelian >= 50% disebut kelompok pembeli,
   diurutkan dari rata-rata pendapatan terbesar.
2. Cluster lainnya disebut kelompok pengunjung,
   diurutkan dari rata-rata aktivitas keranjang terbesar.
"""
from pyspark.sql import functions as F

NAMA_PEMBELI = {
    1: ["Pembeli"],
    2: ["Pembeli Bernilai Tinggi", "Pembeli Menengah"],
    3: ["Pembeli Bernilai Tinggi", "Pembeli Menengah", "Pembeli Rendah"],
}
NAMA_PENGUNJUNG = {
    1: ["Pengunjung"],
    2: ["Pengunjung Aktif", "Pengunjung Kasual"],
    3: ["Pengunjung Aktif", "Pengunjung Kasual", "Pengunjung Pasif"],
}


def _urut(nama_map, n, awalan):
    return nama_map.get(n, [f"{awalan} {i + 1}" for i in range(n)])


def beri_nama(seg):
    """seg: DataFrame Spark berisi kolom cluster, total_spend, cart_count, purchase_count.
    Mengembalikan dict {cluster: nama_segmen}."""
    kpi = seg.groupBy("cluster").agg(
        F.avg("total_spend").alias("avg_spend"),
        F.avg("cart_count").alias("avg_carts"),
        F.avg((F.col("purchase_count") > 0).cast("double")).alias("buyer_rate"),
    ).toPandas()
    pembeli = kpi[kpi.buyer_rate >= 0.5].sort_values("avg_spend", ascending=False)
    pengunjung = kpi[kpi.buyer_rate < 0.5].sort_values("avg_carts", ascending=False)
    peta = {}
    for df, nama_map, awalan in ((pembeli, NAMA_PEMBELI, "Pembeli"), (pengunjung, NAMA_PENGUNJUNG, "Pengunjung")):
        for c, nama in zip(df.cluster, _urut(nama_map, len(df), awalan)):
            peta[int(c)] = nama
    print("Peta segmen:", peta)
    print(kpi.assign(segmen=kpi.cluster.map(peta)).round(3).to_string(index=False))
    return peta
