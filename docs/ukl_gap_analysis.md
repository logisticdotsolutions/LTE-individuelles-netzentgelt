# UKL-Gap-Analyse – Individuelles Netzentgelt Deutschland

Stand: 2026-06-11

## 1. Ausgangslage

Die lokale Testsuite wurde nach der Cleanup-Phase erfolgreich ausgeführt: 115 Tests bestanden. Die bekannte Warnung `W001_SOURCE_ROW_HASH_NOT_INTEGRATED` bleibt bis zur späteren Integration einer persistierten `source_row_hash`-Spalte bestehen.

Die UKL-Prozessbeschreibung Version 1.2 und die sechs bereitgestellten XLSX-Vorlagen wurden gegen den aktuellen Codebestand gespiegelt.

## 2. Fachlicher Prozessrahmen

Die Prozessbeschreibung unterscheidet zwei fachliche Ebenen:

1. Regulierter BNB-Prozess: Der ANe-tEns beziehungsweise Halter bleibt verantwortlich für die vollständige Zuordnungsdatensatzliste an den BNB.
2. Ergänzender UKL-Prozess zur Nutzungsüberlassung: Übergaben, Übernahmeanfragen, Quittungen und Zuordnungen je Meldetag werden zwischen ANe-tEns und ANu-vEns beziehungsweise zwischen mehreren ANu-vEns ausgetauscht.

Wichtige fachliche Vorgaben:

- Meldungen und Quittungen werden über Zeitstempel versioniert.
- Datum-Zeit-Angaben im Nachrichtenaustausch werden in UTC übertragen.
- Nur quittierte Meldungen dürfen in Folgeprozessen verarbeitet werden.
- Übergabemeldungen dürfen korrigiert werden, wenn dieselbe Referenz mit jüngerem Zeitstempel erneut versendet wird.
- Die tEns darf bei einer Übergabekorrektur nicht verändert werden.
- Storno und rückwirkende Änderungen von Beginn oder Ende sind nur innerhalb von zehn Werktagen zulässig.
- Zuordnung-Meldetag kann abweichende vEns-Zeitabschnitte 15-minutenscharf abbilden.
- Nicht gemeldete Zeiten eines Meldetags fallen auf die vEns der Übergabe zurück.
- Zeitabschnitte eines Meldetags dürfen sich nicht überschneiden.

## 3. Analyse der UKL-Vorlagen

| UKL-Artefakt | Tabellenblatt | Version | Pflichtfelder | Kontrollierte Werte | Aktueller Stand |
|---|---|---:|---|---|---|
| Nutzungsmeldung | `Zuordnungsdatensatzliste` | `N01` | `TfzE oder tEns*`, `Beginn der Nutzung*`, `Nutzer-vEns*`, `Marktpartner ID für Nutzungsüberlassung*` | Spalte `Übernahmeanfrage oder Übergabemeldung?` fachlich noch zu klären | XLSX je PerformingRU implementiert |
| Zuordnungen | `Zuordnungsdatensatzliste` | `Z01` | `TfzE oder tEns*`, `Beginn der Zuordnung*`, `Nutzer-vEns*` | keine Liste in Vorlage | CSV vorhanden; XLSX-Export fehlt |
| Aufenthaltsereignis | `Aufenthaltsereignisse` | `AE01` | `TfzE oder tEns*`, `vEns*`, `Ort*`, `Zeitpunkt*`, `Netzstatus*` | `netzintern`, `netzextern`, `einfahrend`, `ausfahrend` | XLSX je PerformingRU implementiert |
| Aufenthaltsabschnitt | `Aufenthaltsabschnitt` | `AV01` | `TfzE oder tEns*`, `vEns*`, `Beginn*`, `Ende*`, `Netzstatus*` | `netzintern`, `netzextern`, `einfahrend`, `ausfahrend` | noch nicht implementiert |
| Abstellungen | `Abstellungen` | `AB01` | `TfzE oder tEns*`, `vEns*`, `Art*`, `Beginn*`, `Ende*` | `Abstellung warm`, `TfzE nicht in Nutzung` | noch nicht implementiert |
| Traktionsleistungen | `Traktionsleistungen` | `T01` | `TfzE oder tEns*`, Abfahrt `Zeitpunkt*`, Abfahrt `Ort*`, Ankunft `Zeitpunkt*`, Ankunft `Ort*`, `Entfernung*`, `Gewicht Anhängelast*`, `Bestellkriterium*`, `Verwendungsart*` | Bestellkriterium: `Güterverkehr`, `Fernverkehr`, `Regioverkehr`, `S-Bahn`; Verwendungsart: `OR`, `LLA`, `LLN`, `SE`, `LH`, `SG` | noch nicht implementiert |

Hinweis: Die Vorlagen enthalten ausgeblendete `Quellen`-Blätter mit Wertelisten, aber keine aktiv hinterlegten Excel-Datenvalidierungen. Die Anwendung muss die erlaubten Werte daher selbst validieren.

## 4. Quellfelder aus dem Datalake

### LocomotiveMovement.csv

Für die UKL-Exporte besonders relevant:

