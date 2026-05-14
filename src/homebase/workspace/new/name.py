from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..projects import _next_available_alpha_name, resolve_new_project_name


def resolve_final_name(
    base_dir: Path,
    candidate: str,
    *,
    add_date_prefix: bool,
    add_tmp_suffix: bool,
    ts_name: bool = False,
    alpha_name: bool = False,
) -> str:
    if ts_name and not candidate:
        candidate = datetime.now().strftime("%Y%m%d-%H%M%S")
    if alpha_name and not candidate:
        candidate = _next_available_alpha_name(
            base_dir,
            add_date_prefix=add_date_prefix,
            add_tmp_suffix=add_tmp_suffix,
        )
    if not candidate:
        raise ValueError("folder name is empty")
    return resolve_new_project_name(candidate, add_date_prefix, add_tmp_suffix)
