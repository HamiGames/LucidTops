f""" this is the image schema for the LucidTops blockchain's reward token generation
[genesisTokens]: a series of sexy topless goddesses, with a sense of mythology and lore, they will all be unique images for the genesis tokens.and
all other images will be a series of randomly generated, heroes, villains, creatures, and other characters from mythology and lore, they will all be unique images for the other tokens, 
randomly output NSFW images in the schema for the other tokens. this will use a set of character personality profiles to generate the images.
the image generation will be done in via a universe wide search engine or a text to image AI model. (perchance.org)
"""

import hashlib
import os
import struct
import sys
import urllib.parse
import zlib
from pathlib import Path
from typing import Any

BLOCKCHAIN_DIR = Path(__file__).resolve().parent

if str(BLOCKCHAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BLOCKCHAIN_DIR))

from configBlock import LUCID_TOPS_ROOT  # noqa: E402

MAX_TOKEN_IMAGE_BYTES = 1_048_576
DEFAULT_IMAGE_WIDTH = 512
DEFAULT_IMAGE_HEIGHT = 512

LUCID_IMAGE_SCHEMA_PROFILE_ENV = "LUCID_IMAGE_SCHEMA_PROFILE"
IMAGE_GENERATOR_URL_ENV = "IMAGE_GENERATOR_URL"
IMAGE_GENERATOR_ENABLED_ENV = "IMAGE_GENERATOR_ENABLED"
IMAGE_GENERATOR_HOST_ENV = "IMAGE_GENERATOR_HOST"
IMAGE_GENERATOR_PORT_ENV = "IMAGE_GENERATOR_PORT"
IMAGE_GENERATOR_TIMEOUT_ENV = "IMAGE_GENERATOR_TIMEOUT_SECONDS"

DEFAULT_IMAGE_GENERATOR_URL = "https://perchance.org"
DEFAULT_STANDARD_PROFILE = "standardTokens"
GENESIS_SCHEMA_PROFILE = "genesisTokens"

SCHEMA_PROFILES: dict[str, dict[str, Any]] = {
    GENESIS_SCHEMA_PROFILE: {
        "label": "genesisTokens",
        "theme": "mythology_goddess_lore",
        "palette": ("#d4af37", "#f5e6cc", "#1a237e", "#4a148c", "#00695c"),
        "composition": "radial_halo_lore",
        "content_profile": "genesis_mythology",
    },
    DEFAULT_STANDARD_PROFILE: {
        "label": "standardTokens",
        "theme": "mythology_character_roster",
        "palette": ("#263238", "#b71c1c", "#1565c0", "#2e7d32", "#6a1b9a"),
        "composition": "character_silhouette_lore",
        "content_profile": "mythology_cast",
    },
}

CHARACTER_PERSONALITY_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "archetype": "hero",
        "name": "Solar Champion",
        "traits": ("courage", "honor", "resolve"),
        "mythology": "sky_legends",
        "palette_shift": (1.0, 0.92, 0.78),
    },
    {
        "archetype": "villain",
        "name": "Shadow Sovereign",
        "traits": ("ambition", "cunning", "dominion"),
        "mythology": "underworld_lore",
        "palette_shift": (0.55, 0.48, 0.72),
    },
    {
        "archetype": "creature",
        "name": "Primordial Warden",
        "traits": ("instinct", "ancient", "wild"),
        "mythology": "deep_forest_myth",
        "palette_shift": (0.62, 1.05, 0.66),
    },
    {
        "archetype": "hero",
        "name": "Tidecaller",
        "traits": ("mercy", "flow", "memory"),
        "mythology": "ocean_sagas",
        "palette_shift": (0.74, 0.88, 1.18),
    },
    {
        "archetype": "villain",
        "name": "Iron Oracle",
        "traits": ("prophecy", "control", "silence"),
        "mythology": "forged_pantheon",
        "palette_shift": (0.82, 0.76, 0.64),
    },
    {
        "archetype": "creature",
        "name": "Starlit Chimera",
        "traits": ("hybrid", "mystery", "wander"),
        "mythology": "celestial_beasts",
        "palette_shift": (1.08, 0.84, 1.22),
    },
)


def _sha512_hex(value: str) -> str:
    return hashlib.sha512(value.encode("utf-8")).hexdigest()


def resolve_schema_profile(*, profile: str | None = None) -> str:
    """Resolve active schema profile from argument or DockerDNS-friendly env."""
    selected = (profile or os.environ.get(LUCID_IMAGE_SCHEMA_PROFILE_ENV, "")).strip()
    if selected in SCHEMA_PROFILES:
        return selected
    return DEFAULT_STANDARD_PROFILE


def select_character_profile(*, lucid_token_id: str, owner_id: str) -> dict[str, Any]:
    """Pick a deterministic mythology character profile for a token."""
    digest = _sha512_hex(f"{lucid_token_id}:{owner_id}:character")
    index = int(digest[:8], 16) % len(CHARACTER_PERSONALITY_PROFILES)
    profile = dict(CHARACTER_PERSONALITY_PROFILES[index])
    profile["seed"] = digest[:16]
    return profile


