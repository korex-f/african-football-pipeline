# 1. Cloud platforms are not in scope at this time

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** The project removed the planned phases for S3, Snowflake, and Databricks.
- **Why:** The main source stopped working. The larger problem was that the pipeline used only one source. Cloud platforms add cost and complexity, but they do not make bad data better. Thus, the project first makes a reliable local pipeline.
- **How:** The project removed all cloud references from this README and from the package description. The project will examine cloud platforms again when the multi-source pipeline is complete and verified.
