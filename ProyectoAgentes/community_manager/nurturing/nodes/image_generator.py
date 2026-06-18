"""Image generator node — generates images for the newsletter slides.

Uses GPT Image 2 via ImageGenClient to generate images based on
the approved plan. This runs AFTER human approval of the text/plan.
"""

from __future__ import annotations

import logging

from community_manager.models.schemas import GeneratedImage
from community_manager.tools.image_gen import ImageGenClient

logger = logging.getLogger(__name__)


async def image_generator_node(state: dict) -> dict:
    """Generate images based on the approved plan.

    Input: slides_plan (SlidesPlan)
    Output: generated_images (list[GeneratedImage])
    """
    logger.info("▶ Image generator node starting")

    slides_plan = state.get("slides_plan")
    if not slides_plan or not slides_plan.image_plans:
        logger.info("No images to generate")
        return {"generated_images": []}

    image_plans = slides_plan.image_plans
    prompts = [plan.prompt for plan in image_plans]

    logger.info("Generating %d images with GPT Image 2", len(prompts))

    client = ImageGenClient(image_model="image_2", quality="high")
    try:
        images = await client.generate_images(prompts)

        # Assign slide numbers from plans
        for i, (image, plan) in enumerate(zip(images, image_plans)):
            if image:
                images[i] = image.model_copy(update={"slide_number": plan.slide_number})

        logger.info("✅ Image generator completed: %d images", len(images))
        return {"generated_images": images}

    except Exception:
        logger.exception("Image generation failed")
        return {"generated_images": []}

    finally:
        await client.close()
