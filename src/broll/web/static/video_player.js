/**
 * Professional Video Player with Frame Stepping, Trimming, and Enhanced Controls
 * 
 * Features:
 * - Frame-by-frame stepping (prev/next frame buttons, 30fps default)
 * - Playback speed control (0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x)
 * - Trimming UI with in/out point handles on scrubber
 * - Loop toggle for repeating clips
 * - Fullscreen with metadata overlay
 * - Picture-in-picture support
 * - Volume slider (0-150%)
 * - Enhanced keyboard shortcuts (space, arrows, j/k for frames)
 */

class VideoPlayer {
    constructor(container, videoId, options = {}) {
        this.container = container;
        this.videoId = videoId;
        this.options = {
            fps: options.fps || 30,
            videoSrc: options.videoSrc || null,
            metadata: options.metadata || {},
            onTrim: options.onTrim || null,
            ...options
        };

        this.video = null;
        this.isPlaying = false;
        this.isWaiting = false;
        this.playbackRate = 1;
        this.loop = false;
        this.trimStart = null;
        this.trimEnd = null;
        this.markers = [];           // Array of {id, label, in_seconds, out_seconds, color}
        this.activeMarkerId = null;  // Currently selected marker
        this.volume = 1;
        this.isFullscreen = false;
        this.isPiP = false;
        this.isDraggingTrim = null;
        this.frameStepSize = 1 / this.options.fps;

        this.elements = {};
        this.init();
    }

    init() {
        this.createPlayerHTML();
        this.cacheElements();
        this.bindEvents();
        this.setupKeyboardShortcuts();
        this.loadVideo();
    }

