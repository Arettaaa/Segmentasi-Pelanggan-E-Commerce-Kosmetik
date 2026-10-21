COPY (
    SELECT
        cluster,
        COUNT(*) AS customers,
        COUNT(*) FILTER (
            WHERE purchase_count > 0
        ) AS buyers,
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
        PERCENTILE_CONT(0.5)
            WITHIN GROUP (ORDER BY view_count) AS med_views,
        PERCENTILE_CONT(0.5)
            WITHIN GROUP (ORDER BY cart_count) AS med_carts,
        PERCENTILE_CONT(0.5)
            WITHIN GROUP (ORDER BY purchase_count) AS med_purchases,
        PERCENTILE_CONT(0.5)
            WITHIN GROUP (ORDER BY total_spend) AS med_spend,
        PERCENTILE_CONT(0.5)
            WITHIN GROUP (
                ORDER BY days_since_last_event
            ) AS med_recency_days
    FROM customer_segments
    GROUP BY cluster
    ORDER BY cluster
) TO '/tmp/profile.csv'
WITH (FORMAT CSV, HEADER);

COPY (
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
                PARTITION BY cluster
                ORDER BY random()
            ) AS rn
        FROM customer_segments
    ) t
    WHERE rn <= 5000
) TO '/tmp/sample.csv'
WITH (FORMAT CSV, HEADER);