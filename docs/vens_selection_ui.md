# Nutzer-vEns-Auswahl in der Fallbearbeitung

Stand: 2026-06-12

## Zweck

Wenn für ein nutzendes EVU mehrere Nutzer-vEns vorhanden sind, darf die Anwendung keine stille Auswahl treffen. Die Zuordnung wird deshalb im Reiter `3. Fall bearbeiten` kontrolliert ausgewählt und auditierbar gespeichert.

## Katalog

Versionierter Nutzer-vEns-Katalog:

```text
data/01_mapping/ukl_user_vens_catalog.csv
```

Der Katalog enthält ausschließlich auswählbare Nutzer-vEns. Basis-vEns werden bewusst nicht im operativen Dropdown angeboten.

## Auswahl

Im Bereich `Nutzer-vEns auswählen oder korrigieren` wird zuerst ein Timeline-Fall gewählt. Danach zeigt das Dropdown nur Nutzer-vEns des passenden nutzenden EVU an.

Die Anzeige enthält:

- Nutzer-vEns
- Marktlokation Entnahme
- Marktlokation Rückspeisung

## Gültigkeit

Zwei Varianten sind verfügbar:

| Variante | Priorität | Verhalten |
|---|---:|---|
| Nur für diesen Zeitraum | `10` | gilt für den ausgewählten Zeitraum und übersteuert ein Standardmapping |
| Als Standard ab Fallbeginn | `100` | gilt ab dem gewählten Beginn, bis eine spätere Regel greift |

Kleinere Prioritätswerte gewinnen bei der Auflösung.

## Speicherung und Audit

Aktive Mappingdatei:

```text
data/01_mapping/performing_ru_vens_mapping.csv
```

Lokales Änderungsprotokoll:

```text
data/01_mapping/performing_ru_vens_mapping_change_log.csv
```

Vor jeder Änderung wird eine lokale Sicherung unter `.vens_mapping_backups` angelegt. Die Rohdaten aus RailCube bleiben unverändert.
