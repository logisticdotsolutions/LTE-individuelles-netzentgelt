# UKL source inventory

Stand: 2026-06-12

## Current downloadable UKL files

| Object | File | Sheet | Version | SHA-256 |
|---|---|---|---|---|
| Aufenthaltsereignis | `Vorlage_Aufenthaltsereignis.xlsx` | `Aufenthaltsereignisse` | `AE01` | `3dcf96308d9587d398e31ca29cff3c06b8cb2b33c969557481b5dcdc97484372` |
| Aufenthaltsabschnitt | `Vorlage_Aufenthaltsabschnitt.xlsx` | `Aufenthaltsabschnitt` | `AV01` | `bd4bf399160945d2c34e209966ec600743876aefd7b639c4447f63f2ce03a070` |
| Abstellung | `Vorlage_Abstellungen.xlsx` | `Abstellungen` | `AB01` | `57e70c300607015e18fa88c37cd27128d0a1c55c9d77fb4b305a411248786f2b` |
| Übernahmeanfrage / Übergabemeldung | `Vorlage_Übernahmeanfrage,Übergabemeldung.xlsx` | `Zuordnungsdatensatzliste` | `N01` | `15d602b73eca40b5894b2837f18c60a94580ccb0e158e68fbd363347bcf886c9` |
| Traktionsleistung | `Vorlage_Traktionsleistungen.xlsx` | `Traktionsleistungen` | `T01` | `c5e6c955266ed33822d5adec85bf93b642000d52c02a73acba6af7c7b5e9d015` |
| Zuordnung | `Vorlage_Zuordnungen.xlsx` | `Zuordnungsdatensatzliste` | `Z01` | `e9022ff420dc75692e53b4ba3e63ef57ae4ee80ab2ad99d57b4f7faa295f9807` |
| Halterschaft | `Vorlage_Halterschaft.xlsx` | `Zuordnungsdatensatzliste` | `H01` | `3d5c63709f504b4d68ecf37879ed22e097639e7ca5e2854c630a06030b5e5edb` |

Documentation:

- `Prozessbeschreibung Nutzungsüberlassung_V1_2.pdf`, version 1.2, 30.09.2025
- `Handbuch - aktuelle Funktionen der Web-Anwendung.pdf`, 23.02.2026

## Important corrections for the MVP

1. The current N01 template has exactly five columns:
   - `TfzE oder tEns*`
   - `Beginn der Nutzung*`
   - `Ende der Nutzung`
   - `Nutzer-vEns*`
   - `Marktpartner ID für Nutzungsüberlassung*`

   It does not contain a sixth column `Übernahmeanfrage oder Übergabemeldung?`. The existing export must be checked and hardened against the current template before productive use.

2. `Halterschaft` is a separate upload type (`H01`) and must be treated as its own upstream scope.

3. `Z01` is a holder-side export and must not be generated per PerformingRU. LTE Holding is the only holder-side sender for the locomotive assignments. The export therefore consists of exactly one LTE-Holding file containing the locomotives with DE relevance in the selected period. PerformingRU remains relevant only as row-level assignment information for the target `Nutzer-vEns*`.

4. The remaining BNB usage-data templates are:
   - Traktionsleistung `T01`
   - Aufenthaltsabschnitt `AV01`
   - Abstellung `AB01`

5. UKL imports are strict: outdated versions, wrong template types and files with at least one error are rejected as complete files.

## Recommended implementation order

1. Replace the current Z01 per-PerformingRU UI with one LTE-Holding assignment export filtered to DE-relevant locomotives.
2. Harden existing N01 export against the current UKL template.
3. Implement T01.
4. Implement AV01.
5. Implement AB01.
6. Add H01 as a separate upstream scope.
7. Add package manifest, hashes and portal-style preflight validation.
