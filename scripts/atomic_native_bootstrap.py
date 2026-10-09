"""Execute an unchanged native skill with narrow local runtime compatibility.

The environment's rasterio DLL shadows expat if loaded first. Matplotlib 3.11
removed the deprecated boxplot(labels=...) alias used by upstream reporting.
Neither shim changes data, algorithms, status or report conclusions.
"""
import sys
import pyexpat  # noqa: F401 -- load stdlib XML DLL before rasterio
import inspect
from pathlib import Path
import runpy

from matplotlib.axes import Axes
if 'labels' not in inspect.signature(Axes.boxplot).parameters:
    original_boxplot = Axes.boxplot
    def compatible_boxplot(self, *args, **kwargs):
        if 'labels' in kwargs:
            kwargs['tick_labels'] = kwargs.pop('labels')
        return original_boxplot(self, *args, **kwargs)
    Axes.boxplot = compatible_boxplot

sys.argv = sys.argv[1:]
sys.path.insert(0, str(Path(sys.argv[0]).resolve().parent))
runpy.run_path(sys.argv[0], run_name='__main__')
