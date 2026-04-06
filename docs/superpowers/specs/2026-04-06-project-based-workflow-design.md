# Project-Based Workflow Design

**Date:** 2026-04-06  
**Status:** Approved for Implementation  
**Related Issues:** #47 (Usage Tracking), #50 (Content-Ideas Integration)

---

## Context

The current playlist system stores whole videos, not clips. With the addition of video markers (clip in/out points), we need a project-based workflow that:

1. Works with clips (marked segments) rather than whole videos
2. Tracks clip usage across projects to prevent overuse
3. Integrates with the OpenClaw Agent-managed content-ideas.md
4. Exports clip sequences for Canva final assembly
5. Supports voiceover scripts and project metadata

---

## Goals

- Replace playlists with **projects** as the content creation unit
- Enable clip-level organization across videos
- Provide usage heatmap to identify overused clips
- Support Canva export workflow (ZIP of MP4s + voiceover script)
- Enable Agent-managed bidirectional linking with content-ideas.md

---

## Non-Goals

- Complex video editing (cutting, transitions, effects) - Canva handles this
- Automatic content idea generation - Agent handles this
- Publishing integration - manual process

---

## Database Schema

### `projects` Table

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| name | TEXT NOT NULL | Project name |
| description | TEXT | Optional description |
| content_idea_reference | TEXT | Agent-managed reference to content-ideas.md |
| aspect_ratio | TEXT | Enum: `16:9`, `4:3`, `9:16`, `1:1`, `21:9` |
| output_resolution | TEXT | Enum: `720p`, `1080p`, `4K` |
| target_duration_seconds | INTEGER | Target length in seconds |
| status | TEXT | Enum: `planning`, `gathering`, `ready`, `exported`, `published` |
| voiceover_script | TEXT | Full script text |
| notes | TEXT | General project notes |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |

### `project_clips` Table

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| project_id | INTEGER NOT NULL | FK to projects |
| video_id | INTEGER NOT NULL | FK to videos |
| video_marker_id | INTEGER NULL | FK to video_markers (NULL = use whole video) |
| position | INTEGER NOT NULL | Order in project (0, 1, 2...) |
| notes | TEXT | Why this clip, usage notes |
| added_at | TEXT | ISO timestamp |

**Indexes:**
- `idx_project_clips_project_id` on project_id
- `idx_project_clips_position` on (project_id, position)

### `clip_usage` Table

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| video_id | INTEGER NOT NULL | FK to videos |
| video_marker_id | INTEGER NULL | FK to video_markers (NULL = whole video) |
| project_id | INTEGER NOT NULL | FK to projects |
| used_at | TEXT | ISO timestamp |

**Purpose:** Tracks every clip usage across projects. Enables heatmap by counting occurrences per clip.

**Index:**
- `idx_clip_usage_clip` on (video_id, video_marker_id)
- `idx_clip_usage_project` on project_id

---

## CLI Commands

### Project Management

```bash
# Create project
broll project create "Hidden Onsen Gems" \
  --idea-ref "idea-123" \
  --aspect 9:16 \
  --resolution 1080p \
  --duration 60 \
  --status planning

# List projects
broll project list [--status planning] [--aspect 9:16]

# Update project
broll project update 123 \
  --status ready \
  --script ./voiceover.txt \
  --notes "Focus on steam effects"

# Delete project
broll project delete 123

# Show project details with clips
broll project show 123
```

### Clip Management

```bash
# Add a marked clip to project
broll project add-clip 123 \
  --marker 456 \
  --position 1 \
  --notes "Opening shot with steam"

# Add whole video to project (creates implicit full-clip)
broll project add-clip 123 \
  --video 789 \
  --position 2

# Reorder clips
broll project reorder 123 --clips 456,789,101,112

# Remove clip from project
broll project remove-clip 123 --clip-id 456

# Update clip notes
broll project update-clip 123 --clip-id 456 --notes "Better lighting"
```

### Search with Usage Awareness

```bash
# Search clips unused in this project
broll search temple --unused-in-project 123

# Search with usage heatmap (shows count per result)
broll search temple --show-usage

# Show where a clip is used
broll clip-usage --video 789 --marker 456
```

### Export for Canva

```bash
# Export project as Canva-ready ZIP
broll project export 123 \
  --format canva \
  --output ./exports/hidden_onsen.zip

# Output contains:
#   001.mp4, 002.mp4, ... (clips in order)
#   voiceover.txt (script text)
#   manifest.json (metadata for reference)
```

---

## Web UI

### Projects List Page (`/projects`)

- Grid view of all projects
- Filter by: status, aspect_ratio
- Badges: status, clip count, target duration
- Quick actions: edit, delete, export

### Project Detail Page (`/projects/<id>`)

**Header Section:**
- Editable name, description
- Status dropdown (planning → gathering → ready → exported → published)
- Aspect ratio selector
- Output resolution selector
- Target duration input
- Content idea reference (display only, managed by Agent)

**Script Panel:**
- Text area for voiceover script
- Auto-save on blur/idle

**Notes Panel:**
- Text area for general project notes

**Clip Timeline:**
- Horizontal strip of clips in position order
- Each clip: thumbnail + label + duration + notes icon
- Drag handle for reordering
- Click to jump to video detail with marker highlighted
- Usage indicator (color-coded dot: green=unused, yellow=used, red=overused)
- Delete button on hover

