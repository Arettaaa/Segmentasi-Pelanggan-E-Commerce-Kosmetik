import os
from flask import Flask, jsonify, render_template
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
PG = dict(host=os.getenv("PG_HOST", "postgres"), port=int(os.getenv("PG_PORT", "5432")),
          dbname="segmentasi", user="bigdata", password="bigdata")

PROFILE_SQL = """
SELECT cluster, COUNT(*) AS customers,
       AVG(view_count) avg_views, AVG(cart_count) avg_carts, AVG(remove_count) avg_removes,
       AVG(purchase_count) avg_purchases, AVG(session_count) avg_sessions,
       AVG(total_spend) avg_spend, AVG(days_since_last_event) avg_recency,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY view_count) med_views,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cart_count) med_carts,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY purchase_count) med_purchases,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_spend) med_spend,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_since_last_event) med_recency
FROM customer_segments GROUP BY cluster ORDER BY cluster
"""
SAMPLE_SQL = """
SELECT cluster, view_count, cart_count, purchase_count, total_spend, days_since_last_event
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY cluster ORDER BY random()) rn
      FROM customer_segments) t WHERE rn <= 1500
"""
TABLES = {
    "econ": "SELECT * FROM segment_economics ORDER BY revenue_share DESC",
    "funnel": "SELECT * FROM funnel_customer",
    "funnel_seg": "SELECT * FROM funnel_segment",
    "brand": "SELECT * FROM top_brand_segment ORDER BY cluster, rank",
    "product": "SELECT * FROM top_product_segment ORDER BY cluster, rank",
    "price": "SELECT * FROM price_range_segment",
    "hour": "SELECT * FROM activity_hour_segment ORDER BY jam",
    "day": "SELECT * FROM activity_day_segment ORDER BY dow",
    "churn": "SELECT * FROM churn_risk_segment",
    "sim": "SELECT * FROM conversion_simulation",
    "assume": "SELECT * FROM marketing_assumptions",
    "ksel": "SELECT * FROM k_selection ORDER BY k",
    "val": "SELECT * FROM model_validation",
    "sil": "SELECT * FROM silhouette_detail",
    "stab": "SELECT * FROM cluster_stability",
    "seed": "SELECT * FROM seed_wssse ORDER BY seed",
    "corr": "SELECT * FROM feature_correlation",
    "sens": "SELECT * FROM feature_sensitivity",
    "bench": "SELECT * FROM pipeline_benchmark",
    "spec": "SELECT * FROM pipeline_spec",
}


def connect():
    try:
        return psycopg2.connect(**PG, connect_timeout=5)
    except psycopg2.OperationalError:
        return psycopg2.connect(**{**PG, "host": "localhost"}, connect_timeout=5)


def fetch(cur, sql, quiet=True):
    try:
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            for k, v in r.items():
                if hasattr(v, "is_finite"):
                    r[k] = float(v)
        return rows
    except Exception:
        cur.connection.rollback()
        if quiet:
            return []
        raise


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    try:
        conn = connect()
    except Exception as e:
        return jsonify(error=f"Tidak dapat terhubung ke PostgreSQL: {e}"), 503
    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        out = {k: fetch(cur, s) for k, s in TABLES.items()}
        out["profile"] = fetch(cur, PROFILE_SQL, quiet=False)
        out["sample"] = fetch(cur, SAMPLE_SQL)
    conn.close()

    if not out["econ"]:
        return jsonify(error="Tabel segment_economics kosong. Jalankan analisis_lanjutan.py."), 500

    peta = {int(r["cluster"]): r["segmen"] for r in out["econ"]}
    for key in ("profile", "sample"):
        for r in out[key]:
            r["cluster"] = int(r["cluster"])
            r["segmen"] = peta.get(r["cluster"], f"Cluster {r['cluster']}")

    total = sum(r["customers"] for r in out["econ"])
    out["kpi"] = dict(
        total=total,
        buyers=sum(r["buyers"] for r in out["econ"]),
        revenue=sum(r["segment_revenue"] for r in out["econ"]),
        k=len(out["econ"]),
        order=[r["segmen"] for r in out["econ"]],
    )
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8502)