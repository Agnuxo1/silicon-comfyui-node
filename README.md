# SiliconSignature ComfyUI Node

A ComfyUI custom node that embeds and verifies cryptographic watermarks in images using **SiliconSignature** technology. It uses LSB (Least Significant Bit) steganography combined with Reed-Solomon error correction to create tamper-resistant image signatures.

## Features

- **Sign Images**: Embed a cryptographic watermark with SHA-256 Proof-of-Work nonce
- **Verify Images**: Extract and verify watermarks to check authenticity
- **Error Correction**: Reed-Solomon (32-symbol) protects against up to 16 byte errors
- **5x Redundancy**: Signature is repeated 5 times across the image for robustness
- **Software Mode**: CPU-based PoW nonce search for testing without hardware
- **ASIC Mode**: Simulates BM1387 ASIC authentication
- **Any Image Size**: Automatically checks capacity before embedding

## Installation

### Method 1: Manual Install

1. Copy the entire `comfyui-node` folder to your ComfyUI custom nodes directory:
   ```bash
   cp -r /path/to/comfyui-node /path/to/ComfyUI/custom_nodes/SiliconSignature
   ```

2. Restart ComfyUI

3. The nodes will appear under the **SiliconSignature** category

### Method 2: ComfyUI-Manager

If you have ComfyUI-Manager installed, navigate to:
- **Manager > Install via Git URL**
- Enter the repository URL (if published to Git)

### Requirements

All dependencies are already included with ComfyUI:
- `torch`
- `numpy`
- `Pillow`

No additional packages needed.

## Nodes

### 1. SiliconSignature Sign (`SiliconSignatureEmbed`)

Embeds a cryptographic watermark into an image.

**Inputs:**
| Name       | Type   | Default    | Description                          |
|------------|--------|------------|--------------------------------------|
| `image`    | IMAGE  | (required) | Input image tensor (B,H,W,C)         |
| `creator_id`| STRING| `""`       | Optional creator identifier          |
| `mode`     | COMBO  | "software" | Signing mode: "software" or "asic"   |

**Outputs:**
| Name           | Type        | Description                          |
|---------------|-------------|--------------------------------------|
| `signed_image` | IMAGE       | Watermarked image (visually identical) |
| `signature`    | SILICON_SIG | Signature payload dictionary         |

**Signature Payload Format:**
```json
{
  "hash": "65501a37b306f5ac183848bab643350219c18111bfa97c706856b668d3bd5996",
  "nonce": "f16823b5",
  "ntime": "6964c85e",
  "version": "20000000",
  "status": "AUTHENTICATED_BY_BM1387",
  "creator_id": "optional_creator",
  "timestamp": 1715432000
}
```

### 2. SiliconSignature Verify (`SiliconSignatureVerify`)

Extracts and verifies a watermark from a signed image.

**Inputs:**
| Name    | Type  | Default    | Description                  |
|---------|-------|------------|------------------------------|
| `image` | IMAGE | (required) | Image to verify              |

**Outputs:**
| Name           | Type    | Description                          |
|----------------|---------|--------------------------------------|
| `is_authentic` | BOOLEAN | True if watermark is valid           |
| `details`      | STRING  | JSON string with full verification details |

**Details JSON includes:**
- `verified`: Overall verification result
- `integrity`: "FULL", "PARTIAL", or "NONE"
- `confidence`: 0.0 to 1.0 similarity score
- `signature`: Extracted signature payload
- `hash_match`: Whether stored hash matches current image

## How It Works

### Encoding Pipeline
```
JSON payload -> UTF-8 bytes -> Reed-Solomon encode (nsym=32) -> 
4-byte BE length header -> 5x repetition -> bit stream -> 
LSB embed in all RGB channels
```

### Decoding Pipeline
```
LSB extract from RGB channels -> split by 5 repetitions -> 
for each: RS decode -> JSON parse -> return first valid
```

### Technical Details

- **Field**: GF(2^8) with primitive polynomial 0x11d
- **Error Correction**: 32 symbols (corrects up to 16 errors)
- **Primitive element**: 2 (alpha = 0x02)
- **Generator**: Product of (x - alpha^i) for i = 0..31
- **Software Signing**: SHA-256(SHA-256(hash || nonce)) < target_difficulty
- **Target Difficulty**: 0x0000FFFF00000000000000000000000000000000000000000000000000000000

## Workflow Example

```
[Load Image] -> [SiliconSignature Sign] -> [Save Image]
                    |                           |
                    v                           v
              [signature] ->        [SiliconSignature Verify]
                                     [is_authentic]
                                     [details]
```

1. Load or generate an image
2. Pass it through **SiliconSignature Sign** with your creator_id
3. Save the signed image
4. Later, load the saved image and pass through **SiliconSignature Verify**
5. Check the `is_authentic` output to confirm the watermark is valid

## Notes

- The watermark is **invisible** - images look identical before and after signing
- The signature survives **lossless** formats (PNG, BMP, TIFF)
- The signature will be destroyed by **lossy** compression (JPEG, WebP quality < 100)
- Large images have more capacity and redundancy for the watermark
- Minimum recommended image size: ~100x20 pixels (theoretical), ~200x100 (practical)

## File Structure

```
comfyui-node/
|-- __init__.py                  # Node registration
|-- silicon_signature_node.py    # ComfyUI node classes
|-- watermark.py                 # LSB steganography + signing
|-- reedsolomon.py              # Reed-Solomon error correction
|-- README.md                    # This file
```

## License

MIT License - See LICENSE file for details.

## Interoperability

Images signed with this ComfyUI node can be verified by any other SiliconSignature
implementation (browser extension, mobile app, Go/Rust CLI tools, etc.) because all
implementations use the same binary format:
- Same GF(2^8) tables with primitive polynomial 0x11d
- Same generator polynomial construction
- Same 5x repetition + LSB embedding scheme
- Same JSON payload structure
