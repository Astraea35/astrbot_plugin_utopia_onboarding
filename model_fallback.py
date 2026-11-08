from __future__ import annotations

import asyncio
import time

from astrbot.api import logger
from astrbot.core.provider.provider import Provider


class ImageProviderUnavailable(ValueError):
    """No configured chat provider can read the attached images."""


async def generate_with_fallback(context, config, umo, purpose, validate, **kwargs):
    """Call a bounded chain of chat providers and validate each completion.

    Args:
        context: AstrBot plugin context.
        config: Plugin configuration, with optional provider overrides.
        umo: Session whose current model and fallback list should be used.
        purpose: Either intent or chat.
        validate: Parser that rejects empty or malformed completions.
        **kwargs: Arguments forwarded to AstrBot's direct generation API.

    Returns:
        A pair containing the validated result and successful provider ID.

    Raises:
        ImageProviderUnavailable: No usable provider supports image input.
        ValueError: All available attempts failed or no provider was configured.
    """
    native = context.get_config(umo)
    model = native.get("agent_runner", {}).get("config", {}).get("model", {})
    primary = config.get(purpose + "_provider_id", "").strip()
    if not primary:
        try:
            primary = await context.get_current_chat_provider_id(umo)
        except Exception:
            primary = model.get("provider_id", "")
    fallbacks = config.get(purpose + "_fallback_provider_ids") or model.get(
        "fallback_provider_ids", []
    )
    ids = [primary] + (fallbacks if isinstance(fallbacks, list) else [])
    # Keep provider-specific persona hooks out of the direct generation path.
    # A malformed reply retries the original task on the next provider, so no
    # unchecked text can become a reply or a learned matching phrase.
    seen = set()
    attempts = 0
    image_capable = False
    deadline = time.monotonic() + (30 if purpose == "intent" else 65)
    for provider_id in ids:
        if not isinstance(provider_id, str):
            continue
        provider_id = provider_id.strip()
        if not provider_id or provider_id in seen:
            continue
        seen.add(provider_id)
        provider = context.get_provider_by_id(provider_id)
        if not isinstance(provider, Provider):
            continue
        settings = provider.provider_config
        if not settings.get("enable", True):
            continue
        source_id = settings.get("provider_source_id")
        if any(
            source.get("id") == source_id and not source.get("enable", True)
            for source in native.get("provider_sources", [])
        ):
            continue
        modalities = settings.get("modalities")
        if kwargs.get("image_urls") and modalities and "image" not in modalities:
            continue
        image_capable = True
        remaining = deadline - time.monotonic()
        if attempts >= 3 or remaining <= 0:
            break
        attempts += 1
        try:
            async with asyncio.timeout(
                min(10 if purpose == "intent" else 25, remaining)
            ):
                response = await context.llm_generate(
                    chat_provider_id=provider_id, **kwargs
                )
                result = validate(response.completion_text)
            if attempts > 1:
                logger.info(
                    "Utopia fallback succeeded: purpose=%s provider=%s attempt=%d images=%s",
                    purpose,
                    provider_id,
                    attempts,
                    bool(kwargs.get("image_urls")),
                )
            return result, provider_id
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning(
                "Utopia model attempt failed: purpose=%s provider=%s error=%s attempt=%d",
                purpose,
                provider_id,
                type(error).__name__,
                attempts,
            )
    if kwargs.get("image_urls") and not image_capable:
        raise ImageProviderUnavailable("No image-capable chat provider is configured")
    raise ValueError(f"All {purpose} model attempts failed ({attempts} attempted)")
