"""
Pipedream node classes.

All node modules are imported here and collected into ``ALL_NODES`` for
registration by the root ``__init__.py``.
"""

from .project_context import PDProjectContext
from .shot_token import PDShotToken
from .output_namer import PDOutputNamer
from .network_output import PDNetworkOutput
from .switch import PDSwitch
from .wedge import PDWedge
from .rasterizer import PDRasterizer

ALL_NODES: list = [
    PDProjectContext,
    PDShotToken,
    PDOutputNamer,
    PDNetworkOutput,
    PDSwitch,
    PDWedge,
    PDRasterizer,
]
