"""PDF converter for manga chapters.

Converts directories of images (PNG, JPG, JPEG, WebP) into multi-page PDF files
with optional compression for efficient storage.
"""

import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def create_pdf_from_images(
    image_dir: Path,
    output_pdf: Path,
    quality: int = 85,
) -> Path:
    """Convert directory of images to single PDF.

    Supports PNG, JPG, JPEG, and WebP image formats.
    Processes images in sorted order, maintains reading sequence,
    and applies JPEG compression within the PDF for file size optimization.

    Args:
        image_dir: Directory containing images (in reading order)
        output_pdf: Output PDF file path
        quality: JPEG quality for compression (0-100, default 85)

    Returns:
        Path to created PDF file

    Raises:
        ValueError: If no images found in directory
        Exception: If image processing or PDF creation fails
    """
    # List and sort images by filename (ensures correct reading order)
    # Support multiple image formats: png, jpg, jpeg, webp
    candidate_images = []
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        candidate_images.extend(image_dir.glob(ext))

    # Validate files are actually images (filter out HTML error pages, etc.)
    valid_images = []
    for img_path in candidate_images:
        try:
            # Try to open the image to verify it's valid
            with Image.open(img_path) as img:
                img.verify()  # Verify it's a valid image
            valid_images.append(img_path)
        except (UnidentifiedImageError, IOError, Exception):
            # Skip invalid files (HTML errors, corrupted files, etc.)
            continue

    # Sort by numeric stem so mixed-extension chapters order correctly
    images = sorted(valid_images, key=lambda p: int(p.stem) if p.stem.isdigit() else p.name)

    if not images:
        msg = f"No valid images found in {image_dir}"
        raise ValueError(msg)

    try:
        # Open first image (cover) and convert to RGB
        first_image = None
        try:
            first_image = Image.open(images[0]).convert("RGB")
        except Exception as e:
            warnings.warn(f"Skipping bad page {images[0]}: {e}", stacklevel=2)

        if first_image is None:
            msg = f"No valid images could be processed in {image_dir}"
            raise ValueError(msg)

        # Open remaining images and convert to RGB, skipping bad pages
        other_images = []
        for img_path in images[1:]:
            try:
                img = Image.open(img_path).convert("RGB")
                other_images.append(img)
            except Exception as e:
                warnings.warn(f"Skipping bad page {img_path}: {e}", stacklevel=2)
                continue

        # Save as multi-page PDF with compression
        first_image.save(
            output_pdf,
            "PDF",
            save_all=True,
            append_images=other_images,
            quality=quality,
            optimize=True,
        )
    except Exception:
        if output_pdf.exists():
            output_pdf.unlink(missing_ok=True)
        raise

    return output_pdf
