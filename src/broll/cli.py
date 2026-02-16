# src/broll/cli.py
'''
CLI entry point for the b-roll organizer.
'''
from __future__ import annotations
from pickle import FALSE

import click
from datetime import datetime, timezone
from pathlib import Path

from .config import get_db_path, get_thumbs_dir, WEB_HOST, WEB_PORT
from .db import Database


@click.group()
@click.version_option(version='0.1.0')
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

    with Database(db_path) as db:
        db.initialize()

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
def process(drive_path: str, force: bool, scan_only: bool):
    '''Scan and process new videos on the drive.'''
    from tqdm import tqdm
    from .scanner import scan_drive
    from .metadata import extract_all_metadata
    from .frames import extract_keyframes
    from .analyzer import analyze_frames
    from .embeddings import generate_embedding, build_searchable_text

    drive = Path(drive_path)
    db_path = get_db_path(drive)
    thumbs_dir = get_thumbs_dir(drive)

    if not db_path.exists():
        click.echo('Database not found. Run &#x27;broll init&#x27; first.')
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

        if scan_only:
            click.echo(f'\n   Running in --scan-only mode (metadata only, no LLM)\n')
        else:
            click.echo()

        processed = 0
        errors = 0

        desc = 'Extracting metadata' if scan_only else 'Processing videos'
        for video_info in tqdm(new_files, desc=desc, unit='file'):
            try:
                # Step 1: Extract metadata (always)
                metadata = extract_all_metadata(video_info['absolute_path'])
                video_info.update(metadata)

                if not scan_only:
                    # Step 2: Extract keyframes
                    tqdm.write(f'  Extracting frames: {video_info['file_name']}')
                    keyframes = extract_keyframes(
                        video_info,
                        thumb_dir=str(thumbs_dir),
                    )

                    # Step 3: LLM vision analysis
                    tqdm.write(f'  Analyzing with {_get_vision_model_name()}...')
                    analysis = analyze_frames(keyframes)
                    video_info.update(analysis)

                    # Step 4: Generate embedding
                    search_text = build_searchable_text(video_info)
                    if search_text.strip():
                        tqdm.write(f'  Generating embedding...')
                        embedding = generate_embedding(search_text)
                        video_info['embedding'] = embedding
                else:
                    video_info['scene_description'] = None
                    video_info['tags'] = None
                    video_info['mood'] = None
                    video_info['camera_movement'] = None
                    video_info['time_of_day'] = None
                    video_info['thumbnail_path'] = None

                # Step 5: Save to database
                video_info['processed_at'] = datetime.now(timezone.utc).isoformat()
                db.insert_video(video_info)
                processed += 1

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
                    video_info["processed_at"] = datetime.now(timezone.utc).isoformat()
                    db.insert_video(video_info)
                except Exception:
                    pass

                errors += 1
                continue

        # Summary
        click.echo(f'\n{'-' * 50}')
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
                _print_analyzed_samples(new_files[:3])


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


@cli.command()
@click.argument("query")
@click.option("--drive", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--limit", default=10, help="Max results to show")
@click.option(
    "--mode",
    type=click.Choice(["hybrid", "keyword", "semantic"]),
    default="hybrid",
    help="Search mode",
)
def search(query: str, drive: str, limit: int, mode: str):
    """Search for video clips by description."""
    from .search import hybrid_search, keyword_search, semantic_search

    drive_path = Path(drive)
    db_path = get_db_path(drive_path)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    with Database(db_path) as db:
        stats = db.get_catalog_stats()
        click.echo(f"Searching {stats['total_videos']} videos ({mode} mode)...\n")

        if mode == "keyword":
            results = keyword_search(query, db, limit)
        elif mode == "semantic":
            results = semantic_search(query, db, limit)
        else:
            results = hybrid_search(query, db, limit)

        if not results:
            click.echo("No results found.")
            click.echo("\nTips:")
            click.echo("  - Try broader terms")
            click.echo("  - Use --mode keyword for exact word matching")
            click.echo("  - Use --mode semantic for meaning-based search")
            return

        click.echo(f"Found {len(results)} result(s):\n")

        for i, video in enumerate(results, 1):
            _print_search_result(i, video)


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
@click.option("--host", default=WEB_HOST, help="Host to bind to")
def web(drive_path: str, port: int, host: str):
    """Launch the web UI for browsing and chatting."""
    from .web.app import create_app

    drive = Path(drive_path)
    db_path = get_db_path(drive)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    app = create_app(drive_path)

    click.echo(f"\nB-Roll Catalog Web UI")
    click.echo(f"  http://{host}:{port}")
    click.echo(f"  Database: {db_path}")
    click.echo(f"  Press Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=False)



@cli.command()
@click.argument("drive_path", type=click.Path(exists=True, file_okay=False))
def stats(drive_path: str):
    """Show catalog statistics."""
    drive = Path(drive_path)
    db_path = get_db_path(drive)

    if not db_path.exists():
        click.echo("Database not found. Run 'broll init' first.")
        raise SystemExit(1)

    with Database(db_path) as db:
        s = db.get_catalog_stats()

    total_gb = s["total_size_bytes"] / (1024 ** 3)
    total_min = s["total_duration_seconds"] / 60

    click.echo(f"\nCatalog Statistics")
    click.echo(f"{'=' * 40}")
    click.echo(f"  Total videos:       {s['total_videos']}")
    click.echo(f"  With AI analysis:   {s['analyzed_count']}")
    click.echo(f"  With embeddings:    {s['total_with_embeddings']}")
    click.echo(f"  Geotagged:          {s['geotagged_count']}")
    click.echo(f"  Source devices:     {s['device_count']}")
    click.echo(f"  Total file size:    {total_gb:.2f} GB")
    click.echo(f"  Total duration:     {total_min:.1f} min")
    click.echo()
