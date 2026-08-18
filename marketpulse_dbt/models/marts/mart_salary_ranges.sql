-- CTE 1: total postings per country and seniority (unfiltered)
WITH total_postings AS (
	SELECT country, seniority_level, COUNT(title) AS total_count
	FROM {{ ref('int_jobs_enriched') }}
	GROUP BY country, seniority_level
),
-- CTE 2: postings with salary data per country and seniority (filtered)
salary_postings AS (
	SELECT 
        country,
        seniority_level,
        ROUND(AVG(salary_mid), 2) AS average,
        MIN(salary_mid) AS salary_min,
        MAX(salary_mid) AS salary_max,
        COUNT(salary_mid) AS salary_count
	FROM {{ ref('int_jobs_enriched') }}
	WHERE salary_mid IS NOT NULL 
	GROUP BY country, seniority_level
)
-- Final SELECT: join both, coverage as salary_count / total_count
SELECT 
	t.country,
	t.seniority_level,
	s.average, s.salary_min, s.salary_max, s.salary_count,
	t.total_count,
	ROUND(salary_count * 100.0 / total_count, 1) AS coverage_pct 
FROM total_postings t
JOIN salary_postings s ON t.country = s.country AND t.seniority_level = s.seniority_level
	