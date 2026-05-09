"""
SiliconSignature ComfyUI Custom Node
Embed and verify ASIC watermarks in images using LSB steganography
with Reed-Solomon error correction.
"""
import json
import hashlib
import torch
import numpy as np
from PIL import Image

# Handle both package import and direct import
from .watermark import (
    software_sign,
    asic_sign,
    extract_watermark,
    verify_watermark,
    _compute_image_hash,
)


# ---- Tensor <-> PIL conversion utilities ----

def tensor_to_pil(image_tensor):
    """
    Convert ComfyUI IMAGE tensor to PIL Image.
    
    ComfyUI images are torch tensors (B, H, W, C) in float32, range 0-1.
    Returns a single PIL Image (takes first from batch if B > 1).
    
    Args:
        image_tensor: torch.Tensor of shape (B, H, W, C) or (H, W, C)
    
    Returns:
        PIL.Image in RGB mode
    """
    if isinstance(image_tensor, torch.Tensor):
        # Detach and move to CPU
        img_np = image_tensor.detach().cpu().numpy()
    else:
        img_np = np.array(image_tensor)
    
    # Handle batch dimension
    if img_np.ndim == 4:
        # (B, H, W, C) - take first image
        img_np = img_np[0]
    
    # Convert from float32 [0, 1] to uint8 [0, 255]
    if img_np.dtype == np.float32 or img_np.dtype == np.float64:
        img_np = (np.clip(img_np, 0.0, 1.0) * 255.0).astype(np.uint8)
    else:
        img_np = img_np.astype(np.uint8)
    
    # Handle channel count
    if img_np.shape[2] == 4:
        # RGBA
        img = Image.fromarray(img_np, 'RGBA').convert('RGB')
    elif img_np.shape[2] == 3:
        img = Image.fromarray(img_np, 'RGB')
    elif img_np.shape[2] == 1:
        img = Image.fromarray(img_np[:, :, 0], 'L').convert('RGB')
    else:
        raise ValueError(f"Unexpected number of channels: {img_np.shape[2]}")
    
    return img


def pil_to_tensor(pil_image, target_batch=1):
    """
    Convert PIL Image to ComfyUI IMAGE tensor.
    
    Returns torch tensor of shape (B, H, W, C) in float32, range 0-1.
    
    Args:
        pil_image: PIL.Image in RGB mode
        target_batch: batch size (default 1)
    
    Returns:
        torch.Tensor of shape (B, H, W, 3)
    """
    # Ensure RGB
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    # Convert to numpy uint8 array
    img_np = np.array(pil_image, dtype=np.uint8)
    
    # Convert to float32 [0, 1]
    img_float = img_np.astype(np.float32) / 255.0
    
    # Add batch dimension
    img_batched = np.stack([img_float] * target_batch, axis=0)
    
    # Convert to torch tensor
    tensor = torch.from_numpy(img_batched)
    
    return tensor


# ---- ComfyUI Node Classes ----

class SiliconSignatureEmbed:
    """
    Embed ASIC watermark into image.
    Signs the image with a SHA-256 PoW nonce and embeds via LSB steganography.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "creator_id": ("STRING", {"default": ""}),
                "mode": (["software", "asic"], {"default": "software"}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "SILICON_SIG")
    RETURN_NAMES = ("signed_image", "signature")
    FUNCTION = "embed_signature"
    CATEGORY = "SiliconSignature"
    DESCRIPTION = "Embed a SiliconSignature watermark into an image using LSB steganography with Reed-Solomon error correction"

    def embed_signature(self, image, creator_id="", mode="software"):
        """
        Embed SiliconSignature watermark into image.
        
        Args:
            image: ComfyUI IMAGE tensor (B, H, W, C) float32 [0,1]
            creator_id: optional creator identifier string
            mode: "software" or "asic" signing mode
        
        Returns:
            (signed_image_tensor, signature_dict)
        """
        # Get batch size
        batch_size = image.shape[0] if image.ndim == 4 else 1
        
        # Convert to PIL Image (process first image)
        pil_img = tensor_to_pil(image)
        
        # Check image size
        width, height = pil_img.size
        total_pixels = width * height
        min_pixels_needed = 2000  # Rough estimate for safety
        if total_pixels < min_pixels_needed:
            raise ValueError(
                f"Image too small for watermarking: {width}x{height} = {total_pixels} pixels. "
                f"Need at least ~{min_pixels_needed} pixels."
            )
        
        # Sign the image
        if mode == "asic":
            watermarked_pil, signature = asic_sign(pil_img, creator_id)
        else:
            watermarked_pil, signature = software_sign(pil_img, creator_id)
        
        # Convert back to tensor with same batch size
        signed_tensor = pil_to_tensor(watermarked_pil, target_batch=batch_size)
        
        return (signed_tensor, signature)


class SiliconSignatureVerify:
    """
    Verify SiliconSignature watermark in image.
    Extracts and verifies the embedded signature payload.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
            }
        }
    
    RETURN_TYPES = ("BOOLEAN", "STRING")
    RETURN_NAMES = ("is_authentic", "details")
    FUNCTION = "verify_signature"
    CATEGORY = "SiliconSignature"
    DESCRIPTION = "Verify a SiliconSignature watermark from an image"

    def verify_signature(self, image):
        """
        Verify SiliconSignature watermark in image.
        
        Args:
            image: ComfyUI IMAGE tensor (B, H, W, C) float32 [0,1]
        
        Returns:
            (is_authentic_bool, details_json_string)
        """
        # Convert to PIL Image
        pil_img = tensor_to_pil(image)
        
        # Extract watermark
        extracted = extract_watermark(pil_img)
        
        if extracted is None:
            details = json.dumps({
                "verified": False,
                "error": "No SiliconSignature watermark found in image",
                "integrity": "NONE",
                "confidence": 0.0,
            }, indent=2)
            return (False, details)
        
        # Verify the watermark
        result = verify_watermark(pil_img, extracted)
        
        # Build details string
        details_dict = {
            "verified": result["verified"],
            "integrity": result["integrity"],
            "confidence": round(result["confidence"], 4),
            "signature": result["signature"],
        }
        
        # Add hash comparison info
        if result["signature"] is not None:
            current_hash = _compute_image_hash(pil_img)
            stored_hash = result["signature"].get("hash", "")
            details_dict["hash_match"] = (current_hash == stored_hash)
            details_dict["current_hash"] = current_hash
            details_dict["stored_hash"] = stored_hash
        
        details = json.dumps(details_dict, indent=2)
        
        return (result["verified"], details)


# ---- Node registration mappings ----

NODE_CLASS_MAPPINGS = {
    "SiliconSignatureEmbed": SiliconSignatureEmbed,
    "SiliconSignatureVerify": SiliconSignatureVerify,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SiliconSignatureEmbed": "SiliconSignature Sign",
    "SiliconSignatureVerify": "SiliconSignature Verify",
}
