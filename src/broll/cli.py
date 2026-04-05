# src/broll/cli.py
'''
CLI entry point for the b-roll organizer.
'''
from __future__ import annotations

import click
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
@click.version_option(version='0.3.0')
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
def search(query: str, drive: str, limit: int, mode: str, grid: str | None, export_gallery: str | None, gallery_base64: bool):
    """Search for video clips by description."""
    from .search import hybrid_search, keyword_search, semantic_search
    from .gallery import generate_contact_sheet, generate_html_gallery, get_grids_dir, parse_grid_size

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
                safe_query = "".join(c if c.isalnum() else "_" for c in query)[:30]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                grid_filename = f"grid_{safe_query}_{timestamp}_{cols}x{rows}.jpg"
                grid_path = grids_dir / grid_filename

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
                generate_html_gallery(
                    results,
                    gallery_path,
                    title=f"Search: {query}",
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


@cli.command()
@click.argument('drive_path', type=click.Path(exists=True, file_okay=False))
@click.option('--show-status', is_flag=True, help='Show current migration status')
def migrate(drive_path: str, show_status: bool):
    """Run database migrations on the external drive.
    
    This upgrades the database schema to the latest version.
    Use --show-status to see current migration state without running migrations.
    """
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
