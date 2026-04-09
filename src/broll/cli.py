# src/broll/cli.py
'''
CLI entry point for the b-roll organizer.
'''
from __future__ import annotations

import click
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import get_db_path, get_thumbs_dir, WEB_HOST, WEB_PORT, AGENT_API_HOST, AGENT_API_PORT
from .db import Database
from .doctor import (
    run_health_check,
    format_text_report,
    format_json_report,
    fix_missing_files,
    fix_orphaned_thumbnails,
)


def _run_migrations(drive_path: Path) -> bool:
    """Run Alembic migrations for the specified drive."""
    db_path = get_db_path(drive_path)
    
    # Find the project root (where alembic.ini lives)
    project_root = Path(__file__).parent.parent.parent
    alembic_ini = project_root / "alembic.ini"
    
    if not alembic_ini.exists():
        click.echo(f"Alembic configuration not found at {alembic_ini}", err=True)
        return False
    
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "alembic",
                "-c", str(alembic_ini),
                "-x", f"drive_path={drive_path}",
                "upgrade", "head"
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        click.echo(f"Migration failed: {e.stderr}", err=True)
        return False


def _get_migration_status(drive_path: Path) -> str:
    """Get current migration status for the drive."""
    project_root = Path(__file__).parent.parent.parent
    alembic_ini = project_root / "alembic.ini"
    
    if not alembic_ini.exists():
        return "unknown"
    
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "alembic",
                "-c", str(alembic_ini),
                "-x", f"drive_path={drive_path}",
                "current"
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "error"


@click.group()
@click.version_option(version='0.4.0')
def cli():
    '''B-Roll Organizer - AI-powered video catalog using local LLMs.'''
    pass


@cli.command()
@click.argument('drive_path', type=click.Path(exists=True, file_okay=False))
def init(drive_path: str):
    '''Initialize the database on the external drive.'''
    drive = Path(drive_path)
    db_path = get_db_path(drive)
    thumbs_dir = get_thumbs_dir(drive)

    thumbs_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f'Thumbnails directory: {thumbs_dir}')

    # Run database migrations (creates schema if new, updates if existing)
    click.echo('\nRunning database migrations...')
    if _run_migrations(drive):
        click.echo('Database migrations complete')
    else:
        click.echo('Warning: Falling back to legacy initialization...')
        with Database(db_path) as db:
            db.initialize()
            # Also run legacy migrations for any schema updates
            db.migrate()
    
    # Show migration status
    status = _get_migration_status(drive)
    if status and status not in ('unknown', 'error'):
        click.echo(f'   Migration: {status}')

    click.echo(f'\nB-Roll Organizer ready!')
    click.echo(f'   Database: {db_path}')
    click.echo(f'   Next step: broll process {drive_path}')


@cli.command()
@click.argument('drive_path', type=click.Path(exists=True, file_okay=False))
@click.option('--force', is_flag=True, help='Reprocess all files')
@click.option(
    '--scan-only', is_flag=True,
    help='Only scan and extract metadata - skip LLM analysis and embeddings',
)
@click.option(
    '--concurrency', type=int, default=5,
    help='Number of videos to process in parallel (default: 5)'
)
@click.option(
    '--transcribe/--no-transcribe', default=True,
    help='Enable/disable audio transcription (default: enabled)'
)
def process(drive_path: str, force: bool, scan_only: bool, concurrency: int, transcribe: bool):
    '''Scan and process new videos on the drive with parallel processing.'''
    import asyncio
    from tqdm import tqdm
    from .scanner import scan_drive
    from .transcription import is_whisper_available, get_transcription_info

    drive = Path(drive_path)
    db_path = get_db_path(drive)
    thumbs_dir = get_thumbs_dir(drive)

    if not db_path.exists():
        click.echo('Database not found. Run "broll init" first.')
        raise SystemExit(1)

    thumbs_dir.mkdir(parents=True, exist_ok=True)

    with Database(db_path) as db:
        existing_hashes = db.get_all_file_hashes()
        total_existing = len(existing_hashes)

        click.echo(f'Scanning {drive_path} for video files...')
        click.echo(f'   ({total_existing} videos already cataloged)\n')

        new_files = scan_drive(drive_path, existing_hashes, force=force)

        if not new_files:
            click.echo('Everything is up to date! No new videos found.')
            return

        click.echo(f'Found {len(new_files)} new video(s) to process\n')

        # Show breakdown by device
        devices: dict[str, int] = {}
        for f in new_files:
            dev = f['source_device']
            devices[dev] = devices.get(dev, 0) + 1
        for dev, count in sorted(devices.items()):
            click.echo(f'   {dev}: {count} file(s)')

        lrf_count = sum(1 for f in new_files if f.get('lrf_path'))
        if lrf_count:
            click.echo(f'   {lrf_count} file(s) have LRF previews (will use for faster analysis)')

        # Show transcription status
        if transcribe and not scan_only:
            if is_whisper_available():
                info = get_transcription_info()
                click.echo(f"   Transcription: enabled (model: {info['default_model']})")
            else:
                click.echo("   Transcription: whisper.cpp not found (install for audio search)")

        if scan_only:
            click.echo(f'\n   Running in --scan-only mode (metadata only, no LLM)\n')
        else:
            click.echo(f'\n   Processing with concurrency={concurrency}\n')

        # Run async processing
        asyncio.run(_run_processing(
            new_files=new_files,
            db_path=db_path,
            drive_path=drive,
            thumbs_dir=thumbs_dir,
            scan_only=scan_only,
            transcribe=transcribe and not scan_only,
            concurrency=concurrency,
            total_existing=total_existing,
        ))


async def _run_processing(
    new_files: list[dict],
    db_path: Path,
    drive_path: Path,
    thumbs_dir: Path,
    scan_only: bool,
    transcribe: bool,
    concurrency: int,
    total_existing: int,
):
    """Run video processing with controlled concurrency using semaphore."""
    import asyncio
    from tqdm.asyncio import tqdm_asyncio

    semaphore = asyncio.Semaphore(concurrency)

    async def process_with_limit(video_info: dict) -> tuple[bool, dict]:
        """Process a single video with semaphore-controlled concurrency."""
        async with semaphore:
            return await _process_single_video(
                video_info,
                db_path,
                drive_path,
                thumbs_dir,
                scan_only,
                transcribe,
            )

    # Create tasks for all videos
    tasks = [process_with_limit(v) for v in new_files]

    # Run all tasks with progress bar
    results = await tqdm_asyncio.gather(*tasks, desc='Processing videos', unit='video')

    # Calculate stats
    processed = sum(1 for success, _ in results if success)
    errors = sum(1 for success, _ in results if not success)

    # Summary
    click.echo(f'\n{"-" * 50}')
    click.echo(f'Processing complete!')
    click.echo(f'   Processed: {processed}')
    if errors:
        click.echo(f'   Errors: {errors}')
    click.echo(f'   Total in catalog: {total_existing + processed}')

    if scan_only:
        click.echo(
            f'\n   Metadata only (--scan-only). '
            f'Run without the flag for full LLM analysis.'
        )
    else:
        if processed > 0:
            click.echo(f'\nSample results:\n')
            successful_videos = [v for success, v in results if success and v.get('scene_description')]
            _print_analyzed_samples(successful_videos[:3])


