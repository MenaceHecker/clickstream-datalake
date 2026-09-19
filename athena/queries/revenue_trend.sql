SELECT
    year,
    month,
    day,
    COUNT(*) AS purchase_count,
    ROUND(SUM(price), 2) AS daily_revenue
FROM clickstream_curated.curated
WHERE event_type = 'purchase'
GROUP BY year, month, day
ORDER BY year, month, day;