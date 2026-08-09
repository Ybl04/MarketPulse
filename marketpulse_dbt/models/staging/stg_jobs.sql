SELECT
    external_id,
    TRIM(title)                           AS title,
    TRIM(COALESCE(company, 'Unknown'))    AS company,
    TRIM(COALESCE(location , 'Unknown'))  AS location,
    UPPER(country)                        AS country,
    salary_min::numeric                   AS salary_min,
    salary_max::numeric                   AS salary_max,
    TRIM(description)                     AS description,
    TRIM(COALESCE(category, 'Unknown'))   AS category,
    created_at
FROM {{source('marketpulse', 'jobs')}}
WHERE external_id IS NOT NULL