- Lok: `LocomotiveNo`, `LocomotiveID`, `LocomotiveHolder`, `LocomotiveOwner`, `LocomotiveType`
- Nutzung: `PerformingRU`, `TractionType`, `Traction`
- Zeitbezug: `ActualDeparture`, `ActualArrival`, `LocomotiveActualDeparture`, `LocomotiveActualArrival`
- Orte und Grenzbezug: `OriginLocationName`, `DestinationLocationName`, `OriginCountryISO`, `DestinationCountryISO`, `OriginBorderLocationName`, `DestinationBorderLocationName`
- Transport: `TransportNumber`, `TrainNo`, `MovementType`, `TransportType`, `CalculatedDistance`, `Distance`
- Zugdaten: `TrainWeightGross`, `TrainWeightNett`, `WagonWeight`, `FreightWeight`, `TractionLocomotiveWeight`, `SendLocomotiveWeight`

### TransportDetail.csv

Für Traktionsleistungen und Aufenthaltslogik besonders relevant:

- Zeitbezug: `ActualDeparture`, `ActualArrival`
- Orte und Grenzbezug: `OriginLocationName`, `DestinationLocationName`, `OriginCountryISO`, `DestinationCountryISO`, `OriginBorderLocationName`, `DestinationBorderLocationName`
- Transport: `TransportNumber`, `TrainNo`, `MovementType`, `TransportType`, `CalculatedDistance`, `Distance`
- Nutzung: `PerformingRU`
- Zugdaten: `TrainWeightGross`, `TrainWeightNett`, `WagonWeight`, `FreightWeight`, `TractionLocomotiveWeight`, `SendLocomotiveWeight`

### Locomotive.csv

Für Stammdaten- und Dummy-Prüfungen relevant:

- `LocomotiveID`
- `LocomotiveNo`
- `Alias`
- `TypeNo`
- `TypeName`

## 5. Soll-Ist-Matrix

| UKL-Vorlage | Bereits implementiert | Teilweise implementiert | Noch nicht implementiert | Benötigte Quelltabellen | Offene Fachfragen |
|---|---|---|---|---|---|
| Nutzungsmeldung | XLSX je RU, Mapping-Fallbacks, Gate-Prüfung, Cache | Feld `Übernahmeanfrage oder Übergabemeldung?` bleibt leer | explizite UKL-End-to-End-Validierung | `core_usage_assignment_segments`, Mappingtabellen, Gate-Tabellen | Soll das Feld dauerhaft leer bleiben oder regelbasiert gefüllt werden? |
| Zuordnungen | CSV `export_zuordnungen` | Segmentlogik ist vorhanden | offizieller XLSX-Export, UI-Download, Tests | `core_usage_assignment_segments`, Mappingtabellen, Gate-Tabellen | Soll das optionale Ende bei offenen Zuordnungen leer bleiben können? |
| Aufenthaltsereignis | XLSX je RU, Richtungsklassifikation, Gate-Prüfung, Cache | Validierung der Grenzort-Regel kann weiter gehärtet werden | End-to-End-Prüfung | `core_loco_timeline`, Mappingtabellen, Gate-Tabellen | Muss `vEns*` zwingend die ANU_VENS-ID statt DataLake-PerformingRU enthalten? |
| Aufenthaltsabschnitt | keine | Zeitachse und Aufenthaltsereignisse als Grundlage vorhanden | Ableitung, XLSX, UI, Tests | `core_loco_timeline`, Ereignisse, Segmente | Exakte Bildung von Beginn/Ende und Statuswechseln klären |
| Abstellungen | keine | `core_loco_stand_candidates` vorhanden | fachliche Klassifikation, XLSX, UI, Tests | Standkandidaten, manuelle Gap-Klassifikation, Mappingtabellen | Abgrenzung `Abstellung warm` vs. `TfzE nicht in Nutzung` klären |
| Traktionsleistungen | keine | notwendige Rohfelder sind grundsätzlich vorhanden | fachliche Aggregation, XLSX, UI, Tests | Bewegungen, Transportdetails, Lokdaten, Mappingtabellen | Entfernung, Anhängelast, Bestellkriterium und Verwendungsart fachlich exakt definieren |
| Vollständiges Uploadpaket | keine | Einzel-XLSX für Nutzung und Ereignisse vorhanden | Paketbildung, Dateinamenskonvention, Manifest, Audit | alle Exportmodule | Einzeldateien oder ZIP? Je RU oder global? |
| UKL-Rückmeldungen | keine | Audit-Grundlagen vorhanden | Import und Statusverarbeitung | zukünftige AS4-/Dateirückmeldungen | Welche Rückmeldedateien liefert UKL? |

## 6. Priorisierte Umsetzung

1. Zuordnungen als offizieller XLSX-Export auf Basis der bereits vorhandenen Segmente.
2. Traktionsleistungen, da hierfür zusätzliche fachliche Aggregationsregeln geklärt und getestet werden müssen.
3. Aufenthaltsabschnitte als aus Ereignissen und Zeitachsen abgeleitete Intervalle.
4. Abstellungen auf Basis der Standkandidaten und manuellen Klassifikationen.
5. Härtung der bereits vorhandenen Nutzungsmeldung und Aufenthaltsereignisse.
6. Einheitliches UKL-Exportpaket mit Manifest, Auditdatei und End-to-End-Validierung.
7. Spätere Erweiterung um versionierte UKL-Rückmeldungen beziehungsweise AS4-Nachrichtenstatus.

## 7. Bewusste Abgrenzung des ersten Umsetzungspakets

Der erste technische Schritt ergänzt ausschließlich den offiziellen XLSX-Export für `Vorlage_Zuordnungen.xlsx`. Die vorhandene Segmentlogik, Gate-Logik und Mappinglogik werden wiederverwendet. Es erfolgt keine stille Änderung der bestehenden Nutzungsmeldung oder Aufenthaltsereignisse.
