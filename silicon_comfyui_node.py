"""
SiliconSignature Node for ComfyUI
===================================
Post-generation image signing with hardware-bound proof-of-work.

Installation:
1. Copy this file to ComfyUI/custom_nodes/silicon_signature_node/
2. Copy silicon_signature_node.py to the same folder
3. Restart ComfyUI
4. Find "🔏 Silicon Signature" under image/postprocessing

Author: Francisco Angulo de Lafuente
"""

import os
import sys
import json
import requests
from pathlib import Path

# ComfyUI imports
import comfy
import torch
from PIL import Image
import numpy as np


class SiliconSignatureNode:
    """
    ComfyUI custom node that signs generated images with Silicon signatures.
    """
    
    CATEGORY = "image/postprocessing"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("signed_image", "signature_json")
    FUNCTION = "sign_image"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),  # Batch of images from sampler
                "enabled": ("BOOLEAN", {"default": True}),
                "creator_id": ("STRING", {"default": "comfyui_user"}),
            },
            "optional": {
                "api_url": ("STRING", {"default": "http://localhost:8000"}),
                "api_key": ("STRING", {"default": ""}),
                "watermark": ("BOOLEAN", {"default": True}),
            }
        }
    
    def sign_image(self, images, enabled, creator_id, api_url="http://localhost:8000", api_key="", watermark=True):
        """
        Sign a batch of images with Silicon signatures.
        
        Args:
            images: torch.Tensor [B,H,W,C] — image batch from ComfyUI
            enabled: Whether to sign
            creator_id: Identifier for the creator
            api_url: Silicon API endpoint
            api_key: API key for authentication
            watermark: Whether to embed LSB watermark
            
        Returns:
            (signed_images, signature_json)
        """
        if not enabled:
            return (images, json.dumps({"status": "disabled"}))
        
        # Convert tensor to PIL images
        batch_size = images.shape[0]
        signed_images = []
        signatures = []
        
        for i in range(batch_size):
            # Convert tensor to numpy
            img_np = images[i].cpu().numpy()
            
            # Convert from [H,W,C] float to [H,W,C] uint8
            if img_np.dtype == np.float32 or img_np.dtype == np.float64:
                img_np = (img_np * 255).clip(0, 255).astype(np.uint8)
            
            # Handle different channel orders
            if img_np.shape[-1] == 3:
                # RGB
                img_pil = Image.fromarray(img_np, 'RGB')
            elif img_np.shape[-1] == 4:
                # RGBA
                img_pil = Image.fromarray(img_np, 'RGBA')
            else:
                # Grayscale or other
                img_pil = Image.fromarray(img_np)
            
            # Save temporarily
            temp_path = f"/tmp/comfyui_silicon_{i}.png"
            img_pil.save(temp_path, 'PNG')
            
            try:
                # Call Silicon API
                with open(temp_path, 'rb') as f:
                    files = {'file': f}
                    data = {'creator_id': creator_id}
                    
                    headers = {}
                    if api_key:
                        headers['X-API-Key'] = api_key
                    
                    response = requests.post(
                        f"{api_url}/api/v1/sign",
                        files=files,
                        data=data,
                        headers=headers,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        # Load signed image
                        signed_path = f"/tmp/comfyui_silicon_signed_{i}.png"
                        with open(signed_path, 'wb') as f:
                            f.write(response.content)
                        
                        signed_pil = Image.open(signed_path)
                        signed_np = np.array(signed_pil).astype(np.float32) / 255.0
                        
                        # Ensure correct shape [H,W,C]
                        if len(signed_np.shape) == 2:
                            signed_np = np.stack([signed_np] * 3, axis=-1)
                        
                        signed_images.append(signed_np)
                        signatures.append({
                            "index": i,
                            "status": "signed",
                            "creator": creator_id
                        })
                        
                        # Cleanup
                        os.remove(signed_path)
                    else:
                        # API error, keep original
                        signed_images.append(img_np.astype(np.float32) / 255.0)
                        signatures.append({
                            "index": i,
                            "status": "error",
                            "message": f"HTTP {response.status_code}"
                        })
                
                # Cleanup temp
                os.remove(temp_path)
                
            except Exception as e:
                # On error, keep original image
                signed_images.append(img_np.astype(np.float32) / 255.0)
                signatures.append({
                    "index": i,
                    "status": "error",
                    "message": str(e)
                })
                
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        
        # Stack back into batch tensor
        result_tensor = torch.from_numpy(np.stack(signed_images))
        
        # Move to same device as input
        result_tensor = result_tensor.to(images.device)
        
        return (result_tensor, json.dumps(signatures, indent=2))


class SiliconVerifyNode:
    """
    Verify Silicon signatures on images.
    """
    
    CATEGORY = "image/analysis"
    RETURN_TYPES = ("STRING", "BOOLEAN")
    RETURN_NAMES = ("verification_result", "is_valid")
    FUNCTION = "verify_image"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "api_url": ("STRING", {"default": "http://localhost:8000"}),
            },
            "optional": {
                "api_key": ("STRING", {"default": ""}),
            }
        }
    
    def verify_image(self, images, api_url="http://localhost:8000", api_key=""):
        """Verify a batch of images."""
        
        batch_size = images.shape[0]
        results = []
        all_valid = True
        
        for i in range(batch_size):
            img_np = images[i].cpu().numpy()
            
            if img_np.dtype == np.float32 or img_np.dtype == np.float64:
                img_np = (img_np * 255).clip(0, 255).astype(np.uint8)
            
            if img_np.shape[-1] == 3:
                img_pil = Image.fromarray(img_np, 'RGB')
            elif img_np.shape[-1] == 4:
                img_pil = Image.fromarray(img_np, 'RGBA')
            else:
                img_pil = Image.fromarray(img_np)
            
            temp_path = f"/tmp/comfyui_verify_{i}.png"
            img_pil.save(temp_path, 'PNG')
            
            try:
                with open(temp_path, 'rb') as f:
                    files = {'file': f}
                    headers = {'X-API-Key': api_key} if api_key else {}
                    
                    response = requests.post(
                        f"{api_url}/api/v1/verify",
                        files=files,
                        headers=headers,
                        timeout=30
                    )
                    
                    result = response.json() if response.status_code == 200 else {"error": f"HTTP {response.status_code}"}
                    results.append(result)
                    
                    if not result.get('valid', False) and not result.get('verified', False):
                        all_valid = False
                
                os.remove(temp_path)
                
            except Exception as e:
                results.append({"error": str(e)})
                all_valid = False
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        
        return (json.dumps(results, indent=2), all_valid)


# Node registration for ComfyUI
NODE_CLASS_MAPPINGS = {
    "SiliconSignature": SiliconSignatureNode,
    "SiliconVerify": SiliconVerifyNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SiliconSignature": "🔏 Silicon Signature",
    "SiliconVerify": "🔍 Silicon Verify",
}

# Install instructions
INSTALL_INSTRUCTIONS = """
=== SiliconSignature for ComfyUI ===

1. Create directory:
   mkdir -p ComfyUI/custom_nodes/silicon_signature_node

2. Copy files:
   cp silicon_comfyui_node.py ComfyUI/custom_nodes/silicon_signature_node/
   
3. Create __init__.py:
   echo "from .silicon_comfyui_node import *" > ComfyUI/custom_nodes/silicon_signature_node/__init__.py

4. Restart ComfyUI

5. Find nodes in:
   - image/postprocessing: "🔏 Silicon Signature"
   - image/analysis: "🔍 Silicon Verify"

Usage:
  1. Connect "Save Image" output to "🔏 Silicon Signature" input
  2. Set creator_id (e.g., "artist_name")
  3. Configure API URL (default: http://localhost:8000)
  4. Run workflow — images are auto-signed!
"""

print(INSTALL_INSTRUCTIONS)
