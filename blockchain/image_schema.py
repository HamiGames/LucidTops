f""" this is the image schema for the LucidTops blockchain's reward token generation
[genesisTokens]: a series of sexy topless goddesses, with a sense of mythology and lore, they will all be unique images for the genesis tokens.and
all other images will be a series of randomly generated, heroes, villains, creatures, and other characters from mythology and lore, they will all be unique images for the other tokens, 
randomly output NSFW images in the schema for the other tokens. this will use a set of character personality profiles to generate the images.
the image generation will be done in via a universe wide search engine or a text to image AI model. (perchance.org)[https://perchance.org/ai-text-to-image-generator#data=uup1:c6c1b3e21abeeaf1c68d590a79a6d4b5.gz]
"""

import argparse
import hashlib
import json
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

from blockchain_secrets import (  # noqa: E402
    resolve_image_generator_enabled,
    resolve_image_generator_url,
    resolve_universe_search_enabled,
    resolve_universe_search_url,
)
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
UNIVERSE_SEARCH_ENABLED_ENV = "UNIVERSE_SEARCH_ENABLED"
UNIVERSE_SEARCH_HOST_ENV = "UNIVERSE_SEARCH_HOST"
UNIVERSE_SEARCH_PORT_ENV = "UNIVERSE_SEARCH_PORT"
UNIVERSE_SEARCH_URL_ENV = "UNIVERSE_SEARCH_URL"
NSFW_OUTPUT_RATIO_ENV = "LUCID_TOKEN_NSFW_RATIO"

DEFAULT_STANDARD_PROFILE = "standardTokens"
GENESIS_SCHEMA_PROFILE = "genesisTokens"
DEFAULT_NSFW_OUTPUT_RATIO = 0.35

