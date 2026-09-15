-- Revenue broken down by country and device type, purchases only.

SELECT
    country,
    device_type,
    COUNT(*) AS purchase_count,
    ROUND(SUM(price), 2) AS total_revenue,
    ROUND(AVG(price), 2) AS avg_order_value
FROM clickstream_curated.curated
WHERE event_type = 'purchase'
GROUP BY country, device_type
ORDER BY total_revenue DESC;