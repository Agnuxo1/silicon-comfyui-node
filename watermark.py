"""
SiliconSignature watermarking - LSB steganography for images.
Embeds JSON signature payloads using Reed-Solomon error correction.
"""
import json
import hashlib
import struct
import time
import numpy as np
from PIL import Image

from .reedsolomon import rs_encode_msg, rs_correct_msg

# ---- Constants ----
SIGNATURE_REPEATS = 5
RS_NSYM = 32

# Target difficulty for software signing
TARGET_DIFFICULTY = 0x0000FFFF00000000000000000000000000000000000000000000000000000000

# Default signature values
DEFAULT_VERSION = "20000000"
DEFAULT_STATUS = "AUTHENTICATED_BY_BM1387"


def _compute_image_hash(pil_image):
    """Compute SHA-256 hash of image pixel data."""
    data = pil_image.tobytes()
    return hashlib.sha256(data).hexdigest()


def _double_sha256(data_bytes):
    """Double SHA-256 hash."""
    return hashlib.sha256(hashlib.sha256(data_bytes).digest()).digest()


def _uint256_from_bytes(b):
    """Convert 32 bytes to big-endian integer."""
    return int.from_bytes(b, 'big')


def _find_nonce(image_hash_hex, target_difficulty=None):
    """
    Search for a nonce such that SHA-256(SHA-256(hash || nonce)) < target.
    CPU-based Proof-of-Work.
    
    Args:
        image_hash_hex: 64-character hex string of image hash
        target_difficulty: int, defaults to TARGET_DIFFICULTY
    
    Returns:
        (nonce_hex, ntime_hex) tuple
    """
    if target_difficulty is None:
        target_difficulty = TARGET_DIFFICULTY
    
    image_hash_bytes = bytes.fromhex(image_hash_hex)
    ntime = int(time.time())
    ntime_hex = f"{ntime:08x}"
    
    nonce = 0
    while True:
        nonce_hex = f"{nonce:08x}"
        message = image_hash_bytes + bytes.fromhex(nonce_hex)
        h = _double_sha256(message)
        h_int = _uint256_from_bytes(h)
        
        if h_int < target_difficulty:
            return nonce_hex, ntime_hex
        
        nonce = (nonce + 1) & 0xFFFFFFFF
        
        # Safety: if we've searched too long, use whatever we have
        if nonce > 0xFFFFFFFF:
            nonce = 0


def create_signature_payload(image_hash_hex, creator_id="", nonce_hex=None, ntime_hex=None):
    """
    Create the signature payload dictionary.
    
    Args:
        image_hash_hex: 64-char hex string
        creator_id: optional creator identifier
        nonce_hex: 8-char hex string (auto-generated if None)
        ntime_hex: 8-char hex string (auto-generated if None)
    
    Returns:
        dict: signature payload
    """
    if nonce_hex is None or ntime_hex is None:
        nonce_hex, ntime_hex = _find_nonce(image_hash_hex)
    
    payload = {
        "hash": image_hash_hex,
        "nonce": nonce_hex,
        "ntime": ntime_hex,
        "version": DEFAULT_VERSION,
        "status": DEFAULT_STATUS,
        "creator_id": creator_id,
        "timestamp": int(time.time()),
    }
    return payload


def _encode_payload_to_bits(payload_dict):
    """
    Encode signature payload to bit stream:
    JSON -> UTF-8 -> RS encode -> 4-byte BE length header -> 5x repeat
    
    Returns:
        list of bits (0 or 1)
    """
    # JSON to UTF-8 bytes
    json_str = json.dumps(payload_dict, separators=(',', ':'))
    json_bytes = json_str.encode('utf-8')
    
    # Reed-Solomon encode
    rs_data = rs_encode_msg(list(json_bytes), RS_NSYM)
    # rs_data is [ecc | data]
    
    # 4-byte big-endian length header (length of RS-encoded data)
    length_bytes = struct.pack('>I', len(rs_data))
    
    # Combine: length header + RS data
    full_packet = list(length_bytes) + rs_data
    
    # Repeat 5 times
    repeated = full_packet * SIGNATURE_REPEATS
    
    # Convert to bits
    bits = []
    for byte in repeated:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    
    return bits


def _bits_to_bytes(bits):
    """Convert list of bits back to bytes."""
    bytes_list = []
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            if i + j < len(bits):
                byte = (byte << 1) | bits[i + j]
            else:
                byte = byte << 1
        bytes_list.append(byte)
    return bytes(bytes_list)


def embed_watermark(pil_image, signature_dict):
    """
    Embed SiliconSignature watermark into a PIL Image.
    
    Args:
        pil_image: PIL Image (RGB or RGBA)
        signature_dict: signature payload dictionary
    
    Returns:
        PIL Image with watermark embedded
    """
    # Convert to RGB if necessary
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    # Get image dimensions
    width, height = pil_image.size
    total_pixels = width * height
    total_bits_available = total_pixels * 3  # 3 channels per pixel
    
    # Encode payload to bits
    bits = _encode_payload_to_bits(signature_dict)
    
    if len(bits) > total_bits_available:
        raise ValueError(
            f"Image too small for watermark: need {len(bits)} bits, "
            f"have {total_bits_available} bits"
        )
    
    # Convert to numpy array for fast manipulation
    img_array = np.array(pil_image, dtype=np.uint8)
    
    # Flatten RGB channels
    flat = img_array.reshape(-1, 3)
    
    # Embed bits in LSB of all RGB channels
    for i, bit in enumerate(bits):
        channel = i % 3
        pixel_idx = i // 3
        # Clear LSB and set to bit value
        flat[pixel_idx, channel] = (flat[pixel_idx, channel] & 0xFE) | bit
    
    # Reshape back and create PIL Image
    watermarked_array = flat.reshape(height, width, 3)
    watermarked_image = Image.fromarray(watermarked_array, 'RGB')
    
    return watermarked_image


