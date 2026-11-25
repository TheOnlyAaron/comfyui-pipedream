"""
Pipedream node classes, collected into ``ALL_NODES`` for registration by
the root ``__init__.py``.
"""

from .project_context import PDProjectContext
from .custom_context import PDCustomContext
from .tokens_to_string import PDTokensToString
from .output import PDOutput
from .load import PDLoad
from .switch import PDSwitch
from .wedge import PDWedge
from .video import PDImagesToVideo, PDVideoToImages, PDVideoGetFrame, PDImageFromBatch
from .sound import PDSound
from .ocio import PDOCIOTransform, PDOCIODisplay, PDOCIOApplyLUT
from .profiler import PDProfiler
from .exr_metadata import PDExrMetadataGet, PDExrMetadataMerge

ALL_NODES: list = [
    PDProjectContext,
    PDCustomContext,
    PDTokensToString,
    PDOutput,
    PDLoad,
    PDSwitch,
    PDSound,
    PDWedge,
    PDImagesToVideo,
    PDVideoToImages,
    PDVideoGetFrame,
    PDImageFromBatch,
    PDOCIOTransform,
    PDOCIODisplay,
    PDOCIOApplyLUT,
    PDProfiler,
    PDExrMetadataGet,
    PDExrMetadataMerge,
]
