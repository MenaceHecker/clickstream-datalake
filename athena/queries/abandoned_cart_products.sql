-- Top products added to cart but never purchased in the same session.

WITH cart_adds AS (
    SELECT DISTINCT session_id, product_id
    FROM clickstream_curated.curated
    WHERE event_type = 'add_to_cart' AND product_id IS NOT NULL
),
purchases AS (
    SELECT DISTINCT session_id, product_id
    FROM clickstream_curated.curated
    WHERE event_type = 'purchase' AND product_id IS NOT NULL
)
SELECT
    c.product_id,
    COUNT(*) AS abandoned_count
FROM cart_adds c
LEFT JOIN purchases p
    ON c.session_id = p.session_id AND c.product_id = p.product_id
WHERE p.session_id IS NULL
GROUP BY c.product_id
ORDER BY abandoned_count DESC
LIMIT 20;