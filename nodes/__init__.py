"""
Pipedream node classes, collected into ``ALL_NODES`` for registration by
the root ``__init__.py``.
"""

from .project_context import PDProjectContext
from .custom_context import PDCustomContext
from .shot_token import PDShotToken
from .output import PDOutput
from .switch import PDSwitch
from .wedge import PDWedge
from .video import PDImagesToVideo, PDVideoToImages, PDVideoFrame, PDImageFrame
from .sound import PDSound
from .ocio import PDOCIOTransform, PDOCIODisplay

ALL_NODES: list = [
    PDProjectContext,
    PDCustomContext,
    PDShotToken,
    PDOutput,
    PDSwitch,
    PDSound,
    PDWedge,
    PDImagesToVideo,
    PDVideoToImages,
    PDVideoFrame,
    PDImageFrame,
    PDOCIOTransform,
    PDOCIODisplay,
]
