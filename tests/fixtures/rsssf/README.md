# RSSSF fixtures

These files are copies of pages of the Rec.Sport.Soccer Statistics Foundation (RSSSF), https://www.rsssf.org/. The tests of the RSSSF adapter read them. The files are not changed. Do not format them: the tests need the original text.

The licence of each page: "You are free to copy this document in whole or part provided that proper acknowledgement is given to the authors. All rights reserved."

| File | Page | Authors | Last updated (on the page) | Copied |
|---|---|---|---|---|
| `nigchamp.html` | https://www.rsssf.org/tablesn/nigchamp.html | Djidenou Medjigbodo and RSSSF | 16 Aug 2026 | 24 Nov 2026 |
| `ghachamp.html` | https://www.rsssf.org/tablesg/ghachamp.html | Karel Stokkermans and RSSSF | 18 May 2026 | 24 Nov 2026 |
| `egychamp.html` | https://www.rsssf.org/tablese/egychamp.html | Ahmed El-Gammal, Amro Hassanin, Tarek Said and RSSSF | 16 Jul 2026 | 24 Nov 2026 |

## Season pages (`seasons/`)

Each file shows one form of the pages ([decision 22](../../../docs/decisions/0022-rsssf-parser.md)). The tests in `tests/unit/test_rsssf_parser.py` read them.

| File | Page | Authors | Last updated (on the page) | Form that the file shows |
|---|---|---|---|---|
| `seasons/nig2024.html` | https://www.rsssf.org/tablesn/nig2024.html | Hans Schöggl, Karel Stokkermans and RSSSF | 13 Oct 2024 | Structure A; a note that continues in a column at the right of the next results |
| `seasons/gha2024.html` | https://www.rsssf.org/tablesg/gha2024.html | Hans Schöggl, Karel Stokkermans and RSSSF | 22 Oct 2026 | Structure A; the score of an awarded match in its note; agrees with Soccerway |
| `seasons/nig2019.html` | https://www.rsssf.org/tablesn/nig2019.html | Karel Stokkermans and RSSSF | 14 Nov 2019 | Structure A with `<b>` stages and `<u>` groups |
| `seasons/nig05.html` | https://www.rsssf.org/tablesn/nig05.html | José Batalha and RSSSF | 16 Aug 2026 | Structure B; tabs between the columns; the table before the results; replays |
| `seasons/nig01.html` | https://www.rsssf.org/tablesn/nig01.html | José Batalha, Hans Schöggl and RSSSF | 27 Sep 2018 | Structure B; tables in the middle of the league (`Table:`) |
| `seasons/gha02.html` | https://www.rsssf.org/tablesg/gha02.html | José Batalha, Hans Schöggl and RSSSF | 14 Jun 2003 | Structure B; a competition heading without `===`; a play-off after the final table is not a part of the league; a note after a space and a tab |
| `seasons/egy05.html` | https://www.rsssf.org/tablese/egy05.html | Tarek Said and RSSSF | 7 Sep 2007 | Structure B; the cup starts after the final table without a heading |
| `seasons/gha08.html` | https://www.rsssf.org/tablesg/gha08.html | José Batalha and RSSSF | 21 Dec 2009 | Structure B; headings with `===`; the date on the round line |
| `seasons/nig72.html` | https://www.rsssf.org/tablesn/nig72.html | Hans Schöggl and RSSSF | 6 Jul 2026 | One page for the seasons 1969/70 to 1979, with `<b><a name>` anchors |
| `seasons/ghahist.html` | https://www.rsssf.org/tablesg/ghahist.html | Gerd Heuser, Hans Schöggl and RSSSF | 2 Oct 2024 | One page for many seasons, with anchors without `<b>`; tables only |
| `seasons/gha2013.html` | https://www.rsssf.org/tablesg/gha2013.html | José Batalha and RSSSF | 15 Apr 2021 | A crosstable of results (not read; reported) |
| `seasons/egy53.html` | https://www.rsssf.org/tablese/egy53.html | Tarek Said and RSSSF | 21 Mar 2007 | The results of each team as a grid (not read; reported) |
| `seasons/egy95.html` | https://www.rsssf.org/tablese/egy95.html | Josef Bobrowsky and RSSSF | 27 Sep 1999 | A final table only; a cup final with a label (`Cup Final:`) |
| `seasons/nig99.html` | https://www.rsssf.org/tablesn/nig99.html | Eric Boesenberg, Karel Stokkermans, Hans Schöggl and RSSSF | 7 Jun 2013 | Dates of two days (`[Mar 24,25]`); rounds without a date |

## Season pages of other countries (`seasons/`, decision 24)

These pages come from a survey of 56 African countries (November 2026). Each shows one rule of the choice of the national league. `tests/unit/test_rsssf_league_choice.py` reads them.

| File | Page | Authors | Last updated (on the page) | Form that the file shows |
|---|---|---|---|---|
| `seasons/kaapv2024.html` | https://www.rsssf.org/tablesk/kaapv2024.html | José Batalha and RSSSF | 25 Jan 2025 | Nine island leagues, no national league |
| `seasons/kaapv95.html` | https://www.rsssf.org/tablesk/kaapv95.html | José Batalha and RSSSF | 8 Sep 2002 | The national league after the page title |
| `seasons/kam2011.html` | https://www.rsssf.org/tablesk/kam2011.html | Hans Schöggl and RSSSF | 5 Jul 2017 | The cup has results; the league has only its table |
| `seasons/maro2012.html` | https://www.rsssf.org/tablesm/maro2012.html | Ian King and RSSSF | 16 Jun 2021 | The same, in Morocco ('GNF I') |
| `seasons/egy2011.html` | https://www.rsssf.org/tablese/egy2011.html | Tarek Said, Hans Schöggl and RSSSF | 31 Aug 2025 | The same, in Egypt: the cup was the league before |
| `seasons/tun2026.html` | https://www.rsssf.org/tablest/tun2026.html | Karel Stokkermans and RSSSF | 16 Jul 2026 | 'Ligue Professionnelle 2' is a lower level |
| `seasons/nig06.html` | https://www.rsssf.org/tablesn/nig06.html | José Batalha and RSSSF | 27 Sep 2018 | A first stage with more results than the final stage |
| `seasons/sier01.html` | https://www.rsssf.org/tabless/sier01.html | Hans Schöggl, José Batalha and RSSSF | 27 Sep 2003 | Groups first, then the national league |
| `seasons/niger03.html` | https://www.rsssf.org/tablesn/niger03.html | José Batalha and RSSSF | 18 Jan 2004 | A French league name in lower case |
| `seasons/moz08.html` | https://www.rsssf.org/tablesm/moz08.html | José Batalha and RSSSF | 20 Mar 2009 | A row of a table of participants and a result line without a space ('Liga ...') |
| `seasons/ethi08.html` | https://www.rsssf.org/tablese/ethi08.html | Mamo Gebrehiwot and RSSSF | 1 Dec 2016 | A sentence before the league heading |
| `seasons/reunion2022.html` | https://www.rsssf.org/tablesr/reunion2022.html | Hans Schöggl and RSSSF | 12 Jul 2023 | 'Régional 1' is the top league of Réunion |