    createPlayerHTML() {
        const metadata = this.options.metadata;
        const tags = metadata.tags ? this.parseTags(metadata.tags) : [];

        this.container.innerHTML = `
            <div class="video-player-container" role="region" aria-label="Video player">
                <div class="video-wrapper">
                    <video class="video-element" preload="auto" playsinline crossorigin="anonymous" aria-label="Video content">
                        <source src="${this.options.videoSrc}" type="video/mp4">
                        Your browser does not support video playback.
                    </video>
                    <div class="metadata-overlay" id="metadataOverlay" aria-hidden="true">
                        <div class="metadata-content">
                            <div class="metadata-filename">${metadata.file_name || 'Unknown'}</div>
                            <div class="metadata-tags">
                                ${tags.map(tag => `<span class="metadata-tag">${tag}</span>`).join('')}
                            </div>
                            ${metadata.mood && metadata.mood !== 'unknown' ? `<div class="metadata-mood">Mood: ${metadata.mood}</div>` : ''}
                        </div>
                    </div>
                    <div class="loading-indicator" id="loadingIndicator" aria-hidden="true">
                        <div class="spinner" role="status"></div>
                    </div>
                </div>
                
                <div class="player-controls" role="toolbar" aria-label="Video player controls">
                    <div class="controls-row time-display-row">
                        <span class="current-time" id="currentTime" aria-label="Current time">00:00:00</span>
                        <span class="trim-indicators" id="trimIndicators" aria-live="polite"></span>
                        <span class="duration" id="duration" aria-label="Total duration">00:00:00</span>
                    </div>
                    
                    <div class="scrubber-container" id="scrubberContainer" role="slider" aria-label="Video progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" tabindex="0">
                        <div class="scrubber-track">
                            <div class="scrubber-buffered" id="scrubberBuffered" aria-hidden="true"></div>
                            <div class="trim-region" id="trimRegion" aria-hidden="true"></div>
                            <div class="scrubber-progress" id="scrubberProgress" aria-hidden="true"></div>
                            <div class="trim-handle trim-handle-in" id="trimHandleIn" data-handle="in" role="slider" aria-label="Trim start point" tabindex="0">
                                <div class="handle-marker" aria-hidden="true">&#9662;</div>
                                <div class="handle-label" aria-hidden="true">IN</div>
                            </div>
                            <div class="trim-handle trim-handle-out" id="trimHandleOut" data-handle="out" role="slider" aria-label="Trim end point" tabindex="0">
                                <div class="handle-marker" aria-hidden="true">&#9662;</div>
                                <div class="handle-label" aria-hidden="true">OUT</div>
                            </div>
                        </div>
                        <input type="range" class="scrubber-input" id="scrubberInput" min="0" max="100" step="0.01" value="0" aria-label="Seek video position">
                    </div>
                    
                    <div class="controls-row main-controls">
                        <div class="control-group left-controls" role="group" aria-label="Playback controls">
                            <button class="control-btn" id="playPauseBtn" title="Play/Pause (Space)" aria-label="Play or pause video">
                                <span class="icon-play" aria-hidden="true">▶</span>
                                <span class="icon-pause" aria-hidden="true">⏸</span>
                            </button>
                            <button class="control-btn" id="framePrevBtn" title="Previous Frame (← or J)" aria-label="Previous frame">
                                <span aria-hidden="true">⏴</span>
                            </button>
                            <button class="control-btn" id="frameNextBtn" title="Next Frame (→ or K)" aria-label="Next frame">
                                <span aria-hidden="true">⏵</span>
                            </button>
                            <div class="volume-container" role="group" aria-label="Volume controls">
                                <button class="control-btn" id="muteBtn" title="Mute (M)" aria-label="Toggle mute">
                                    <span class="icon-volume" aria-hidden="true">🔊</span>
                                    <span class="icon-mute" aria-hidden="true">🔇</span>
                                </button>
                                <input type="range" class="volume-slider" id="volumeSlider" min="0" max="1.5" step="0.01" value="1" title="Volume (0-150%)" aria-label="Volume level">
                            </div>
                        </div>
                        
                        <div class="control-group center-controls" role="group" aria-label="Playback settings">
                            <select class="speed-select" id="speedSelect" title="Playback Speed" aria-label="Playback speed">
                                <option value="0.25">0.25x</option>
                                <option value="0.5">0.5x</option>
                                <option value="0.75">0.75x</option>
                                <option value="1" selected>1x</option>
                                <option value="1.25">1.25x</option>
                                <option value="1.5">1.5x</option>
                                <option value="2">2x</option>
                            </select>
                            <button class="control-btn" id="loopBtn" title="Toggle Loop" aria-label="Toggle loop playback" aria-pressed="false">
                                <span class="loop-icon" aria-hidden="true">🔁</span>
                            </button>
                        </div>
                        
                        <div class="control-group right-controls" role="group" aria-label="Trim and export controls">
                            <button class="control-btn trim-btn" id="trimInBtn" title="Set In Point [" aria-label="Set trim start point">[<span class="trim-btn-label" aria-hidden="true">IN</span></button>
                            <button class="control-btn trim-btn" id="trimOutBtn" title="Set Out Point ]" aria-label="Set trim end point">]<span class="trim-btn-label" aria-hidden="true">OUT</span></button>
                            <button class="control-btn trim-btn" id="clearTrimBtn" title="Clear Trim Points" aria-label="Clear trim points">✕</button>
                            <button class="control-btn" id="saveMarkerBtn" title="Save as Marker (Shift+M)" aria-label="Save trim as marker">🚩</button>
                            <button class="control-btn" id="exportClipBtn" title="Export Clip" aria-label="Export trimmed clip">💾</button>
                            <button class="control-btn" id="pipBtn" title="Picture in Picture" aria-label="Toggle picture in picture" aria-pressed="false">
                                <span class="icon-pip" aria-hidden="true">⧉</span>
                            </button>
                            <button class="control-btn" id="fullscreenBtn" title="Fullscreen (F)" aria-label="Toggle fullscreen">
                                <span class="icon-fullscreen" aria-hidden="true">⛶</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    cacheElements() {
        this.elements = {
            video: this.container.querySelector('.video-element'),
            metadataOverlay: this.container.querySelector('#metadataOverlay'),
            loadingIndicator: this.container.querySelector('#loadingIndicator'),
            currentTime: this.container.querySelector('#currentTime'),
            duration: this.container.querySelector('#duration'),
            trimIndicators: this.container.querySelector('#trimIndicators'),
            scrubberContainer: this.container.querySelector('#scrubberContainer'),
            scrubberProgress: this.container.querySelector('#scrubberProgress'),
            scrubberBuffered: this.container.querySelector('#scrubberBuffered'),
            trimRegion: this.container.querySelector('#trimRegion'),
            trimHandleIn: this.container.querySelector('#trimHandleIn'),
            trimHandleOut: this.container.querySelector('#trimHandleOut'),
            scrubberInput: this.container.querySelector('#scrubberInput'),
            playPauseBtn: this.container.querySelector('#playPauseBtn'),
            framePrevBtn: this.container.querySelector('#framePrevBtn'),
            frameNextBtn: this.container.querySelector('#frameNextBtn'),
            muteBtn: this.container.querySelector('#muteBtn'),
            volumeSlider: this.container.querySelector('#volumeSlider'),
            speedSelect: this.container.querySelector('#speedSelect'),
            loopBtn: this.container.querySelector('#loopBtn'),
            trimInBtn: this.container.querySelector('#trimInBtn'),
            trimOutBtn: this.container.querySelector('#trimOutBtn'),
            clearTrimBtn: this.container.querySelector('#clearTrimBtn'),
            saveMarkerBtn: this.container.querySelector('#saveMarkerBtn'),
            exportClipBtn: this.container.querySelector('#exportClipBtn'),
            pipBtn: this.container.querySelector('#pipBtn'),
            fullscreenBtn: this.container.querySelector('#fullscreenBtn'),
        };
        this.video = this.elements.video;
    }

    bindEvents() {
        this.video.addEventListener('loadedmetadata', () => this.onLoadedMetadata());
        this.video.addEventListener('timeupdate', () => this.onTimeUpdate());
        this.video.addEventListener('play', () => this.onPlay());
        this.video.addEventListener('pause', () => this.onPause());
        this.video.addEventListener('waiting', () => this.onWaiting());
        this.video.addEventListener('canplay', () => this.onCanPlay());
        this.video.addEventListener('progress', () => this.onProgress());
        this.video.addEventListener('ended', () => this.onEnded());
        this.video.addEventListener('volumechange', () => this.onVolumeChange());
        this.video.addEventListener('enterpictureinpicture', () => this.onEnterPiP());
        this.video.addEventListener('leavepictureinpicture', () => this.onLeavePiP());

        this.elements.playPauseBtn.addEventListener('click', () => this.togglePlay());
        this.elements.framePrevBtn.addEventListener('click', () => this.stepFrame(-1));
        this.elements.frameNextBtn.addEventListener('click', () => this.stepFrame(1));
        this.elements.muteBtn.addEventListener('click', () => this.toggleMute());
        this.elements.volumeSlider.addEventListener('input', (e) => this.setVolume(e.target.value));
        this.elements.speedSelect.addEventListener('change', (e) => this.setPlaybackRate(parseFloat(e.target.value)));
        this.elements.loopBtn.addEventListener('click', () => this.toggleLoop());
        this.elements.trimInBtn.addEventListener('click', () => this.setTrimPoint('in'));
        this.elements.trimOutBtn.addEventListener('click', () => this.setTrimPoint('out'));
        this.elements.clearTrimBtn.addEventListener('click', () => this.clearTrim());
        this.elements.saveMarkerBtn.addEventListener('click', () => this.saveCurrentTrimAsMarker());
        this.elements.exportClipBtn.addEventListener('click', () => this.exportClip());
        this.elements.pipBtn.addEventListener('click', () => this.togglePiP());
        this.elements.fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());

        this.elements.scrubberInput.addEventListener('input', (e) => this.seekToPercent(parseFloat(e.target.value)));
        this.elements.scrubberInput.addEventListener('mousedown', () => this.onScrubberStart());
        this.elements.scrubberInput.addEventListener('mouseup', () => this.onScrubberEnd());
        this.elements.scrubberInput.addEventListener('touchstart', () => this.onScrubberStart());
        this.elements.scrubberInput.addEventListener('touchend', () => this.onScrubberEnd());

        this.elements.trimHandleIn.addEventListener('mousedown', (e) => this.onTrimHandleStart(e, 'in'));
        this.elements.trimHandleOut.addEventListener('mousedown', (e) => this.onTrimHandleStart(e, 'out'));
        this.elements.trimHandleIn.addEventListener('touchstart', (e) => this.onTrimHandleStart(e, 'in'));
        this.elements.trimHandleOut.addEventListener('touchstart', (e) => this.onTrimHandleStart(e, 'out'));

        document.addEventListener('mousemove', (e) => this.onTrimHandleMove(e));
        document.addEventListener('mouseup', () => this.onTrimHandleEnd());
        document.addEventListener('touchmove', (e) => this.onTrimHandleMove(e));
        document.addEventListener('touchend', () => this.onTrimHandleEnd());

        this.container.addEventListener('mousemove', () => this.showMetadataOverlay());
        let metadataTimeout;
        this.container.addEventListener('mousemove', () => {
            clearTimeout(metadataTimeout);
            metadataTimeout = setTimeout(() => this.hideMetadataOverlay(), 3000);
        });

        this.video.addEventListener('contextmenu', (e) => e.preventDefault());

        document.addEventListener('fullscreenchange', () => this.onFullscreenChange());
        document.addEventListener('webkitfullscreenchange', () => this.onFullscreenChange());
        document.addEventListener('mozfullscreenchange', () => this.onFullscreenChange());
        document.addEventListener('MSFullscreenChange', () => this.onFullscreenChange());
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
                return;
            }

            switch (e.key) {
                case ' ':
                case 'k':
                case 'K':
                    e.preventDefault();
                    this.togglePlay();
                    break;
                case 'ArrowLeft':
                    e.shiftKey ? this.seekRelative(-5) : this.stepFrame(-1);
                    break;
                case 'ArrowRight':
                    e.shiftKey ? this.seekRelative(5) : this.stepFrame(1);
                    break;
                case 'j':
                case 'J':
                    this.stepFrame(-1);
                    break;
                case 'l':
                case 'L':
                    this.stepFrame(1);
                    break;
                case 'f':
                case 'F':
                    this.toggleFullscreen();
                    break;
                case 'm':
                case 'M':
                    if (e.shiftKey) {
                        e.preventDefault();
                        this.saveCurrentTrimAsMarker();
                    } else {
                        this.toggleMute();
                    }
                    break;
                case '[':
                case 'i':
                case 'I':
                    this.setTrimPoint('in');
                    break;
                case ']':
                case 'o':
                case 'O':
                    this.setTrimPoint('out');
                    break;
                case 'Escape':
                    if (this.isFullscreen) this.exitFullscreen();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.adjustVolume(0.1);
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    this.adjustVolume(-0.1);
                    break;
            }
        });
    }

    loadVideo() {
        if (this.options.videoSrc) {
            this.elements.loadingIndicator.classList.add('visible');
        }
    }

    onLoadedMetadata() {
        this.elements.duration.textContent = this.formatTime(this.video.duration);
        this.elements.scrubberInput.max = this.video.duration;
        this.elements.scrubberInput.value = 0;
        this.elements.loadingIndicator.classList.remove('visible');

        if (this.options.metadata.fps) {
            this.options.fps = this.options.metadata.fps;
            this.frameStepSize = 1 / this.options.fps;
        }

        this.video.volume = this.volume;
        this.updateVolumeIcon();
        this.loadTrimFromURL();
        this.loadMarkers();  // Load markers for this video

        // Pre-buffer the first 10 seconds for smoother playback start
        this.prebuffer(10);
    }

    prebuffer(seconds) {
        // Ensure the browser has buffered enough data before playing
        const checkBuffer = () => {
            if (this.video.buffered.length > 0) {
                const bufferedEnd = this.video.buffered.end(0);
                if (bufferedEnd >= seconds || bufferedEnd >= this.video.duration) {
                    return;
                }
            }
            if (!this.video.paused) {
                // If already playing, let it continue
                return;
            }
            setTimeout(checkBuffer, 100);
        };
        checkBuffer();
    }

    onTimeUpdate() {
        const current = this.video.currentTime;
        const duration = this.video.duration;

        this.elements.currentTime.textContent = this.formatTime(current);

        const percent = (current / duration) * 100;
        this.elements.scrubberProgress.style.width = `${percent}%`;
        this.elements.scrubberInput.value = current;

        // Monitor buffer to prevent stuttering - show loading if buffer is low
        if (this.video.buffered.length > 0) {
            const bufferedEnd = this.video.buffered.end(this.video.buffered.length - 1);
            const bufferedAhead = bufferedEnd - current;
            const isBufferLow = bufferedAhead < 1.0 && current < duration - 2;

            if (isBufferLow && !this.video.paused) {
                // We might stall soon - show loading indicator proactively
                this.elements.loadingIndicator.classList.add('visible');
            } else if (!isBufferLow && !this.isWaiting) {
                // Buffer is healthy - hide loading
                this.elements.loadingIndicator.classList.remove('visible');
            }
        }

        if (this.trimStart !== null && this.trimEnd !== null) {
            if (current < this.trimStart) {
                this.video.currentTime = this.trimStart;
            } else if (current >= this.trimEnd) {
                if (this.loop) {
                    this.video.currentTime = this.trimStart;
                } else {
                    this.video.pause();
                    this.video.currentTime = this.trimStart;
                }
            }
        }
    }

    onPlay() {
        this.isPlaying = true;
        this.container.classList.add('playing');
        this.updatePlayButton();
    }

    onPause() {
        this.isPlaying = false;
        this.container.classList.remove('playing');
        this.updatePlayButton();
    }

    updatePlayButton() {
        const playIcon = this.elements.playPauseBtn.querySelector('.icon-play');
        const pauseIcon = this.elements.playPauseBtn.querySelector('.icon-pause');

        if (this.isPlaying) {
            if (playIcon) playIcon.style.display = 'none';
            if (pauseIcon) pauseIcon.style.display = 'inline';
            this.elements.playPauseBtn.setAttribute('aria-label', 'Pause video');
            this.elements.playPauseBtn.setAttribute('title', 'Pause (Space)');
        } else {
            if (playIcon) playIcon.style.display = 'inline';
            if (pauseIcon) pauseIcon.style.display = 'none';
            this.elements.playPauseBtn.setAttribute('aria-label', 'Play video');
            this.elements.playPauseBtn.setAttribute('title', 'Play (Space)');
        }
    }

    onWaiting() {
        this.isWaiting = true;
        this.elements.loadingIndicator.classList.add('visible');
    }

    onCanPlay() {
        this.isWaiting = false;
        this.elements.loadingIndicator.classList.remove('visible');
    }

    onProgress() {
        if (this.video.buffered.length > 0) {
            const bufferedEnd = this.video.buffered.end(this.video.buffered.length - 1);
            const duration = this.video.duration;
            const bufferedPercent = (bufferedEnd / duration) * 100;
            this.elements.scrubberBuffered.style.width = `${bufferedPercent}%`;
        }
    }

    onEnded() {
        if (this.loop && this.trimStart !== null && this.trimEnd !== null) {
            this.video.currentTime = this.trimStart;
            this.video.play();
        }
    }

    onVolumeChange() {
        this.volume = this.video.volume;
        this.elements.volumeSlider.value = this.volume;
        this.updateVolumeIcon();
    }

    onEnterPiP() {
        this.isPiP = true;
        this.elements.pipBtn.classList.add('active');
        this.elements.pipBtn.setAttribute('aria-pressed', 'true');
    }

    onLeavePiP() {
        this.isPiP = false;
        this.elements.pipBtn.classList.remove('active');
        this.elements.pipBtn.setAttribute('aria-pressed', 'false');
    }

    onFullscreenChange() {
        this.isFullscreen = !!document.fullscreenElement;
        this.container.classList.toggle('fullscreen', this.isFullscreen);
        if (this.isFullscreen) {
            this.showMetadataOverlay();
        }
    }

    togglePlay() {
        if (this.video.paused || this.video.ended) {
            // Ensure enough buffer before playing for smoother start
            this.playWhenReady();
        } else {
            this.video.pause();
        }
    }

    async playWhenReady(minBufferSeconds = 2) {
        // Wait until we have enough buffered data for smooth playback
        const hasEnoughBuffer = () => {
            if (this.video.buffered.length === 0) return false;
            const bufferedEnd = this.video.buffered.end(this.video.buffered.length - 1);
            const currentTime = this.video.currentTime;
            const bufferedAhead = bufferedEnd - currentTime;
            return bufferedAhead >= minBufferSeconds || bufferedEnd >= this.video.duration - 0.1;
        };

        if (!hasEnoughBuffer()) {
            this.elements.loadingIndicator.classList.add('visible');
            // Wait for canplay event or check periodically
            await new Promise(resolve => {
                const checkBuffer = () => {
                    if (hasEnoughBuffer() || this.video.readyState >= 4) {
                        resolve();
                    } else {
                        setTimeout(checkBuffer, 100);
                    }
                };
                const onCanPlay = () => {
                    if (hasEnoughBuffer()) {
                        this.video.removeEventListener('canplaythrough', onCanPlay);
                        resolve();
                    }
                };
                this.video.addEventListener('canplaythrough', onCanPlay, { once: true });
                checkBuffer();
            });
            this.elements.loadingIndicator.classList.remove('visible');
        }

        return this.video.play();
    }

    stepFrame(direction) {
        const wasPlaying = !this.video.paused;
        this.video.pause();
        
        const newTime = this.video.currentTime + (direction * this.frameStepSize);
        this.video.currentTime = Math.max(0, Math.min(newTime, this.video.duration));
        
        this.showFrameIndicator(direction > 0 ? 'forward' : 'backward');
    }

    setPlaybackRate(rate) {
        this.playbackRate = rate;
        this.video.playbackRate = rate;
        this.elements.speedSelect.value = rate;
    }

    toggleLoop() {
        this.loop = !this.loop;
        this.elements.loopBtn.classList.toggle('active', this.loop);
        this.elements.loopBtn.setAttribute('aria-pressed', this.loop.toString());
    }

    setVolume(value) {
        this.volume = parseFloat(value);
        this.video.volume = Math.min(1, this.volume);
        this.video.muted = false;
    }

    adjustVolume(delta) {
        const newVolume = Math.max(0, Math.min(1.5, this.volume + delta));
        this.setVolume(newVolume);
        this.elements.volumeSlider.value = newVolume;
    }

    toggleMute() {
        this.video.muted = !this.video.muted;
        this.updateVolumeIcon();
    }

    updateVolumeIcon() {
        const isMuted = this.video.muted || this.video.volume === 0;
        this.elements.muteBtn.classList.toggle('muted', isMuted);
    }

    seekToPercent(percent) {
        const time = (percent / 100) * this.video.duration;
        this.seekTo(time);
    }

    seekTo(time) {
        this.video.currentTime = Math.max(0, Math.min(time, this.video.duration));
    }

    seekRelative(seconds) {
        this.seekTo(this.video.currentTime + seconds);
    }

    onScrubberStart() {
        this.wasPlayingBeforeScrub = !this.video.paused;
        this.video.pause();
    }

    onScrubberEnd() {
        if (this.wasPlayingBeforeScrub) {
            this.video.play();
        }
    }

    setTrimPoint(type) {
        const current = this.video.currentTime;
        
        if (type === 'in') {
            this.trimStart = current;
            if (this.trimEnd !== null && this.trimEnd <= this.trimStart) {
                this.trimEnd = null;
            }
        } else {
            this.trimEnd = current;
            if (this.trimStart !== null && this.trimStart >= this.trimEnd) {
                this.trimStart = null;
            }
        }

        this.updateTrimUI();
        this.updateTrimIndicators();
        this.updateURLWithTrim();
        
        if (this.options.onTrim) {
            this.options.onTrim({ start: this.trimStart, end: this.trimEnd });
        }
    }

    clearTrim() {
        this.trimStart = null;
        this.trimEnd = null;
        this.updateTrimUI();
        this.updateTrimIndicators();
        this.updateURLWithTrim();
        
        if (this.options.onTrim) {
            this.options.onTrim({ start: null, end: null });
        }
    }

    updateTrimUI() {
        const duration = this.video.duration;

        if (this.trimStart !== null) {
            const leftPercent = (this.trimStart / duration) * 100;
            this.elements.trimHandleIn.style.left = `${leftPercent}%`;
            this.elements.trimHandleIn.classList.add('active');
        } else {
            this.elements.trimHandleIn.style.left = '0%';
            this.elements.trimHandleIn.classList.remove('active');
        }

        if (this.trimEnd !== null) {
            const rightPercent = (this.trimEnd / duration) * 100;
            this.elements.trimHandleOut.style.left = `${rightPercent}%`;
            this.elements.trimHandleOut.classList.add('active');
        } else {
            this.elements.trimHandleOut.style.left = '100%';
            this.elements.trimHandleOut.classList.remove('active');
        }

        if (this.trimStart !== null && this.trimEnd !== null) {
            const leftPercent = (this.trimStart / duration) * 100;
            const widthPercent = ((this.trimEnd - this.trimStart) / duration) * 100;
            this.elements.trimRegion.style.left = `${leftPercent}%`;
            this.elements.trimRegion.style.width = `${widthPercent}%`;
            this.elements.trimRegion.classList.add('active');
        } else {
            this.elements.trimRegion.classList.remove('active');
        }

        this.elements.trimInBtn.classList.toggle('active', this.trimStart !== null);
        this.elements.trimOutBtn.classList.toggle('active', this.trimEnd !== null);
    }

    updateTrimIndicators() {
        let text = '';
        if (this.trimStart !== null || this.trimEnd !== null) {
            text = 'Trim: ';
            if (this.trimStart !== null) text += this.formatTime(this.trimStart);
            text += ' - ';
            if (this.trimEnd !== null) text += this.formatTime(this.trimEnd);
        }
        this.elements.trimIndicators.textContent = text;
    }

    onTrimHandleStart(e, handle) {
        e.preventDefault();
        e.stopPropagation();
        this.isDraggingTrim = handle;
        this.wasPlayingBeforeTrim = !this.video.paused;
        this.video.pause();
    }

    onTrimHandleMove(e) {
        if (!this.isDraggingTrim) return;

        e.preventDefault();
        const containerRect = this.elements.scrubberContainer.getBoundingClientRect();
        
        const clientX = e.touches && e.touches.length > 0 ? e.touches[0].clientX : e.clientX;
        const percent = Math.max(0, Math.min(1, (clientX - containerRect.left) / containerRect.width));
        const time = percent * this.video.duration;

        if (this.isDraggingTrim === 'in') {
            this.trimStart = Math.max(0, Math.min(time, this.trimEnd || this.video.duration));
        } else {
            this.trimEnd = Math.min(this.video.duration, Math.max(time, this.trimStart || 0));
        }

        this.updateTrimUI();
        this.updateTrimIndicators();
        this.seekTo(this.isDraggingTrim === 'in' ? this.trimStart : this.trimEnd);
    }

    onTrimHandleEnd() {
        if (this.isDraggingTrim) {
            this.isDraggingTrim = null;
            this.updateURLWithTrim();
            if (this.options.onTrim) {
                this.options.onTrim({ start: this.trimStart, end: this.trimEnd });
            }
        }
    }

    loadTrimFromURL() {
        const urlParams = new URLSearchParams(window.location.search);
        const start = urlParams.get('trim_start');
        const end = urlParams.get('trim_end');
        
        if (start !== null) this.trimStart = parseFloat(start);
        if (end !== null) this.trimEnd = parseFloat(end);
        
        if (this.trimStart !== null || this.trimEnd !== null) {
            this.updateTrimUI();
            this.updateTrimIndicators();
        }
    }

    updateURLWithTrim() {
        const url = new URL(window.location);
        if (this.trimStart !== null) {
            url.searchParams.set('trim_start', this.trimStart.toFixed(3));
        } else {
            url.searchParams.delete('trim_start');
        }
        if (this.trimEnd !== null) {
            url.searchParams.set('trim_end', this.trimEnd.toFixed(3));
        } else {
            url.searchParams.delete('trim_end');
        }
        window.history.replaceState({}, '', url);
    }

    async exportClip() {
        if (this.trimStart === null && this.trimEnd === null) {
            alert('Please set trim points first');
            return;
        }

        const start = this.trimStart !== null ? this.trimStart : 0;
        const end = this.trimEnd !== null ? this.trimEnd : this.video.duration;
        const duration = end - start;

        if (duration <= 0) {
            alert('Invalid trim selection');
            return;
        }

        const formatTimeHMS = (seconds) => {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            return `${h}h${m.toString().padStart(2, '0')}m${s.toString().padStart(2, '0')}s`;
        };

        const baseName = (this.options.metadata.file_name || 'clip').replace(/\.[^/.]+$/, '');
        const filename = `${baseName}_trim_${formatTimeHMS(start)}-${formatTimeHMS(end)}.mp4`;

        this.elements.exportClipBtn.disabled = true;
        this.elements.exportClipBtn.textContent = '⏳';

        try {
            const response = await fetch('/api/clip/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_id: this.videoId,
                    start_time: start,
                    end_time: end,
                    filename: filename
                }),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Export failed');
            }

            const result = await response.json();
            
            const link = document.createElement('a');
            link.href = result.download_url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            this.showNotification(`Clip exported: ${filename}`);
        } catch (error) {
            console.error('Export error:', error);
            alert('Export failed: ' + error.message);
        } finally {
            this.elements.exportClipBtn.disabled = false;
            this.elements.exportClipBtn.textContent = '💾';
        }
    }

    toggleFullscreen() {
        if (this.isFullscreen) {
            this.exitFullscreen();
        } else {
            this.enterFullscreen();
        }
    }

    enterFullscreen() {
        const container = this.container.querySelector('.video-player-container');
        if (container.requestFullscreen) {
            container.requestFullscreen();
        } else if (container.webkitRequestFullscreen) {
            container.webkitRequestFullscreen();
        } else if (container.mozRequestFullScreen) {
            container.mozRequestFullScreen();
        } else if (container.msRequestFullscreen) {
            container.msRequestFullscreen();
        }
    }

    exitFullscreen() {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.mozCancelFullScreen) {
            document.mozCancelFullScreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
    }

    async togglePiP() {
        if (!document.pictureInPictureEnabled) {
            alert('Picture-in-Picture is not supported in your browser');
            return;
        }

        try {
            if (this.isPiP) {
                await document.exitPictureInPicture();
            } else {
                await this.video.requestPictureInPicture();
            }
        } catch (error) {
            console.error('PiP error:', error);
        }
    }

    showMetadataOverlay() {
        this.elements.metadataOverlay.classList.add('visible');
    }

    hideMetadataOverlay() {
        if (this.isFullscreen) {
            this.elements.metadataOverlay.classList.remove('visible');
        }
    }

    formatTime(seconds) {
        if (isNaN(seconds)) return '--:--';
        
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        const ms = Math.floor((seconds % 1) * 100);

        if (h > 0) {
            return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`;
        }
        return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`;
    }

    parseTags(tags) {
        if (typeof tags === 'string') {
            try {
                const parsed = JSON.parse(tags);
                if (Array.isArray(parsed)) return parsed;
            } catch (e) {
                return tags.split(',').map(t => t.trim()).filter(t => t);
            }
        }
        if (Array.isArray(tags)) return tags;
        return [];
    }

    showFrameIndicator(direction) {
        const indicator = document.createElement('div');
        indicator.className = `frame-indicator frame-${direction}`;
        indicator.textContent = direction === 'forward' ? '→' : '←';
        this.container.appendChild(indicator);
        
        requestAnimationFrame(() => indicator.classList.add('show'));
        setTimeout(() => {
            indicator.classList.remove('show');
            setTimeout(() => indicator.remove(), 300);
        }, 200);
    }

    showNotification(message) {
        const notification = document.createElement('div');
        notification.className = 'player-notification';
        notification.textContent = message;
        this.container.appendChild(notification);

        requestAnimationFrame(() => notification.classList.add('show'));
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    // ═════════════════════════════════════════════════════════════════
    // Marker (Clip In/Out Points) Methods
    // ═════════════════════════════════════════════════════════════════

    async loadMarkers() {
        """Load markers from the API for this video."""
        try {
            const response = await fetch(`/api/videos/${this.videoId}/markers`);
            if (!response.ok) {
                throw new Error('Failed to load markers');
            }
            const data = await response.json();
            this.markers = data.markers || [];
            this.renderMarkerIndicators();
            return this.markers;
        } catch (error) {
            console.error('Error loading markers:', error);
            return [];
        }
    }

    async saveMarker(label, inSeconds, outSeconds, color = '#3b82f6') {
        """Save a new marker for the current video."""
        try {
            const response = await fetch(`/api/videos/${this.videoId}/markers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    label: label,
                    in_seconds: inSeconds,
                    out_seconds: outSeconds,
                    color: color
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to save marker');
            }

            const data = await response.json();
            await this.loadMarkers();  // Refresh markers
            this.showNotification(`Marker '${label}' saved`);
            return data.marker_id;
        } catch (error) {
            console.error('Error saving marker:', error);
            alert('Failed to save marker: ' + error.message);
            return null;
        }
    }

    async deleteMarker(markerId) {
        """Delete a marker by ID."""
        try {
            const response = await fetch(`/api/markers/${markerId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error('Failed to delete marker');
            }

            await this.loadMarkers();
            this.showNotification('Marker deleted');
        } catch (error) {
            console.error('Error deleting marker:', error);
            alert('Failed to delete marker');
        }
    }

    async exportMarker(markerId) {
        """Export a marker segment as a video file."""
        const marker = this.markers.find(m => m.id === markerId);
        if (!marker) {
            alert('Marker not found');
            return;
        }

        const formatTimeHMS = (seconds) => {
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            return `${h}h${m.toString().padStart(2, '0')}m${s.toString().padStart(2, '0')}s`;
        };

        const baseName = (this.options.metadata.file_name || 'clip').replace(/\.[^/.]+$/, '');
        const filename = `${baseName}_${marker.label}_${formatTimeHMS(marker.in_seconds)}-${formatTimeHMS(marker.out_seconds)}.mp4`;

        try {
            const response = await fetch(`/api/markers/${markerId}/export`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Export failed');
            }

            // Download the file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);

            this.showNotification(`Marker exported: ${filename}`);
        } catch (error) {
            console.error('Export error:', error);
            alert('Export failed: ' + error.message);
        }
    }

    saveCurrentTrimAsMarker() {
        """Save the current trim region as a new marker."""
        if (this.trimStart === null || this.trimEnd === null) {
            alert('Please set both IN and OUT trim points first');
            return;
        }

        const label = prompt('Enter marker label (e.g., "money shot"):');
        if (!label || label.trim() === '') {
            return;
        }

        // Generate a random color from a palette
        const colors = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899'];
        const color = colors[Math.floor(Math.random() * colors.length)];

        this.saveMarker(label.trim(), this.trimStart, this.trimEnd, color);
    }

    loadMarkerIntoTrim(markerId) {
        """Load a marker's in/out points into the trim region."""
        const marker = this.markers.find(m => m.id === markerId);
        if (!marker) return;

        this.trimStart = marker.in_seconds;
        this.trimEnd = marker.out_seconds;
        this.activeMarkerId = markerId;
        this.updateTrimUI();
        this.updateTrimIndicators();
        this.updateURLWithTrim();
        this.seekTo(marker.in_seconds);

        if (this.options.onTrim) {
            this.options.onTrim({ start: this.trimStart, end: this.trimEnd });
        }
    }

    jumpToMarker(markerId) {
        """Jump to a marker's in point."""
        const marker = this.markers.find(m => m.id === markerId);
        if (marker) {
            this.seekTo(marker.in_seconds);
        }
    }

    renderMarkerIndicators() {
        """Render visual indicators for markers on the scrubber."""
        // Remove existing markers
        const existingMarkers = this.container.querySelectorAll('.marker-indicator');
        existingMarkers.forEach(m => m.remove());

        if (!this.video.duration || this.markers.length === 0) return;

        const track = this.container.querySelector('.scrubber-track');
        if (!track) return;

        this.markers.forEach(marker => {
            const leftPercent = (marker.in_seconds / this.video.duration) * 100;
            const widthPercent = ((marker.out_seconds - marker.in_seconds) / this.video.duration) * 100;

            const indicator = document.createElement('div');
            indicator.className = 'marker-indicator';
            indicator.style.cssText = `
                position: absolute;
                left: ${leftPercent}%;
                width: ${widthPercent}%;
                height: 4px;
                bottom: 0;
                background-color: ${marker.color || '#3b82f6'};
                border-radius: 2px;
                pointer-events: none;
                z-index: 3;
            `;
            indicator.title = `${marker.label} (${this.formatTime(marker.in_seconds)} - ${this.formatTime(marker.out_seconds)})`;
            track.appendChild(indicator);
        });
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { VideoPlayer };
}
