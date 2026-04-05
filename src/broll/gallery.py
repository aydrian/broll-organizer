"""
Gallery generation utilities for broll-organizer.

Handles contact sheet (grid) generation, HTML gallery export,
and base64 encoding for thumbnails.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from .db import Database

# Grid spacing and sizing constants
GRID_PADDING = 10
GRID_BG_COLOR = (30, 30, 30)
GRID_TEXT_COLOR = (255, 255, 255)
GRID_TEXT_SIZE = 12
GRID_THUMB_SIZE = (320, 240)  # Width, Height for grid thumbnails


def get_thumbnail_base64(thumbnail_path: str | Path | None) -> str | None:
    """
    Encode a thumbnail image as base64.

    Args:
        thumbnail_path: Path to the thumbnail image file.

    Returns:
        Base64-encoded JPEG data URI, or None if file doesn't exist.
    """
    if not thumbnail_path:
        return None

    path = Path(thumbnail_path)
    if not path.exists():
        return None

    try:
        # Read the image
        with open(path, "rb") as f:
            image_data = f.read()

        # Encode as base64
        encoded = base64.b64encode(image_data).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return None


def parse_grid_size(grid_spec: str) -> tuple[int, int]:
    """
    Parse a grid size specification like "3x3" or "4x2".

    Args:
        grid_spec: String in format "COLSxROWS" (e.g., "3x3").

    Returns:
        Tuple of (columns, rows).

    Raises:
        ValueError: If the format is invalid.
    """
    try:
        cols_str, rows_str = grid_spec.lower().split("x")
        cols = int(cols_str.strip())
        rows = int(rows_str.strip())
        if cols < 1 or rows < 1:
            raise ValueError("Grid dimensions must be positive integers")
        return (cols, rows)
    except ValueError as e:
        raise ValueError(f"Invalid grid size '{grid_spec}'. Use format like '3x3' or '4x2'.") from e


def generate_contact_sheet(
    videos: list[dict],
    output_path: str | Path,
    grid_size: tuple[int, int] = (3, 3),
    thumb_size: tuple[int, int] = GRID_THUMB_SIZE,
) -> Path:
    """
    Generate a contact sheet (grid) of thumbnails from search results.

    Args:
        videos: List of video dictionaries with thumbnail_path.
        output_path: Path to save the generated contact sheet.
        grid_size: Tuple of (columns, rows) for the grid layout.
        thumb_size: Size to resize each thumbnail to (width, height).

    Returns:
        Path to the generated contact sheet image.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cols, rows = grid_size
    cell_width, cell_height = thumb_size

    # Calculate total image size
    total_width = cols * cell_width + (cols + 1) * GRID_PADDING
    total_height = rows * cell_height + (rows + 1) * GRID_PADDING + rows * 30  # Extra for text

    # Create the base image
    grid_image = Image.new("RGB", (total_width, total_height), GRID_BG_COLOR)
    draw = ImageDraw.Draw(grid_image)

    # Try to load a font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", GRID_TEXT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    # Place thumbnails in the grid
    video_index = 0
    for row in range(rows):
        for col in range(cols):
            if video_index >= len(videos):
                break

            video = videos[video_index]
            thumb_path = video.get("thumbnail_path")

            # Calculate position
            x = col * cell_width + (col + 1) * GRID_PADDING
            y = row * (cell_height + 30) + (row + 1) * GRID_PADDING

            if thumb_path and Path(thumb_path).exists():
                try:
                    # Open and resize the thumbnail
                    with Image.open(thumb_path) as img:
                        # Convert to RGB if necessary
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")

                        # Resize to fit the cell, maintaining aspect ratio
                        img.thumbnail((cell_width, cell_height), Image.Resampling.LANCZOS)

                        # Center the image in the cell
                        paste_x = x + (cell_width - img.width) // 2
                        paste_y = y + (cell_height - img.height) // 2
                        grid_image.paste(img, (paste_x, paste_y))
                except Exception:
                    # Draw placeholder for failed image
                    draw.rectangle([x, y, x + cell_width, y + cell_height], fill=(50, 50, 50))
                    draw.text((x + 10, y + cell_height // 2), "[No Image]", fill=(150, 150, 150), font=font)
            else:
                # Draw placeholder for missing thumbnail
                draw.rectangle([x, y, x + cell_width, y + cell_height], fill=(50, 50, 50))
                draw.text((x + 10, y + cell_height // 2), "[No Thumbnail]", fill=(150, 150, 150), font=font)

            # Draw video info below the thumbnail
            text_y = y + cell_height + 5
            file_name = video.get("file_name", "Unknown")
            # Truncate if too long
            max_chars = 30
            if len(file_name) > max_chars:
                file_name = file_name[:max_chars - 3] + "..."
            draw.text((x, text_y), file_name, fill=GRID_TEXT_COLOR, font=font)

            # Draw video ID and duration
            video_id = video.get("id", "?")
            duration = video.get("duration_seconds")
            if duration:
                duration_str = f"{duration:.1f}s"
            else:
                duration_str = "?"
            info_text = f"ID: {video_id} | {duration_str}"
            draw.text((x, text_y + 14), info_text, fill=(180, 180, 180), font=font)

            video_index += 1

        if video_index >= len(videos):
            break

    # Save the contact sheet
    grid_image.save(output_path, "JPEG", quality=90)
    return output_path


def generate_html_gallery(
    videos: list[dict],
    output_path: str | Path,
    title: str = "B-Roll Search Results",
    include_base64: bool = False,
) -> Path:
    """
    Generate an HTML gallery from search results.

    Args:
        videos: List of video dictionaries with thumbnail_path and metadata.
        output_path: Path to save the generated HTML file.
        title: Gallery title.
        include_base64: Whether to embed thumbnails as base64 data URIs.

    Returns:
        Path to the generated HTML file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html_parts = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "    <meta charset=\"UTF-8\">",
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        f"    <title>{title}</title>",
        "    <style>",
        "        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: #eee; }",
        "        h1 { margin: 0 0 20px 0; font-size: 24px; color: #fff; }",
        "        .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }",
        "        .video-card { background: #2a2a2a; border-radius: 8px; overflow: hidden; transition: transform 0.2s; }",
        "        .video-card:hover { transform: translateY(-4px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }",
        "        .thumbnail { width: 100%; height: 200px; object-fit: cover; background: #333; }",
        "        .thumbnail-placeholder { width: 100%; height: 200px; display: flex; align-items: center; justify-content: center; background: #333; color: #666; font-size: 14px; }",
        "        .info { padding: 15px; }",
        "        .file-name { font-weight: 600; font-size: 14px; margin-bottom: 8px; color: #fff; word-break: break-word; }",
        "        .meta { font-size: 12px; color: #aaa; line-height: 1.6; }",
        "        .meta span { margin-right: 12px; }",
        "        .tags { margin-top: 8px; }",
        "        .tag { display: inline-block; background: #444; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin: 2px; color: #ddd; }",
        "        .description { margin-top: 10px; font-size: 13px; color: #ccc; line-height: 1.5; }",
        "        .no-results { text-align: center; padding: 60px; color: #666; }",
        "        .stats { margin-bottom: 20px; font-size: 14px; color: #888; }",
        "    </style>",
        "</head>",
        "<body>",
        f"    <h1>{title}</h1>",
        f"    <div class=\"stats\">Showing {len(videos)} video(s)</div>",
    ]

    if not videos:
        html_parts.append('    <div class="no-results">No videos found</div>')
    else:
        html_parts.append('    <div class="gallery">')

        for video in videos:
            file_name = video.get("file_name", "Unknown")
            video_id = video.get("id", "?")
            duration = video.get("duration_seconds")
            resolution = video.get("resolution", "?")
            location = video.get("gps_location_name", "")
            description = video.get("scene_description", "")
            tags = video.get("tags", [])
            mood = video.get("mood", "")
            movement = video.get("camera_movement", "")
            time_of_day = video.get("time_of_day", "")

            # Format duration
            if duration:
                mins = int(duration // 60)
                secs = int(duration % 60)
                duration_str = f"{mins}:{secs:02d}" if mins else f"{secs}s"
            else:
                duration_str = "?"

            # Get thumbnail
            thumb_path = video.get("thumbnail_path")
            thumb_html = ""

            if include_base64:
                thumb_data = get_thumbnail_base64(thumb_path)
                if thumb_data:
                    thumb_html = f'<img class="thumbnail" src="{thumb_data}" alt="{file_name}">'
                else:
                    thumb_html = '<div class="thumbnail-placeholder">No Thumbnail</div>'
            else:
                # Use file path if available
                if thumb_path and Path(thumb_path).exists():
                    # Make relative to gallery output or use absolute
                    thumb_html = f'<img class="thumbnail" src="file://{thumb_path}" alt="{file_name}">'
                else:
                    thumb_html = '<div class="thumbnail-placeholder">No Thumbnail</div>'

            # Parse tags
            tag_html = ""
            if tags:
                if isinstance(tags, str):
                    try:
                        import json
                        parsed_tags = json.loads(tags)
                        if isinstance(parsed_tags, list):
                            tags = parsed_tags
                    except (json.JSONDecodeError, TypeError):
                        tags = [tags]
                if isinstance(tags, list):
                    for tag in tags[:8]:  # Limit to 8 tags
                        tag_html += f'<span class="tag">{tag}</span>'

            # Build meta line
            meta_parts = [f"<span>⏱ {duration_str}</span>", f"<span>📐 {resolution}</span>"]
            if location:
                meta_parts.append(f"<span>📍 {location}</span>")
            if mood and mood != "unknown":
                meta_parts.append(f"<span>🎭 {mood}</span>")
            if movement and movement != "unknown":
                meta_parts.append(f"<span>🎥 {movement}</span>")
            if time_of_day and time_of_day != "unknown":
                meta_parts.append(f"<span>☀️ {time_of_day}</span>")

            meta_html = " ".join(meta_parts)

            # Truncate description
            if description and len(description) > 200:
                description = description[:197] + "..."

            html_parts.append('        <div class="video-card">')
            html_parts.append(f"            {thumb_html}")
            html_parts.append('            <div class="info">')
            html_parts.append(f'                <div class="file-name">{file_name}</div>')
            html_parts.append(f'                <div class="meta">{meta_html}</div>')
            if tag_html:
                html_parts.append(f'                <div class="tags">{tag_html}</div>')
            if description:
                html_parts.append(f'                <div class="description">{description}</div>')
            html_parts.append('            </div>')
            html_parts.append('        </div>')

        html_parts.append('    </div>')

    html_parts.extend([
        "</body>",
        "</html>",
    ])

    # Write the HTML file
    output_path.write_text("\n".join(html_parts), encoding="utf-8")
    return output_path


def get_grids_dir(drive_root: str | Path) -> Path:
    """Return the full path to the grids directory on the drive."""
    from .config import APP_DIR_NAME
    return Path(drive_root) / APP_DIR_NAME / "grids"
