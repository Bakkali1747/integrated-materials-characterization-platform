import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / ".mplconfig"))

import numpy as np
import pandas as pd
import pytest

from core.models import COLUMNS


@pytest.fixture
def frame():
    return pd.DataFrame(np.array([[2, 4, .2, 1.5, .3], [3, 4.1, .25, 1.4, .4],
                                  [4, 4.2, .3, 1.3, .5]]), columns=COLUMNS)
