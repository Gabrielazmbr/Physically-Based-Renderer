"""
Post-process denoising via Intel Open Image Denoise (OIDN).

Not a Mitsuba plugin — this runs on a rendered image after the fact,
using the albedo and normal AOVs from path_tracer.py as auxiliary
feature buffers to help the denoiser distinguish real detail from noise.

Requires: uv pip install pyoidn
"""
import numpy as np
import pyoidn


def denoise(color, albedo=None, normal=None, hdr=True, device_type=None):
    """
    Denoises a rendered image.

    color   : (H, W, 3) float array — the noisy render
    albedo  : (H, W, 3) optional flat albedo AOV
    normal  : (H, W, 3) optional shading-normal AOV, raw (-1..1)
    hdr     : True for unbounded linear renders (the normal case here).
              Must be False only for already-tonemapped [0,1] input.

    Auxiliary buffers are optional — OIDN works without them, just less
    well, since it has no way to tell a real texture edge from noise.
    """
    c = np.ascontiguousarray(color, dtype=np.float32)
    out = np.zeros_like(c)

    if device_type is None:
        device_type = pyoidn.OIDN_DEVICE_TYPE_CPU
    dev = pyoidn.Device(device_type)
    dev.commit()

    flt = pyoidn.Filter(dev, "RT")
    flt.set_image(pyoidn.OIDN_IMAGE_COLOR, c, pyoidn.OIDN_FORMAT_FLOAT3)
    if albedo is not None:
        a = np.ascontiguousarray(albedo, dtype=np.float32)
        flt.set_image(pyoidn.OIDN_IMAGE_ALBEDO, a, pyoidn.OIDN_FORMAT_FLOAT3)
    if normal is not None:
        n = np.ascontiguousarray(normal, dtype=np.float32)
        flt.set_image(pyoidn.OIDN_IMAGE_NORMAL, n, pyoidn.OIDN_FORMAT_FLOAT3)
    flt.set_image(pyoidn.OIDN_IMAGE_OUTPUT, out, pyoidn.OIDN_FORMAT_FLOAT3)
    flt.set_bool("hdr", hdr)  # essential: renders are unbounded, not [0,1]
    flt.commit()
    flt.execute()

    err = dev.get_error()
    flt.release()
    dev.release()
    if err:
        raise RuntimeError(f"OIDN error: {err}")

    return out


def denoise_aov_render(img, hdr=True, device_type=None):
    """
    Convenience wrapper for a render made with with_aovs=True.
    Expects the 10-channel layout from path_tracer.py:
      0:3 colour, 3:6 albedo, 6:9 normal, 9 depth (unused by OIDN).
    Falls back to colour-only denoising for a plain 3-channel image.
    """
    arr = np.asarray(img)
    if arr.shape[-1] >= 9:
        return denoise(arr[..., 0:3], arr[..., 3:6], arr[..., 6:9], hdr, device_type)
    return denoise(arr[..., 0:3], hdr=hdr, device_type=device_type)

def denoise_composite_aov_render(img, emitter_threshold=2.0, hdr=True):
    """
    Convenience wrapper combining denoise_aov_render's channel-splitting
    with denoise_composite's emitter masking — the correct default entry
    point for a with_aovs=True render (see Section 17: composite masking
    is not optional, it's what makes the RMSE improvement real).
    """
    arr = np.asarray(img)
    color = arr[..., 0:3]
    albedo = arr[..., 3:6] if arr.shape[-1] >= 9 else None
    normal = arr[..., 6:9] if arr.shape[-1] >= 9 else None
    return denoise_composite(color, albedo, normal, emitter_threshold, hdr)


def denoise_composite(color, albedo=None, normal=None, emitter_threshold=2.0, hdr=True):
    """
    Denoises, then restores the original pixels wherever a light source is
    directly visible. OIDN's albedo demodulation assumes colour = albedo x
    illumination, which is false for emissive surfaces — filtering them
    smears sharp, very bright edges and dominates error metrics.

    Emitters are identified by a luminance threshold: a deliberate
    simplification. The principled alternative is a dedicated emission AOV
    (captured at the first hit, subtracted before denoising and added back
    after), which would not depend on a magic number.
    """
    out = denoise(color, albedo, normal, hdr=hdr)
    mask = (np.asarray(color).mean(axis=-1) > emitter_threshold)[..., None]
    return np.where(mask, color, out)
