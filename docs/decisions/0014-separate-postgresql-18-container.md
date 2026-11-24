# 14. The pipeline database is a separate PostgreSQL 18 container

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** A `pipeline-db` container (`postgres:18`) in the root `docker-compose.yaml`. The Airflow Compose file includes this file. The port is `127.0.0.1:5433`.
- **The debate:**
  1. **Use the Airflow metadata database** (`postgres` in `airflow/docker-compose.yaml`). There is no new container. But Airflow owns this database. An Airflow upgrade or reset can change it, and the pipeline data then depends on Airflow.
  2. **Define the database in the Airflow Compose file.** Then a person must start Airflow to use the database, also for tests and manual work.
  3. **A root Compose file that Airflow includes (the decision).** The database has one definition. You can start it alone, and Airflow starts it with the other services.
- **Why these settings:**
  - **Port `127.0.0.1:5433`:** `127.0.0.1` keeps the database off the network. The password is a development value, thus other computers must not connect. `5433` prevents a conflict with a PostgreSQL that uses `5432` on the same computer.
  - **The volume is mounted at `/var/lib/postgresql`**, not at `/var/lib/postgresql/data`. From version 18, the image keeps the data in `/var/lib/postgresql/18/docker`. With the old mount path, the data is not in the volume, and it is lost when the container is removed. The project checked the `data_directory` setting, and it stopped and started the container to prove that the data stays.
  - **The volume has a fixed name** (`african-football-pipeline-db`). Compose adds the project name to a volume name, and the project name is the name of the folder. Without a fixed name, the root folder and `airflow/` use two different volumes, without an error.
- **Trade-offs:**
  - Only one `pipeline-db` can run at a time. The root project and the Airflow project make different containers, and both use port `5433`.
  - `include:` needs Docker Compose 2.20 or later.
  - Docker is now necessary for the database tests. Without `DATABASE_URL`, pytest skips them.
