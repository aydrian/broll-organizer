# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-04-06

### Added
- **Timeline View** - Browse B-roll chronologically by year, month, and day with activity heatmap
- **Batch Operations & Multi-Select** - Select multiple videos with Ctrl/Cmd+Click, then batch add to playlists or set location
- **Hover Video Previews** - Preview videos on hover in browse view with 200ms delay
- **Location Picker** - Search for places or enter coordinates manually when setting location
- Enhanced keyboard shortcuts (J/K for navigating videos)

### Fixed
- Fixed all JavaScript errors in browse.js (ReferenceError issues)
- Fixed duplicate "Online" indicators in header
- Fixed folder navigation not working
- Fixed multi-select toolbar not dismissing after operations
- Fixed location display not updating immediately after batch set
- Fixed timeline showing month numbers alongside names
- Fixed missing API endpoint for month view in timeline
- Fixed video-file endpoint for hover previews

### Changed
- Improved batch selection UI with "Select All" and "Deselect" buttons
- Updated multi-select toolbar with "📍 Location" button

## [0.3.0] - 2026-04-05

### Added
- Systemd service for auto-start on boot (`systemd/broll-catalog.service`)
- Install script for easy service setup (`systemd/install.sh`)
- Drive disconnection handling with friendly error page
- Graceful handling when external SSD is unplugged/plugged in
- Template `drive_not_connected.html` for offline drive status

### Changed
- Moved project to `/home/openclaw/apps/broll-organizer`
- Web UI now detects drive connection status before each request
- API returns 503 with JSON error when drive is disconnected

## [0.2.0] - 2025-12-21

### Added
- Interactive map view for browsing geotagged videos
- Location-based filtering in sidebar
- Cluster markers for dense video regions
- Popup previews on map markers

### Fixed
- GPS coordinate extraction from DJI video metadata
- Thumbnail generation for 4K videos

## [0.1.0] - 2025-12-15

### Added
- Initial release
- Video catalog with AI-generated scene descriptions
- Thumbnail generation with keyframe extraction
- Search with keyword + semantic (sqlite-vec) hybrid
- Playlist/collection management
- Basic web UI for browsing and searching