**Add Clips Flow:**
- "Add Clips" button opens search interface
- Search results show "Add to Project" dropdown
- Selecting a marker adds it to the end of the timeline
- Or select "Use whole video" to add without markers

**Usage Heatmap Sidebar:**
- List of clips in this project with usage count
- Visual indicator: 0=green, 1-2=yellow, 3+=red
- Click to see other projects using this clip

### Video Detail Page Updates

**Markers Section:**
- Add "Add to Project" button on each marker row
- Usage indicator next to each marker (used in N projects)
- Tooltip on hover: list of project names

---

## Canva Export Format

The export command produces a ZIP file containing:

### Video Files

- `001.mp4`, `002.mp4`, ... `NNN.mp4`
- Clips exported in project position order
- H.264 codec for Canva compatibility
- Resolution per project setting (720p/1080p/4K)
- Aspect ratio maintained from source (assumes source matches project setting)

### voiceover.txt

Plain text file with the project's voiceover_script content, formatted for easy copy-paste:

```
Project: Hidden Onsen Gems
Target Duration: 60 seconds
Aspect Ratio: 9:16 (Vertical)

=== VO Script ===

[Full voiceover script text here]

=== End Script ===
```

### manifest.json (Optional Reference)

```json
{
  "project_id": 123,
  "name": "Hidden Onsen Gems",
  "exported_at": "2026-04-06T14:30:00Z",
  "clips": [
    {
      "sequence": 1,
      "filename": "001.mp4",
      "original_video": "DJI_0123.mp4",
      "marker_label": "steam opening",
      "in_seconds": 15.5,
      "out_seconds": 22.3,
      "duration_seconds": 6.8,
      "notes": "Opening shot with steam"
    }
  ]
}
```

---

## Agent Integration (OpenClaw)

### Agent Responsibilities

The OpenClaw Agent manages content-ideas.md and creates/updates projects:

1. **Create content ideas** in `content-ideas.md` with frontmatter IDs
2. **Create projects** from ideas: `broll project create "Title" --idea-ref "idea-123"`
3. **Update content-ideas.md** with project references:

   ```markdown
   ---
   id: idea-123
   status: in_progress
   ---

   # 5 Hidden Onsen in Beppu

   - **Project:** [#456](broll://project/456) (status: gathering)
   - **Aspect:** 9:16 vertical for Shorts/Reels
   - **Script:** [View/Edit](broll://project/456/script)
   ```

4. **Track project status** and update content-ideas.md accordingly

### Broll Skill Update

The `skills/broll-catalog/SKILL.md` file should be updated with new project commands:

```markdown
### Project Management

Create a project from a content idea:
```bash
uv run broll project create "Hidden Onsen Gems" \
  --idea-ref "idea-123" \
  --aspect 9:16 \
  --resolution 1080p \
  --duration 60
```

Add clips to a project:
```bash
# Add a marked segment
uv run broll project add-clip 456 --marker 78 --notes "Opening shot"

# Add whole video
uv run broll project add-clip 456 --video 123
```

Export for Canva:
```bash
uv run broll project export 456 --format canva --output ./export.zip
```
```

---

## Migration from Playlists

Since there are no existing playlists or markers in production, this is a **clean slate** implementation:

1. Keep `playlists` and `playlist_items` tables for now (backward compatibility)
2. Add new `projects`, `project_clips`, `clip_usage` tables
3. Web UI adds new "Projects" navigation alongside "Playlists"
4. Future migration: optionally convert playlists to projects

---

## Implementation Phases

### Phase 1: Database & CLI Foundation
- Create migration for projects, project_clips, clip_usage tables
- Implement `broll project create/list/update/delete`
- Implement `broll project add-clip/remove-clip/reorder`

### Phase 2: Search & Usage Tracking
- Add `--unused-in-project` and `--show-usage` to search
- Implement `clip_usage` recording when clips are added to projects
- Implement usage queries and heatmap data

### Phase 3: Canva Export
- FFmpeg integration to extract marker segments
- ZIP generation with numbered MP4s
- Voiceover script text file generation

### Phase 4: Web UI
- Projects list page
- Project detail page with clip timeline
- Drag-to-reorder implementation
- Usage heatmap visualization

### Phase 5: Agent Integration
- Update broll-catalog SKILL.md with new commands
- Document content-ideas.md linking convention

---

## Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| Keep playlists? | Yes, alongside projects for now (clean slate, no migration needed) |
| Content ideas in DB? | No - Agent manages content-ideas.md, projects store reference string |
| Platform or aspect ratio? | Aspect ratio + resolution (platforms derived from this) |
| Filenames in export? | Simple 001.mp4, 002.mp4 (order matters, not names) |
| Include voiceover? | Yes, as voiceover.txt in ZIP |
| Warn on overuse? | No - show heatmap instead (green/yellow/red indicator) |
| Reuse clips across projects? | Yes, track usage for awareness |

---

## Appendix: Usage Heatmap Algorithm

```python
def get_clip_usage_heat(video_id, marker_id=None):
    """Returns usage count and heat level."""
    count = query_clip_usage_count(video_id, marker_id)

    if count == 0:
        return {"count": 0, "level": "fresh", "color": "green"}
    elif count <= 2:
        return {"count": count, "level": "used", "color": "yellow"}
    else:
        return {"count": count, "level": "overused", "color": "red"}
```

Heatmap displayed as:
- Dot indicator on clip thumbnails
- Tooltip: "Used in 3 projects: Project A, Project B, Project C"
- Sidebar list in project detail showing all clips with their heat status
