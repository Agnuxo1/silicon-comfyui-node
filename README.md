# SiliconSignature — ComfyUI Custom Node

Hardware-bound image authentication node for [ComfyUI](https://github.com/comfyanonymous/ComfyUI). Automatically sign AI-generated images with ASIC proof-of-work watermarks.

## 🎯 What It Does

After your image generation pipeline completes, this node:
1. Takes the generated image tensor
2. Computes SHA-256 hash of pixel data
3. Generates ASIC-bound nonce via proof-of-work
4. Embeds Reed-Solomon protected signature in LSB
5. Outputs the signed image + metadata

## 📦 Installation

### Option 1: ComfyUI Manager (Recommended)
1. Open ComfyUI → Manager → Custom Nodes Manager
2. Search: `SiliconSignature`
3. Click Install
4. Restart ComfyUI

### Option 2: Manual
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Agnuxo1/silicon-comfyui-node.git
```
Restart ComfyUI.

## 🚀 Usage

In your ComfyUI workflow:

1. Find **SiliconSignature › Sign Image** in the node menu
2. Connect the `IMAGE` output from your latent decode node
3. (Optional) Set `creator_id` to your name/handle
4. The node outputs a signed image + signature metadata

### Node Inputs
| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `image` | IMAGE | required | Image tensor from VAE decode |
| `creator_id` | STRING | "comfyui_user" | Creator identifier |
| `redundancy` | INT | 5 | Reed-Solomon redundancy copies |
| `asic_mode` | BOOLEAN | false | Use real ASIC (requires hardware) |

### Node Outputs
| Output | Type | Description |
|--------|------|-------------|
| `signed_image` | IMAGE | Watermarked image (visually identical) |
| `signature_meta` | STRING | JSON with nonce, hash, timestamp |
| `verification_url` | STRING | URL to verify on silicon.p2pclaw.com |

## 🔍 Verify a Signed Image

Use the **SiliconSignature › Verify Image** node:
1. Connect the signed image
2. Node outputs: `valid` (boolean), `creator`, `timestamp`

## 🏗️ Example Workflow

```
[Load Checkpoint] → [KSampler] → [VAE Decode] → [SiliconSignature Sign] → [Save Image]
                                                          ↓
                                                   [Preview Sig]
```

## ⚙️ Configuration

The node auto-detects ASIC hardware via USB. If no ASIC found, it falls back to CPU software mode (still secure, just slower).

Environment variables:
- `SILICON_ASIC_PATH` — USB device path (default: auto-detect)
- `SILICON_DIFFICULTY` — PoW difficulty (default: 24 bits)
- `SILICON_API_URL` — Optional remote API for cloud signing

## 📁 Files

| File | Purpose |
|------|---------|
| `silicon_comfyui_node.py` | Main node implementation (sign + verify) |

## 🔗 Links

- 🌐 Web App: https://agnuxo1.github.io/siliconsignature-web/
- 📦 Main Repo: https://github.com/Agnuxo1/Secure_image_generation_with_ASIC_signature
- 🏠 Project Hub: https://p2pclaw.com

## 📝 License

MIT — Francisco Angulo de Lafuente (@Agnuxo1)

**Built for the P2PCLAW Ecosystem**
