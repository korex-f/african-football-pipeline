# 8. Pydantic for data from a source, frozen dataclasses for internal data

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** The project uses two tools for data models. Each tool has a different job:

  | Data | Tool | Examples |
  |---|---|---|
  | Data from a source, after the parser reads it | Pydantic | `SourceMatch` |
  | Internal data that the code makes itself | Frozen dataclasses | `RawDocument`, `ResultRow`, `MatchPage` |
  | Data for output (files, database) | Dedicated serializers | The legacy JSON exporter (roadmap step 2) |

- **The debate:** The project examined three options.
  1. **Only dataclasses.** The project already used dataclasses, and they add no dependency. But you must write each check by hand. Rules that compare fields are easy to forget, for example "a penalty shootout needs a draw".
  2. **Only Pydantic.** Pydantic checks types and values when the code makes a record, and it converts records to and from JSON. But internal data does not need checks, because the code made it. Also, if the export uses `model_dump()`, the file format and the model become the same thing. Then a change to the model changes the files.
  3. **Both, with separate jobs (the decision).** Errors come into the pipeline at one location: where page text becomes data. Pydantic checks the data at this location. Inside the pipeline, simple frozen dataclasses are sufficient.
- **Why the settings of `SourceMatch` are strict:**
  - `strict=True`: the parser converts text to values, for example `'3'` to `3`. The model only checks the values. In the default mode, Pydantic converts `'3'` to `3` silently. Then a parser error that sends text is not found. In strict mode, the error occurs at the location of the problem.
  - `frozen=True`: after the parser makes a record, no step can change it. Many steps use the same records: export, database and reconciliation.
  - `extra="forbid"`: a field name with a spelling error causes an error. It is not ignored.
  - Model validators compare fields, for example: a played match must have a score, and a halftime score needs a full-time score.
- **Not now:** A domain `Match` model (frozen dataclass) comes in roadmap step 5. With only one source, there is nothing to reconcile. A `Match` model now would be a copy of `SourceMatch` with no logic.
- **Trade-offs:**
  - Contributors must know two model styles.
  - Pydantic is one more runtime dependency.
  - Strict mode makes more work for each parser: it must convert all values itself.
  - The model and the file format are separate. Thus, the legacy JSON format needs its own exporter code.
