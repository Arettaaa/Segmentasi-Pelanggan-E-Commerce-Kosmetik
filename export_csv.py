
from pathlib import Path

import pandas as pd
import psycopg2

# Koneksi ke PostgreSQL Docker melalui port laptop
PG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "segmentasi",
    "user": "bigdata",
    "password": "bigdata",
}

# Folder tujuan CSV untuk dashboard online
OUT = Path("dashboard/data")
OUT.mkdir(parents=True, exist_ok=True)

# Ringkasan profil setiap cluster dari hasil K-Means Docker
PROFILE_SQL = """
SELECT
    cluster,
    COUNT(*) AS customers,
    COUNT(*) FILTER (WHERE purchase_count > 0) AS buyers,
    AVG(view_count) AS avg_views,
    AVG(cart_count) AS avg_carts,
    AVG(remove_count) AS avg_removes,
    AVG(purchase_count) AS avg_purchases,
    AVG(session_count) AS avg_sessions,
    AVG(total_spend) AS avg_spend,
    AVG(days_since_last_event) AS avg_recency_days,
    SUM(view_count) AS sum_views,
    SUM(cart_count) AS sum_carts,
    SUM(purchase_count) AS sum_purchases,
    SUM(total_spend) AS sum_spend,
    PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY view_count) AS med_views,
    PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY cart_count) AS med_carts,
    PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY purchase_count) AS med_purchases,
    PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY total_spend) AS med_spend,
    PERCENTILE_CONT(0.5) WITHIN GROUP
        (ORDER BY days_since_last_event) AS med_recency_days
FROM customer_segments
GROUP BY cluster
ORDER BY cluster;
"""

# Maksimal 5.000 pelanggan per cluster untuk dashboard
SAMPLE_SQL = """
SELECT
    user_id,
    cluster,
    view_count,
    cart_count,
    remove_count,
    purchase_count,
    session_count,
    total_spend,
    days_since_last_event
FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY cluster ORDER BY random()
           ) AS rn
    FROM customer_segments
) t
WHERE rn <= 5000;
"""

def main():
    print("Menghubungkan ke PostgreSQL...")

    with psycopg2.connect(**PG) as conn:
        print("Mengekspor profil cluster...")
        pd.read_sql_query(PROFILE_SQL, conn).to_csv(
            OUT / "profile.csv", index=False
        )

        print("Mengekspor sampel pelanggan...")
        pd.read_sql_query(SAMPLE_SQL, conn).to_csv(
            OUT / "sample.csv", index=False
        )

        # Coba ekspor metrik pemilihan K jika tabel tersedia
        try:
            pd.read_sql_query(
                "SELECT * FROM k_selection ORDER BY k", conn
            ).to_csv(OUT / "k_selection.csv", index=False)
            print("Metrik K berhasil diekspor.")
        except Exception as e:
            print("Tabel k_selection tidak tersedia:", e)
            print(
                "File k_selection.csv belum dibuat. "
                "Kita bisa menambahkannya setelah memeriksa sumber metrik K."
            )

    print("\nEkspor selesai.")
    print("Lokasi file:", OUT.resolve())
    print("File yang diharapkan: profile.csv dan sample.csv")

if __name__ == "__main__":
    main()
