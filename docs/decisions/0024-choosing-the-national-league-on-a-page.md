# 24. Choosing the national league on an RSSSF page: rules, an override, and a visible choice

*Status: accepted (November 2026). Replaces the rule "the first competition with results" of [decision 22](0022-rsssf-parser.md). [All decisions](README.md)*

- **What:** `choose_league()` in `sources/rsssf/parser.py` chooses the competition of a season page that is the national league. The parser and the table reader both use it. `leagues.yaml` can give a pattern for a league (`rsssf_league`). The adapter writes the choice, its reason and the other competitions to the log.
- **Why:** The project tested the RSSSF code on all African countries (a survey of 2,321 pages of 56 countries, November 2026). The rule of decision 22 ("the first competition with results") was correct for Nigeria, Ghana and Egypt, but not for Africa. It took a cup in 208 seasons, a sentence in 26, a play-off in 16, and an island league in 17. These errors were silent: wrong data, without a problem in the report. The survey also showed that the rule had taken a cup as the league in 22 seasons of Nigeria, Ghana and Egypt (133 matches), which the tests of decision 22 did not show.

## The debate

1. **Rules only.** No setup for each country. But a page where the rules are wrong cannot be corrected without a change to the code.
2. **Configuration only.** Each league names its competition in `leagues.yaml`. Exact, but each new country needs setup before it gives data, and a new sponsor name gives no data until the configuration changes.
3. **Rules, an override, and a visible choice (the decision).** The rules decide for all pages. `rsssf_league` corrects a league where the rules are wrong. The log shows each choice and the alternatives, thus a person can find a wrong choice.

## The rules

| Step | Rule | Example from the survey |
|---|---|---|
| 1 | `rsssf_league` in `leagues.yaml`: the first competition that matches it. If none matches, the page has no league: the rules do not guess | — |
| 2 | Candidates: competitions with results or a table (a final-table heading, or 3 or more table rows), of the kind **league** | — |
| | not a **cup**: Cup, Coupe, Copa, Taça, Trophy, Shield, Tournament, Tournoi, Torneio, ... | Coupe du Trône, Taça Nacional, Moi Golden Cup |
| | not a **lower level**: Second, 2ème, 2ª Divisão, Ligue 2, Division Nationale B, Division 1 North, Stream, Regional, Provincial, Distrital, ... (but `Régional 1`, the top league of Réunion) | Ligue Professionnelle 2, Northern Stream First Division |
| | not a **play-off**: Playoff, Barrage, Mini-league | Championship Playoff |
| | not a **note** (a sentence): ends with `.`, more than 9 words, sentence words (the, were, no, held, ...), or 3 or more words in lower case that are not connectors or league words. Text in `[ ]` and `( )` does not count | "Winners qualify for CAF Cup." |
| | not **unnamed**: a part of a page after a final table without a heading | — |
| 3 | If the first candidate and 3 or more others have only a place name, the page has regional leagues only: no league | Cape Verde 2009/10 to 2025/26: nine island leagues |
| 4 | If the first candidate has no league word and is not the page title, a later candidate with a national name (National, Nacional, Première, 1ère, Elite, Girabola, ...) and a league word. A stage ('First Stage', 'Group A') stays, unless the national competition has more results | Sierra Leone 2001: 'Group A' (4 matches), then 'National Premier League' (36) |
| 5 | Else the first candidate with results; else the first candidate (tables only) | Cameroon 2010/11: the cup has results, 'MTN Elite One' has its table |
| 6 | Else the first competition with results that is not a cup. The reason gives its kind, for example `fallback (lower)` | Angola before 1979: provincial championships only |

A league word is: League, Ligue, Liga, Division, Championnat, Campeonato, Championship, Botola, Premiership, Ligi, Superligue, Girabola, or an abbreviation that ends with L (`NPFL`, `PSL`).

The headings of structure B (one `<pre>` block) use the same words in English, French and Portuguese. A heading is not a sentence, has no column gaps (a row of a table of participants), and has no score.

## How the rules were made

Each rule came from a measurement on all 2,448 seasons of the survey (the survey pages, plus the 187 pages of decision 22). After each change, a script compared each season with the version before: the chosen competition, the matches, the table rows, and the table check (decision 23). A rule was kept only if no season that agreed with its table before was worse. Examples of rules that the comparison corrected:

- A national name replaced the first candidate always. Then 'Nationwide League Division One' (the second level of Nigeria) replaced 'Nigeria Football League'. Thus a first candidate with a league word stays.
- 'NPFL 2023/24' has no league word, thus 'Nigeria National League' (the second level) replaced it. Thus an abbreviation that ends with L is a league word.
- The page title of structure B ('Nigeria 2003') has no league word, and was replaced. Thus the page title stays.
- A French name in lower case ('Championnat national de première division') was a sentence. Thus league words do not count as lower-case words.
- 'Stage' as a league word kept 'Group A' (4 matches) against 'National Premier League' (36). Thus a stage stays only if it has more results.
- Years ('1938/39') looked like place names. Thus a name with a year is not a place name.

## Result

| Chosen as the league | Before | After |
|---|---|---|
| A cup | 208 | 0 |
| A sentence | 26 | 1 |
| A play-off | 16 | 4 (fallback, in the log) |
| A lower level | 17 | 16 (fallback, in the log) |

427 seasons have a different choice. Table rows: 18,480 before, 20,182 after (league tables that the cup hid). Table checks that agree: 899 before, 901 after. No season that agreed before is worse.

## Trade-offs

- The rules are words. A national league with a name that the rules do not know, on a page where it is not the first competition, needs `rsssf_league`.
- A page with only lower or regional competitions gives one of them as a fallback. The reason in the log shows it; the coverage of the season is not complete.
- The words are in English, French and Portuguese. Arabic names on RSSSF are in transcription (Botola), thus they need the words of the transcription.
- The log shows a wrong choice, but a person must read it. The coverage check (decision 7) and the table check (decision 23) show many wrong choices as numbers that do not agree.
