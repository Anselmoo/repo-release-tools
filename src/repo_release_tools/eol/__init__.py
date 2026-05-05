"""Runtime end-of-life (EOL) tracking for repo-release-tools."""

import sys
from typing import TYPE_CHECKING

from . import core as _core

if TYPE_CHECKING:
    from .core import (
        SOURCE_OWNED_TOPIC_DOCS,
        SUPPORTED_LANGUAGES,
        EolRecord,
        EolStatus,
        _extract_version,
        _find_record,
        _parse_cycle,
        _rust_lag_position,
        check_eol_status,
        detect_host_version,
        detect_project_minimum,
        fetch_live_data,
        get_eol_records,
        resolve_override_eol,
    )

    _TYPE_CHECK_EXPORTS = (
        SOURCE_OWNED_TOPIC_DOCS,
        SUPPORTED_LANGUAGES,
        EolRecord,
        EolStatus,
        _extract_version,
        _find_record,
        _parse_cycle,
        _rust_lag_position,
        check_eol_status,
        detect_host_version,
        detect_project_minimum,
        fetch_live_data,
        get_eol_records,
        resolve_override_eol,
    )

_core.__path__ = __path__
_core.__package__ = __name__
sys.modules[__name__] = _core
