SELECT external_id, title, company, location, country, description, category, created_at,
    CASE 
        WHEN LOWER(title) LIKE '%senior%' OR LOWER(title) LIKE '%lead%' THEN 'Senior'
        WHEN LOWER(title) LIKE '%junior%' THEN 'Junior'
        WHEN LOWER(title) LIKE '%alternant%' THEN 'Alternant'
        WHEN LOWER(title) LIKE '%stagiaire%' OR LOWER(title) LIKE '%stage%' THEN 'Intern'
        ELSE 'Mid'
    END AS seniority_level,
    CASE
        WHEN salary_min IS NOT NULL AND salary_max IS NOT NULL
        THEN ROUND ((salary_min + salary_max) /2, 2)
        ELSE NULL
    END AS salary_mid
FROM {{ ref('stg_jobs') }}