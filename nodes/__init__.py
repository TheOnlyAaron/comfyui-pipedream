"""
Pipedream node classes.

All node modules are imported here and collected into ``ALL_NODES`` for
registration by the root ``__init__.py``.
"""

from .project_context import PDProjectContext
from .custom_context import PDCustomContext
from .shot_token import PDShotToken
from .output_relative import PDOutputRelative
from .output_absolute import PDOutputAbsolute
from .switch import PDSwitch
from .wedge import PDWedge
from .rasterizer import PDRasterizer
from .first_last_frame import PDFirstLastFrame

ALL_NODES: list = [
    PDProjectContext,
    PDCustomContext,
    PDShotToken,
    PDOutputRelative,
    PDOutputAbsolute,
    PDSwitch,
    PDWedge,
    PDRasterizer,
    PDFirstLastFrame,
]

# Backward compatibility aliases for saved workflows
PDOutputNamer = PDOutputRelative
PDNetworkOutput = PDOutputAbsolute