SCHEMA_PROFILES: dict[str, dict[str, Any]] = {
    GENESIS_SCHEMA_PROFILE: {
        "label": "genesisTokens",
        "theme": "mythology_goddess_lore",
        "palette": ("#d4af37", "#f5e6cc", "#1a237e", "#4a148c", "#00695c"),
        "composition": "radial_halo_lore",
        "content_profile": "genesis_mythology_goddess",
        "prompt_style": "genesis_goddess_mythology_lore",
        "nsfw_eligible": False,
    },
    DEFAULT_STANDARD_PROFILE: {
        "label": "standardTokens",
        "theme": "mythology_character_roster",
        "palette": ("#263238", "#b71c1c", "#1565c0", "#2e7d32", "#6a1b9a"),
        "composition": "character_silhouette_lore",
        "content_profile": "mythology_cast",
        "prompt_style": "mythology_hero_villain_creature",
        "nsfw_eligible": True,
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
    {
        "archetype": "lorekeeper",
        "name": "Rune Archivist",
        "traits": ("memory", "wisdom", "archive"),
        "mythology": "ancient_scriptoria",
        "palette_shift": (0.9, 0.86, 1.04),
    },
    {
        "archetype": "trickster",
        "name": "Veil Walker",
        "traits": ("wit", "chaos", "surprise"),
        "mythology": "twilight_fables",
        "palette_shift": (1.12, 0.78, 1.06),
    },
    {
        "archetype": "hero",
        "name": "Stormbound Knight",
        "traits": ("valor", "thunder", "oath"),
        "mythology": "storm_pantheon",
        "palette_shift": (0.88, 0.94, 1.16),
    },
    {
        "archetype": "creature",
        "name": "Obsidian Leviathan",
        "traits": ("depth", "power", "myth"),
        "mythology": "abyssal_chronicles",
        "palette_shift": (0.48, 0.52, 0.88),
    },
)


def _sha512_hex(value: str) -> str:
    return hashlib.sha512(value.encode("utf-8")).hexdigest()


def _nsfw_output_ratio() -> float:
    raw = os.environ.get(NSFW_OUTPUT_RATIO_ENV, str(DEFAULT_NSFW_OUTPUT_RATIO)).strip()
    try:
        ratio = float(raw)
    except ValueError:
        ratio = DEFAULT_NSFW_OUTPUT_RATIO
    return max(0.0, min(1.0, ratio))


def resolve_schema_profile(*, profile: str | None = None) -> str:
    """Resolve active schema profile from argument or DockerDNS-friendly env."""
    selected = (profile or os.environ.get(LUCID_IMAGE_SCHEMA_PROFILE_ENV, "")).strip()
    if selected in SCHEMA_PROFILES:
        return selected
    return DEFAULT_STANDARD_PROFILE


def resolve_nsfw_output(
    *,
    lucid_token_id: str,
    owner_id: str,
    schema_profile: str,
) -> bool:
    """Randomly resolve NSFW output for standard token schema (deterministic per token)."""
    schema = SCHEMA_PROFILES.get(schema_profile, SCHEMA_PROFILES[DEFAULT_STANDARD_PROFILE])
    if not schema.get("nsfw_eligible", False):
        return False

    digest = _sha512_hex(f"{lucid_token_id}:{owner_id}:nsfw")
    threshold = int(_nsfw_output_ratio() * 10_000)
    bucket = int(digest[:8], 16) % 10_000
    return bucket < threshold


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
    nsfw_output: bool = False,
) -> str:
    """Build a text prompt for universe search / text-to-image providers (perchance.org)."""
    schema = SCHEMA_PROFILES[schema_profile]
    traits = ", ".join(character_profile.get("traits", ()))

    if schema_profile == GENESIS_SCHEMA_PROFILE:
        return (
            f"LucidToken {lucid_token_id}; owner {owner_id}; schema {schema['label']}; "
            f"theme {schema['theme']}; genesis mythology goddess portrait, ornate lore, "
            f"unique divine mythology art, radiant halo composition, unique genesis token image"
        )

    parts = [
        f"LucidToken {lucid_token_id}",
        f"owner {owner_id}",
        f"schema {schema['label']}",
        f"theme {schema['theme']}",
        f"archetype {character_profile.get('archetype')}",
        f"character {character_profile.get('name')}",
        f"mythology {character_profile.get('mythology')}",
        f"traits {traits}",
        "unique mythology lore portrait",
        "randomly generated hero villain creature mythology character",
    ]
    if nsfw_output:
        parts.append("NSFW mythology lore portrait")
    return "; ".join(parts)


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
    nsfw_output: bool = False,
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
                mix = (radius * 0.65) + ((angle_seed % 97) / 97.0 * 0.35)
                color_a = shifted_palette[angle_seed % len(shifted_palette)]
                color_b = shifted_palette[(angle_seed + 2) % len(shifted_palette)]
                red, green, blue = _blend(color_a, color_b, mix)
                highlight = max(0, int((1.0 - radius) * 48))
                red = min(255, red + highlight)
                green = min(255, green + highlight // 2)
                blue = min(255, blue + highlight // 3)
            else:
                archetype = str(character_profile.get("archetype", "hero"))
                if archetype == "villain":
                    mix = abs(dx) / center_x
                elif archetype == "creature":
                    mix = abs(dy) / center_y
                elif archetype == "trickster":
                    mix = ((angle_seed % 40) / 40.0 + radius) / 2.0
                elif archetype == "lorekeeper":
                    mix = (radius * 0.5) + ((x / width) * 0.5)
                else:
                    mix = (radius + ((angle_seed % 50) / 50.0)) / 2.0
                color_a = shifted_palette[angle_seed % len(shifted_palette)]
                color_b = shifted_palette[(angle_seed + 1) % len(shifted_palette)]
                red, green, blue = _blend(color_a, color_b, mix)
                if nsfw_output:
                    red = min(255, int(red * 1.08))
                    blue = min(255, int(blue * 0.92))

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
        "NSFWOutput": str(nsfw_output),
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
            nsfw_output=nsfw_output,
            width=max(128, width // 2),
            height=max(128, height // 2),
            max_bytes=max_bytes,
        )
    return bytes(png)


def _image_cache_path(*, lucid_token_id: str) -> Path:
    cache_dir = LUCID_TOPS_ROOT / "Lucidtoken" / ".schema_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{lucid_token_id}.png"


def _fetch_http_image(
    *,
    request_url: str,
    max_bytes: int,
    timeout_seconds: float,
) -> bytes | None:
    try:
        import httpx
    except ImportError:
        return None

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(request_url)
            if response.status_code != 200:
                return None
            content_type = response.headers.get("content-type", "")
            body = response.content
            if not body or len(body) > max_bytes:
                return None
            if "image/png" in content_type or body.startswith(b"\x89PNG\r\n\x1a\n"):
                return body
            if "image/" in content_type:
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


def _try_universe_search_engine(
    *,
    prompt: str,
    max_bytes: int,
    timeout_seconds: float,
) -> bytes | None:
    """Universe-wide search engine image lookup (Docker DNS host or perchance.org URL)."""
    enabled = resolve_universe_search_enabled()
    env_enabled = os.environ.get(UNIVERSE_SEARCH_ENABLED_ENV, "").strip().lower()
    if env_enabled in {"0", "false", "no"}:
        enabled = False
    elif env_enabled in {"1", "true", "yes"}:
        enabled = True
    if not enabled:
        return None

    host = os.environ.get(UNIVERSE_SEARCH_HOST_ENV, "").strip()
    port = os.environ.get(UNIVERSE_SEARCH_PORT_ENV, "8091").strip()
    base_url = (
        os.environ.get(UNIVERSE_SEARCH_URL_ENV, "").strip()
        or resolve_universe_search_url()
    ).strip()
    if not base_url and not host:
        return None

    if host:
        request_url = (
            f"http://{host}:{port}/search/image?"
            f"{urllib.parse.urlencode({'q': prompt, 'format': 'png'})}"
        )
    else:
        request_url = (
            f"{base_url.rstrip('/')}?{urllib.parse.urlencode({'prompt': prompt})}"
        )

    return _fetch_http_image(
        request_url=request_url,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
    )


def _try_text_to_image_generator(
    *,
    prompt: str,
    max_bytes: int,
    timeout_seconds: float,
) -> bytes | None:
    """Text-to-image AI model fetch (DockerDNS host or perchance.org URL), with safe fallback."""
    enabled = resolve_image_generator_enabled()
    env_enabled = os.environ.get(IMAGE_GENERATOR_ENABLED_ENV, "").strip().lower()
    if env_enabled in {"0", "false", "no"}:
        enabled = False
    elif env_enabled in {"1", "true", "yes"}:
        enabled = True
    if not enabled:
        return None

    host = os.environ.get(IMAGE_GENERATOR_HOST_ENV, "").strip()
    port = os.environ.get(IMAGE_GENERATOR_PORT_ENV, "8090").strip()
    base_url = (
        os.environ.get(IMAGE_GENERATOR_URL_ENV, "").strip()
        or resolve_image_generator_url()
    ).strip()
    if not base_url and not host:
        return None

    if host:
        request_url = (
            f"http://{host}:{port}/generate?"
            f"{urllib.parse.urlencode({'prompt': prompt})}"
        )
    else:
        request_url = (
            f"{base_url.rstrip('/')}/api/generate?"
            f"{urllib.parse.urlencode({'prompt': prompt})}"
        )

    return _fetch_http_image(
        request_url=request_url,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
    )


def _try_remote_image_sources(
    *,
    prompt: str,
    max_bytes: int,
    timeout_seconds: float,
) -> bytes | None:
    """Try universe search engine then text-to-image provider before procedural fallback."""
    universe_image = _try_universe_search_engine(
        prompt=prompt,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
    )
    if universe_image is not None:
        return universe_image
    return _try_text_to_image_generator(
        prompt=prompt,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
    )


def render_token_image(
    *,
    lucid_token_id: str,
    owner_id: str,
    max_bytes: int = MAX_TOKEN_IMAGE_BYTES,
    schema_profile: str | None = None,
) -> bytes:
    """Generate a LucidToken PNG using the active image schema profile."""
    profile_name = resolve_schema_profile(profile=schema_profile)
    nsfw_output = resolve_nsfw_output(
        lucid_token_id=lucid_token_id,
        owner_id=owner_id,
        schema_profile=profile_name,
    )

    if profile_name == GENESIS_SCHEMA_PROFILE:
        character = {
            "archetype": "genesis",
            "name": "Genesis Mythology Goddess",
            "traits": ("lore", "mythology", "unique", "divine"),
            "mythology": "genesis_pantheon",
            "palette_shift": (1.0, 1.0, 1.0),
            "seed": _sha512_hex(f"{lucid_token_id}:{owner_id}:genesis")[:16],
        }
        nsfw_output = False
    else:
        character = select_character_profile(lucid_token_id=lucid_token_id, owner_id=owner_id)

    prompt = build_generation_prompt(
        lucid_token_id=lucid_token_id,
        owner_id=owner_id,
        schema_profile=profile_name,
        character_profile=character,
        nsfw_output=nsfw_output,
    )

    cache_path = _image_cache_path(lucid_token_id=lucid_token_id)
    if cache_path.exists():
        cached = cache_path.read_bytes()
        if 0 < len(cached) <= max_bytes:
            return cached

    timeout_seconds = float(os.environ.get(IMAGE_GENERATOR_TIMEOUT_ENV, "8"))
    external = _try_remote_image_sources(
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
        nsfw_output=nsfw_output,
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
    nsfw_output = resolve_nsfw_output(
        lucid_token_id=lucid_token_id,
        owner_id=owner_id,
        schema_profile=profile_name,
    )

    if profile_name == GENESIS_SCHEMA_PROFILE:
        character = {
            "archetype": "genesis",
            "name": "Genesis Mythology Goddess",
            "traits": ("lore", "mythology", "unique", "divine"),
            "mythology": "genesis_pantheon",
            "seed": _sha512_hex(f"{lucid_token_id}:{owner_id}:genesis")[:16],
        }
        nsfw_output = False
    else:
        character = select_character_profile(lucid_token_id=lucid_token_id, owner_id=owner_id)

    return {
        "schema_profile": profile_name,
        "character_profile": character,
        "nsfw_output": nsfw_output,
        "prompt": build_generation_prompt(
            lucid_token_id=lucid_token_id,
            owner_id=owner_id,
            schema_profile=profile_name,
            character_profile=character,
            nsfw_output=nsfw_output,
        ),
        "universe_search_enabled": resolve_universe_search_enabled(),
        "universe_search_url": resolve_universe_search_url() or None,
        "generator_url": resolve_image_generator_url() or None,
        "generator_enabled": resolve_image_generator_enabled(),
        "cache_root": (LUCID_TOPS_ROOT / "Lucidtoken" / ".schema_cache").as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LucidTops blockchain image schema")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="Render a LucidToken PNG")
    render_parser.add_argument("--lucid-token-id", required=True)
    render_parser.add_argument("--owner-id", required=True)
    render_parser.add_argument("--schema-profile", default=None)
    render_parser.add_argument("--output", default=None, help="Optional output PNG path")

    meta_parser = subparsers.add_parser("metadata", help="Print schema metadata for a token")
    meta_parser.add_argument("--lucid-token-id", required=True)
    meta_parser.add_argument("--owner-id", required=True)
    meta_parser.add_argument("--schema-profile", default=None)

    subparsers.add_parser("profiles", help="List schema profiles and character personalities")

    args = parser.parse_args()

    if args.command == "render":
        png_bytes = render_token_image(
            lucid_token_id=args.lucid_token_id,
            owner_id=args.owner_id,
            schema_profile=args.schema_profile,
        )
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(png_bytes)
            result = {
                "output_path": output_path.as_posix(),
                "bytes": len(png_bytes),
            }
        else:
            result = {"bytes": len(png_bytes), "cached": True}
    elif args.command == "metadata":
        result = schema_metadata(
            lucid_token_id=args.lucid_token_id,
            owner_id=args.owner_id,
            schema_profile=args.schema_profile,
        )
    elif args.command == "profiles":
        result = {
            "schema_profiles": SCHEMA_PROFILES,
            "character_personality_profiles": CHARACTER_PERSONALITY_PROFILES,
        }
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