async def _process_single_video(
    video_info: dict,
    db_path: Path,
    drive_path: Path,
    thumbs_dir: Path,
    scan_only: bool,
    transcribe: bool,
) -> tuple[bool, dict]:
    """
    Process a single video end-to-end (metadata, frames, analysis, transcription, embedding, DB).

    Returns:
        Tuple of (success: bool, video_info: dict)
    """
    import asyncio
    from .metadata import extract_all_metadata
    from .frames import extract_keyframes, extract_keyframes_optimized
    from .analyzer import analyze_frames_async
    from .embeddings import generate_embeddings_batch, build_searchable_text
    from .transcription import is_whisper_available, transcribe_video_async
    from .proxy import generate_proxy, get_proxy_path
    from tqdm import tqdm

    try:
        # Step 1: Extract metadata (always - synchronous I/O bound)
        metadata = await asyncio.to_thread(
            extract_all_metadata,
            video_info['absolute_path']
        )
        video_info.update(metadata)

        # Set location_source based on GPS availability
        if video_info.get('gps_latitude') is not None and video_info.get('gps_longitude') is not None:
            video_info['location_source'] = 'gps'
        else:
            video_info['location_source'] = 'folder'

        if not scan_only:
            # Step 2: Extract keyframes (try optimized first, fallback to original)
            tqdm.write(f"  Extracting frames: {video_info['file_name']}")
            try:
                keyframes = await asyncio.to_thread(
                    extract_keyframes_optimized,
                    video_info,
                    thumb_dir=str(thumbs_dir),
                )
            except Exception:
                # Fallback to original method
                keyframes = await asyncio.to_thread(
                    extract_keyframes,
                    video_info,
                    thumb_dir=str(thumbs_dir),
                )

            # Step 3: LLM vision analysis (async with connection pooling)
            tqdm.write(f"  Analyzing with {_get_vision_model_name()}...")
            analysis = await analyze_frames_async(keyframes)
            video_info.update(analysis)

            # Step 4: Audio transcription (async, local whisper.cpp)
            transcript_text = None
            if transcribe and is_whisper_available():
                tqdm.write(f"  Transcribing audio: {video_info['file_name']}")
                transcript_result = await transcribe_video_async(
                    video_info['absolute_path']
                )
                if transcript_result:
                    transcript_text = transcript_result['transcript']
                    video_info['transcript'] = transcript_text
                    video_info['transcript_model'] = transcript_result['model']

            # Step 5: Generate embedding (includes transcript if available)
            search_text = build_searchable_text(video_info, include_transcript=True)
            if search_text.strip():
                tqdm.write(f"  Generating embedding...")
                # Use batch endpoint (single item batch for now)
                embeddings = await generate_embeddings_batch([search_text])
                if embeddings and embeddings[0]:
                    video_info['embedding'] = embeddings[0]
        else:
            # Scan-only: set empty fields
            video_info['scene_description'] = None
            video_info['tags'] = None
            video_info['mood'] = None
            video_info['camera_movement'] = None
            video_info['time_of_day'] = None
            video_info['thumbnail_path'] = None
            video_info['transcript'] = None
            video_info['transcript_model'] = None

        # Step 6: Save to database (synchronous)
        video_info['processed_at'] = datetime.now(timezone.utc).isoformat()
        video_id = await asyncio.to_thread(_insert_video_sync, db_path, video_info)

        # Step 7: Generate proxy for smooth web playback (async background)
        if video_id:
            proxy_path = get_proxy_path(video_info['file_hash'], drive_path)
            if not proxy_path.exists():
                tqdm.write(f"  Generating proxy: {video_info['file_name']}")
                success = await asyncio.to_thread(
                    generate_proxy,
                    Path(video_info['absolute_path']),
                    proxy_path,
                    target_height=480,
                    crf=28,
                )
                if success:
                    await asyncio.to_thread(
                        _update_video_proxy_sync,
                        db_path,
                        video_info['relative_path'],
                        str(proxy_path)
                    )

        return True, video_info

    except Exception as e:
        tqdm.write(f"  Error processing {video_info['file_name']}: {e}")

        # Still catalog the file with metadata so we don't retry it every time
        try:
            video_info["scene_description"] = "ERROR: Could not process video - file may be corrupted or incomplete"
            video_info["tags"] = None
            video_info["mood"] = None
            video_info["camera_movement"] = None
            video_info["time_of_day"] = None
            video_info["thumbnail_path"] = None
            video_info['transcript'] = None
            video_info['transcript_model'] = None
            video_info["processed_at"] = datetime.now(timezone.utc).isoformat()
            # Ensure location_source is set even on error
            if "location_source" not in video_info:
                if video_info.get('gps_latitude') is not None and video_info.get('gps_longitude') is not None:
                    video_info['location_source'] = 'gps'
                else:
                    video_info['location_source'] = 'folder'
            await asyncio.to_thread(_insert_video_sync, db_path, video_info)
        except Exception:
            pass

        return False, video_info


def _insert_video_sync(db_path: Path, video_info: dict) -> int:
    """Synchronous wrapper for database insert (called via asyncio.to_thread)."""
    with Database(db_path) as db:
        return db.insert_video(video_info)


def _update_video_proxy_sync(db_path: Path, file_path: str, proxy_path: str):
    """Synchronous wrapper for proxy path update."""
    with Database(db_path) as db:
        db.update_video(file_path, {'proxy_path': proxy_path})


def _get_vision_model_name() -> str:
    from .config import VISION_MODEL
    return VISION_MODEL


def _print_analyzed_samples(videos: list[dict]):
    '''Pretty-print analyzed videos to the console.'''
    for video in videos:
        if not video.get('scene_description'):
            continue

        name = video.get('file_name', 'Unknown')
        device = video.get('source_device', 'unknown')
        duration = video.get('duration_seconds')
        resolution = video.get('resolution', '?')
        location = video.get('gps_location_name')
        description = video.get('scene_description', '')
        tags = video.get('tags', [])
        mood = video.get('mood', '?')
        movement = video.get('camera_movement', '?')
        time_of_day = video.get('time_of_day', '?')
        lrf = 'yes' if video.get('lrf_path') else 'no'

        duration_str = f'{duration:.1f}s' if duration else '?'

        click.echo(f'   {name}')
        click.echo(f'      Device: {device} | Duration: {duration_str} | {resolution}')
        click.echo(f'      LRF used: {lrf}')
        if location:
            click.echo(f'      Location: {location}')
        click.echo(f'      Description: {description[:150]}...')
        
        if tags:
            if isinstance(tags, str):
                try:
                    import json
                    parsed_tags = json.loads(tags)
                    if isinstance(parsed_tags, list):
                        tags = parsed_tags
                except (json.JSONDecodeError, TypeError):
                    pass
            if isinstance(tags, list):
                click.echo(f"      Tags: {', '.join(tags[:8])}")
            else:
                click.echo(f"      Tags: {tags}")
        click.echo(f'      Mood: {mood} | Movement: {movement} | Time: {time_of_day}')
        click.echo()


@cli.command(name='transcribe')
@click.argument('drive_path', type=click.Path(exists=True, file_okay=False))
@click.option('--video-id', type=int, help='Transcribe specific video by ID')
@click.option('--force', is_flag=True, help='Re-transcribe videos that already have transcripts')
@click.option('--model', default=None, help='Whisper model (tiny, base, small, medium)')
@click.option('--batch-size', default=1, help='Number of videos to transcribe concurrently (default: 1)')
@click.option('--limit', type=int, default=None, help='Limit number of videos to process')
def transcribe_command(
    drive_path: str,
    video_id: int | None,
    force: bool,
    model: str | None,
    batch_size: int,
    limit: int | None
):
    '''Transcribe audio for videos missing transcripts.'''
    import asyncio
    from tqdm import tqdm
    from .transcription import (
        is_whisper_available,
        transcribe_video_async,
        get_default_whisper_model,
        get_transcription_info,
    )

    drive = Path(drive_path)
    db_path = get_db_path(drive)

    if not db_path.exists():
        click.echo('Database not found. Run "broll init" first.')
        raise SystemExit(1)

    # Check if whisper.cpp is available
    if not is_whisper_available():
        click.echo(
            'Transcription not available: whisper.cpp not found.\n'
            'Install from: https://github.com/ggerganov/whisper.cpp\n'
            'Examples:\n'
            '  macOS: brew install whisper.cpp\n'
            '  Build: cmake -B build && cmake --build build --config Release'
        )
        raise SystemExit(1)

    # Show info
    info = get_transcription_info()
    whisper_model = model or get_default_whisper_model()
    click.echo(f"Using whisper.cpp model: {whisper_model}")
    click.echo(f"Platform: {info['platform_type']}")
    if info['macos_metal']:
        click.echo("GPU acceleration: Metal enabled")
    click.echo()

    with Database(db_path) as db:
        # Find videos to transcribe
        if video_id:
            video = db.get_video_by_id(video_id)
            if not video:
                click.echo(f'Video ID {video_id} not found.')
                raise SystemExit(1)
            videos = [video]
        else:
            if force:
                # Get all videos (transcribed or not)
                videos = db.get_all_videos(limit=limit or 10000)
                # Filter out those with errors
                videos = [v for v in videos if not v.get('scene_description', '').startswith('ERROR')]
            else:
                videos = db.get_videos_missing_transcript(limit=limit or 10000)

        if not videos:
            click.echo('No videos found needing transcription.')
            return

        click.echo(f'Found {len(videos)} video(s) to transcribe\n')

        # Run transcription
        asyncio.run(_run_transcription_batch(
            videos=videos,
            db_path=db_path,
            model=whisper_model,
            concurrency=batch_size,
        ))

        click.echo(f'\n{"-" * 50}')
        click.echo('Transcription complete!')


