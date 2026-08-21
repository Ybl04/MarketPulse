# MarketPulse — dbt Transformation Layer

This folder contains the dbt project for the MarketPulse transformation layer.  
For full project context and architecture, see the [main README](../README.md).

---

## Prerequisites

- dbt-postgres installed: `pip install dbt-postgres`
- PostgreSQL running with MarketPulse data ingested (V2 Airflow DAG must have run at least once)
- `profiles.yml` configured to point to your local PostgreSQL instance

---

## Running the dbt Layer

```bash
# Run all models
dbt run

# Run a specific model
dbt run -s stg_jobs

# Run all tests
dbt test

# Generate and serve documentation
dbt docs generate
dbt docs serve
```

---

## Layer Structure

| Layer        | Model                  | Materialization | What it does                                              |
|--------------|------------------------|-----------------|-----------------------------------------------------------|
| Staging      | `stg_jobs`             | View            | Cleans and types raw data. Schema evolution firewall.     |
| Intermediate | `int_jobs_enriched`    | View            | Derives `seniority_level` and `salary_mid`.               |
| Marts        | `mart_top_companies`   | Table           | Hiring volume by company and country.                     |
| Marts        | `mart_salary_ranges`   | Table           | Compensation ranges by country and seniority.             |
| Marts        | `mart_skills_demand`   | Table           | Skill keyword mentions with coverage metrics.             |

---

## Tests

28 generic tests across all 5 models. Run `dbt test` to verify.  
See individual `schema.yml` files in each layer folder for full test coverage details.

---

## Data Quality

See the Data Quality Findings section in the [main README](../README.md) for documented limitations of `mart_skills_demand`.