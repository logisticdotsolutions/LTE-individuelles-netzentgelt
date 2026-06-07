"""Gemeinsame Hilfsfunktionen für das DQ-Regelwerk."""


def sql_lit(value: str) -> str:
    """SQL-Textliteral sicher quoten."""
    return "'" + str(value).replace("'", "''") + "'"


def qident(name: str) -> str:
    """SQL-Identifier sicher quoten."""
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(con, table_name: str) -> bool:
    """Prüfen, ob eine DuckDB-Tabelle existiert."""
    return (
        con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
        > 0
    )


def _columns(con, table_name: str) -> list[str]:
    """Spalten einer DuckDB-Tabelle auslesen."""
    return [
        row[0]
        for row in con.execute(
            f"describe {qident(table_name)}"
        ).fetchall()
    ]


def _pick_column(
    available_columns: list[str],
    candidates: list[str],
) -> str | None:
    """Erste tatsächlich vorhandene Spalte aus einer Kandidatenliste wählen."""
    by_lower = {
        column.lower(): column
        for column in available_columns
    }

    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]

    return None


def _text_expr(column_name: str | None) -> str:
    """Bereinigten SQL-Textausdruck für eine optionale Spalte liefern."""
    if column_name is None:
        return "NULL"

    return (
        "nullif(trim(cast("
        + qident(column_name)
        + " as varchar)), '')"
    )


def _import_context_cte() -> str:
    """
    SQL-CTE für den 24-Stunden-Cutoff liefern.

    Maßgeblich ist der jüngste erfolgreich protokollierte Rohdatenimport. Die
    Fehlerlogik verwendet bewusst NICHT current_timestamp, weil ein späteres
    Öffnen der App keine zusätzlichen Fehler ohne neuen Import erzeugen darf.
    """
    return """
        import_context as (
            select
                max(
                    try_cast(
                        replace(imported_at_utc, 'Z', '')
                        as timestamp
                    )
                ) - interval '1 day' as error_cutoff_utc
            from raw_import_run
            where lower(coalesce(status, '')) = 'imported'
        )
    """


def _de_relevance_expr(
    available_columns: list[str],
) -> str:
    """
    DE-Relevanz strikt über OriginCountryISO oder DestinationCountryISO bilden.

    Country wird ausschließlich als technischer Fallback verwendet, wenn in
    der jeweiligen Rohdatei weder ein Origin- noch ein Destination-Länderfeld
    vorhanden ist. Dadurch erzeugen reine Auslandsbewegungen keine Findings.
    """
    origin_column = _pick_column(
        available_columns,
        [
            "OriginCountryISO",
            "OriginCountryIso",
            "OriginCountry",
            "FromCountryISO",
            "FromCountry",
            "DepartureCountryISO",
            "DepartureCountry",
        ],
    )

    destination_column = _pick_column(
        available_columns,
        [
            "DestinationCountryISO",
            "DestinationCountryIso",
            "DestinationCountry",
            "ToCountryISO",
            "ToCountry",
            "ArrivalCountryISO",
            "ArrivalCountry",
        ],
    )

    if origin_column is None and destination_column is None:
        country_column = _pick_column(
            available_columns,
            ["Country"],
        )
        country_expr = _text_expr(country_column)
        return (
            "(upper(coalesce("
            + country_expr
            + ", '')) = 'DE')"
        )

    origin_expr = _text_expr(origin_column)
    destination_expr = _text_expr(destination_column)

    return (
        "(upper(coalesce("
        + origin_expr
        + ", '')) = 'DE' "
        + "or upper(coalesce("
        + destination_expr
        + ", '')) = 'DE')"
    )
