WITH companies_posting_volume AS (
	SELECT company, country, COUNT(title) AS posting_volume
	FROM {{ ref('int_jobs_enriched') }}
	GROUP BY company, country
)

SELECT company, country, posting_volume,
	DENSE_RANK() OVER(PARTITION BY country ORDER BY posting_volume DESC) AS ranking_within_country
FROM companies_posting_volume
