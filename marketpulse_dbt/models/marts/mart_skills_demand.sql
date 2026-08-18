WITH skills_list AS (
	SELECT skill FROM (VALUES 
		('python'), ('sql'), ('etl'), ('elt'), ('airflow'), ('dbt'), ('spark'), ('kafka'), ('azure'), ('aws'),
		('gcp'), ('postgresql'), ('snowflake'), ('databricks'), ('docker'), ('kubernetes'), ('power bi'),
		('tableau'), ('data pipeline'), ('data modeling'), ('data warehouse'), ('data lake'), ('data lakehouse'),
		('data quality'), ('data governance'), ('data integration'), ('batch processing'), ('scalability'),
		('monitoring'), ('observability'), ('data lineage')
		) 
	AS skills(skill)
),
total_postings AS (
	SELECT country, seniority_level, COUNT(title) AS total_count
	FROM {{ ref('int_jobs_enriched') }}
	GROUP BY country, seniority_level
)

SELECT
    l.skill,
    t.country,
	j.seniority_level,
    COUNT(*) FILTER (WHERE j.description ILIKE '%' || l.skill || '%') AS mention_count,
    t.total_count,
	ROUND(COUNT(*) FILTER (WHERE j.description ILIKE '%' || l.skill || '%') * 100.0 / t.total_count, 1) AS coverage_pct
FROM skills_list l
CROSS JOIN {{ ref('int_jobs_enriched') }} j
JOIN total_postings t ON j.country = t.country AND j.seniority_level = t.seniority_level
GROUP BY l.skill, t.country, j.seniority_level, t.total_count