async def _run_transcription_batch(
    videos: list[dict],
    db_path: Path,
    model: str,
    concurrency: int,
):
    """Run transcription on multiple videos with controlled concurrency."""
    import asyncio
    from tqdm.asyncio import tqdm_asyncio
    from .transcription import transcribe_video_async
    from .db import Database

    semaphore = asyncio.Semaphore(concurrency)

    async def transcribe_one(video: dict) -> tuple[int, dict | None]:
        async with semaphore:
            result = await transcribe_video_async(
                video['file_path'],
                model=model,
            )
            return video['id'], result

    tasks = [transcribe_one(v) for v in videos]
    results = await tqdm_asyncio.gather(*tasks, desc='Transcribing videos', unit='video')

    # Update database with results
    success_count = 0
    with Database(db_path) as db:
        for video_id, result in results:
            if result and result.get('transcript'):
                db.update_video_transcript(
                    video_id,
                    result['transcript'],
                    result['model']
                )
                success_count += 1

    click.echo(f'\n   Successfully transcribed: {success_count}/{len(videos)}')


# Resolution name to minimum width mapping
RESOLUTION_MAP = {
    "4k": 3840,
    "4K": 3840,
    "2160p": 3840,
    "1080p": 1920,
    "720p": 1280,
    "480p": 854,
}


