-- Average session duration and average "pages" (page_view + product_view
-- events) per session, across all sessions in the curated dataset.

WITH session_stats AS (
    SELECT
        session_id,
        COUNT(CASE WHEN event_type IN ('page_view', 'product_view') THEN 1 END) AS page_like_events,
        MIN(from_iso8601_timestamp(timestamp)) AS session_start,
        MAX(from_iso8601_timestamp(timestamp)) AS session_end
    FROM clickstream_curated.curated
    GROUP BY session_id
)
SELECT
    COUNT(*) AS total_sessions,
    ROUND(AVG(date_diff('second', session_start, session_end)), 1) AS avg_session_duration_seconds,
    ROUND(AVG(page_like_events), 2) AS avg_pages_per_session
FROM session_stats;