def build_generation_prompt(
    *,
    lucid_token_id: str,
    owner_id: str,
    schema_profile: str,
    character_profile: dict[str, Any],
) -> str:
    """Build a text prompt for universe search / text-to-image providers (perchance.org)."""
    schema = SCHEMA_PROFILES[schema_profile]
    traits = ", ".join(character_profile.get("traits", ()))
    return (
        f"LucidToken {lucid_token_id}; owner {owner_id}; schema {schema['label']}; "
        f"theme {schema['theme']}; archetype {character_profile.get('archetype')}; "
        f"character {character_profile.get('name')}; mythology {character_profile.get('mythology')}; "
        f"traits {traits}; unique mythology lore portrait"
    )


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _blend(a: tuple[int, int, int], b: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    ratio = max(0.0, min(1.0, ratio))
    return (
        int(a[0] + (b[0] - a[0]) * ratio),
        int(a[1] + (b[1] - a[1]) * ratio),
        int(a[2] + (b[2] - a[2]) * ratio),
    )


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _render_procedural_png(
    *,
    lucid_token_id: str,
    owner_id: str,
    schema_profile: str,
    character_profile: dict[str, Any],
    width: int = DEFAULT_IMAGE_WIDTH,
    height: int = DEFAULT_IMAGE_HEIGHT,
    max_bytes: int = MAX_TOKEN_IMAGE_BYTES,
) -> bytes:
    """Render a unique PNG from schema + character personality (stdlib, container-safe)."""
    schema = SCHEMA_PROFILES[schema_profile]
    palette = [_hex_to_rgb(color) for color in schema["palette"]]
    shift = character_profile.get("palette_shift", (1.0, 1.0, 1.0))
    shifted_palette = [
        (
            min(255, int(red * shift[0])),
            min(255, int(green * shift[1])),
            min(255, int(blue * shift[2])),
        )
        for red, green, blue in palette
    ]

    seed = _sha512_hex(f"{lucid_token_id}:{owner_id}:{schema_profile}:{character_profile['seed']}")
    pixels = bytearray()
    center_x = width / 2.0
    center_y = height / 2.0
    max_radius = (center_x**2 + center_y**2) ** 0.5

    for y in range(height):
        row_seed = _sha512_hex(f"{seed}:row:{y}")
        for x in range(width):
            dx = x - center_x
            dy = y - center_y
            radius = ((dx**2 + dy**2) ** 0.5) / max_radius
            angle_seed = int(row_seed[(x * 2) % len(row_seed) : (x * 2) % len(row_seed) + 2], 16)

            if schema_profile == GENESIS_SCHEMA_PROFILE:
                mix = (radius * 0.7) + ((angle_seed % 97) / 97.0 * 0.3)
                color_a = shifted_palette[angle_seed % len(shifted_palette)]
                color_b = shifted_palette[(angle_seed + 2) % len(shifted_palette)]
                red, green, blue = _blend(color_a, color_b, mix)
                highlight = max(0, int((1.0 - radius) * 40))
                red = min(255, red + highlight)
                green = min(255, green + highlight // 2)
            else:
                archetype = str(character_profile.get("archetype", "hero"))
                if archetype == "villain":
                    mix = abs(dx) / center_x
                elif archetype == "creature":
                    mix = abs(dy) / center_y
                else:
                    mix = (radius + ((angle_seed % 50) / 50.0)) / 2.0
                color_a = shifted_palette[angle_seed % len(shifted_palette)]
                color_b = shifted_palette[(angle_seed + 1) % len(shifted_palette)]
                red, green, blue = _blend(color_a, color_b, mix)

            pixels.extend((red, green, blue))

    raw_rows = b"".join(
        b"\x00" + bytes(pixels[y * width * 3 : (y + 1) * width * 3]) for y in range(height)
    )
    compressed = zlib.compress(raw_rows, 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    metadata = {
        "LucidTokenID": lucid_token_id,
        "OwnerID": owner_id,
        "SchemaProfile": schema_profile,
        "CharacterArchetype": character_profile.get("archetype"),
        "CharacterName": character_profile.get("name"),
        "Mythology": character_profile.get("mythology"),
        "ImageGenerator": "procedural",
    }
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(_png_chunk(b"IHDR", ihdr))
    for key, value in metadata.items():
        png.extend(_png_chunk(b"tEXt", f"{key}\x00{value}".encode("utf-8")))
    png.extend(_png_chunk(b"IDAT", compressed))
    png.extend(_png_chunk(b"IEND", b""))

    if len(png) > max_bytes:
        return _render_procedural_png(
            lucid_token_id=lucid_token_id,
            owner_id=owner_id,
            schema_profile=schema_profile,
            character_profile=character_profile,
            width=max(128, width // 2),
            height=max(128, height // 2),
            max_bytes=max_bytes,
        )
    return bytes(png)


def _image_cache_path(*, lucid_token_id: str) -> Path:
    cache_dir = LUCID_TOPS_ROOT / "Lucidtoken" / ".schema_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{lucid_token_id}.png"


def _try_external_generator(
    *,
    prompt: str,
    max_bytes: int,
    timeout_seconds: float,
) -> bytes | None:
    """Optional text-to-image fetch (DockerDNS host or perchance.org URL), with safe fallback."""
    enabled = os.environ.get(IMAGE_GENERATOR_ENABLED_ENV, "false").lower() in {"1", "true", "yes"}
    if not enabled:
        return None

    host = os.environ.get(IMAGE_GENERATOR_HOST_ENV, "").strip()
    port = os.environ.get(IMAGE_GENERATOR_PORT_ENV, "8090").strip()
    base_url = os.environ.get(IMAGE_GENERATOR_URL_ENV, DEFAULT_IMAGE_GENERATOR_URL).strip()

    if host:
        request_url = f"http://{host}:{port}/generate?{urllib.parse.urlencode({'prompt': prompt})}"
    else:
        request_url = f"{base_url.rstrip('/')}/api/generate?{urllib.parse.urlencode({'prompt': prompt})}"

    try:
        import httpx
    except ImportError:
        return None

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(request_url)
            if response.status_code != 200:
                return None
            content_type = response.headers.get("content-type", "")
            body = response.content
            if not body or len(body) > max_bytes:
                return None
            if "image/png" in content_type or body.startswith(b"\x89PNG\r\n\x1a\n"):
                return body
            payload = response.json()
            if isinstance(payload, dict):
                image_url = payload.get("image_url") or payload.get("url")
                if isinstance(image_url, str) and image_url:
                    image_response = client.get(image_url)
                    if (
                        image_response.status_code == 200
                        and image_response.content
                        and len(image_response.content) <= max_bytes
                    ):
                        return image_response.content
    except Exception:
        return None
    return None


def render_token_image(
    *,
    lucid_token_id: str,
    owner_id: str,
    max_bytes: int = MAX_TOKEN_IMAGE_BYTES,
    schema_profile: str | None = None,
) -> bytes:
    """Generate a LucidToken PNG using the active image schema profile."""
    profile_name = resolve_schema_profile(profile=schema_profile)
    if profile_name == GENESIS_SCHEMA_PROFILE:
        character = {
            "archetype": "genesis",
            "name": "Genesis Mythology",
            "traits": ("lore", "mythology", "unique"),
            "mythology": "genesis_pantheon",
            "palette_shift": (1.0, 1.0, 1.0),
            "seed": _sha512_hex(f"{lucid_token_id}:{owner_id}:genesis")[:16],
        }
    else:
        character = select_character_profile(lucid_token_id=lucid_token_id, owner_id=owner_id)

    prompt = build_generation_prompt(
        lucid_token_id=lucid_token_id,
        owner_id=owner_id,
        schema_profile=profile_name,
        character_profile=character,
    )

    cache_path = _image_cache_path(lucid_token_id=lucid_token_id)
    if cache_path.exists():
        cached = cache_path.read_bytes()
        if 0 < len(cached) <= max_bytes:
            return cached

    timeout_seconds = float(os.environ.get(IMAGE_GENERATOR_TIMEOUT_ENV, "8"))
    external = _try_external_generator(
        prompt=prompt,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
    )
    if external is not None:
        cache_path.write_bytes(external)
        return external

    png_bytes = _render_procedural_png(
        lucid_token_id=lucid_token_id,
        owner_id=owner_id,
        schema_profile=profile_name,
        character_profile=character,
        max_bytes=max_bytes,
    )
    cache_path.write_bytes(png_bytes)
    return png_bytes


def schema_metadata(
    *,
    lucid_token_id: str,
    owner_id: str,
    schema_profile: str | None = None,
) -> dict[str, Any]:
    """Return schema metadata for ledger/debug without generating image bytes."""
    profile_name = resolve_schema_profile(profile=schema_profile)
    character = (
        {
            "archetype": "genesis",
            "name": "Genesis Mythology",
            "traits": ("lore", "mythology", "unique"),
            "mythology": "genesis_pantheon",
            "seed": _sha512_hex(f"{lucid_token_id}:{owner_id}:genesis")[:16],
        }
        if profile_name == GENESIS_SCHEMA_PROFILE
        else select_character_profile(lucid_token_id=lucid_token_id, owner_id=owner_id)
    )
    return {
        "schema_profile": profile_name,
        "character_profile": character,
        "prompt": build_generation_prompt(
            lucid_token_id=lucid_token_id,
            owner_id=owner_id,
            schema_profile=profile_name,
            character_profile=character,
        ),
        "generator_url": os.environ.get(IMAGE_GENERATOR_URL_ENV, DEFAULT_IMAGE_GENERATOR_URL),
        "generator_enabled": os.environ.get(IMAGE_GENERATOR_ENABLED_ENV, "false"),
        "cache_root": (LUCID_TOPS_ROOT / "Lucidtoken" / ".schema_cache").as_posix(),
    }
