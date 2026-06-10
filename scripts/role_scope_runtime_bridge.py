"""Runtime bridge enforcing LTE-DE / LTE-NL role scope in the legacy UI."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pandas as pd

from local_auth_module import UserContext
from role_scope_csv_bridge import build_scoped_csv_reader
from role_scope_module import (
    ADMIN_ROLE,
    filter_mapping_rows_for_role,
    restrict_performing_ru_values_for_role,
    visible_primary_export_groups,
)


PHASE9B_SCOPE_RUNTIME_MARKER = "NETZENTGELT_PORTABLE_ROLE_SCOPE_RUNTIME_PHASE9B_V2_20260610"


@contextmanager
def role_scoped_runtime(user: UserContext) -> Iterator[None]:
    """Apply role-based visibility and export restrictions for one UI run."""
    if user.role_code == ADMIN_ROLE:
        yield
        return

    import export_module
    import rest_export_module

    original_read_csv = pd.read_csv
    original_primary_groups = rest_export_module.PRIMARY_EXPORT_GROUPS
    original_lte_groups = export_module.LTE_EXPORT_GROUPS
    original_rest_overview = rest_export_module.list_rest_export_overview
    original_build_nutzungsmeldung = export_module.build_nutzungsmeldung_xlsx
    original_build_aufenthalt = export_module.build_aufenthaltsereignis_xlsx

    scoped_primary_groups = visible_primary_export_groups(
        original_primary_groups,
        user.role_code,
    )
    scoped_lte_groups = visible_primary_export_groups(
        original_lte_groups,
        user.role_code,
    )
    scoped_read_csv = build_scoped_csv_reader(original_read_csv, user.role_code)

    def scoped_rest_overview(*args: Any, **kwargs: Any):
        rows = original_rest_overview(*args, **kwargs)
        return filter_mapping_rows_for_role(rows, user.role_code)

    def scoped_build_nutzungsmeldung(*args: Any, **kwargs: Any):
        if "performing_ru_values" in kwargs:
            kwargs = dict(kwargs)
            kwargs["performing_ru_values"] = restrict_performing_ru_values_for_role(
                kwargs["performing_ru_values"], user.role_code
            )
        elif len(args) >= 2:
            args = list(args)
            args[1] = restrict_performing_ru_values_for_role(args[1], user.role_code)
            args = tuple(args)
        return original_build_nutzungsmeldung(*args, **kwargs)

    def scoped_build_aufenthalt(*args: Any, **kwargs: Any):
        if "performing_ru_values" in kwargs:
            kwargs = dict(kwargs)
            kwargs["performing_ru_values"] = restrict_performing_ru_values_for_role(
                kwargs["performing_ru_values"], user.role_code
            )
        elif len(args) >= 2:
            args = list(args)
            args[1] = restrict_performing_ru_values_for_role(args[1], user.role_code)
            args = tuple(args)
        return original_build_aufenthalt(*args, **kwargs)

    pd.read_csv = scoped_read_csv
    rest_export_module.PRIMARY_EXPORT_GROUPS = scoped_primary_groups
    export_module.LTE_EXPORT_GROUPS = scoped_lte_groups
    rest_export_module.list_rest_export_overview = scoped_rest_overview
    export_module.build_nutzungsmeldung_xlsx = scoped_build_nutzungsmeldung
    export_module.build_aufenthaltsereignis_xlsx = scoped_build_aufenthalt
    try:
        yield
    finally:
        pd.read_csv = original_read_csv
        rest_export_module.PRIMARY_EXPORT_GROUPS = original_primary_groups
        export_module.LTE_EXPORT_GROUPS = original_lte_groups
        rest_export_module.list_rest_export_overview = original_rest_overview
        export_module.build_nutzungsmeldung_xlsx = original_build_nutzungsmeldung
        export_module.build_aufenthaltsereignis_xlsx = original_build_aufenthalt
