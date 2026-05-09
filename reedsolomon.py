"""
Pure Python Reed-Solomon error correction.
GF(2^8) with primitive polynomial 0x11d.
Corrects up to nsym/2 errors.
"""

# ---- GF(2^8) with primitive polynomial 0x11d ----
GF_EXP = [0] * 512
GF_LOG = [0] * 256

GF_PRIM_POLY = 0x11d  # x^8 + x^4 + x^3 + x^2 + 1


def _init_gf_tables():
    """Initialize GF(2^8) exponent and log tables with primitive polynomial 0x11d."""
    GF_EXP[0] = 1
    GF_LOG[0] = 0
    x = 1
    for i in range(1, 255):
        x <<= 1
        if x & 0x100:
            x ^= GF_PRIM_POLY
        x &= 0xFF
        GF_EXP[i] = x
        GF_LOG[x] = i
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i - 255]


_init_gf_tables()


def gf_mul(a, b):
    """GF multiplication using log table."""
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


def gf_div(a, b):
    """GF division using log table."""
    if b == 0:
        raise ZeroDivisionError("GF division by zero")
    if a == 0:
        return 0
    return GF_EXP[(GF_LOG[a] - GF_LOG[b]) % 255]


def gf_pow(a, n):
    """GF power."""
    if a == 0:
        return 0
    return GF_EXP[(GF_LOG[a] * n) % 255]


def gf_poly_mul(p, q):
    """Multiply two GF polynomials (ascending order)."""
    r = [0] * (len(p) + len(q) - 1)
    for j in range(len(q)):
        if q[j] == 0:
            continue
        for i in range(len(p)):
            if p[i] == 0:
                continue
            r[i + j] ^= gf_mul(p[i], q[j])
    return r


def gf_poly_eval(poly, x):
    """Evaluate a GF polynomial at point x using Horner's method."""
    y = poly[-1]
    for i in range(len(poly) - 2, -1, -1):
        y = gf_mul(y, x) ^ poly[i]
    return y


# ---- Reed-Solomon encoding ----

def rs_generator_poly(nsym):
    """Build RS generator polynomial: product of (x - alpha^i) for i=0..nsym-1."""
    g = [1]
    for i in range(nsym):
        g = gf_poly_mul(g, [gf_pow(2, i), 1])
    return g


# Cache generator polynomials
_GEN_POLY_CACHE = {}


def _get_generator_poly(nsym):
    """Get cached generator polynomial."""
    if nsym not in _GEN_POLY_CACHE:
        _GEN_POLY_CACHE[nsym] = rs_generator_poly(nsym)
    return _GEN_POLY_CACHE[nsym]


def rs_encode_msg(data, nsym=32):
    """
    Encode data bytes with Reed-Solomon error correction.
    Uses polynomial division (systematic encoding).
    Returns [ecc_bytes | data_bytes].

    Args:
        data: list or bytes of message data
        nsym: number of error correction symbols (default 32)

    Returns:
        List of integers: ECC bytes followed by data bytes
    """
    if isinstance(data, (bytes, bytearray)):
        data = list(data)

    if len(data) + nsym > 255:
        raise ValueError(f"Message too long: {len(data)} + {nsym} > 255")

    gen = _get_generator_poly(nsym)
    # Message polynomial shifted by x^nsym
    msg = [0] * nsym + list(data)
    # Polynomial division: find remainder of msg / gen
    for i in range(len(data) - 1, -1, -1):
        coef = msg[nsym + i]
        if coef != 0:
            for j in range(nsym + 1):
                msg[i + j] ^= gf_mul(gen[j], coef)
    # Remainder is in first nsym positions
    return msg[:nsym] + list(data)


# ---- Reed-Solomon decoding ----

def _rs_calc_syndromes(msg, nsym):
    """Calculate syndromes S_i = msg(alpha^i) for i=0..nsym-1."""
    return [gf_poly_eval(msg, gf_pow(2, i)) for i in range(nsym)]


def _rs_check_syndromes(syndromes):
    """Check if all syndromes are zero (no errors)."""
    return all(s == 0 for s in syndromes)


