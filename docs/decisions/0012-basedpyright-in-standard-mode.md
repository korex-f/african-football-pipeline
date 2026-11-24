# 12. The type checker is basedpyright, in standard mode

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** CI runs `basedpyright` in the `lint` job. The project sets `typeCheckingMode = "standard"` in `pyproject.toml`.
- **The debate:**
  1. **Pyright** is the type checker from Microsoft. Its default mode is `standard`. It needs Node.js on the computer.
  2. **basedpyright** is a community fork of Pyright. It uses the same type-checking engine and follows the Pyright releases. It adds more rules, a *baseline* function, and editor functions that are not open source in Pylance. The PyPI package contains Node.js. Its default mode is `recommended`, which is much stricter.
  3. **The decision: basedpyright.** The editors of the project author (Neovim and Zed) use basedpyright. If CI used Pyright and the editors used basedpyright, the two tools would show different errors. This is the same problem as two Ruff versions.
- **Why standard mode:** The project measured the two modes on the same code:

  | Mode | Result |
  |---|---|
  | `standard` | 21 errors, all on one line of a test helper |
  | `recommended` | 82 errors and 1,501 warnings, most in the old scraper code |

  In standard mode, Pyright and basedpyright gave the same 21 errors. The project corrected the line (a `dict[str, Any]` type annotation). A new CI check must start with no errors. If not, it stops each pull request until a person corrects the old code.
- **How:** `basedpyright` is a dev dependency, thus `uv.lock` sets its version. The `[tool.pyright]` section has the settings. basedpyright, Pyright and Pylance all read this section. To make sure that the check can fail, the project changed a return type in `RawStore.get` on purpose. basedpyright found the error.
- **Trade-offs:**
  - basedpyright is a fork. A new Pyright release can come to basedpyright some days later.
  - Standard mode does not find all problems, for example values with an unknown type.
  - Later, when the old scraper is removed, the project can use `recommended` mode with a baseline. The baseline file records the current warnings. Then CI fails only on new warnings.