def extract_watermark(pil_image):
    """
    Extract SiliconSignature watermark from a PIL Image.
    
    Args:
        pil_image: PIL Image
    
    Returns:
        dict: signature payload dictionary, or None if not found
    """
    # Convert to RGB if necessary
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    # Convert to numpy array
    img_array = np.array(pil_image, dtype=np.uint8)
    height, width, channels = img_array.shape
    
    # Extract LSB from all RGB channels
    flat = img_array.reshape(-1, 3)
    bits = []
    for pixel in flat:
        for c in range(3):
            bits.append(pixel[c] & 1)
    
    # Convert bits to bytes
    data = _bits_to_bytes(bits)
    
    if len(data) < 4:
        return None
    
    # Read 4-byte length header
    packet_length = struct.unpack('>I', data[:4])[0]
    
    if packet_length < RS_NSYM or packet_length > 255:
        return None
    
    # Total expected size: 4 (header) + packet_length * 5 (repeats)
    total_expected = 4 + packet_length * SIGNATURE_REPEATS
    if len(data) < total_expected:
        return None
    
    # Try each repetition
    for rep in range(SIGNATURE_REPEATS):
        start = 4 + rep * packet_length
        end = start + packet_length
        if end > len(data):
            continue
        
        rs_packet = list(data[start:end])
        
        # Reed-Solomon decode
        try:
            decoded = rs_correct_msg(rs_packet, RS_NSYM)
            if decoded is not None:
                json_bytes = bytes(decoded)
                json_str = json_bytes.decode('utf-8')
                payload = json.loads(json_str)
                return payload
        except Exception:
            continue
    
    return None


def verify_watermark(pil_image, extracted_payload=None):
    """
    Verify a SiliconSignature watermark.
    
    Args:
        pil_image: PIL Image
        extracted_payload: optional pre-extracted payload (saves re-extraction)
    
    Returns:
        dict: verification result with keys 'verified', 'signature', 'integrity', 'confidence'
    """
    if extracted_payload is None:
        extracted_payload = extract_watermark(pil_image)
    
    if extracted_payload is None:
        return {
            "verified": False,
            "signature": None,
            "integrity": "NONE",
            "confidence": 0.0,
        }
    
    # Verify image hash matches
    current_hash = _compute_image_hash(pil_image)
    stored_hash = extracted_payload.get("hash", "")
    
    if current_hash == stored_hash:
        integrity = "FULL"
        confidence = 1.0
    else:
        # Hash mismatch - image may have been modified
        # Check how many bits differ
        try:
            current_bytes = bytes.fromhex(current_hash)
            stored_bytes = bytes.fromhex(stored_hash)
            if len(current_bytes) == len(stored_bytes):
                diff_bits = sum(bin(a ^ b).count('1') for a, b in zip(current_bytes, stored_bytes))
                confidence = max(0.0, 1.0 - (diff_bits / (len(current_bytes) * 8)))
                if confidence > 0.8:
                    integrity = "PARTIAL"
                else:
                    integrity = "NONE"
            else:
                confidence = 0.0
                integrity = "NONE"
        except Exception:
            confidence = 0.0
            integrity = "NONE"
    
    # Verify PoW nonce
    nonce_valid = False
    try:
        image_hash_bytes = bytes.fromhex(stored_hash)
        nonce_hex = extracted_payload.get("nonce", "00000000")
        message = image_hash_bytes + bytes.fromhex(nonce_hex)
        h = _double_sha256(message)
        h_int = _uint256_from_bytes(h)
        nonce_valid = h_int < TARGET_DIFFICULTY
    except Exception:
        nonce_valid = False
    
    verified = nonce_valid and integrity != "NONE"
    
    return {
        "verified": verified,
        "signature": extracted_payload,
        "integrity": integrity,
        "confidence": confidence,
    }


def software_sign(pil_image, creator_id=""):
    """
    Sign an image using software (CPU) mode.
    
    Args:
        pil_image: PIL Image
        creator_id: optional creator identifier
    
    Returns:
        tuple: (watermarked PIL Image, signature dict)
    """
    # Compute hash of original image
    image_hash = _compute_image_hash(pil_image)
    
    # Find nonce via CPU PoW
    nonce_hex, ntime_hex = _find_nonce(image_hash)
    
    # Create signature payload
    signature = create_signature_payload(
        image_hash_hex=image_hash,
        creator_id=creator_id,
        nonce_hex=nonce_hex,
        ntime_hex=ntime_hex,
    )
    
    # Embed watermark
    watermarked = embed_watermark(pil_image, signature)
    
    return watermarked, signature


def asic_sign(pil_image, creator_id=""):
    """
    Sign an image in ASIC mode (same format as software, but marks as ASIC-authenticated).
    
    Args:
        pil_image: PIL Image
        creator_id: optional creator identifier
    
    Returns:
        tuple: (watermarked PIL Image, signature dict)
    """
    # Compute hash of original image
    image_hash = _compute_image_hash(pil_image)
    
    # Find nonce via CPU PoW (simulating ASIC)
    nonce_hex, ntime_hex = _find_nonce(image_hash)
    
    # Create signature payload with ASIC status
    signature = create_signature_payload(
        image_hash_hex=image_hash,
        creator_id=creator_id,
        nonce_hex=nonce_hex,
        ntime_hex=ntime_hex,
    )
    signature["status"] = "AUTHENTICATED_BY_BM1387"
    
    # Embed watermark
    watermarked = embed_watermark(pil_image, signature)
    
    return watermarked, signature