def _berlekamp_massey(synd, nsym):
    """
    Berlekamp-Massey algorithm to find error locator polynomial.
    Returns error locator polynomial Lambda(x) in ascending order.
    """
    C = [1] + [0] * nsym  # Error locator
    B = [1] + [0] * nsym  # Previous error locator
    L = 0  # Number of errors found
    m = 1  # Shift counter

    for n in range(nsym):
        # Calculate discrepancy
        delta = synd[n]
        for i in range(1, L + 1):
            if C[i] != 0 and synd[n - i] != 0:
                delta ^= gf_mul(C[i], synd[n - i])

        if delta == 0:
            m += 1
        elif 2 * L <= n:
            T = list(C)
            for i in range(len(B)):
                if m + i < len(C) and B[i] != 0:
                    C[m + i] ^= gf_mul(delta, B[i])
            L = n + 1 - L
            B = [gf_div(x, delta) for x in T]
            m = 1
        else:
            for i in range(len(B)):
                if m + i < len(C) and B[i] != 0:
                    C[m + i] ^= gf_mul(delta, B[i])
            m += 1

    # Trim trailing zeros
    while len(C) > 0 and C[-1] == 0:
        C.pop()
    if len(C) == 0:
        C = [1]
    return C


def _chien_search(err_loc, nmess):
    """
    Chien search: find roots of error locator polynomial.
    Returns list of error positions or None if failed.
    """
    errs = len(err_loc) - 1
    err_pos = []
    for i in range(nmess):
        x = gf_pow(2, (255 - i) % 255)
        if gf_poly_eval(err_loc, x) == 0:
            err_pos.append(i)
    if len(err_pos) != errs:
        return None
    return err_pos


def _solve_error_values(synd, err_pos):
    """
    Solve for error values using a Vandermonde system.
    S_i = sum_k Y_k * X_k^i where X_k = alpha^{pos_k}.
    Gaussian elimination in GF(2^8).
    """
    X = [gf_pow(2, pos) for pos in err_pos]
    n = len(err_pos)

    # Build Vandermonde matrix A and vector b
    A = []
    for i in range(n):
        row = [gf_pow(x, i) for x in X]
        A.append(row)
    b = synd[:n]

    # Gaussian elimination
    for col in range(n):
        pivot = None
        for row in range(col, n):
            if A[row][col] != 0:
                pivot = row
                break
        if pivot is None:
            continue
        if pivot != col:
            A[col], A[pivot] = A[pivot], A[col]
            b[col], b[pivot] = b[pivot], b[col]

        pivot_val = A[col][col]
        for row in range(col + 1, n):
            if A[row][col] != 0:
                factor = gf_div(A[row][col], pivot_val)
                for c in range(col, n):
                    A[row][c] ^= gf_mul(factor, A[col][c])
                b[row] ^= gf_mul(factor, b[col])

    # Back substitution
    Y = [0] * n
    for i in range(n - 1, -1, -1):
        val = b[i]
        for j in range(i + 1, n):
            val ^= gf_mul(A[i][j], Y[j])
        if A[i][i] == 0:
            return None
        Y[i] = gf_div(val, A[i][i])

    return Y


def rs_decode_msg(data, nsym=32):
    """
    Decode Reed-Solomon encoded message.
    Returns original data bytes or raises ValueError if uncorrectable.

    Args:
        data: list of integers [ecc | data] format
        nsym: number of error correction symbols (default 32)

    Returns:
        List of integers: original data bytes
    """
    if isinstance(data, (bytes, bytearray)):
        data = list(data)

    msg = list(data)

    if len(msg) > 255:
        raise ValueError(f"Message too long: {len(msg)} > 255")

    # Calculate syndromes
    synd = _rs_calc_syndromes(msg, nsym)

    # If all syndromes are zero, no errors
    if _rs_check_syndromes(synd):
        return msg[nsym:]

    # Berlekamp-Massey to find error locator
    err_loc = _berlekamp_massey(synd, nsym)
    errs = len(err_loc) - 1

    if errs == 0 or errs > nsym // 2:
        raise ValueError("Too many errors to correct")

    # Chien search to find error positions
    err_pos = _chien_search(err_loc, len(msg))
    if err_pos is None:
        raise ValueError("Could not locate all errors")

    # Solve for error values
    Y = _solve_error_values(synd, err_pos)
    if Y is None:
        raise ValueError("Could not solve for error values")

    # Apply corrections
    for pos, y in zip(err_pos, Y):
        msg[pos] ^= y

    # Verify syndromes after correction
    synd = _rs_calc_syndromes(msg, nsym)
    if not _rs_check_syndromes(synd):
        raise ValueError("Correction failed - residual errors")

    return msg[nsym:]


def rs_correct_msg(data, nsym=32):
    """
    Decode with robust error handling.
    Returns original data bytes, or None if uncorrectable.

    Args:
        data: list of integers [ecc | data] format
        nsym: number of error correction symbols

    Returns:
        List of integers: original data bytes, or None
    """
    try:
        return rs_decode_msg(data, nsym)
    except Exception:
        return None
