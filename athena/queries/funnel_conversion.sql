-- Funnel conversion rate (product_view -> add_to_cart -> purchase),
-- broken down by product category.
--
-- Uses COUNT(DISTINCT session_id) rather than COUNT(*) so a session that
-- views the same category's products multiple times doesn't inflate the
-- funnel counts.

WITH funnel AS (
    SELECT
        category,
        COUNT(DISTINCT CASE WHEN event_type = 'product_view' THEN session_id END) AS viewed_sessions,
        COUNT(DISTINCT CASE WHEN event_type = 'add_to_cart' THEN session_id END) AS added_to_cart_sessions,
        COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN session_id END) AS purchased_sessions
    FROM clickstream_curated.curated
    WHERE category IS NOT NULL
    GROUP BY category
)
SELECT
    category,
    viewed_sessions,
    added_to_cart_sessions,
    purchased_sessions,
    ROUND(100.0 * added_to_cart_sessions / NULLIF(viewed_sessions, 0), 2) AS view_to_cart_pct,
    ROUND(100.0 * purchased_sessions / NULLIF(added_to_cart_sessions, 0), 2) AS cart_to_purchase_pct,
    ROUND(100.0 * purchased_sessions / NULLIF(viewed_sessions, 0), 2) AS view_to_purchase_pct
FROM funnel
ORDER BY viewed_sessions DESC;