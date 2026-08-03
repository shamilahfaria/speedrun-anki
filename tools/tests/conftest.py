# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Speedrun addition. tools/ is a script directory, not a package; put it on the
# path so the bench harness can be imported by its module name.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