@cli.command()
@click.argument("query", required=False)
@click.option("--drive", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--limit", default=10, help="Max results to show")
@click.option(
    "--mode",
    type=click.Choice(["hybrid", "keyword", "semantic"]),
    default="hybrid",
    help="Search mode",
)
@click.option(
    "--grid",
    metavar="COLSxROWS",
    help="Generate a contact sheet (grid) of thumbnails. Format: '3x3', '4x2', etc."
)
@click.option(
    "--export-gallery",
    "export_gallery",
    type=click.Path(),
    help="Export search results to an HTML gallery file"
)
@click.option(
    "--gallery-base64",
    is_flag=True,
    help="Embed thumbnails as base64 in HTML gallery (makes file self-contained but larger)"
)
# Duration filters
@click.option(
    "--duration",
    help="Duration range in seconds (e.g., '5-30', '5:30', or '5..30')"
)
@click.option(
    "--min-duration",
    type=float,
    help="Minimum duration in seconds"
)
@click.option(
    "--max-duration",
    type=float,
    help="Maximum duration in seconds"
)
# Resolution filters
@click.option(
    "--resolution",
    help="Resolution name (4K, 1080p, 720p) or minimum width in pixels"
)
@click.option(
    "--min-width",
    type=int,
    help="Minimum video width in pixels"
)
@click.option(
    "--min-height",
    type=int,
    help="Minimum video height in pixels"
)
# Aspect ratio / orientation filters
@click.option(
    "--aspect",
    help="Aspect ratio (e.g., '16:9', '4:3', '9:16', '1:1')"
)
@click.option(
    "--portrait",
    is_flag=True,
    help="Portrait orientation (taller than wide)"
)
@click.option(
    "--landscape",
    is_flag=True,
    help="Landscape orientation (wider than tall)"
)
# Date filters
@click.option(
    "--date",
    help="Date range (e.g., '2025-01-01:2025-12-31', '2025-01-01..2025-12-31')"
)
@click.option(
    "--since",
    help="Videos since date (YYYY-MM-DD or ISO 8601)"
)
@click.option(
    "--until",
    help="Videos until date (YYYY-MM-DD or ISO 8601)"
)
# Metadata filters
@click.option(
    "--mood",
    help="Filter by mood (e.g., calm, energetic, mysterious)"
)
@click.option(
    "--movement",
    help="Filter by camera movement (e.g., static, pan, gimbal)"
)
@click.option(
    "--time",
    "time_of_day",
    help="Filter by time of day (e.g., morning, night, golden_hour)"
)
@click.option(
    "--location",
    help="Filter by location name (partial match)"
)
@click.option(
    "--device",
    help="Filter by source device (e.g., dji_pocket3, iphone)"
)
@click.option(
    "--unused-in-project",
    type=int,
    default=None,
    help="Exclude clips already used in this project ID"
)
@click.option(
    "--show-usage",
    is_flag=True,
    help="Show usage heatmap (count per result)"
)
def search(
    query: str | None,
    drive: str,
    limit: int,
    mode: str,
    grid: str | None,
    export_gallery: str | None,
    gallery_base64: bool,
    # Duration
    duration: str | None,
    min_duration: float | None,
    max_duration: float | None,
    # Resolution
    resolution: str | None,
    min_width: int | None,
    min_height: int | None,
    # Aspect
    aspect: str | None,
    portrait: bool,
    landscape: bool,
    # Date
    date: str | None,
    since: str | None,
    until: str | None,
    # Metadata
    mood: str | None,
    movement: str | None,
    time_of_day: str | None,
    location: str | None,
    device: str | None,
    # Usage
    unused_in_project: int | None,
    show_usage: bool,
):
    """Search for video clips by description and/or filters.

    Examples:
        broll search "sunset" --drive /path/to/drive
        broll search "beach" --duration 5-30 --resolution 4K
        broll search --location "Tokyo" --time night --movement static
        broll search --mood calm --since 2025-01-01
    """
    from .search import hybrid_search, keyword_search, semantic_search
    from .gallery import generate_contact_sheet, generate_html_gallery, get_grids_dir, parse_grid_size

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    # Build filters dict from CLI options
    filters: dict[str, Any] = {}

    # Duration filters
    if duration:
        # Parse duration range: "5-30", "5:30", "5..30"
        for sep in ["-", ":", "..", " "]:
            if sep in duration:
                parts = duration.split(sep, 1)
                try:
                    filters["duration_min"] = float(parts[0].strip())
                    filters["duration_max"] = float(parts[1].strip())
                    break
                except (ValueError, IndexError):
                    pass
        else:
            # Single value - treat as minimum duration
            try:
                filters["duration_min"] = float(duration)
            except ValueError:
                click.echo(f"Warning: Invalid duration format: {duration}", err=True)

    if min_duration is not None:
        filters["duration_min"] = min_duration
    if max_duration is not None:
        filters["duration_max"] = max_duration

    # Resolution filters
    if resolution:
        if resolution in RESOLUTION_MAP:
            filters["min_width"] = RESOLUTION_MAP[resolution]
        else:
            # Try to parse as integer (min width)
            try:
                filters["min_width"] = int(resolution)
            except ValueError:
                click.echo(f"Warning: Unknown resolution: {resolution}", err=True)

    if min_width is not None:
        filters["min_width"] = max(filters.get("min_width", 0), min_width)
    if min_height is not None:
        filters["min_height"] = min_height

    # Aspect ratio / orientation
    if aspect:
        filters["aspect_ratio"] = aspect
    elif portrait and landscape:
        click.echo("Warning: Both --portrait and --landscape specified, ignoring orientation", err=True)
    elif portrait:
        filters["orientation"] = "portrait"
    elif landscape:
        filters["orientation"] = "landscape"

    # Date filters
    if date:
        # Parse date range: "2025-01-01:2025-12-31", "2025-01-01..2025-12-31", "2025-01-01--2025-12-31"
        date_parsed = False

        # Try range separators first (colon or double characters)
        for sep in [":", "..", "--"]:
            if sep in date:
                parts = date.split(sep, 1)
                if len(parts) == 2:
                    filters["date_from"] = parts[0].strip()
                    filters["date_to"] = parts[1].strip()
                    date_parsed = True
                    break

        if not date_parsed:
            # Try " to " or comma
            for sep in [" to ", ","]:
                if sep in date:
                    parts = date.split(sep, 1)
                    filters["date_from"] = parts[0].strip()
                    filters["date_to"] = parts[1].strip()
                    date_parsed = True
                    break

        if not date_parsed:
            click.echo(f"Warning: Invalid date format: {date}. Use YYYY-MM-DD:YYYY-MM-DD or YYYY-MM-DD..YYYY-MM-DD", err=True)

    if since:
        filters["date_from"] = since
    if until:
        filters["date_to"] = until

    # Metadata filters
    if mood:
        filters["mood"] = mood
    if movement:
        filters["movement"] = movement
    if time_of_day:
        filters["time_of_day"] = time_of_day
    if location:
        filters["location"] = location
    if device:
        filters["device"] = device

    # Validate: need at least a query or some filters
    if not query and not filters:
        click.echo("Error: Provide a search query or at least one filter option.")
        click.echo("\nExamples:")
        click.echo('  broll search "sunset" --drive /path/to/drive')
        click.echo('  broll search --location "Tokyo" --time night')
        raise SystemExit(1)

    with Database(db_path) as db:
        stats = db.get_catalog_stats()

        # Build search description for display
        search_desc = f'"{query}"' if query else "filtered results"
        filter_desc = ""
        if filters:
            filter_parts = []
            if "duration_min" in filters or "duration_max" in filters:
                dur_parts = []
                if "duration_min" in filters:
                    dur_parts.append(f">={filters['duration_min']}s")
                if "duration_max" in filters:
                    dur_parts.append(f"<={filters['duration_max']}s")
                filter_parts.append(f"duration: {' '.join(dur_parts)}")
            if "min_width" in filters:
                filter_parts.append(f"width>={filters['min_width']}")
            if "location" in filters:
                filter_parts.append(f"location:{filters['location']}")
            if "mood" in filters:
                filter_parts.append(f"mood:{filters['mood']}")
            if "time_of_day" in filters:
                filter_parts.append(f"time:{filters['time_of_day']}")
            filter_desc = f" ({', '.join(filter_parts)})"

        click.echo(f"Searching {stats['total_videos']} videos ({mode} mode): {search_desc}{filter_desc}\n")

        try:
            if mode == "keyword":
                results = keyword_search(query, db, limit, filters=filters if filters else None)
            elif mode == "semantic":
                results = semantic_search(query, db, limit, filters=filters if filters else None)
            else:
                results = hybrid_search(query, db, limit, filters=filters if filters else None)
        except Exception as e:
            click.echo(f"Search error: {e}", err=True)
            raise SystemExit(1)

        if not results:
            click.echo("No results found.")
            if query:
                click.echo("\nTips:")
                click.echo("  - Try broader terms")
                click.echo("  - Use --mode keyword for exact word matching")
                click.echo("  - Use --mode semantic for meaning-based search")
            if filters:
                click.echo("\nFilter criteria may be too restrictive. Try removing some filters.")
            return

        click.echo(f"Found {len(results)} result(s):\n")

        for i, video in enumerate(results, 1):
            _print_search_result(i, video)

        # Generate contact sheet if requested
        if grid:
            try:
                cols, rows = parse_grid_size(grid)
                grid_count = cols * rows
                if len(results) > grid_count:
                    click.echo(f"\nNote: Grid fits {grid_count} images, but {len(results)} results found. Showing first {grid_count}.")
                    grid_videos = results[:grid_count]
                else:
                    grid_videos = results

                grids_dir = get_grids_dir(drive_path)
                grids_dir.mkdir(parents=True, exist_ok=True)

                # Generate filename based on query and timestamp
                from datetime import datetime
                if query:
                    safe_query = "".join(c if c.isalnum() else "_" for c in query)[:30]
                else:
                    # Use filter description for filename when no query
                    filter_parts = []
                    if filters.get("location"):
                        filter_parts.append(f"loc_{filters['location'][:10]}")
                    if filters.get("mood"):
                        filter_parts.append(f"mood_{filters['mood']}")
                    if filters.get("time_of_day"):
                        filter_parts.append(f"time_{filters['time_of_day']}")
                    safe_query = "_".join(filter_parts)[:30] or "filtered"

                click.echo(f"\nGenerating contact sheet ({cols}x{rows})...")
                generate_contact_sheet(grid_videos, grid_path, grid_size=(cols, rows))
                click.echo(f"Saved to: {grid_path}")
            except ValueError as e:
                click.echo(f"\nError: {e}", err=True)
                raise SystemExit(1)
            except Exception as e:
                click.echo(f"\nError generating grid: {e}", err=True)
                raise SystemExit(1)

        # Export HTML gallery if requested
        if export_gallery:
            try:
                gallery_path = Path(export_gallery)
                click.echo(f"\nExporting HTML gallery...")
                gallery_title = f"Search: {query}" if query else "Filtered Results"
                generate_html_gallery(
                    results,
                    gallery_path,
                    title=gallery_title,
                    include_base64=gallery_base64
                )
                click.echo(f"Saved to: {gallery_path}")
            except Exception as e:
                click.echo(f"\nError exporting gallery: {e}", err=True)
                raise SystemExit(1)


def _print_search_result(rank: int, video: dict):
    """Pretty-print a single search result."""
    name = video.get("file_name", "Unknown")
    description = video.get("scene_description", "")
    duration = video.get("duration_seconds")
    resolution = video.get("resolution", "?")
    location = video.get("gps_location_name")
    mood = video.get("mood")
    movement = video.get("camera_movement")
    time_of_day = video.get("time_of_day")
    tags = video.get("tags", "")
    relative_path = video.get("file_path", "")
    thumbnail_path = video.get("thumbnail_path")

    # Search metadata
    score = video.get("search_score", 0)
    in_fts = video.get("in_fts", False)
    in_vec = video.get("in_vec", False)

    duration_str = f"{duration:.1f}s" if duration else "?"

    # Match source indicator
    match_sources = []
    if in_fts:
        match_sources.append("keyword")
    if in_vec:
        match_sources.append("semantic")
    match_str = " + ".join(match_sources) if match_sources else "?"

    click.echo(f"  {rank}. {name}  (score: {score:.4f}, matched via: {match_str})")
    click.echo(f"     Path: {relative_path}")
    click.echo(f"     Duration: {duration_str} | {resolution}")

    # Show thumbnail path if available
    if thumbnail_path:
        click.echo(f"     Thumbnail: {thumbnail_path}")

    if description and not description.startswith("ERROR"):
        click.echo(f"     {description[:200]}")

    if tags:
        if isinstance(tags, str):
            try:
                import json
                parsed_tags = json.loads(tags)
                if isinstance(parsed_tags, list):
                    tags = parsed_tags
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(tags, list):
            click.echo(f"     Tags: {', '.join(tags[:8])}")
        else:
            click.echo(f"     Tags: {tags}")

    details = []
    if mood and mood != "unknown":
        details.append(f"Mood: {mood}")
    if movement and movement != "unknown":
        details.append(f"Camera: {movement}")
    if time_of_day and time_of_day != "unknown":
        details.append(f"Time: {time_of_day}")
    if details:
        click.echo(f"     {' | '.join(details)}")

    if location:
        click.echo(f"     Location: {location}")

    click.echo()



@cli.command()
@click.argument("drive_path", type=click.Path(exists=True, file_okay=False))
@click.option("--port", default=WEB_PORT, help="Port for the web UI")
@click.option("--host", default=WEB_HOST, help="Host to bind to (use 0.0.0.0 for Tailscale/external access)")
def web(drive_path: str, port: int, host: str):
    """Launch the web UI for browsing and chatting."""
    from .web.app import create_app
    import socket

    drive = Path(drive_path)
    db_path = get_db_path(drive)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    app = create_app(drive_path)

    click.echo(f"\nB-Roll Catalog Web UI")
    click.echo(f"  Local:    http://{host}:{port}")
    
    # Try to detect Tailscale IP and hostname
    if host == "0.0.0.0":
        try:
            # Look for tailscale0 interface
            import subprocess
            result = subprocess.run(
                ["ip", "addr", "show", "tailscale0"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                import re
                match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/\d+', result.stdout)
                if match:
                    tailscale_ip = match.group(1)
                    click.echo(f"  Tailscale: http://{tailscale_ip}:{port}")
            
            # Try to get MagicDNS hostname
            magic_result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True
            )
            if magic_result.returncode == 0:
                import json
                status = json.loads(magic_result.stdout)
                self_dns = status.get("Self", {}).get("DNSName", "")
                if self_dns:
                    # Remove trailing dot if present
                    hostname = self_dns.rstrip(".")
                    click.echo(f"  MagicDNS:  http://{hostname}:{port}")
        except Exception:
            pass
        click.echo(f"  (Accessible from other devices on your Tailscale network)")
    
    click.echo(f"  Database: {db_path}")
    click.echo(f"\n  Press Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=False)



@cli.command()
@click.argument("drive_path", type=click.Path(exists=True, file_okay=False))
@click.option("--port", default=AGENT_API_PORT, help="Port for the agent API")
@click.option("--host", default=AGENT_API_HOST, help="Host to bind to")
def agent(drive_path: str, port: int, host: str):
    """Launch the OpenClaw Agent API for programmatic access."""
    from .agent_api import create_agent_app

    drive = Path(drive_path)
    db_path = get_db_path(drive)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    app = create_agent_app(drive_path)

    click.echo(f"\nB-Roll Catalog Agent API")
    click.echo(f"  http://{host}:{port}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"\nEndpoints:")
    click.echo(f"  GET  /health       - Health check")
    click.echo(f"  GET  /stats        - Catalog statistics")
    click.echo(f"  GET  /search?q=... - Search videos")
    click.echo(f"  GET  /videos       - List videos")
    click.echo(f"  GET  /video/<id>   - Get video details")
    click.echo(f"  GET  /thumbnail/<id> - Get video thumbnail")
    click.echo(f"  POST /chat         - Chat with the catalog")
    click.echo(f"\nPress Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=False)


@cli.command()
@click.argument("drive_path", type=click.Path(exists=True, file_okay=False))
@click.option("--detailed", is_flag=True, help="Show per-location breakdown")
@click.option("--timeline", is_flag=True, help="Show videos by date histogram")
@click.option("--missing-metadata", is_flag=True, help="Show videos lacking descriptions/tags")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format")
def stats(drive_path: str, detailed: bool, timeline: bool, missing_metadata: bool, output_format: str):
    """Show catalog statistics."""
    from collections import Counter
    import json as json_lib
    
    drive = Path(drive_path)
    db_path = get_db_path(drive)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    with Database(db_path) as db:
        s = db.get_catalog_stats()
        
        # Build output data structure
        output = {
            "summary": {
                "total_videos": s["total_videos"],
                "analyzed_count": s["analyzed_count"],
                "total_with_embeddings": s["total_with_embeddings"],
                "geotagged_count": s["geotagged_count"],
                "device_count": s["device_count"],
                "total_size_gb": round(s["total_size_bytes"] / (1024 ** 3), 2),
                "total_duration_min": round(s["total_duration_seconds"] / 60, 1),
            }
        }
        
        # Detailed location breakdown
        if detailed:
            all_videos = db.get_all_videos(limit=1000000)
            
            # Count by location
            location_counts = Counter()
            location_durations = {}
            for video in all_videos:
                loc = video.get("gps_location_name") or "Unknown"
                location_counts[loc] += 1
                duration = video.get("duration_seconds") or 0
                location_durations[loc] = location_durations.get(loc, 0) + duration
            
            output["locations"] = {
                loc: {
                    "count": count,
                    "duration_min": round(location_durations.get(loc, 0) / 60, 1)
                }
                for loc, count in sorted(location_counts.items(), key=lambda x: -x[1])
            }
        
        # Timeline histogram
        if timeline:
            all_videos = db.get_all_videos(limit=1000000)
            
            # Group by creation date (month)
            date_counts = Counter()
            for video in all_videos:
                creation = video.get("creation_date")
                if creation:
                    # Parse ISO date and get year-month
                    try:
                        if "T" in creation:
                            month = creation[:7]  # YYYY-MM
                        else:
                            month = creation[:7]
                        date_counts[month] += 1
                    except:
                        date_counts["Unknown"] += 1
                else:
                    date_counts["Unknown"] += 1
            
            output["timeline"] = dict(sorted(date_counts.items()))
        
        # Missing metadata
        if missing_metadata:
            all_videos = db.get_all_videos(limit=1000000)
            
            missing_list = []
            for video in all_videos:
                scene_desc = video.get("scene_description")
                tags = video.get("tags")
                is_error = scene_desc and str(scene_desc).startswith("ERROR")
                
                if not scene_desc or is_error or not tags:
                    missing_list.append({
                        "id": video.get("id"),
                        "file_path": video.get("file_path"),
                        "file_name": video.get("file_name"),
                        "missing_description": not scene_desc or is_error,
                        "missing_tags": not tags,
                        "error": is_error,
                    })
            
            output["missing_metadata"] = missing_list

    # Output formatting
    if output_format == "json":
        click.echo(json_lib.dumps(output, indent=2))
    else:
        # Text format
        click.echo(f"\nCatalog Statistics")
        click.echo(f"{'=' * 40}")
        click.echo(f"  Total videos:       {output['summary']['total_videos']}")
        click.echo(f"  With AI analysis:   {output['summary']['analyzed_count']}")
        click.echo(f"  With embeddings:    {output['summary']['total_with_embeddings']}")
        click.echo(f"  Geotagged:          {output['summary']['geotagged_count']}")
        click.echo(f"  Source devices:     {output['summary']['device_count']}")
        click.echo(f"  Total file size:    {output['summary']['total_size_gb']:.2f} GB")
        click.echo(f"  Total duration:     {output['summary']['total_duration_min']:.1f} min")
        
        # Detailed location breakdown
        if detailed and "locations" in output:
            click.echo(f"\n{'-' * 40}")
            click.echo("Location Breakdown:")
            for loc, data in list(output["locations"].items())[:10]:
                click.echo(f"  {loc}: {data['count']} videos ({data['duration_min']:.1f} min)")
            if len(output["locations"]) > 10:
                click.echo(f"  ... and {len(output['locations']) - 10} more locations")
        
        # Timeline
        if timeline and "timeline" in output:
            click.echo(f"\n{'-' * 40}")
            click.echo("Timeline (by month):")
            for month, count in list(output["timeline"].items())[-12:]:  # Last 12 months
                click.echo(f"  {month}: {count} videos")
        
        # Missing metadata
        if missing_metadata and "missing_metadata" in output:
            click.echo(f"\n{'-' * 40}")
            click.echo(f"Missing Metadata ({len(output['missing_metadata'])} videos):")
            for video in output["missing_metadata"][:10]:
                missing = []
                if video["missing_description"]:
                    missing.append("description")
                if video["missing_tags"]:
                    missing.append("tags")
                click.echo(f"  {video['file_name']} - missing: {', '.join(missing)}")
            if len(output["missing_metadata"]) > 10:
                click.echo(f"  ... and {len(output['missing_metadata']) - 10} more")
        
        click.echo()


@cli.command()
@click.argument("drive_path", type=click.Path(exists=True, file_okay=False))
@click.option("--thumbnails", is_flag=True, help="Check for missing thumbnails")
@click.option("--orphaned", is_flag=True, help="Check for orphaned thumbnails")
@click.option("--hashes", is_flag=True, help="Check for hash mismatches")
@click.option("--fix", is_flag=True, help="Automatically fix issues where possible")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.option("--all", "check_all", is_flag=True, help="Run all checks (default behavior)")
def doctor(drive_path: str, thumbnails: bool, orphaned: bool, hashes: bool, fix: bool, output_format: str, check_all: bool):
    """Run health checks on the catalog database."""
    drive = Path(drive_path)
    db_path = get_db_path(drive)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    # Default to all checks if no specific checks requested
    run_all = check_all or not (thumbnails or orphaned or hashes)
    
    with Database(db_path) as db:
        click.echo("Running health checks...")
        report = run_health_check(
            db=db,
            drive_path=drive,
            check_thumbnails=run_all or thumbnails,
            check_orphaned=run_all or orphaned,
            check_hashes=run_all or hashes,
            check_all=run_all,
        )
        
        # Auto-fix if requested
        if fix:
            click.echo("\nApplying fixes...")
            
            # Fix missing files (remove DB entries for non-existent files)
            missing_file_issues = [i for i in report.issues if i.type == "missing_file"]
            if missing_file_issues:
                fixed = fix_missing_files(db, missing_file_issues, dry_run=False)
                click.echo(f"  Removed {fixed} database entries for missing files")
            
            # Fix orphaned thumbnails (delete files)
            orphaned_issues = [i for i in report.issues if i.type == "orphaned_thumbnail"]
            if orphaned_issues:
                fixed = fix_orphaned_thumbnails(orphaned_issues, drive, dry_run=False)
                click.echo(f"  Deleted {fixed} orphaned thumbnail files")
            
            # Re-run check to get updated report
            if missing_file_issues or orphaned_issues:
                click.echo("\nRe-running checks after fixes...")
                report = run_health_check(
                    db=db,
                    drive_path=drive,
                    check_thumbnails=run_all or thumbnails,
                    check_orphaned=run_all or orphaned,
                    check_hashes=run_all or hashes,
                    check_all=run_all,
                )
        
        # Output report
        if output_format == "json":
            click.echo(format_json_report(report, drive))
        else:
            click.echo(format_text_report(report, drive))
    
    # Exit with appropriate code
    if report.healthy:
        raise SystemExit(0)
    else:
        raise SystemExit(1)


@cli.command()
@click.option("--id", "video_id", type=int, required=True, help="Video ID to fetch thumbnail for")
@click.option("--drive", required=True, type=click.Path(exists=True, file_okay=False), help="Path to the external drive")
@click.option("--base64", "base64_output", is_flag=True, help="Output as base64-encoded data URI")
@click.option("--output", "output_path", type=click.Path(), help="Save thumbnail to file path")
def thumbnail(video_id: int, drive: str, base64_output: bool, output_path: str | None):
    """Get a video thumbnail by ID."""
    from .gallery import get_thumbnail_base64

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    with Database(db_path) as db:
        video = db.get_video_by_id(video_id)

        if not video:
            click.echo(f"Video with ID {video_id} not found.", err=True)
            raise SystemExit(1)

        thumb_path = video.get("thumbnail_path")

        if not thumb_path:
            click.echo(f"No thumbnail available for video ID {video_id}.", err=True)
            raise SystemExit(1)

        thumb_file = Path(thumb_path)
        if not thumb_file.exists():
            click.echo(f"Thumbnail file not found: {thumb_path}", err=True)
            raise SystemExit(1)

        # Output to file if requested
        if output_path:
            import shutil
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(thumb_path, output_path)
            click.echo(f"Thumbnail saved to: {output_path}")
            return

        # Output as base64 if requested
        if base64_output:
            base64_data = get_thumbnail_base64(thumb_path)
            if base64_data:
                click.echo(base64_data)
            else:
                click.echo("Failed to encode thumbnail as base64.", err=True)
                raise SystemExit(1)
            return

        # Default: just print the path
        click.echo(thumb_path)


# =============================================================================
# Marker Commands
# =============================================================================

@cli.group()
def marker():
    """Manage video markers (clip in/out points)."""
    pass


@marker.command()
@click.argument('video_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--in', 'in_seconds', required=True, type=float, help='In point in seconds')
@click.option('--out', 'out_seconds', required=True, type=float, help='Out point in seconds')
@click.option('--label', required=True, help='Marker label (e.g., "money shot", "intro")')
@click.option('--color', default='#3b82f6', help='Marker color (hex code, default: #3b82f6)')
def set(video_id: int, drive: str, in_seconds: float, out_seconds: float, label: str, color: str):
    """Set a marker (in/out point) for a video."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    if in_seconds >= out_seconds:
        click.echo("Error: in point must be less than out point.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        # Verify video exists
        video = db.get_video_by_id(video_id)
        if not video:
            click.echo(f"Video with ID {video_id} not found.", err=True)
            raise SystemExit(1)

        # Check if marker with this label already exists
        existing_markers = db.get_video_markers(video_id)
        existing = next((m for m in existing_markers if m['label'] == label), None)

        if existing:
            # Update existing marker
            db.update_marker(existing['id'], {
                'in_seconds': in_seconds,
                'out_seconds': out_seconds,
                'color': color
            })
            click.echo(f"Updated marker '{label}' for '{video['file_name']}': {in_seconds:.1f}s - {out_seconds:.1f}s")
        else:
            # Create new marker
            marker_id = db.create_marker(video_id, label, in_seconds, out_seconds, color)
            duration = out_seconds - in_seconds
            click.echo(f"Created marker '{label}' (ID: {marker_id}) for '{video['file_name']}'")
            click.echo(f"  In: {in_seconds:.1f}s | Out: {out_seconds:.1f}s | Duration: {duration:.1f}s")


@marker.command()
@click.argument('video_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format')
def list(video_id: int, drive: str, output_format: str):
    """List all markers for a video."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        # Verify video exists
        video = db.get_video_by_id(video_id)
        if not video:
            click.echo(f"Video with ID {video_id} not found.", err=True)
            raise SystemExit(1)

        markers = db.get_video_markers(video_id)

        if output_format == 'json':
            import json
            click.echo(json.dumps(markers, indent=2, default=str))
        else:
            if not markers:
                click.echo(f"No markers found for '{video['file_name']}'.")
                return

            click.echo(f"\nMarkers for '{video['file_name']}' (ID: {video_id}):")
            click.echo("=" * 70)
            click.echo(f"{'ID':<6} {'Label':<20} {'In':<10} {'Out':<10} {'Duration':<10} {'Color'}")
            click.echo("-" * 70)

            for m in markers:
                duration = m['out_seconds'] - m['in_seconds']
                click.echo(
                    f"{m['id']:<6} {m['label']:<20} "
                    f"{m['in_seconds']:<10.1f} {m['out_seconds']:<10.1f} "
                    f"{duration:<10.1f} {m.get('color', '#3b82f6')}"
                )
            click.echo()


@marker.command()
@click.argument('marker_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.confirmation_option(prompt='Are you sure you want to delete this marker?')
def delete(marker_id: int, drive: str):
    """Delete a marker by ID."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        marker = db.get_marker(marker_id)
        if not marker:
            click.echo(f"Marker with ID {marker_id} not found.", err=True)
            raise SystemExit(1)

        db.delete_marker(marker_id)
        click.echo(f"Deleted marker '{marker['label']}' (ID: {marker_id})")


@marker.command()
@click.argument('marker_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--output', required=True, type=click.Path(), help='Output file path for the exported clip')
def export(marker_id: int, drive: str, output: str):
    """Export a marker segment as a video clip using FFmpeg."""
    import subprocess

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    output_path = Path(output)
    if not output_path.suffix:
        output_path = output_path.with_suffix('.mp4')

    with Database(db_path) as db:
        marker = db.get_marker(marker_id)
        if not marker:
            click.echo(f"Marker with ID {marker_id} not found.", err=True)
            raise SystemExit(1)

        video = db.get_video_by_id(marker['video_id'])
        if not video:
            click.echo(f"Video for marker not found.", err=True)
            raise SystemExit(1)

        # Build video path
        file_path = video['file_path']
        if file_path.startswith(str(drive_path)):
            video_path = Path(file_path)
        else:
            video_path = drive_path / file_path

        if not video_path.exists():
            click.echo(f"Video file not found: {video_path}", err=True)
            raise SystemExit(1)

        start_time = marker['in_seconds']
        duration = marker['out_seconds'] - start_time

        click.echo(f"Exporting marker '{marker['label']}' from '{video['file_name']}'...")
        click.echo(f"  In: {start_time:.1f}s | Out: {marker['out_seconds']:.1f}s | Duration: {duration:.1f}s")

        # Build FFmpeg command for lossless trimming
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-ss', str(start_time),  # Start time
            '-i', str(video_path),   # Input file
            '-t', str(duration),     # Duration
            '-c', 'copy',            # Copy streams (lossless)
            '-avoid_negative_ts', '1',
            '-movflags', '+faststart',
            str(output_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                click.echo(f"FFmpeg error: {result.stderr}", err=True)
                raise SystemExit(1)

            # Get output file size
            file_size = output_path.stat().st_size
            click.echo(f"Exported to: {output_path}")
            click.echo(f"  File size: {file_size / (1024*1024):.1f} MB")

        except subprocess.TimeoutExpired:
            click.echo("Export timed out after 5 minutes.", err=True)
            raise SystemExit(1)
        except FileNotFoundError:
            click.echo("FFmpeg not found. Please install FFmpeg.", err=True)
            raise SystemExit(1)
        except Exception as e:
            click.echo(f"Export failed: {e}", err=True)
            raise SystemExit(1)


# =============================================================================
# Project Commands
# =============================================================================

@cli.group()
def project():
    """Manage projects (clip sequences for content creation)."""
    pass


@project.command()
@click.argument('name')
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--description', default=None, help='Project description')
@click.option('--aspect', '--aspect-ratio', default=None, type=click.Choice(['16:9', '4:3', '9:16', '1:1', '21:9'], case_sensitive=False), help='Target aspect ratio')
@click.option('--resolution', '--output-resolution', default=None, type=click.Choice(['720p', '1080p', '4K'], case_sensitive=False), help='Target output resolution')
@click.option('--duration', '--target-duration', type=int, default=None, help='Target duration in seconds')
@click.option('--status', default='planning', type=click.Choice(['planning', 'gathering', 'ready', 'exported', 'published']), help='Project status')
def create(name: str, drive: str, description: str | None, aspect: str | None, resolution: str | None, duration: int | None, status: str):
    """Create a new project."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        project_id = db.create_project(
            name=name,
            description=description,
            aspect_ratio=aspect,
            target_duration_seconds=duration,
            status=status
        )
        click.echo(f"Created project '{name}' (ID: {project_id})")


@project.command()
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--status', default=None, type=click.Choice(['planning', 'gathering', 'ready', 'exported', 'published']), help='Filter by status')
@click.option('--aspect', '--aspect-ratio', default=None, type=click.Choice(['16:9', '4:3', '9:16', '1:1', '21:9'], case_sensitive=False), help='Filter by aspect ratio')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format')
def list(drive: str, status: str | None, aspect: str | None, output_format: str):
    """List all projects with optional filters."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        projects = db.list_projects(status=status, aspect_ratio=aspect)

        if output_format == 'json':
            click.echo(json.dumps(projects, indent=2, default=str))
        else:
            if not projects:
                click.echo("No projects found.")
                return

            click.echo(f"\nProjects ({len(projects)} total):")
            click.echo("=" * 80)
            click.echo(f"{'ID':<6} {'Name':<30} {'Status':<12} {'Aspect':<8} {'Duration'}")
            click.echo("-" * 80)

            for p in projects:
                duration_str = f"{int(p['target_duration_seconds'])}s" if p.get('target_duration_seconds') else "-"
                click.echo(
                    f"{p['id']:<6} {p['name'][:28]:<30} {p.get('status', '-'):<12} "
                    f"{p.get('aspect_ratio', '-'):<8} {duration_str}"
                )
            click.echo()


@project.command()
@click.argument('project_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--name', default=None, help='New project name')
@click.option('--description', default=None, help='New description')
@click.option('--status', default=None, type=click.Choice(['planning', 'gathering', 'ready', 'exported', 'published']), help='New status')
@click.option('--aspect', '--aspect-ratio', default=None, type=click.Choice(['16:9', '4:3', '9:16', '1:1', '21:9'], case_sensitive=False), help='New aspect ratio')
@click.option('--duration', '--target-duration', type=int, default=None, help='New target duration in seconds')
def update(project_id: int, drive: str, name: str | None, description: str | None, status: str | None, aspect: str | None, duration: int | None):
    """Update a project."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        project = db.get_project(project_id)
        if not project:
            click.echo(f"Project with ID {project_id} not found.", err=True)
            raise SystemExit(1)

        updates = {}
        if name is not None:
            updates['name'] = name
        if description is not None:
            updates['description'] = description
        if status is not None:
            updates['status'] = status
        if aspect is not None:
            updates['aspect_ratio'] = aspect
        if duration is not None:
            updates['target_duration_seconds'] = duration

        if not updates:
            click.echo("No updates specified. Use --name, --description, --status, --aspect, or --duration.", err=True)
            raise SystemExit(1)

        db.update_project(project_id, updates)
        click.echo(f"Updated project {project_id}")


@project.command()
@click.argument('project_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.confirmation_option(prompt='Are you sure you want to delete this project?')
def delete(project_id: int, drive: str):
    """Delete a project and all its clips."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        project = db.get_project(project_id)
        if not project:
            click.echo(f"Project with ID {project_id} not found.", err=True)
            raise SystemExit(1)

        result = db.delete_project(project_id)
        if result:
            click.echo(f"Deleted project '{project['name']}' (ID: {project_id})")
        else:
            click.echo(f"Failed to delete project {project_id}", err=True)
            raise SystemExit(1)


@project.command()
@click.argument('project_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help='Output format')
def show(project_id: int, drive: str, output_format: str):
    """Show project details including clips."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        project = db.get_project(project_id)
        if not project:
            click.echo(f"Project with ID {project_id} not found.", err=True)
            raise SystemExit(1)

        clips = db.get_project_clips(project_id)

        if output_format == 'json':
            output = {
                'project': project,
                'clips': clips
            }
            click.echo(json.dumps(output, indent=2, default=str))
        else:
            click.echo(f"\nProject: {project['name']}")
            click.echo("=" * 70)
            click.echo(f"ID: {project['id']}")
            if project.get('description'):
                click.echo(f"Description: {project['description']}")
            click.echo(f"Status: {project.get('status', '-')}")
            click.echo(f"Aspect Ratio: {project.get('aspect_ratio', '-')}")
            click.echo(f"Target Duration: {int(project['target_duration_seconds'])}s" if project.get('target_duration_seconds') else "Target Duration: -")
            click.echo(f"Created: {project.get('created_at', '-')}")
            click.echo(f"Updated: {project.get('updated_at', '-')}")

            if clips:
                click.echo(f"\nClips ({len(clips)}):")
                click.echo("-" * 70)
                click.echo(f"{'Pos':<4} {'Video ID':<10} {'Label':<20} {'In':<8} {'Out':<8}")
                click.echo("-" * 70)
                for c in clips:
                    label = c.get('marker_label', '-') or '-'
                    in_sec = f"{c['in_seconds']:.1f}s" if c.get('in_seconds') is not None else "-"
                    out_sec = f"{c['out_seconds']:.1f}s" if c.get('out_seconds') is not None else "-"
                    click.echo(
                        f"{c['position']:<4} {c['video_id']:<10} {label[:18]:<20} {in_sec:<8} {out_sec:<8}"
                    )
            else:
                click.echo("\nNo clips in this project.")
            click.echo()


@project.command(name='add-clip')
@click.argument('project_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--video', type=int, help='Video ID (for whole video)')
@click.option('--marker', type=int, help='Video marker ID (for marked segment)')
@click.option('--position', type=int, default=None, help='Position in sequence (default: append to end)')
@click.option('--notes', default=None, help='Usage notes for this clip')
def add_clip(project_id: int, drive: str, video: int | None, marker: int | None, position: int | None, notes: str | None):
    """Add a clip to a project. Either --video or --marker is required."""
    if not video and not marker:
        click.echo("Error: Either --video or --marker is required.", err=True)
        raise SystemExit(1)

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            click.echo(f"Project with ID {project_id} not found.", err=True)
            raise SystemExit(1)

        video_id = video
        marker_id = None

        if marker:
            # Get video_id from the marker
            conn = db.connect()
            row = conn.execute(
                "SELECT video_id FROM video_markers WHERE id = ?",
                (marker,)
            ).fetchone()
            if not row:
                click.echo(f"Marker with ID {marker} not found.", err=True)
                raise SystemExit(1)
            video_id = row['video_id']
            marker_id = marker

        clip_id = db.add_project_clip(
            project_id, video_id=video_id, video_marker_id=marker_id,
            position=position, notes=notes
        )
        click.echo(f"Added clip to project '{project['name']}' (clip ID: {clip_id})")


@project.command(name='remove-clip')
@click.argument('project_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--clip-id', required=True, type=int, help='ID of the project clip to remove')
@click.confirmation_option(prompt='Are you sure you want to remove this clip?')
def remove_clip(project_id: int, drive: str, clip_id: int):
    """Remove a clip from a project."""
    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        result = db.remove_project_clip(project_id, clip_id)
        if result:
            click.echo(f"Removed clip {clip_id} from project {project_id}")
        else:
            click.echo(f"Clip with ID {clip_id} not found in project {project_id}.", err=True)
            raise SystemExit(1)


@project.command(name='reorder')
@click.argument('project_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--clips', required=True, help='Comma-ordered list of clip IDs (e.g., 5,2,8,1)')
def reorder(project_id: int, drive: str, clips: str):
    """Reorder clips in a project by providing comma-ordered clip IDs."""
    try:
        clip_ids = [int(x.strip()) for x in clips.split(',')]
    except ValueError:
        click.echo("Error: --clips must be comma-separated integers", err=True)
        raise SystemExit(1)

    if not clip_ids:
        click.echo("Error: No clip IDs provided.", err=True)
        raise SystemExit(1)

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        db.reorder_project_clips(project_id, clip_ids)
        click.echo(f"Reordered {len(clip_ids)} clips in project {project_id}")


@project.command(name='export')
@click.argument('project_id', type=int)
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--format', default='canva', type=click.Choice(['canva']), help='Export format')
@click.option('--output', '-o', required=True, type=click.Path(), help='Output ZIP file path')
def export_project(project_id: int, drive: str, format: str, output: str):
    """Export project as Canva-ready ZIP with clips and voiceover script."""
    import subprocess

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)
    video_source_dir = drive_path  # Videos are in drive root

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    output_path = Path(output)

    with Database(db_path) as db:
        try:
            manifest = db.export_project(project_id, output_path, video_source_dir)
            click.echo(f"Exported project to {output_path}")
            click.echo(f"  - {len(manifest['clips'])} clips")
            click.echo(f"  - voiceover.txt")
            click.echo(f"  - manifest.json")
        except FileNotFoundError as e:
            click.echo(f"Video file not found: {e}", err=True)
            raise SystemExit(1)
        except subprocess.CalledProcessError as e:
            click.echo(f"FFmpeg error: {e}", err=True)
            raise SystemExit(1)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)


# =============================================================================
# Migrate Command
# =============================================================================

@cli.command()
@click.argument('drive_path', type=click.Path(exists=True, file_okay=False))
@click.option('--show-status', is_flag=True, help='Show current migration status without running migrations')
def migrate(drive_path: str, show_status: bool):
    """Run database migrations for the specified drive."""
    drive = Path(drive_path)
    db_path = get_db_path(drive)
    
    # Ensure .broll directory exists
    app_dir = db_path.parent
    app_dir.mkdir(parents=True, exist_ok=True)
    
    if show_status:
        click.echo(f"Migration status for {drive_path}:")
        status = _get_migration_status(drive)
        if status:
            click.echo(f"  {status}")
        else:
            click.echo("  No migrations applied yet")
        return
    
    click.echo(f"Running migrations for {drive_path}...")
    
    if _run_migrations(drive):
        click.echo(f"Migrations complete")
        status = _get_migration_status(drive)
        if status:
            click.echo(f"   Current: {status}")
    else:
        click.echo("Migration failed", err=True)
        raise SystemExit(1)


@cli.command()
@click.argument('drive_path', type=click.Path(exists=True, file_okay=False))
@click.option('--revision', default='da98fc08f8df', help='Alembic revision to stamp (default: da98fc08f8df for initial schema)')
def stamp(drive_path: str, revision: str):
    """Mark an existing database as migrated without running migrations.

    Use this for databases created before Alembic was added to the project.
    This marks the database as being at the specified revision without
    actually executing any migration SQL.

    After stamping, you can run 'broll migrate' to apply any newer migrations.

    \b
    Example:
        broll stamp /mnt/external-drive
        broll stamp /mnt/external-drive --revision head
    """
    drive = Path(drive_path)
    db_path = get_db_path(drive)

    if not db_path.exists():
        click.echo(f"Database not found at {db_path}", err=True)
        click.echo("This command is for existing databases that need migration stamping.", err=True)
        click.echo("For new drives, use 'broll init' instead.", err=True)
        raise SystemExit(1)

    # Verify it looks like a broll database (has videos table)
    try:
        with Database(db_path) as db:
            conn = db.connect()
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='videos'"
            ).fetchone()
            if not result:
                click.echo(f"Database at {db_path} does not appear to be a broll database.", err=True)
                click.echo("Expected 'videos' table not found.", err=True)
                raise SystemExit(1)
    except Exception as e:
        click.echo(f"Error checking database: {e}", err=True)
        raise SystemExit(1)

    # Find the project root (where alembic.ini lives)
    project_root = Path(__file__).parent.parent.parent
    alembic_ini = project_root / "alembic.ini"

    if not alembic_ini.exists():
        click.echo(f"Alembic configuration not found at {alembic_ini}", err=True)
        raise SystemExit(1)

    click.echo(f"Stamping database at {db_path} with revision '{revision}'...")

    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "alembic",
                "-c", str(alembic_ini),
                "-x", f"drive_path={drive_path}",
                "stamp", revision
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True
        )
        click.echo("Stamp complete!")

        # Show current status
        status = _get_migration_status(drive)
        if status:
            click.echo(f"   Current revision: {status}")

        click.echo("\nYou can now run 'broll migrate' to apply any newer migrations.")

    except subprocess.CalledProcessError as e:
        click.echo(f"Stamp failed: {e.stderr}", err=True)
        raise SystemExit(1)


# =============================================================================
# GPS & Location Commands
# =============================================================================

@cli.command()
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--lat', type=float, help='Latitude of center point')
@click.option('--lon', type=float, help='Longitude of center point')
@click.option('--location', help='Location name to geocode (alternative to lat/lon)')
@click.option('--radius', default='5km', help='Search radius (e.g., 5km, 2mi, 1000m)')
@click.option('--limit', default=50, help='Maximum number of results')
def nearby(drive: str, lat: float | None, lon: float | None, location: str | None, radius: str, limit: int):
    """Find videos within a radius of a location using Haversine formula."""
    import re
    import urllib.request
    import urllib.parse

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    # Parse radius with unit
    radius_match = re.match(r'^([\d.]+)\s*(km|m|mi)?$', radius.lower())
    if not radius_match:
        click.echo(f"Invalid radius format: {radius}. Use e.g., 5km, 2mi, 1000m", err=True)
        raise SystemExit(1)

    radius_value = float(radius_match.group(1))
    unit = radius_match.group(2) or 'km'

    # Convert to kilometers
    if unit == 'm':
        radius_km = radius_value / 1000
    elif unit == 'mi':
        radius_km = radius_value * 1.60934
    else:  # km
        radius_km = radius_value

    with Database(db_path) as db:
        # Determine coordinates
        if location:
            # Geocode location name
            cached = db.get_cached_location(location)
            if cached:
                lat, lon = cached['lat'], cached['lon']
                click.echo(f"Using cached coordinates for '{location}': {lat:.5f}, {lon:.5f}")
            else:
                # Call Nominatim API
                headers = {"User-Agent": "B-Roll-Organizer/0.3.0"}
                params = urllib.parse.urlencode(
                    {"q": location, "format": "json", "limit": 1, "addressdetails": 0}
                )
                url = f"https://nominatim.openstreetmap.org/search?{params}"

                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as response:
                        if response.status != 200:
                            click.echo(f"Geocoding failed: HTTP {response.status}", err=True)
                            raise SystemExit(1)

                        data = json.loads(response.read().decode())
                        if not data:
                            click.echo(f"Location not found: '{location}'", err=True)
                            raise SystemExit(1)

                        result = data[0]
                        lat = float(result.get("lat"))
                        lon = float(result.get("lon"))

                        # Cache the result
                        db.cache_location(location, lat, lon)
                        click.echo(f"Geocoded '{location}': {lat:.5f}, {lon:.5f}")
                except Exception as e:
                    click.echo(f"Geocoding error: {e}", err=True)
                    raise SystemExit(1)
        elif lat is None or lon is None:
            click.echo("Either --lat/--lon or --location is required", err=True)
            raise SystemExit(1)

        # Search for nearby videos
        videos = db.nearby_videos(lat, lon, radius_km, limit)

        if not videos:
            click.echo(f"\nNo videos found within {radius} of the specified location.")
            return

        click.echo(f"\nFound {len(videos)} video(s) within {radius}:")
        click.echo("-" * 80)

        for video in videos:
            distance = video.get('distance_km', 0)
            location_name = video.get('gps_location_name') or 'Unknown'
            source = video.get('location_source') or 'unknown'

            click.echo(f"\n  {video['file_name']}")
            click.echo(f"    Distance: {distance:.2f} km")
            click.echo(f"    Location: {location_name} (source: {source})")
            if video.get('scene_description'):
                desc = video['scene_description'][:60]
                if len(video['scene_description']) > 60:
                    desc += "..."
                click.echo(f"    Description: {desc}")


@cli.command()
@click.option('--drive', required=True, type=click.Path(exists=True, file_okay=False), help='Path to the external drive')
@click.option('--id', 'video_id', type=int, required=True, help='Video ID to update')
@click.option('--lat', type=float, required=True, help='Latitude')
@click.option('--lon', type=float, required=True, help='Longitude')
@click.option('--name', help='Location name (auto-reverse-geocoded if not provided)')
@click.option('--accuracy', type=float, help='GPS accuracy in meters')
def set_location(drive: str, video_id: int, lat: float, lon: float, name: str | None, accuracy: float | None):
    """Manually set GPS coordinates for a video."""
    from .metadata import reverse_geocode

    # Validate coordinates
    if not (-90 <= lat <= 90):
        click.echo(f"Invalid latitude: {lat}. Must be between -90 and 90.", err=True)
        raise SystemExit(1)
    if not (-180 <= lon <= 180):
        click.echo(f"Invalid longitude: {lon}. Must be between -180 and 180.", err=True)
        raise SystemExit(1)

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.", err=True)
        raise SystemExit(1)

    with Database(db_path) as db:
        # Verify video exists
        video = db.get_video_by_id(video_id)
        if not video:
            click.echo(f"Video with ID {video_id} not found.", err=True)
            raise SystemExit(1)

        # Auto-reverse-geocode if name not provided
        if name is None:
            name = reverse_geocode(lat, lon)
            if name:
                click.echo(f"Reverse geocoded location: {name}")
            else:
                name = "Unknown Location"

        # Update video location
        db.update_video_location(video_id, lat, lon, name, accuracy)

        click.echo(f"Updated location for '{video['file_name']}':")
        click.echo(f"  Coordinates: {lat:.5f}, {lon:.5f}")
        click.echo(f"  Location: {name}")
        if accuracy:
            click.echo(f"  Accuracy: {accuracy}m")
