"""
SiliconSignature ComfyUI Custom Node

A ComfyUI node that signs and verifies images using SiliconSignature watermarking
technique - LSB steganography with Reed-Solomon error correction.

Installation:
    Copy the entire 'comfyui-node' folder to ComfyUI/custom_nodes/ directory
    and restart ComfyUI.

Nodes:
    - SiliconSignature Sign: Embed a cryptographic watermark into an image
    - SiliconSignature Verify: Extract and verify a watermark from an image
"""

from .silicon_signature_node import (
    SiliconSignatureEmbed,
    SiliconSignatureVerify,
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
)

__all__ = [
    "SiliconSignatureEmbed",
    "SiliconSignatureVerify",
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]

# ComfyUI node registration
NODE_CLASS_MAPPINGS = NODE_CLASS_MAPPINGS
NODE_DISPLAY_NAME_MAPPINGS = NODE_DISPLAY_NAME_MAPPINGS
