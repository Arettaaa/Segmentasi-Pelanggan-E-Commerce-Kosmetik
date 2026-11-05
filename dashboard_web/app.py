import logging
import os
import threading
import time
from datetime import datetime, timezone

import psycopg2
from flask import Flask, jsonify, render_template, request
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dashboard_web")

app = Flask(__name__)
app.json.sort_keys = False  # pertahankan urutan kolom dari PostgreSQL

# Kredensial dari environment (lihat docker-compose.yml), default hanya untuk lokal
PG = dict(
    host=os.getenv("PG_HOST", "postgres"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "segmentasi"),
    user=os.getenv("PG_USER", "bigdata"),
    password=os.getenv("PG_PASSWORD", "bigdata"),
)
CACHE_TTL = int(os.getenv("CACHE_TTL", "600"))          # detik; hasil analisis bersifat statis
DATA_PERIOD = os.getenv("DATA_PERIOD", "Okt 2019 – Feb 2020")
CURRENCY = os.getenv("CURRENCY", "USD")                   # satuan harga dataset Kaggle REES46

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
TABLES = {
    "econ": "SELECT * FROM segment_economics ORDER BY revenue_share DESC",
    "funnel": "SELECT * FROM funnel_customer",
    "funnel_seg": "SELECT * FROM funnel_segment",
    "brand": "SELECT * FROM top_brand_segment ORDER BY cluster, rank",
    "category": "SELECT * FROM top_category_segment ORDER BY cluster, rank",
    "product": "SELECT * FROM top_product_segment ORDER BY cluster, rank",
    "price": "SELECT * FROM price_range_segment",
    "hour": "SELECT * FROM activity_hour_segment ORDER BY jam",
    "day": "SELECT * FROM activity_day_segment ORDER BY dow",
    "churn": "SELECT * FROM churn_risk_segment",
    "sim": "SELECT * FROM conversion_simulation",
    "assume": "SELECT * FROM marketing_assumptions",
    "ksel": "SELECT * FROM k_selection ORDER BY k",
    "kcmp": "SELECT * FROM k_compare ORDER BY k",
    "val": "SELECT * FROM model_validation",
    "sil": "SELECT * FROM silhouette_detail",
    "stab": "SELECT * FROM cluster_stability",
    "seed": "SELECT * FROM seed_wssse ORDER BY seed",
    "corr": "SELECT * FROM feature_correlation",
    "sens": "SELECT * FROM feature_sensitivity",
    "purity": "SELECT * FROM cluster_purity ORDER BY cluster",
    "bench": "SELECT * FROM pipeline_benchmark",
    "spec": "SELECT * FROM pipeline_spec",
}

_cache = {"data": None, "ts": 0.0}
_lock = threading.Lock()


def connect():
    try:
        return psycopg2.connect(**PG, connect_timeout=5)
    except psycopg2.OperationalError:
        if PG["host"] == "localhost":
            raise
        log.warning("Gagal konek ke host %s, mencoba localhost", PG["host"])
        return psycopg2.connect(**{**PG, "host": "localhost"}, connect_timeout=5)


def fetch(cur, name, sql, missing, quiet=True):
    try:
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            for k, v in r.items():
                if hasattr(v, "is_finite"):  # Decimal -> float
                    r[k] = float(v)
        return rows
    except Exception as e:
        cur.connection.rollback()
        log.error("Query '%s' gagal: %s", name, str(e).strip())
        if not quiet:
            raise
        missing.append(name)
        return []


def build_payload():
    missing = []
    t0 = time.perf_counter()
    conn = connect()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            out = {k: fetch(cur, k, s, missing) for k, s in TABLES.items()}
            out["profile"] = fetch(cur, "profile", PROFILE_SQL, missing, quiet=False)
    finally:
        conn.close()

    if not out["econ"]:
        raise LookupError("Tabel segment_economics kosong. Jalankan analisis_lanjutan.py.")

    peta = {int(r["cluster"]): r["segmen"] for r in out["econ"]}
    for key in ("profile", "purity"):
        for r in out[key]:
            r["cluster"] = int(r["cluster"])
            r["segmen"] = peta.get(r["cluster"], f"Cluster {r['cluster']}")

    # pengaman: jumlah pengguna per cluster di customer_segments harus sama dengan segment_economics
    econ_n = {int(r["cluster"]): int(r["customers"]) for r in out["econ"]}
    prof_n = {r["cluster"]: int(r["customers"]) for r in out["profile"]}
    mismatch = sorted(c for c in set(econ_n) | set(prof_n) if econ_n.get(c) != prof_n.get(c))
    if mismatch:
        log.warning("customer_segments tidak sinkron dengan segment_economics (cluster %s)", mismatch)

    k_final = next((r["nilai"] for r in out["val"] if r["metrik"].startswith("K final")), None)
    out["meta"] = dict(
        period=DATA_PERIOD,
        currency=CURRENCY,
        k=int(k_final) if k_final else len(out["econ"]),
        order=[r["segmen"] for r in out["econ"]],
        updated_at=datetime.now(timezone.utc).isoformat(),
        cache_ttl=CACHE_TTL,
        query_ms=round((time.perf_counter() - t0) * 1000),
        missing=missing,
        mismatch=mismatch,
    )
    if missing:
        log.warning("Tabel belum tersedia: %s", ", ".join(missing))
    return out


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    force = request.args.get("refresh") == "1"
    with _lock:
        fresh = _cache["data"] is not None and time.time() - _cache["ts"] < CACHE_TTL
        if force or not fresh:
            try:
                _cache["data"] = build_payload()
                _cache["ts"] = time.time()
            except LookupError as e:
                return jsonify(error=str(e)), 500
            except psycopg2.OperationalError as e:
                log.error("Koneksi PostgreSQL gagal: %s", e)
                return jsonify(error=f"Tidak dapat terhubung ke PostgreSQL ({PG['host']}:{PG['port']})."), 503
            except Exception as e:
                log.exception("Gagal membangun data dashboard")
                return jsonify(error=f"Gagal memuat data: {e}"), 500
        return jsonify(_cache["data"])


@app.route("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8502)
