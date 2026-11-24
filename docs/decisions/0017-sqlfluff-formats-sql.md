# 17. sqlfluff formats the SQL files

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** A pre-commit hook runs `sqlfluff fix`, and the `lint` job runs `sqlfluff lint`. The settings are in `pyproject.toml`.
- **The debate:**
  1. **Only the capitalisation rules.** Keywords in upper case, types and names in lower case, as in the PostgreSQL documentation. But long `CHECK` lines stay long.
  2. **All the rules (the decision).** sqlfluff also splits lines longer than 88 characters (the Ruff value) and corrects the spaces. Its default spacing removes the aligned column types. The setting `spacing_before = "align"` for `data_type` keeps them aligned.
- **Settings that are not default:**
  - `max_line_length = 88`. A wrong key (`max_length`) gave no error, and sqlfluff used its default of 80. The project found this when the hook stopped a commit.
  - `exclude_rules = "RF04"`. This rule rejects column names that are SQL keywords, for example `name`, `source` and `timezone`. In PostgreSQL these are non-reserved keywords, and they are correct column names. They are also the field names of `SourceMatch`.
- **Trade-offs:** sqlfluff cannot split a long `COMMENT ON` line. A person must do this. sqlfluff checks the style, not the meaning: a constraint name in a comment that does not exist passed the check. The migration tests found that error.
