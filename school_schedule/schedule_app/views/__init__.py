"""HTTP view facades grouped by responsibility.

The implementation remains backward-compatible in legacy_views while callers use
focused modules during the incremental migration.
"""

from ..legacy_views import *
