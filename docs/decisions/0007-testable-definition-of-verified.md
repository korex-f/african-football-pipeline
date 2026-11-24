# 7. "Verified" has a definition that you can test

*Status: accepted (November 2026). [All decisions](README.md)*

- **What:** A season is *verified* when these two conditions are true:
  - The number of matches is equal to the expected number.
  - An independent source agrees, or the total goals agree with a final table.

  If not, the season status is *complete (single source)*, *incomplete*, *failed*, or *unavailable*.
- **Why:** Without a clear rule, the word "verified" has no meaning. Many African league seasons are not regular. Examples are seasons cancelled because of COVID, seasons with groups, and cancelled matches. Thus, the rule needs exceptions for each season.
- **How (planned, roadmap step 5):** For a double round-robin league with *n* teams, the default expected number of matches is *n × (n − 1)*. The configuration can change this number for each season. Incomplete data never replaces verified data.
