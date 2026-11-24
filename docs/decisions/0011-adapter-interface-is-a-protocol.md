# 11. The adapter interface is a Protocol, not a base class

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** `SourceAdapter` is a `typing.Protocol` with `discover_seasons`, `fetch` (both async) and `parse`.
- **Why:** An adapter does not inherit from a base class. A class that has these methods is an adapter. Thus, the adapters do not depend on a shared base module, and there is no class hierarchy. `fetch` uses the network, thus it is async. `parse` reads files only, thus it is not async.
- **Trade-offs:** Python does not examine a Protocol when the program runs. Only a type checker finds an adapter with a wrong method. CI runs a type checker (basedpyright, see [decision 12](0012-basedpyright-in-standard-mode.md)). But a type checker examines a Protocol only where the code uses it, for example `adapter: SourceAdapter = SoccerwayAdapter()`. Before part 3b, no code used `SourceAdapter`. A test proved this: a wrong return type in the Protocol gave no error. Now `FootballScraper` assigns the adapter to a variable of the type `SourceAdapter`. A test proved that the check works: with a wrong return type in `SoccerwayAdapter.parse`, basedpyright gave the error `Type "SoccerwayAdapter" is not assignable to declared type "SourceAdapter"`.
