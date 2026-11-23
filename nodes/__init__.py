"""
Pipedream node classes, collected into ``ALL_NODES`` for registration by
the root ``__init__.py``.
"""

from .project_context import PDProjectContext
from .custom_context import PDCustomContext
from .token_string import PDTokenString
from .output import PDOutput
from .switch import PDSwitch
from .wedge import PDWedge
from .video import PDImagesToVideo, PDVideoToImages, PDVideoGetFrame, PDImageFromBatch
from .sound import PDSound
from .ocio import PDOCIOTransform, PDOCIODisplay

ALL_NODES: list = [
    PDProjectContext,
    PDCustomContext,
    PDTokenString,
    PDOutput,
    PDSwitch,
    PDSound,
    PDWedge,
    PDImagesToVideo,
    PDVideoToImages,
    PDVideoGetFrame,
    PDImageFromBatch,
    PDOCIOTransform,
    PDOCIODisplay,
]
