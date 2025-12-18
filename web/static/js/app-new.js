// WebStatus - Slide-out Panel UI
class WebStatusApp {
    constructor() {
        this.apiBase = '/api/v1';
        this.refreshInterval = null;
        this.currentEditingId = null;
        this.selectedTargetId = null;
        this.eventLogPaused = false;
        this.eventLogRefreshInterval = null;
        this.allEvents = []; // Store all events for filtering
        this.filteredEvents = []; // Store filtered events
        this.eventFilters = {
            target: '',
            eventType: '',
            dateFrom: '',
            dateTo: ''
        };
        this.uptimeTimeRange = '24h'; // Default time range for uptime report
        this.devicePresets = {}; // Device type presets for auto-configuration
        this.features = {}; // Feature flags (loaded from backend)
        this.dashboardSortMethod = 'smart'; // Default sort method for dashboard
        this.incidentsDays = 14; // Default: 14 days for incidents
        this.allIncidents = []; // Store all incidents for show more
        this.showingAllIncidents = false; // Track show more state
        this.incidentsStatusFilter = 'all'; // Filter: all, ongoing, resolved
        this.incidentsSummary = null; // Store summary stats

        // Audio management for autoplay compatibility
        this.audioElements = {}; // Pre-loaded audio elements
        this.audioUnlocked = false; // Track if user has interacted
        this.audioInitialized = false; // Track if audio elements are initialized

        // Alert state polling (new approach for reliable audio alerts)
        this.alertStatePollInterval = null;
        this.alertStatePollFrequency = 2000; // Poll every 2 seconds
        this.localStorageKey = 'webstatus_audio_state';
        this.isInitialPoll = true; // Flag to prevent false alerts on page load
        this.initialPollCount = 0; // Count polls during initial load phase

        this.init();
    }

    // Security: Escape HTML to prevent XSS attacks
    escapeHtml(unsafe) {
        if (unsafe === null || unsafe === undefined) return '';
        return String(unsafe)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // ========================================
    // UI ENHANCEMENT HELPERS
    // ========================================

    // Generate enhanced spinner with text
    createSpinner(text = 'Loading...', size = 'normal') {
        const sizeClass = size === 'small' ? 'spinner-small' : '';
        return `
            <div class="spinner-container">
                <div class="spinner-enhanced ${sizeClass}"></div>
                <div class="spinner-text">${this.escapeHtml(text)}</div>
            </div>
        `;
    }

    // Generate dots loader
    createDotsLoader(text = '') {
        return `
            <div class="spinner-container">
                <div class="dots-loader">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
                ${text ? `<div class="spinner-text">${this.escapeHtml(text)}</div>` : ''}
            </div>
        `;
    }

    // Generate skeleton card for loading state
    createSkeletonCard() {
        return `
            <div class="skeleton-target-card">
                <div class="skeleton-line skeleton-line-title"></div>
                <div class="skeleton-badge"></div>
                <div class="skeleton-line skeleton-line-medium"></div>
                <div class="skeleton-line skeleton-line-short"></div>
            </div>
        `;
    }

    // Generate multiple skeleton cards
    createSkeletonGrid(count = 3) {
        return Array(count).fill(this.createSkeletonCard()).join('');
    }

    // Generate empty state
    createEmptyState(options = {}) {
        const {
            icon = '📊',
            title = 'No Data',
            description = 'There is no data to display.',
            actionText = null,
            actionCallback = null,
            compact = false,
            customClass = ''
        } = options;

        const compactClass = compact ? 'empty-state-compact' : '';
        const action = actionText ? `
            <div class="empty-state-action">
                <button class="btn btn-primary" onclick="${actionCallback || ''}"">
                    ${this.escapeHtml(actionText)}
                </button>
            </div>
        ` : '';

        return `
            <div class="empty-state ${compactClass} ${customClass}">
                <div class="empty-state-icon">${icon}</div>
                <h3 class="empty-state-title">${this.escapeHtml(title)}</h3>
                <p class="empty-state-description">${this.escapeHtml(description)}</p>
                ${action}
            </div>
        `;
    }

    // Add animation class to element
    addAnimation(element, animationClass) {
        if (element && animationClass) {
            element.classList.add(animationClass);
        }
    }

    // Add slide-in animation to multiple elements with stagger
    addStaggeredAnimation(elements, animationClass = 'slide-in') {
        elements.forEach((element, index) => {
            setTimeout(() => {
                element.classList.add(animationClass);
            }, index * 50);
        });
    }

    async init() {
        try {
            // Load feature flags first
            await this.loadFeatureFlags();

            this.setupEventListeners();

            this.loadTheme();

            this.loadDashboard();

            this.loadSettings();

            this.loadAudioLibrary();

            this.loadDevicePresets();

            // Initialize audio system for browser autoplay compatibility
            this.initializeAudioSystem();

            this.startAutoRefresh();

            // Start polling alert state for audio playback
            this.startAlertStatePolling();

        } catch (error) {
            console.error('❌ App initialization failed:', error);
        }
    }

    // ========================================
    // AUDIO SYSTEM MANAGEMENT
    // ========================================

    initializeAudioSystem() {
        console.log('🔊 Initializing audio system...');

        // Pre-load common audio files
        this.preloadAudioFile('system_down.aiff');
        this.preloadAudioFile('system_up.aiff');

        // Set up user interaction handler to unlock audio
        this.setupAudioUnlockHandler();

        // Disable media controls to prevent AirPods/keyboard controls from triggering alerts
        this.disableMediaControls();
    }

    preloadAudioFile(filename) {
        try {
            const audio = new Audio();
            audio.preload = 'auto';
            audio.volume = 1.0;
            audio.controls = false;  // Prevent browser from treating this as a media player

            // Try multiple formats for browser compatibility
            // Chrome doesn't support AIFF, so we'll try MP3 first, then AIFF for Safari
            const baseName = filename.replace(/\.(aiff|mp3|wav|ogg)$/i, '');
            const formats = ['mp3', 'aiff', 'wav'];

            // Set up sources with fallbacks
            formats.forEach(ext => {
                const source = document.createElement('source');
                source.src = `/sounds/${baseName}.${ext}`;
                source.type = ext === 'mp3' ? 'audio/mpeg' :
                             ext === 'aiff' ? 'audio/aiff' :
                             ext === 'wav' ? 'audio/wav' : 'audio/ogg';
                audio.appendChild(source);
            });

            // Store the audio element
            this.audioElements[filename] = audio;

            console.log(`✅ Pre-loaded audio: ${filename}`);
        } catch (error) {
            console.error(`Failed to preload audio ${filename}:`, error);
        }
    }

    setupAudioUnlockHandler() {
        // Create one-time handler for any user interaction
        const unlockAudio = async () => {
            if (this.audioUnlocked) return;

            try {
                // Try to play and immediately pause all pre-loaded audio
                // This "unlocks" the audio context in the browser
                for (const filename in this.audioElements) {
                    const audio = this.audioElements[filename];
                    await audio.play();
                    audio.pause();
                    audio.currentTime = 0;
                }

                this.audioUnlocked = true;
                console.log('✅ Audio context unlocked');

                // Remove event listeners after unlock
                document.removeEventListener('click', unlockAudio);
                document.removeEventListener('keydown', unlockAudio);
                document.removeEventListener('touchstart', unlockAudio);
            } catch (error) {
                console.warn('Audio unlock attempt failed:', error);
            }
        };

        // Listen for any user interaction
        document.addEventListener('click', unlockAudio, { once: false });
        document.addEventListener('keydown', unlockAudio, { once: false });
        document.addEventListener('touchstart', unlockAudio, { once: false });

        console.log('🎧 Audio unlock handlers set up (waiting for user interaction)');
    }

    disableMediaControls() {
        // Prevent AirPods, keyboard, and other media controls from triggering our alert audio
        try {
            if ('mediaSession' in navigator) {
                // Set playback state to 'none' to tell the browser we don't support media controls
                navigator.mediaSession.playbackState = 'none';

                // Disable all media control action handlers
                const mediaActions = ['play', 'pause', 'stop', 'seekbackward', 'seekforward',
                                     'seekto', 'previoustrack', 'nexttrack'];

                mediaActions.forEach(action => {
                    try {
                        // Set handlers to do nothing (prevents default browser behavior)
                        navigator.mediaSession.setActionHandler(action, null);
                    } catch (error) {
                        // Some browsers don't support all actions, ignore errors
                    }
                });

                console.log('🚫 Media controls disabled (AirPods/keyboard controls won\'t trigger alerts)');
            } else {
                console.log('⚠️  Media Session API not supported in this browser');
            }
        } catch (error) {
            console.warn('Failed to disable media controls:', error);
        }
    }

    playAlertAudio(alertData) {
        const audioFilename = alertData.audio_filename || 'system_down.aiff';
        const eventType = alertData.event_type || 'unknown';

        console.log(`🔊 Playing alert audio: ${audioFilename} (type: ${eventType})`);

        // Check if we have a pre-loaded element for this file
        if (this.audioElements[audioFilename]) {
            const audio = this.audioElements[audioFilename];

            // Reset to beginning and play
            audio.currentTime = 0;

            audio.play()
                .then(() => {
                    console.log(`✅ Successfully played: ${audioFilename}`);
                })
                .catch(error => {
                    console.error(`Failed to play ${audioFilename}:`, error);

                    if (!this.audioUnlocked) {
                        this.showToast('Click anywhere to enable audio alerts', 'warning');
                    } else {
                        this.showToast('Failed to play audio', 'error');
                    }
                });
        } else {
            // Fallback to creating new audio element
            console.warn(`No pre-loaded audio for ${audioFilename}, using fallback`);
            this.previewAudio(audioFilename);
        }
    }

    // ========================================
    // ALERT STATE POLLING
    // ========================================

    startAlertStatePolling() {
        console.log('🔄 Starting alert state polling (every 2 seconds)...');

        // Poll immediately
        this.pollAlertState();

        // Then poll every 2 seconds
        this.alertStatePollInterval = setInterval(() => {
            this.pollAlertState();
        }, this.alertStatePollFrequency);
    }

    stopAlertStatePolling() {
        if (this.alertStatePollInterval) {
            clearInterval(this.alertStatePollInterval);
            this.alertStatePollInterval = null;
            console.log('🛑 Stopped alert state polling');
        }
    }

    async pollAlertState() {
        try {
            const response = await fetch(`${this.apiBase}/alerts/state`);
            if (!response.ok) {
                console.error('Failed to fetch alert state:', response.status);
                return;
            }

            const serverState = await response.json();
            this.handleAlertState(serverState);
        } catch (error) {
            console.error('Error polling alert state:', error);
        }
    }

    handleAlertState(serverState) {
        const localState = this.getLocalAlertState();

        // During initial poll window, we need to RECORD alert state but NOT play sounds
        // This prevents false alerts on page refresh/load
        if (this.isInitialPoll) {
            // Record current state to localStorage without playing sounds
            if (serverState.is_alerting && serverState.current_alert) {
                const alert = serverState.current_alert;
                console.log(`🔄 Initial poll ${this.initialPollCount + 1}/3 - Recording down alert (${alert.target_name}) without playing`);

                // Save to localStorage so future polls know about this alert
                this.saveLocalAlertState({
                    ...localState,
                    last_down_alert: {
                        target_id: alert.target_id,
                        target_name: alert.target_name,
                        played_at: new Date().toISOString()  // Mark as "played" to prevent immediate playback
                    }
                });
            }

            // Record recovery state without playing
            if (serverState.last_recovery) {
                const recovery = serverState.last_recovery;
                console.log(`🔄 Initial poll ${this.initialPollCount + 1}/3 - Recording recovery (${recovery.target_name}) without playing`);

                this.saveLocalAlertState({
                    ...localState,
                    last_recovery_played: {
                        target_id: recovery.target_id,
                        target_name: recovery.target_name,
                        played_at: new Date(recovery.timestamp).toISOString()
                    }
                });
            }

            // Increment poll counter
            this.initialPollCount++;
            if (this.initialPollCount >= 3) {
                console.log('✅ Initial alert state window complete - alerts now enabled');
                this.isInitialPoll = false;
            }

            // Exit early - don't process alerts during initial window
            return;
        }

        // After initial poll window, process alerts normally
        // Check for DOWN alerts
        if (serverState.is_alerting && serverState.current_alert) {
            this.handleDownAlert(serverState.current_alert, localState);
        }

        // Check for RECOVERY alerts
        if (serverState.last_recovery) {
            this.handleRecoveryAlert(serverState.last_recovery, localState);
        }
    }

    handleDownAlert(alert, localState) {
        const now = new Date();
        const nextPlayTime = new Date(alert.next_play_time);
        const intervalMs = alert.interval_seconds * 1000;
        const lastIntervalTime = new Date(nextPlayTime - intervalMs);

        // Check if we should play this interval
        if (now >= lastIntervalTime) {
            const lastDownAlert = localState.last_down_alert;

            // Check if this is a different target than before
            if (!lastDownAlert || lastDownAlert.target_id !== alert.target_id) {
                console.log(`🔄 Alert switched to new target: ${alert.target_name}`);
                // Don't play immediately - wait for next interval
                // Just record the target switch
                this.saveLocalAlertState({
                    ...localState,
                    last_down_alert: {
                        target_id: alert.target_id,
                        played_at: null  // Will play at next interval
                    }
                });
                return;
            }

            // Same target - check if we've already played this interval
            const lastPlayed = lastDownAlert && lastDownAlert.played_at
                ? new Date(lastDownAlert.played_at)
                : null;

            if (!lastPlayed || lastPlayed < lastIntervalTime) {
                // Time to play!
                console.log(`🔊 Playing DOWN alert: ${alert.target_name} (interval: ${alert.interval_seconds}s)`);
                this.playAudioFile(alert.audio_file);

                // Record that we played this interval
                this.saveLocalAlertState({
                    ...localState,
                    last_down_alert: {
                        target_id: alert.target_id,
                        target_name: alert.target_name,
                        played_at: now.toISOString()
                    }
                });
            }
        }
    }

    handleRecoveryAlert(recovery, localState) {
        const lastRecoveryPlayed = localState.last_recovery_played;
        const recoveryTimestamp = new Date(recovery.timestamp);

        // Check if we've already played this recovery
        if (!lastRecoveryPlayed ||
            lastRecoveryPlayed.target_id !== recovery.target_id ||
            new Date(lastRecoveryPlayed.played_at) < recoveryTimestamp) {

            // Play recovery sound
            console.log(`🔊 Playing RECOVERY alert: ${recovery.target_name}`);
            this.playAudioFile(recovery.audio_file);

            // Show toast notification
            this.showToast(`✅ ${recovery.target_name} has recovered`, 'success');

            // Record that we played this recovery
            this.saveLocalAlertState({
                ...this.getLocalAlertState(),
                last_recovery_played: {
                    target_id: recovery.target_id,
                    target_name: recovery.target_name,
                    played_at: new Date().toISOString()
                }
            });
        }
    }

    playAudioFile(filename) {
        // Use existing audio playback infrastructure
        if (this.audioElements[filename]) {
            const audio = this.audioElements[filename];
            audio.currentTime = 0;

            audio.play()
                .then(() => {
                    console.log(`✅ Successfully played: ${filename}`);
                })
                .catch(error => {
                    console.error(`Failed to play ${filename}:`, error);

                    if (!this.audioUnlocked) {
                        this.showToast('Click anywhere to enable audio alerts', 'warning');
                    } else {
                        this.showToast('Failed to play audio', 'error');
                    }
                });
        } else {
            // Fallback - try to play anyway
            console.warn(`No pre-loaded audio for ${filename}, attempting fallback`);
            this.previewAudio(filename);
        }
    }

    getLocalAlertState() {
        try {
            const stored = localStorage.getItem(this.localStorageKey);
            return stored ? JSON.parse(stored) : {
                last_down_alert: null,
                last_recovery_played: null
            };
        } catch (error) {
            console.error('Error reading localStorage:', error);
            return {
                last_down_alert: null,
                last_recovery_played: null
            };
        }
    }

    saveLocalAlertState(state) {
        try {
            localStorage.setItem(this.localStorageKey, JSON.stringify(state));
        } catch (error) {
            console.error('Error writing to localStorage:', error);
        }
    }

    setupEventListeners() {
        // Sidebar toggles - Nav hamburger button
        document.getElementById('navHamburgerBtn').addEventListener('click', () => this.openSidebar());
        document.getElementById('closeSidebarBtn').addEventListener('click', () => this.closeSidebar());
        document.getElementById('sidebarOverlay').addEventListener('click', () => this.closeSidebar());

        // Sidebar navigation
        document.querySelectorAll('.sidebar-nav-item').forEach(button => {
            button.addEventListener('click', (e) => {
                const tab = e.currentTarget.dataset.tab;
                
                this.switchTab(tab);
                this.closeSidebar();
            });
        });
        

        // Sidebar action buttons
        document.getElementById('sidebarAddTargetBtn').addEventListener('click', () => {
            this.showTargetEditPanel();
            this.closeSidebar();
        });

        // Logout button
        document.getElementById('logoutBtn').addEventListener('click', async () => {
            if (confirm('Are you sure you want to logout?')) {
                try {
                    const response = await fetch('/auth/logout', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    });
                    if (response.ok) {
                        window.location.href = '/auth/login';
                    }
                } catch (error) {
                    console.error('Logout failed:', error);
                    alert('Logout failed. Please try again.');
                }
            }
        });

        // Target Edit Panel buttons
        document.getElementById('closeTargetEditBtn').addEventListener('click', () => this.hideTargetEditPanel());
        document.getElementById('targetEditOverlay').addEventListener('click', () => this.hideTargetEditPanel());
        document.getElementById('targetForm').addEventListener('submit', (e) => this.handleTargetSubmit(e));

        // Slide panel buttons
        document.getElementById('closeSlidePanelBtn').addEventListener('click', () => this.closeSlidePanel());
        document.getElementById('slidePanelOverlay').addEventListener('click', () => this.closeSlidePanel());

        // Settings button
        document.getElementById('saveSettingsBtn')?.addEventListener('click', () => this.saveSettings());

        // Event log buttons
        document.getElementById('clearEventsBtn')?.addEventListener('click', () => this.clearEventLog());
        document.getElementById('pauseEventsBtn')?.addEventListener('click', () => this.toggleEventLogPause());
        document.getElementById('exportCsvBtn')?.addEventListener('click', () => this.exportEventsCsv());
        document.getElementById('exportJsonBtn')?.addEventListener('click', () => this.exportEventsJson());
        document.getElementById('applyFiltersBtn')?.addEventListener('click', () => this.applyEventFilters());

        // Dashboard sort dropdown
        const dashboardSortSelect = document.getElementById('dashboardSortSelect');
        if (dashboardSortSelect) {
            // Load saved sort preference from localStorage
            const savedSort = localStorage.getItem('webstatus_dashboard_sort');
            if (savedSort) {
                this.dashboardSortMethod = savedSort;
                dashboardSortSelect.value = savedSort;
            }

            // Sort dropdown change handler
            dashboardSortSelect.addEventListener('change', (e) => {
                this.dashboardSortMethod = e.target.value;
                localStorage.setItem('webstatus_dashboard_sort', e.target.value);
                this.loadDashboard(); // Re-render with new sort
            });
        }

        // Incidents filter buttons
        document.querySelectorAll('.incidents-filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.incidents-filter-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.incidentsDays = parseInt(e.target.dataset.days);
                this.loadIncidents();
            });
        });

        // Incidents status filter dropdown
        document.getElementById('incidentsStatusFilter')?.addEventListener('change', (e) => {
            this.incidentsStatusFilter = e.target.value;
            this.renderIncidents(this.allIncidents, this.showingAllIncidents);
        });

        // Incidents show more button
        document.getElementById('incidentsShowMoreBtn')?.addEventListener('click', () => this.toggleShowMoreIncidents());

        // Uptime filter buttons
        document.querySelectorAll('.uptime-filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.uptime-filter-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.uptimeTimeRange = e.target.dataset.range;
                this.loadUptimeDashboard();
            });
        });
        document.getElementById('clearFiltersBtn')?.addEventListener('click', () => this.clearEventFilters());

        // Device type buttons
        document.getElementById('deviceType')?.addEventListener('change', (e) => this.handleDeviceTypeChange(e));
        document.getElementById('targetType')?.addEventListener('change', (e) => this.handleTargetTypeChange(e));

        // Discovery buttons
        document.getElementById('startDiscoveryBtn')?.addEventListener('click', () => this.startDiscovery());
        document.getElementById('stopDiscoveryBtn')?.addEventListener('click', () => this.stopDiscovery());
        document.getElementById('selectAllDevicesBtn')?.addEventListener('click', () => this.selectAllDevices());
        document.getElementById('deselectAllDevicesBtn')?.addEventListener('click', () => this.deselectAllDevices());
        document.getElementById('importSelectedBtn')?.addEventListener('click', () => this.importSelectedDevices());

        // Audio library buttons (now in Settings)
        document.getElementById('uploadNewSoundBtn')?.addEventListener('click', () => this.showAudioUploadForm());
        document.getElementById('cancelUploadBtn')?.addEventListener('click', () => this.hideAudioUploadForm());
        document.getElementById('uploadAudioBtn')?.addEventListener('click', () => this.uploadNewAudioToLibrary());
        document.getElementById('previewDownAudioBtn')?.addEventListener('click', () => {
            let filename = document.getElementById('audioDownAlert').value;
            // If "Use Default" is selected (empty), use the actual default from library
            if (!filename && this.audioLibrary) {
                filename = this.audioLibrary.default_down_alert || 'system_down.aiff';
            }
            if (filename) this.previewAudio(filename);
        });
        document.getElementById('previewUpAudioBtn')?.addEventListener('click', () => {
            let filename = document.getElementById('audioUpAlert').value;
            // If "Use Default" is selected (empty), use the actual default from library
            if (!filename && this.audioLibrary) {
                filename = this.audioLibrary.default_up_alert || 'system_up.aiff';
            }
            if (filename) this.previewAudio(filename);
        });
        document.getElementById('previewDefaultDownBtn')?.addEventListener('click', () => {
            const filename = document.getElementById('defaultDownSound').value;
            if (filename) this.previewAudio(filename);
        });
        document.getElementById('previewDefaultUpBtn')?.addEventListener('click', () => {
            const filename = document.getElementById('defaultUpSound').value;
            if (filename) this.previewAudio(filename);
        });

        // Health dashboard button
        document.getElementById('refreshHealthBtn')?.addEventListener('click', () => this.loadHealthDashboard());

        // Test audio button
        document.getElementById('testAudioBtn')?.addEventListener('click', () => this.testAudio());

        // SMTP settings buttons
        document.getElementById('testSmtpBtn')?.addEventListener('click', () => this.testSmtp());

        // Backup settings buttons
        document.getElementById('createBackupBtn')?.addEventListener('click', () => this.createBackup());
        document.getElementById('viewBackupsBtn')?.addEventListener('click', () => this.toggleBackupList());
        document.getElementById('uploadBackupBtn')?.addEventListener('click', () => this.triggerBackupUpload());
        document.getElementById('backupFileInput')?.addEventListener('change', (e) => this.handleBackupUpload(e));

        // Theme selector buttons
        document.querySelectorAll('.theme-option').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const theme = e.currentTarget.dataset.theme;
                this.setTheme(theme);
            });
        });

        // Sharing tab buttons
        document.getElementById('generateTokenBtn')?.addEventListener('click', () => this.generatePublicToken());
        document.getElementById('previewPublicPageBtn')?.addEventListener('click', () => this.previewPublicPage());

        // API key management buttons
        document.getElementById('generateApiKeyBtn')?.addEventListener('click', () => this.openGenerateApiKeyModal());
        document.getElementById('confirmGenerateApiKeyBtn')?.addEventListener('click', () => this.createApiKey());
    }

    openSidebar() {
        document.getElementById('sidebar').classList.add('active');
        document.getElementById('sidebarOverlay').classList.add('active');
    }

    closeSidebar() {
        document.getElementById('sidebar').classList.remove('active');
        document.getElementById('sidebarOverlay').classList.remove('active');
    }

    async loadDashboard() {
        const grid = document.getElementById('targetsGrid');

        try {
            const [targets, status] = await Promise.all([
                this.apiGet('/targets'),
                this.apiGet('/status')
            ]);

            // Only show skeleton on first load (when grid is empty or has empty state)
            const isFirstLoad = !grid || grid.children.length === 0 || grid.querySelector('.empty-state');
            if (grid && targets.length > 0 && isFirstLoad) {
                grid.innerHTML = this.createSkeletonGrid(6);
            }

            // Fetch uptime metrics for each target
            const targetsWithUptime = await Promise.all(
                targets.map(async (target) => {
                    try {
                        const uptime = await this.apiGet(`/targets/${target.id}/uptime`);
                        return { ...target, uptime };
                    } catch (error) {
                        console.error(`Failed to load uptime for ${target.name}:`, error);
                        return target; // Return without uptime if it fails
                    }
                })
            );

            this.renderCompactTargets(targetsWithUptime);
            this.updateSystemStatus(status);
            this.updateAlertIndicator(targetsWithUptime);
        } catch (error) {
            console.error('Failed to load dashboard:', error);
            if (grid) {
                grid.innerHTML = this.createEmptyState({
                    icon: '⚠️',
                    title: 'Failed to Load Dashboard',
                    description: 'There was an error loading the dashboard. Please try refreshing the page.',
                    compact: true
                });
            }
        }
    }

    // Uptime Dashboard - Status Page Timeline
    async loadUptimeDashboard() {
        const grid = document.getElementById('uptimeGrid');

        if (!grid) {
            return;
        }

        // Show enhanced spinner
        grid.innerHTML = this.createSpinner('Loading uptime data...');

        try {
            const targets = await this.apiGet('/targets');

            if (targets.length === 0) {
                grid.innerHTML = this.createEmptyState({
                    icon: '📊',
                    title: 'No Targets Configured',
                    description: 'Add monitoring targets to see uptime reports and status history.',
                    actionText: '+ Add Target',
                    actionCallback: 'app.showTargetEditPanel()',
                    customClass: 'empty-targets'
                });
                return;
            }

            // Calculate history limit based on time range
            const limits = {
                '24h': 1440,   // 1 check per minute for 24 hours
                '7d': 10080,   // 1 check per minute for 7 days
                '30d': 43200,  // 1 check per minute for 30 days
                '90d': 129600  // 1 check per minute for 90 days
            };
            const limit = limits[this.uptimeTimeRange] || 1440;

            // Fetch history and uptime for all targets
            const dataPromises = targets.map(async (target) => {
                try {
                    const history = await this.apiGet(`/targets/${target.id}/history?limit=${limit}`);
                    const uptimeData = await this.apiGet(`/targets/${target.id}/uptime`);
                    return { ...target, history, uptimeData };
                } catch (error) {
                    return { ...target, history: [], uptimeData: null };
                }
            });

            const targetsWithData = await Promise.all(dataPromises);
            this.renderStatusTimeline(targetsWithData);

        } catch (error) {
            const safeError = this.escapeHtml(error.message);
            grid.innerHTML = this.createEmptyState({
                icon: '⚠️',
                title: 'Failed to Load Uptime Data',
                description: `There was an error loading uptime data: ${safeError}`,
                compact: true
            });
            console.error('Uptime dashboard error:', error);
        }
    }

    renderStatusTimeline(targets) {
        const grid = document.getElementById('uptimeGrid');

        // Configure segments and duration based on time range
        const config = {
            '24h': { segments: 96, duration: 15 * 60 * 1000, label: '24h ago' },      // 15 minutes per segment
            '7d': { segments: 84, duration: 2 * 60 * 60 * 1000, label: '7d ago' },    // 2 hours per segment
            '30d': { segments: 90, duration: 8 * 60 * 60 * 1000, label: '30d ago' },  // 8 hours per segment
            '90d': { segments: 90, duration: 24 * 60 * 60 * 1000, label: '90d ago' }  // 24 hours per segment
        };

        const timeConfig = config[this.uptimeTimeRange] || config['24h'];
        const segments = timeConfig.segments;
        const segmentDuration = timeConfig.duration;
        const timeLabel = timeConfig.label;
        const now = Date.now(); // Use timestamp instead of Date object

        const html = targets.map(target => {
            const uptime = target.uptimeData;
            const history = target.history || [];

            // Select uptime percentage based on time range
            let uptimePct;
            switch (this.uptimeTimeRange) {
                case '24h':
                    uptimePct = uptime ? uptime.uptime_24h : 0;
                    break;
                case '7d':
                    uptimePct = uptime ? uptime.uptime_7d : 0;
                    break;
                case '30d':
                case '90d':
                    uptimePct = uptime ? uptime.uptime_30d : 0;
                    break;
                default:
                    uptimePct = uptime ? uptime.uptime_24h : 0;
            }

            // Build timeline segments
            let timelineHTML = '';

            for (let i = segments - 1; i >= 0; i--) {
                const segmentStart = now - (i * segmentDuration);
                const segmentEnd = segmentStart + segmentDuration;

                // Find checks in this segment
                const checksInSegment = history.filter(check => {
                    // Handle timestamp - if it doesn't have timezone info, treat it as UTC
                    let checkTime;
                    if (check.timestamp.endsWith('Z') || check.timestamp.includes('+') || check.timestamp.includes('T')) {
                        checkTime = new Date(check.timestamp).getTime();
                    } else {
                        // Assume UTC for timestamps without timezone - add 'Z' suffix
                        checkTime = new Date(check.timestamp.replace(' ', 'T') + 'Z').getTime();
                    }
                    return checkTime >= segmentStart && checkTime < segmentEnd;
                });

                // Determine segment color and create tooltip
                let segmentClass = 'unknown';
                let statusText = 'No data';
                if (checksInSegment.length > 0) {
                    const hasDown = checksInSegment.some(c => c.status === 'down');
                    const hasUp = checksInSegment.some(c => c.status === 'up');

                    if (hasDown) {
                        segmentClass = 'down';
                        statusText = 'DOWN';
                    } else if (hasUp) {
                        segmentClass = 'up';
                        statusText = 'UP';
                    }
                }

                // Format time range for tooltip
                const startDate = new Date(segmentStart);
                const endDate = new Date(segmentEnd);
                const timeRange = `${startDate.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} - ${endDate.toLocaleString('en-US', { hour: '2-digit', minute: '2-digit' })}`;

                timelineHTML += `<div class="timeline-segment ${segmentClass}" title="${timeRange}\nStatus: ${statusText}\nChecks: ${checksInSegment.length}"></div>`;
            }

            const safeName = this.escapeHtml(target.name);
            return `
                <div class="status-row status-${target.status}">
                    <div class="status-row-header">
                        <div class="status-service-name" title="${safeName}">${safeName}</div>
                    </div>
                    <div class="status-row-meta">
                        <div class="status-badge status-${target.status}">${target.status === 'unknown' ? 'CHECKING...' : target.status.toUpperCase()}</div>
                        <div class="status-uptime-pct">${uptimePct}%</div>
                    </div>
                    <div class="status-timeline">${timelineHTML}</div>
                    <div class="status-time-labels">
                        <span class="time-label-left">${timeLabel}</span>
                        <span class="time-label-right">now</span>
                    </div>
                </div>
            `;
        }).join('');

        grid.innerHTML = html || '<div class="loading">No services to display</div>';
    }

    renderCompactTargets(targets) {
        const grid = document.getElementById('targetsGrid');

        if (targets.length === 0) {
            grid.innerHTML = this.createEmptyState({
                icon: '📡',
                title: 'No Monitoring Targets',
                description: 'Get started by adding your first monitoring target. You can monitor servers, network devices, or any IP-based service.',
                actionText: '+ Add Your First Target',
                actionCallback: 'app.showTargetEditPanel(); app.closeSidebar();',
                customClass: 'empty-targets'
            });
            return;
        }

        // Sort targets based on current sort method
        const sortedTargets = this.sortTargets([...targets], this.dashboardSortMethod);

        // Store targets with uptime data for detail panel
        this.targetsWithUptime = sortedTargets;

        // Check if we need to do a full re-render or just update existing cards
        const existingCards = grid.querySelectorAll('.compact-card');
        const needsFullRender = existingCards.length !== sortedTargets.length ||
                                !this.canUpdateInPlace(existingCards, sortedTargets);

        if (needsFullRender) {
            // Full render: new targets added/removed or first load
            grid.innerHTML = sortedTargets.map(target => this.createCompactCard(target)).join('');

            // Add click listeners to cards
            const cards = grid.querySelectorAll('.compact-card');
            cards.forEach(card => {
                card.addEventListener('click', () => {
                    const targetId = card.dataset.id;
                    this.showTargetDetails(targetId, this.targetsWithUptime);
                });
            });

            // Only add slide-in animation on full render
            this.addStaggeredAnimation(Array.from(cards), 'slide-in');
        } else {
            // In-place update: just update the content of existing cards
            this.updateCardsInPlace(existingCards, sortedTargets);
        }
    }

    canUpdateInPlace(existingCards, targets) {
        // Check if all target IDs match (same targets, just updated data)
        if (existingCards.length !== targets.length) return false;

        for (let i = 0; i < existingCards.length; i++) {
            if (existingCards[i].dataset.id !== targets[i].id) {
                return false;
            }
        }
        return true;
    }

    updateCardsInPlace(existingCards, targets) {
        // Simple update: replace innerHTML but keep it clean and maintainable
        existingCards.forEach((card, index) => {
            const target = targets[index];
            const newCardHTML = this.createCompactCard(target);

            // Create a temporary container to parse the new HTML
            const temp = document.createElement('div');
            temp.innerHTML = newCardHTML;
            const newCard = temp.firstElementChild;

            // Update status class and attributes
            card.className = newCard.className;
            card.dataset.id = newCard.dataset.id;

            // Update inner HTML (keeps code simple and maintainable)
            card.innerHTML = newCard.innerHTML;
        });

        // NO slide-in animation on refresh - cards are already visible
        // Animation only happens on full render (new targets added)
    }

    sortTargets(targets, method) {
        const deviceTypePriority = {
            'server': 1,
            'network': 2,
            'workstation': 3,
            'mobile': 4,
            'printer': 5,
            'iot': 6,
            'storage': 7,
            'other': 8
        };

        const statusPriority = {
            'down': 1,
            'unknown': 2,
            'up': 3
        };

        switch (method) {
            case 'smart':
                // Priority: Status (down first) → Device Type → Name (A-Z)
                return targets.sort((a, b) => {
                    const statusDiff = statusPriority[a.status] - statusPriority[b.status];
                    if (statusDiff !== 0) return statusDiff;

                    const deviceDiff = deviceTypePriority[a.device_type || 'other'] - deviceTypePriority[b.device_type || 'other'];
                    if (deviceDiff !== 0) return deviceDiff;

                    return a.name.localeCompare(b.name);
                });

            case 'name-asc':
                return targets.sort((a, b) => a.name.localeCompare(b.name));

            case 'name-desc':
                return targets.sort((a, b) => b.name.localeCompare(a.name));

            case 'status-down':
                return targets.sort((a, b) => {
                    const statusDiff = statusPriority[a.status] - statusPriority[b.status];
                    return statusDiff !== 0 ? statusDiff : a.name.localeCompare(b.name);
                });

            case 'status-up':
                return targets.sort((a, b) => {
                    const statusDiff = statusPriority[b.status] - statusPriority[a.status];
                    return statusDiff !== 0 ? statusDiff : a.name.localeCompare(b.name);
                });

            case 'device-type':
                return targets.sort((a, b) => {
                    const deviceDiff = deviceTypePriority[a.device_type || 'other'] - deviceTypePriority[b.device_type || 'other'];
                    return deviceDiff !== 0 ? deviceDiff : a.name.localeCompare(b.name);
                });

            case 'uptime-worst':
                return targets.sort((a, b) => {
                    const uptimeA = a.uptime?.uptime_24h || 100;
                    const uptimeB = b.uptime?.uptime_24h || 100;
                    return uptimeA - uptimeB;
                });

            case 'uptime-best':
                return targets.sort((a, b) => {
                    const uptimeA = a.uptime?.uptime_24h || 0;
                    const uptimeB = b.uptime?.uptime_24h || 0;
                    return uptimeB - uptimeA;
                });

            case 'newest':
                return targets.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

            case 'oldest':
                return targets.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

            default:
                return targets;
        }
    }

    createCompactCard(target) {
        const statusClass = target.status || 'unknown';
        const acknowledgedClass = target.acknowledged ? 'acknowledged' : '';
        // Check for enabled === 0 or enabled === false
        const isDisabled = (target.enabled === 0 || target.enabled === false);
        const disabledClass = isDisabled ? 'disabled' : '';
        const ackIcon = target.acknowledged ? '<span class="ack-icon icon-bell-off" title="Acknowledged"></span>' : '';
        const audioMutedIcon = (target.audio_behavior === 'silent') ? '<span class="audio-muted-icon" title="Audio alerts disabled for this target">🔕</span>' : '';
        const disabledBadge = isDisabled ? '<span class="disabled-badge" title="Monitoring Disabled">DISABLED</span>' : '';

        // Random animation delay for LED to desynchronize them (0-500ms)
        const ledDelay = Math.random() * 0.5;

        // Uptime metrics (industry standard)
        let uptimeHtml = '';
        if (target.uptime) {
            const uptime = target.uptime.uptime_24h;
            const uptimeClass = uptime >= 99.9 ? 'uptime-excellent' : uptime >= 99 ? 'uptime-good' : 'uptime-poor';
            const currentDuration = target.uptime.current_duration_formatted || target.current_uptime_formatted || target.current_downtime_formatted || '0s';

            const durationIcon = statusClass === 'up' ? '<span class="icon-up"></span>' : '<span class="icon-down"></span>';
            uptimeHtml = `
                <div class="compact-card-metrics">
                    <span class="metric-uptime ${uptimeClass}" title="24-hour uptime">${uptime}% (24h)</span>
                    <span class="metric-duration">${durationIcon} ${currentDuration}</span>
                </div>
            `;
        }

        const safeName = this.escapeHtml(target.name);
        return `
            <div class="compact-card status-${statusClass} ${acknowledgedClass} ${disabledClass}" data-id="${target.id}">
                <div class="compact-card-header">
                    <div class="compact-card-name-row">
                        <div class="compact-card-name" title="${safeName}">${safeName}</div>
                    </div>
                    ${disabledBadge}
                </div>
                ${uptimeHtml}
                <div class="compact-card-footer">
                    <div class="compact-card-type-with-led">
                        <span class="port-led led-${statusClass}" style="animation-delay: -${ledDelay}s;" title="Link Status"></span>
                        <span class="compact-card-type">${target.type}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        ${audioMutedIcon}
                        ${ackIcon}
                        <div class="compact-card-status ${statusClass}">${statusClass === 'unknown' ? 'CHECKING...' : statusClass.toUpperCase()}</div>
                    </div>
                </div>
            </div>
        `;
    }

    showTargetDetails(targetId, targets) {
        const target = targets.find(t => t.id === targetId);
        if (!target) return;

        this.selectedTargetId = targetId;

        // Build detail panel HTML
        const panel = document.getElementById('slidePanel');
        const body = document.getElementById('slidePanelBody');

        const safeName = this.escapeHtml(target.name);
        const safeAddress = this.escapeHtml(target.address);

        const acknowledgeSection = target.status === 'down'
            ? (target.acknowledged
                ? `<div class="ack-notice">
                        <span>Acknowledged - Alerts silenced</span>
                        <button class="btn btn-tiny btn-link" onclick="app.unacknowledgeTarget('${targetId}')">Remove</button>
                    </div>`
                : `<div style="margin: 15px 0;">
                        <button class="btn btn-warning" style="width: 100%;" onclick="app.acknowledgeTarget('${targetId}')">
                            Acknowledge Alert
                        </button>
                    </div>`)
            : '';

        body.innerHTML = `
            <div class="detail-content">
                <div class="detail-header">
                    <div class="detail-header-left">
                        <h2>${safeName}</h2>
                        <span class="detail-status-inline ${target.status}">
                            <span class="status-icon">${target.status === 'up' ? '▲' : '▼'}</span>
                            ${target.status === 'up' ? 'Up' : 'Down'} for ${target.uptime?.current_duration_formatted || target.current_uptime_formatted || target.current_downtime_formatted || '0s'}
                        </span>
                    </div>
                    <div class="detail-header-right">
                        <span class="target-type">${target.type.toUpperCase()}</span>
                        <div class="compact-card-status ${target.status}">${target.status === 'unknown' ? 'CHECKING...' : target.status.toUpperCase()}</div>
                    </div>
                </div>

                ${acknowledgeSection}

                <!-- Industry Standard Uptime Metrics -->
                ${target.uptime ? `
                <div class="detail-uptime-section">
                    <div class="detail-section-title">Uptime</div>
                    <div class="uptime-metrics-grid">
                        <div class="uptime-metric">
                            <div class="uptime-metric-label">Last 24 Hours</div>
                            <div class="uptime-metric-value ${target.uptime.uptime_24h >= 99.9 ? 'uptime-excellent' : target.uptime.uptime_24h >= 99 ? 'uptime-good' : 'uptime-poor'}">
                                ${target.uptime.uptime_24h}%
                            </div>
                            <div class="uptime-metric-checks">${target.uptime.up_checks_24h || 0}/${target.uptime.checks_24h || 0} checks</div>
                        </div>
                        <div class="uptime-metric">
                            <div class="uptime-metric-label">Last 7 Days</div>
                            <div class="uptime-metric-value ${target.uptime.uptime_7d >= 99.9 ? 'uptime-excellent' : target.uptime.uptime_7d >= 99 ? 'uptime-good' : 'uptime-poor'}">
                                ${target.uptime.uptime_7d}%
                            </div>
                            <div class="uptime-metric-checks">${target.uptime.up_checks_7d || 0}/${target.uptime.checks_7d || 0} checks</div>
                        </div>
                        <div class="uptime-metric">
                            <div class="uptime-metric-label">Last 30 Days</div>
                            <div class="uptime-metric-value ${target.uptime.uptime_30d >= 99.9 ? 'uptime-excellent' : target.uptime.uptime_30d >= 99 ? 'uptime-good' : 'uptime-poor'}">
                                ${target.uptime.uptime_30d}%
                            </div>
                            <div class="uptime-metric-checks">${target.uptime.up_checks_30d || 0}/${target.uptime.checks_30d || 0} checks</div>
                        </div>
                    </div>
                </div>
                ` : ''}

                <!-- Additional Info -->
                <div class="target-info">
                    <div class="info-row">
                        <span class="info-label">Address</span>
                        <span class="info-value">${safeAddress}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Last Check</span>
                        <span class="info-value">${target.last_check ? new Date(target.last_check).toLocaleString() : 'Never'}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Failures</span>
                        <span class="info-value">${target.current_failures} / ${target.failure_threshold} threshold</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Total Checks</span>
                        <span class="info-value">${target.total_checks || 0} (${target.failed_checks || 0} failed)</span>
                    </div>
                </div>

                <div class="target-actions">
                    <button class="btn btn-secondary" onclick="app.editTarget('${targetId}')">
                        <span class="icon-edit"></span> Edit
                    </button>
                </div>
            </div>
        `;

        panel.classList.add('active');
    }

    closeSlidePanel() {
        document.getElementById('slidePanel').classList.remove('active');
        this.selectedTargetId = null;
    }

    async acknowledgeTarget(id) {
        try {
            await this.apiPost(`/targets/${id}/acknowledge`, {});
            this.showToast('Target acknowledged\nALERTS SILENCED', 'success');
            await this.loadDashboard();
            this.closeSlidePanel();
        } catch (error) {
            this.showToast('Failed to acknowledge target', 'error');
        }
    }

    async unacknowledgeTarget(id) {
        try {
            await this.apiDelete(`/targets/${id}/acknowledge`);
            this.showToast('Acknowledgment removed', 'info');
            await this.loadDashboard();
            this.closeSlidePanel();
        } catch (error) {
            this.showToast('Failed to remove acknowledgment', 'error');
        }
    }

    async checkTargetNow(id) {
        try {
            await this.apiPost(`/targets/${id}/check`, {});
            this.showToast('Check triggered', 'info');
            setTimeout(() => this.loadDashboard(), 2000);
        } catch (error) {
            this.showToast('Failed to trigger check', 'error');
        }
    }

    async editTarget(id) {
        try {
            const target = await this.apiGet(`/targets/${id}`);
            this.showTargetEditPanel(target);
            this.closeSlidePanel();
        } catch (error) {
            this.showToast('Failed to load target', 'error');
        }
    }

    async deleteTarget(id, name) {
        if (!confirm(`Are you sure you want to delete "${name}"?`)) {
            return;
        }

        try {
            await this.apiDelete(`/targets/${id}`);
            this.showToast('Target deleted successfully', 'success');
            this.loadDashboard();
            this.closeSlidePanel();
            this.hideTargetEditPanel(); // Also close edit panel if open
        } catch (error) {
            this.showToast('Failed to delete target', 'error');
        }
    }

    // Keep existing methods for tabs, modals, API calls, etc...
    switchTab(tab) {
        // Check if feature is disabled
        if (tab === 'discovery' && !this.features.discoveryEnabled) {
            this.showToast('Discovery feature is disabled in this deployment', 'warning');
            return; // Block tab switch
        }

        document.querySelectorAll('.sidebar-nav-item').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

        document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
        document.getElementById(tab).classList.add('active');

        if (tab === 'settings') {
            this.loadSettings();
            this.loadHealthDashboard(); // Load health dashboard as it's now part of settings
            this.initSharingTab(); // Sharing is now part of settings
            this.loadApiKeys(); // Load API keys for relay controllers
        } else if (tab === 'uptime') {

            this.loadUptimeDashboard();
        } else if (tab === 'incidents') {
            this.loadIncidents();
            this.stopEventLogRefresh();
        } else if (tab === 'events') {
            this.loadEventLog();
            this.startEventLogRefresh();
        } else if (tab === 'dashboard') {
            this.stopEventLogRefresh();
        } else if (tab === 'discovery') {
            this.initDiscoveryTab();
            this.stopEventLogRefresh();
        } else if (tab === 'api-docs') {
            this.stopEventLogRefresh();
        }
    }

    async showTargetEditPanel(target = null) {
        const panel = document.getElementById('targetEditPanel');
        const form = document.getElementById('targetForm');
        const title = document.getElementById('targetEditTitle');
        const deleteBtn = document.getElementById('deleteTargetBtn');

        // Ensure audio library is loaded and dropdowns are populated
        await this.loadAudioLibrary();

        if (target) {
            title.textContent = 'Edit Target';

            // Show delete button when editing
            deleteBtn.style.display = 'block';
            deleteBtn.onclick = () => this.deleteTarget(target.id, target.name);
            document.getElementById('targetId').value = target.id;
            document.getElementById('targetName').value = target.name;
            document.getElementById('targetType').value = target.type;
            document.getElementById('targetAddress').value = target.address;
            document.getElementById('deviceType').value = target.device_type || 'other';
            document.getElementById('checkInterval').value = target.check_interval;
            document.getElementById('failureThreshold').value = target.failure_threshold;

            // Set audio behavior with fallback to 'normal'
            document.getElementById('audioBehavior').value = target.audio_behavior || 'normal';

            document.getElementById('targetEnabled').checked = target.enabled;

            // Load audio alert selections
            document.getElementById('audioDownAlert').value = target.audio_down_alert || '';
            document.getElementById('audioUpAlert').value = target.audio_up_alert || '';
        } else {
            title.textContent = 'Add Target';
            form.reset();
            document.getElementById('targetId').value = '';
            document.getElementById('audioBehavior').value = 'normal';

            // Hide delete button when adding new target
            deleteBtn.style.display = 'none';
        }

        // Initialize target type handler
        this.handleTargetTypeChange();

        panel.classList.add('active');
    }

    hideTargetEditPanel() {
        document.getElementById('targetEditPanel').classList.remove('active');
    }

    async handleTargetSubmit(e) {
        e.preventDefault();

        const targetId = document.getElementById('targetId').value;
        const targetType = document.getElementById('targetType').value;

        const data = {
            name: document.getElementById('targetName').value,
            type: targetType,
            address: document.getElementById('targetAddress').value,
            device_type: document.getElementById('deviceType').value,
            check_interval: parseInt(document.getElementById('checkInterval').value),
            failure_threshold: parseInt(document.getElementById('failureThreshold').value),
            audio_behavior: document.getElementById('audioBehavior').value || 'normal',
            enabled: document.getElementById('targetEnabled').checked
        };

        // Add audio alert selections
        const audioDownAlert = document.getElementById('audioDownAlert').value;
        const audioUpAlert = document.getElementById('audioUpAlert').value;
        if (audioDownAlert) {
            data.audio_down_alert = audioDownAlert;
        }
        if (audioUpAlert) {
            data.audio_up_alert = audioUpAlert;
        }

        try {
            if (targetId) {
                await this.apiPut(`/targets/${targetId}`, data);
                this.showToast('Target updated successfully', 'success');
            } else {
                await this.apiPost('/targets', data);
                this.showToast('Target added successfully', 'success');
            }

            this.hideTargetEditPanel();
            this.loadDashboard();
        } catch (error) {
            this.showToast('Failed to save target', 'error');
        }
    }

    updateSystemStatus(status) {
        // Create individual status regions with icons
        // Only add has-targets class to down region when count > 0 to enable pulsing
        const downClass = status.targets_down > 0 ? 'status-region status-down has-targets' : 'status-region status-down';
        const statusHTML = `
            <div class="status-region status-up">
                <span class="status-icon">▲</span>
                <span class="status-text">${status.targets_up}</span>
            </div>
            <div class="${downClass}">
                <span class="status-icon">▼</span>
                <span class="status-text">${status.targets_down}</span>
            </div>
        `;

        // Update top bar badge
        const badge = document.getElementById('statusBadge');
        badge.innerHTML = statusHTML;
    }

    updateAlertIndicator(targets) {
        // Check if there are any down targets that are not acknowledged
        const unacknowledgedDownTargets = targets.filter(t =>
            t.status === 'down' && !t.acknowledged && t.enabled
        );

        const navStatusCenter = document.getElementById('navStatusCenter');

        if (unacknowledgedDownTargets.length > 0) {
            // Show flashing ALERT
            navStatusCenter.innerHTML = '<span class="alert-flash"><span class="text-desktop">⚠ ALERT ⚠</span><span class="text-mobile">⚠ ALERT</span></span>';
        } else {
            // Show calm SYSTEM OPERATIONAL
            navStatusCenter.innerHTML = '<span class="system-operational"><span class="text-desktop">SYSTEM OPERATIONAL</span><span class="text-mobile">OPERATIONAL</span></span>';
        }
    }

    async loadSettings() {
        try {
            const config = await this.apiGet('/config');

            document.getElementById('failureThresholdDefault').value = config.failure_threshold || 3;
            document.getElementById('checkIntervalDefault').value = config.check_interval || 60;
            document.getElementById('alertRepeatInterval').value = config.alert_repeat_interval || 300;
            document.getElementById('audioEnabled').checked = config.audio_enabled !== false;
            document.getElementById('webhookUrl').value = config.webhook_url || '';
            document.getElementById('webhookEnabled').checked = config.webhook_enabled || false;
            document.getElementById('pingTimeout').value = config.ping_timeout || 5;
            document.getElementById('httpTimeout').value = config.http_timeout || 10;

            // Load SMTP settings
            await this.loadSmtpSettings();

            // Load backup settings
            await this.loadBackupSettings();

            // Load and render audio library in settings
            await this.renderAudioLibraryInSettings();
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    }


    async saveSettings() {
        const saveBtn = document.getElementById('saveSettingsBtn');
        const originalText = saveBtn.innerHTML;

        // Show loading state on button
        saveBtn.innerHTML = '<div class="dots-loader" style="display: inline-flex; gap: 4px;"><span style="width: 8px; height: 8px;"></span><span style="width: 8px; height: 8px;"></span><span style="width: 8px; height: 8px;"></span></div>';
        saveBtn.disabled = true;

        const config = {
            failure_threshold: parseInt(document.getElementById('failureThresholdDefault').value),
            check_interval: parseInt(document.getElementById('checkIntervalDefault').value),
            alert_repeat_interval: parseInt(document.getElementById('alertRepeatInterval').value),
            audio_enabled: document.getElementById('audioEnabled').checked,
            webhook_url: document.getElementById('webhookUrl').value,
            webhook_enabled: document.getElementById('webhookEnabled').checked,
            ping_timeout: parseInt(document.getElementById('pingTimeout').value),
            http_timeout: parseInt(document.getElementById('httpTimeout').value)
        };

        try {
            // Save general config
            await this.apiPut('/config', config);

            // Save default audio alert selections
            const defaultDownSound = document.getElementById('defaultDownSound');
            const defaultUpSound = document.getElementById('defaultUpSound');

            if (defaultDownSound && defaultUpSound) {
                const audioDefaults = {
                    default_down_alert: defaultDownSound.value,
                    default_up_alert: defaultUpSound.value
                };

                await this.apiPut('/audio/library/defaults', audioDefaults);
            }

            // Save SMTP settings
            await this.saveSmtpSettings();

            // Save backup settings
            await this.saveBackupSettings();

            // Show success with checkmark
            saveBtn.innerHTML = '✓ Saved!';
            this.showToast('Settings saved successfully', 'success');

            // Reset button after 2 seconds
            setTimeout(() => {
                saveBtn.innerHTML = originalText;
                saveBtn.disabled = false;
            }, 2000);
        } catch (error) {
            // Show error with shake animation
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
            saveBtn.classList.add('shake');
            setTimeout(() => saveBtn.classList.remove('shake'), 500);
            this.showToast('Failed to save settings', 'error');
        }
    }

    async testAudio() {
        try {
            // Get the current default down sound
            const defaultDownSound = document.getElementById('defaultDownSound');
            const filename = defaultDownSound?.value || this.audioLibrary?.default_down_alert || 'system_down.aiff';

            this.showToast('Playing test audio...', 'info');
            this.previewAudio(filename);
        } catch (error) {
            console.error('Failed to test audio:', error);
            this.showToast('Failed to play test audio', 'error');
        }
    }

    // SMTP Settings Methods
    async loadSmtpSettings() {
        try {
            const smtp = await this.apiGet('/settings/smtp');
            document.getElementById('smtpEnabled').checked = smtp.enabled || false;
            document.getElementById('smtpHost').value = smtp.host || '';
            document.getElementById('smtpPort').value = smtp.port || 587;
            document.getElementById('smtpUseTls').checked = smtp.use_tls !== false;
            document.getElementById('smtpUsername').value = smtp.username || '';
            // Password is not returned for security - leave blank
            document.getElementById('smtpPassword').value = '';
            document.getElementById('smtpFromAddress').value = smtp.from_address || '';
            document.getElementById('smtpFromName').value = smtp.from_name || 'WebStatus';

            // Recipients - join array into newline-separated string
            const recipients = smtp.recipients || [];
            document.getElementById('smtpRecipients').value = recipients.join('\n');
        } catch (error) {
            console.error('Failed to load SMTP settings:', error);
        }
    }

    async saveSmtpSettings() {
        const recipientsText = document.getElementById('smtpRecipients').value;
        const recipients = recipientsText
            .split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0);

        const smtp = {
            enabled: document.getElementById('smtpEnabled').checked,
            host: document.getElementById('smtpHost').value,
            port: parseInt(document.getElementById('smtpPort').value) || 587,
            use_tls: document.getElementById('smtpUseTls').checked,
            username: document.getElementById('smtpUsername').value,
            from_address: document.getElementById('smtpFromAddress').value,
            from_name: document.getElementById('smtpFromName').value,
            recipients: recipients
        };

        // Only include password if it was changed (not empty)
        const password = document.getElementById('smtpPassword').value;
        if (password) {
            smtp.password = password;
        }

        try {
            await this.apiPost('/settings/smtp', smtp);
        } catch (error) {
            console.error('Failed to save SMTP settings:', error);
            throw error;
        }
    }

    async testSmtp() {
        const testEmail = document.getElementById('smtpTestEmail').value;
        if (!testEmail) {
            this.showToast('Please enter a test email address', 'error');
            return;
        }

        try {
            this.showToast('Sending test email...', 'info');
            await this.apiPost('/settings/smtp/test', { email: testEmail });
            this.showToast('Test email sent successfully! Check your inbox.', 'success');
        } catch (error) {
            console.error('Failed to send test email:', error);
            this.showToast('Failed to send test email. Check your SMTP settings.', 'error');
        }
    }

    // Backup Settings Methods
    async loadBackupSettings() {
        try {
            const backup = await this.apiGet('/settings/backup');
            document.getElementById('backupEnabled').checked = backup.enabled || false;
            document.getElementById('backupSchedule').value = backup.schedule || '0 2 * * *';
            document.getElementById('backupRetentionDays').value = backup.retention_days || 30;
            document.getElementById('backupCompression').checked = backup.compression !== false;
        } catch (error) {
            console.error('Failed to load backup settings:', error);
        }
    }

    async saveBackupSettings() {
        const backup = {
            enabled: document.getElementById('backupEnabled').checked,
            schedule: document.getElementById('backupSchedule').value,
            retention_days: parseInt(document.getElementById('backupRetentionDays').value) || 30,
            compression: document.getElementById('backupCompression').checked
        };

        try {
            await this.apiPost('/settings/backup', backup);
        } catch (error) {
            console.error('Failed to save backup settings:', error);
            throw error;
        }
    }

    async createBackup() {
        try {
            this.showToast('Creating backup...', 'info');
            const result = await this.apiPost('/backups/create', {});
            this.showToast('Backup created successfully!', 'success');

            // Refresh backup list if it's visible
            const listContainer = document.getElementById('backupListContainer');
            if (listContainer.style.display !== 'none') {
                await this.loadBackupList();
            }
        } catch (error) {
            console.error('Failed to create backup:', error);
            this.showToast('Failed to create backup', 'error');
        }
    }

    async toggleBackupList() {
        const listContainer = document.getElementById('backupListContainer');
        const viewBtn = document.getElementById('viewBackupsBtn');

        if (listContainer.style.display === 'none') {
            listContainer.style.display = 'block';
            viewBtn.innerHTML = '<span class="icon-list"></span> Hide Backups';
            await this.loadBackupList();
        } else {
            listContainer.style.display = 'none';
            viewBtn.innerHTML = '<span class="icon-list"></span> View Backups';
        }
    }

    async loadBackupList() {
        try {
            const response = await this.apiGet('/backups');
            // API returns {backups: [...], count: N}, we need just the array
            const backups = response.backups || [];
            this.renderBackupList(backups);
        } catch (error) {
            console.error('Failed to load backup list:', error);
            this.showToast('Failed to load backup list', 'error');
        }
    }

    renderBackupList(backups) {
        const listContainer = document.getElementById('backupList');

        if (!backups || backups.length === 0) {
            listContainer.innerHTML = '<p style="color: var(--text-secondary);">No backups available</p>';
            return;
        }

        listContainer.innerHTML = backups.map(backup => `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px; background: var(--bg-primary); border-radius: 6px; margin-bottom: 10px;">
                <div>
                    <div style="font-weight: 600; margin-bottom: 5px;">${this.escapeHtml(backup.name)}</div>
                    <div style="font-size: 0.875rem; color: var(--text-secondary);">
                        Size: ${this.formatFileSize(backup.size)} |
                        Created: ${this.formatDate(backup.created_at)} |
                        Age: ${this.formatTimeSince(backup.created_at)}
                    </div>
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-primary btn-small" onclick="app.restoreBackup('${this.escapeHtml(backup.name)}')">
                        Restore
                    </button>
                    <button class="btn btn-secondary btn-small" onclick="app.downloadBackup('${this.escapeHtml(backup.name)}')">
                        Download
                    </button>
                    <button class="btn btn-secondary btn-small" onclick="app.deleteBackup('${this.escapeHtml(backup.name)}')">
                        Delete
                    </button>
                </div>
            </div>
        `).join('');
    }

    async downloadBackup(backupName) {
        try {
            window.open(`${this.apiBase}/backups/download/${encodeURIComponent(backupName)}`, '_blank');
            this.showToast('Download started', 'success');
        } catch (error) {
            console.error('Failed to download backup:', error);
            this.showToast('Failed to download backup', 'error');
        }
    }

    async deleteBackup(backupName) {
        if (!confirm(`Are you sure you want to delete backup "${backupName}"?`)) {
            return;
        }

        try {
            await this.apiDelete(`/backups/${encodeURIComponent(backupName)}`);
            this.showToast('Backup deleted successfully', 'success');
            await this.loadBackupList();
        } catch (error) {
            console.error('Failed to delete backup:', error);
            this.showToast('Failed to delete backup', 'error');
        }
    }

    async restoreBackup(backupName) {
        // Show strong warning about data loss
        if (!confirm(
            `⚠️ WARNING: Restoring this backup will OVERWRITE your current database and configuration!\n\n` +
            `Backup: ${backupName}\n\n` +
            `This action cannot be undone. Are you sure you want to continue?`
        )) {
            return;
        }

        // Second confirmation
        if (!confirm(
            `This is your final warning!\n\n` +
            `Restoring "${backupName}" will replace ALL current data.\n\n` +
            `Click OK to proceed with restore.`
        )) {
            return;
        }

        try {
            this.showToast('Restoring backup... Please wait.', 'info');
            const result = await this.apiPost(`/backups/restore/${encodeURIComponent(backupName)}`, {});

            // Server will restart automatically - reload page after fixed delay
            this.showToast(
                '✅ Backup restored! Server restarting... Page will reload in 8 seconds.',
                'success'
            );

            setTimeout(() => {
                window.location.reload();
            }, 8000);  // 3s for restore + 5s for restart = 8s total

        } catch (error) {
            console.error('Failed to restore backup:', error);
            this.showToast('Failed to restore backup. Check the console for details.', 'error');
        }
    }

    triggerBackupUpload() {
        // Trigger the hidden file input
        const fileInput = document.getElementById('backupFileInput');
        if (fileInput) {
            fileInput.value = ''; // Reset to allow re-uploading same file
            fileInput.click();
        }
    }

    async handleBackupUpload(event) {
        const file = event.target.files[0];
        if (!file) {
            return;
        }

        // Validate file type
        if (!file.name.endsWith('.tar.gz') && !file.name.endsWith('.tgz')) {
            this.showToast('Please select a .tar.gz backup file', 'error');
            return;
        }

        // Validate file size (100MB max)
        const maxSize = 100 * 1024 * 1024; // 100MB
        if (file.size > maxSize) {
            this.showToast('File too large. Maximum size is 100MB', 'error');
            return;
        }

        try {
            this.showToast('Uploading backup... Please wait.', 'info');

            // Create FormData
            const formData = new FormData();
            formData.append('file', file);

            // Upload using fetch directly (not our apiPost method since it's FormData)
            const response = await fetch(`${this.apiBase}/backups/upload`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const result = await response.json();

            this.showToast(
                `Backup uploaded successfully: ${result.filename}`,
                'success'
            );

            // Refresh backup list if visible
            const listContainer = document.getElementById('backupListContainer');
            if (listContainer.style.display !== 'none') {
                await this.loadBackupList();
            }

        } catch (error) {
            console.error('Failed to upload backup:', error);
            this.showToast(`Failed to upload backup: ${error.message}`, 'error');
        } finally {
            // Reset file input
            event.target.value = '';
        }
    }

    formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }

    formatTimeSince(timestamp) {
        const now = new Date();
        const then = new Date(timestamp);
        const diffMs = now - then;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffDays > 0) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
        if (diffHours > 0) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
        if (diffMins > 0) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
        return 'Just now';
    }

    formatDate(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString();
    }

    async loadHealthDashboard() {
        const grid = document.getElementById('healthGrid');

        // Show skeleton loading
        if (grid) {
            grid.innerHTML = this.createSkeletonGrid(4);
        }

        try {
            const health = await this.apiGet('/health');
            this.renderHealthDashboard(health);
        } catch (error) {
            console.error('Failed to load health data:', error);
            if (grid) {
                grid.innerHTML = this.createEmptyState({
                    icon: '🏥',
                    title: 'Health Check Failed',
                    description: 'Unable to retrieve system health information. The monitoring system may be experiencing issues.',
                    compact: true
                });
            }
            this.showToast('Failed to load system health', 'error');
        }
    }

    renderHealthDashboard(health) {
        const grid = document.getElementById('healthGrid');
        const overallBadge = document.getElementById('overallStatusBadge');

        // Clear grid
        grid.innerHTML = '';

        const cards = [];

        // Render each component card (excluding relay)
        for (const [name, component] of Object.entries(health.components)) {
            // Skip relay component
            if (name === 'relay') continue;

            const card = document.createElement('div');
            card.className = `health-card status-${component.status} fade-in`;

            const detailsHTML = component.active_monitors !== undefined
                ? `<div class="health-detail-item"><strong>Active Monitors:</strong> ${component.active_monitors}</div>`
                : component.active !== undefined
                ? `<div class="health-detail-item"><strong>Active:</strong> ${component.active ? 'Yes' : 'No'}</div>`
                : component.looping !== undefined
                ? `<div class="health-detail-item"><strong>Looping:</strong> ${component.looping ? 'Yes' : 'No'}</div>`
                : '';

            const safeName = this.escapeHtml(name);
            const safeMessage = this.escapeHtml(component.message);

            card.innerHTML = `
                <div class="health-card-header">
                    <div class="health-card-title" title="${safeName}">${safeName}</div>
                </div>
                <div class="health-card-status">${component.status}</div>
                <div class="health-card-message" title="${safeMessage}">${safeMessage}</div>
                ${detailsHTML ? `<div class="health-card-details">${detailsHTML}</div>` : ''}
            `;

            grid.appendChild(card);
            cards.push(card);
        }

        // Add staggered animation to health cards
        this.addStaggeredAnimation(cards, 'fade-in');

        // Update overall status badge
        overallBadge.textContent = health.status === 'unknown' ? 'CHECKING...' : health.status.toUpperCase();
        overallBadge.className = `overall-badge status-${health.status}`;
    }

    startAutoRefresh() {
        // Clear any existing interval to prevent multiple intervals running
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        this.refreshInterval = setInterval(() => {
            this.loadDashboard();
        }, 5000);
    }

    stopAutoRefresh() {
        // Stop the auto-refresh interval
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type} show`;

        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }

    copyToClipboard(text) {
        navigator.clipboard.writeText(text.trim()).then(() => {
            this.showToast('Copied to clipboard', 'success');
        }).catch(err => {
            console.error('Failed to copy:', err);
            this.showToast('Failed to copy to clipboard', 'error');
        });
    }

    // API Helper Methods
    async apiGet(endpoint) {
        const response = await fetch(this.apiBase + endpoint);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }

    async apiPost(endpoint, data) {
        const response = await fetch(this.apiBase + endpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.status === 204 ? null : response.json();
    }

    async apiPut(endpoint, data) {
        const response = await fetch(this.apiBase + endpoint, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }

    async apiDelete(endpoint) {
        const response = await fetch(this.apiBase + endpoint, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return null;
    }

    // Event Log Methods
    async loadEventLog() {
        if (this.eventLogPaused) return;

        const container = document.getElementById('eventLogContent');

        // Show loading state only on first load (not on refresh)
        if (!this.allEvents || this.allEvents.length === 0) {
            container.innerHTML = this.createDotsLoader('Loading events...');
        }

        try {
            const events = await this.apiGet('/alerts?limit=200');
            this.allEvents = events;
            this.populateTargetFilter(events);
            this.applyEventFilters();
        } catch (error) {
            console.error('Failed to load event log:', error);
            container.innerHTML = this.createEmptyState({
                icon: '⚠️',
                title: 'Failed to Load Events',
                description: 'There was an error loading the event log. Please try refreshing.',
                compact: true
            });
        }
    }

    populateTargetFilter(events) {
        const targetFilter = document.getElementById('filterTarget');
        const uniqueTargets = [...new Set(events.map(e => e.target_name))].sort();

        // Keep "All Targets" option and add unique targets
        const currentValue = targetFilter.value;
        targetFilter.innerHTML = '<option value="">All Targets</option>';
        uniqueTargets.forEach(target => {
            const option = document.createElement('option');
            option.value = target;
            option.textContent = target;
            targetFilter.appendChild(option);
        });
        targetFilter.value = currentValue;
    }

    renderEventLog(events) {
        const container = document.getElementById('eventLogContent');

        if (events.length === 0) {
            container.innerHTML = this.createEmptyState({
                icon: '📋',
                title: 'No Events Yet',
                description: 'Events will appear here when your targets change status or when system events occur. Your monitoring is active and watching.',
                compact: true,
                customClass: 'empty-events'
            });
            return;
        }

        const eventHtml = events.map(event => {
            // Handle both old format (without Z) and new format (with +00:00)
            let timestampStr = event.timestamp;
            if (!timestampStr.includes('Z') && !timestampStr.includes('+') && !timestampStr.includes('-', 10)) {
                timestampStr += 'Z'; // Add Z for old timestamps without timezone
            }
            const date = new Date(timestampStr);
            const timestamp = date.toLocaleString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            });
            const relativeTime = this.getRelativeTime(date);
            const eventTypeClass = this.getEventTypeClass(event.event_type);

            const safeTargetName = this.escapeHtml(event.target_name);
            const safeMessage = this.escapeHtml(event.message || '');

            return `
                <div class="event-log-item ${eventTypeClass}">
                    <div class="event-log-time" title="${timestamp}">
                        <div class="event-time-absolute">${timestamp}</div>
                        <div class="event-time-relative">${relativeTime}</div>
                    </div>
                    <div class="event-log-target" title="${safeTargetName}">${safeTargetName}</div>
                    <div class="event-log-type">${this.formatEventType(event.event_type)}</div>
                    <div class="event-log-message" title="${safeMessage}">${safeMessage}</div>
                </div>
            `;
        }).join('');

        container.innerHTML = eventHtml;

        // Auto-scroll to top for newest events
        container.scrollTop = 0;
    }

    getRelativeTime(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHour = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHour / 24);

        if (diffSec < 10) return 'just now';
        if (diffSec < 60) return `${diffSec}s ago`;
        if (diffMin < 60) return `${diffMin}m ago`;
        if (diffHour < 24) return `${diffHour}h ago`;
        if (diffDay < 7) return `${diffDay}d ago`;
        return date.toLocaleDateString();
    }

    getEventTypeClass(eventType) {
        const typeMap = {
            'threshold_reached': 'event-down',
            'alert_repeat': 'event-down',
            'recovered': 'event-up',
            'target_created': 'event-info',
            'target_updated': 'event-info',
            'target_deleted': 'event-info'
        };
        return typeMap[eventType] || 'event-info';
    }

    formatEventType(eventType) {
        const formatMap = {
            'threshold_reached': 'DOWN',
            'alert_repeat': 'DOWN',
            'recovered': 'UP',
            'target_created': 'NEW',
            'target_updated': 'EDIT',
            'target_deleted': 'DEL',
            'acknowledged': 'ACK',
            'unacknowledged': 'UNACK',
            'disabled': 'OFF',
            'enabled': 'ON'
        };
        return formatMap[eventType] || eventType.toUpperCase();
    }

    startEventLogRefresh() {
        this.stopEventLogRefresh();
        this.eventLogRefreshInterval = setInterval(() => {
            if (!this.eventLogPaused) {
                this.loadEventLog();
            }
        }, 5000); // Refresh every 5 seconds
    }

    stopEventLogRefresh() {
        if (this.eventLogRefreshInterval) {
            clearInterval(this.eventLogRefreshInterval);
            this.eventLogRefreshInterval = null;
        }
    }

    toggleEventLogPause() {
        this.eventLogPaused = !this.eventLogPaused;
        const btn = document.getElementById('pauseEventsBtn');

        if (this.eventLogPaused) {
            btn.textContent = 'Resume';
            btn.classList.add('active');
        } else {
            btn.textContent = 'Pause';
            btn.classList.remove('active');
            this.loadEventLog();
        }
    }

    clearEventLog() {
        const container = document.getElementById('eventLogContent');
        container.innerHTML = '<div class="event-log-empty">Log cleared (refresh will reload)</div>';
    }

    applyEventFilters() {
        // Get filter values
        this.eventFilters.target = document.getElementById('filterTarget').value;
        this.eventFilters.eventType = document.getElementById('filterEventType').value;
        this.eventFilters.dateFrom = document.getElementById('filterDateFrom').value;
        this.eventFilters.dateTo = document.getElementById('filterDateTo').value;

        // Filter events
        this.filteredEvents = this.allEvents.filter(event => {
            // Filter by target
            if (this.eventFilters.target && event.target_name !== this.eventFilters.target) {
                return false;
            }

            // Filter by event type
            if (this.eventFilters.eventType && event.event_type !== this.eventFilters.eventType) {
                return false;
            }

            // Filter by date range
            if (this.eventFilters.dateFrom || this.eventFilters.dateTo) {
                let timestampStr = event.timestamp;
                if (!timestampStr.includes('Z') && !timestampStr.includes('+') && !timestampStr.includes('-', 10)) {
                    timestampStr += 'Z';
                }
                const eventDate = new Date(timestampStr);

                if (this.eventFilters.dateFrom) {
                    const fromDate = new Date(this.eventFilters.dateFrom);
                    if (eventDate < fromDate) return false;
                }

                if (this.eventFilters.dateTo) {
                    const toDate = new Date(this.eventFilters.dateTo);
                    if (eventDate > toDate) return false;
                }
            }

            return true;
        });

        this.renderEventLog(this.filteredEvents);
    }

    clearEventFilters() {
        document.getElementById('filterTarget').value = '';
        document.getElementById('filterEventType').value = '';
        document.getElementById('filterDateFrom').value = '';
        document.getElementById('filterDateTo').value = '';

        this.eventFilters = {
            target: '',
            eventType: '',
            dateFrom: '',
            dateTo: ''
        };

        this.applyEventFilters();
    }

    // ========================================
    // INCIDENTS TAB
    // ========================================

    async loadIncidents() {
        const container = document.getElementById('incidentsContainer');

        try {
            const response = await fetch(`${this.apiBase}/incidents?days=${this.incidentsDays}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.allIncidents = data.incidents || [];
            this.incidentsSummary = data.summary || null;

            this.renderSummary(this.incidentsSummary);
            this.renderIncidents(this.allIncidents, this.showingAllIncidents);

        } catch (error) {
            console.error('Failed to load incidents:', error);
            const summaryCard = document.getElementById('incidentsSummary');
            if (summaryCard) summaryCard.style.display = 'none';

            container.innerHTML = this.createEmptyState({
                icon: '⚠️',
                title: 'Failed to Load Incidents',
                description: 'There was an error loading incident data. Please try refreshing.',
                compact: true
            });
        }
    }

    renderIncidents(incidents, showAll = false) {
        const container = document.getElementById('incidentsContainer');
        const showMoreBtn = document.getElementById('incidentsShowMoreBtn');
        const INITIAL_COUNT = 10;

        // Apply status filter
        let filteredIncidents = incidents;
        if (this.incidentsStatusFilter === 'ongoing') {
            filteredIncidents = incidents.filter(inc => inc.status !== 'resolved');
        } else if (this.incidentsStatusFilter === 'resolved') {
            filteredIncidents = incidents.filter(inc => inc.status === 'resolved');
        }

        if (!filteredIncidents || filteredIncidents.length === 0) {
            const filterMsg = this.incidentsStatusFilter === 'ongoing' ? 'No ongoing incidents.' :
                            this.incidentsStatusFilter === 'resolved' ? 'No resolved incidents.' :
                            `No incidents found in the past ${this.incidentsDays} days.`;

            container.innerHTML = this.createEmptyState({
                icon: '✅',
                title: 'No Incidents',
                description: filterMsg + ' All systems running smoothly!',
                compact: true
            });
            showMoreBtn.style.display = 'none';
            return;
        }

        // Show first 10, expand on "Show More"
        const incidentsToShow = showAll ? filteredIncidents : filteredIncidents.slice(0, INITIAL_COUNT);

        const html = incidentsToShow.map(incident => {
            const statusClass = incident.status === 'resolved' ? 'resolved' : 'ongoing';
            const statusText = incident.status === 'resolved' ? 'Resolved' : 'Ongoing';
            const statusIcon = incident.status === 'resolved' ? '✓' : '⚠';

            const safeTitle = this.escapeHtml(incident.title);

            return `
                <div class="incident-item ${statusClass}">
                    <div class="incident-header">
                        <div class="incident-status-indicator ${statusClass}">
                            <span class="incident-icon">${statusIcon}</span>
                        </div>
                        <div class="incident-details">
                            <h3 class="incident-title">${safeTitle}</h3>
                            <div class="incident-meta">
                                <span class="incident-time">${this.formatDateTime(incident.started_at)}</span>
                                <span class="incident-separator">•</span>
                                <span class="incident-duration">${this.escapeHtml(incident.duration)}</span>
                                <span class="incident-separator">•</span>
                                <span class="incident-status ${statusClass}">${statusText}</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = html;

        // Show/hide "Show More" button
        if (filteredIncidents.length > INITIAL_COUNT && !showAll) {
            showMoreBtn.style.display = 'block';
            showMoreBtn.textContent = `Show More (${filteredIncidents.length - INITIAL_COUNT} more)`;
        } else if (filteredIncidents.length > INITIAL_COUNT && showAll) {
            showMoreBtn.style.display = 'block';
            showMoreBtn.textContent = 'Show Less';
        } else {
            showMoreBtn.style.display = 'none';
        }
    }

    renderSummary(summary) {
        const summaryCard = document.getElementById('incidentsSummary');

        if (!summary || summary.total_incidents === 0) {
            summaryCard.style.display = 'none';
            return;
        }

        summaryCard.style.display = 'grid';

        document.getElementById('summaryTotalIncidents').textContent = summary.total_incidents;
        document.getElementById('summaryOngoing').textContent = summary.ongoing_count;
        document.getElementById('summaryResolved').textContent = summary.resolved_count;
        document.getElementById('summaryDowntime').textContent = summary.total_downtime;

        const mostAffectedEl = document.getElementById('summaryMostAffected');
        if (summary.most_affected_target) {
            mostAffectedEl.innerHTML = `${summary.most_affected_target} <span class="incident-count-small">(${summary.most_affected_count} incidents)</span>`;
        } else {
            mostAffectedEl.textContent = '—';
        }
    }

    toggleShowMoreIncidents() {
        this.showingAllIncidents = !this.showingAllIncidents;
        this.renderIncidents(this.allIncidents, this.showingAllIncidents);
    }

    formatDateTime(isoString) {
        if (!isoString) return '--';
        try {
            const date = new Date(isoString);
            return date.toLocaleString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            return '--';
        }
    }

    exportEventsCsv() {
        const events = this.filteredEvents.length > 0 ? this.filteredEvents : this.allEvents;

        if (events.length === 0) {
            this.showToast('No events to export', 'warning');
            return;
        }

        // CSV header
        let csv = 'Timestamp,Target,Event Type,Message\n';

        // CSV rows
        events.forEach(event => {
            const timestamp = event.timestamp.replace(/"/g, '""');
            const target = (event.target_name || '').replace(/"/g, '""');
            const eventType = (event.event_type || '').replace(/"/g, '""');
            const message = (event.message || '').replace(/"/g, '""');

            csv += `"${timestamp}","${target}","${eventType}","${message}"\n`;
        });

        // Download
        this.downloadFile(csv, 'event-log.csv', 'text/csv');
        this.showToast(`Exported ${events.length} events to CSV`, 'success');
    }

    exportEventsJson() {
        const events = this.filteredEvents.length > 0 ? this.filteredEvents : this.allEvents;

        if (events.length === 0) {
            this.showToast('No events to export', 'warning');
            return;
        }

        const json = JSON.stringify(events, null, 2);
        this.downloadFile(json, 'event-log.json', 'application/json');
        this.showToast(`Exported ${events.length} events to JSON`, 'success');
    }

    downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    // ============= Target Type Functions =============

    handleTargetTypeChange() {
        // Target type change handler - currently just ping, http, https
        // Future expansion can add additional logic here
    }

    // ============= Discovery Functions =============

    initDiscoveryTab() {
        // Reset discovery tab state when navigating to it
        const progressDiv = document.getElementById('discoveryProgress');
        const resultsDiv = document.getElementById('discoveryResults');
        const startBtn = document.getElementById('startDiscoveryBtn');
        const stopBtn = document.getElementById('stopDiscoveryBtn');

        // Hide progress and results
        if (progressDiv) progressDiv.style.display = 'none';
        if (resultsDiv) resultsDiv.style.display = 'none';

        // Show start button, hide stop button
        if (startBtn) startBtn.style.display = 'inline-block';
        if (stopBtn) stopBtn.style.display = 'none';
    }

    async startDiscovery() {
        const subnet = document.getElementById('discoverySubnet').value;
        if (!subnet) {
            this.showToast('Please enter a subnet', 'error');
            return;
        }

        // Show enhanced progress with spinner
        const progressDiv = document.getElementById('discoveryProgress');
        progressDiv.innerHTML = this.createSpinner('Scanning network... This may take a moment.');
        progressDiv.style.display = 'block';
        document.getElementById('discoveryResults').style.display = 'none';
        document.getElementById('startDiscoveryBtn').style.display = 'none';
        document.getElementById('stopDiscoveryBtn').style.display = 'inline-block';

        const params = {
            subnet: subnet,
            max_concurrent: parseInt(document.getElementById('discoveryConcurrent').value),
            timeout: parseInt(document.getElementById('discoveryTimeout').value),
            check_http: document.getElementById('discoveryCheckHttp').checked
        };

        try {
            const response = await fetch(`${this.apiBase}/discover/subnet`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });

            if (!response.ok) {
                throw new Error('Discovery failed');
            }

            const result = await response.json();

            document.getElementById('discoveryProgress').style.display = 'none';
            document.getElementById('startDiscoveryBtn').style.display = 'inline-block';
            document.getElementById('stopDiscoveryBtn').style.display = 'none';

            this.renderDiscoveredDevices(result.devices);
            this.showToast(`Found ${result.devices_found} devices`, 'success');
        } catch (error) {
            console.error('Discovery failed:', error);
            this.showToast('Discovery failed', 'error');
            document.getElementById('discoveryProgress').style.display = 'none';
            document.getElementById('startDiscoveryBtn').style.display = 'inline-block';
            document.getElementById('stopDiscoveryBtn').style.display = 'none';
        }
    }

    stopDiscovery() {
        // For now, just hide the buttons (full stop would require WebSocket or polling)
        document.getElementById('discoveryProgress').style.display = 'none';
        document.getElementById('startDiscoveryBtn').style.display = 'inline-block';
        document.getElementById('stopDiscoveryBtn').style.display = 'none';
    }

    renderDiscoveredDevices(devices) {
        const container = document.getElementById('discoveredDevicesList');
        const resultsDiv = document.getElementById('discoveryResults');
        const countSpan = document.getElementById('discoveredCount');

        countSpan.textContent = devices.length;
        resultsDiv.style.display = 'block';

        if (devices.length === 0) {
            container.innerHTML = this.createEmptyState({
                icon: '🔍',
                title: 'No Devices Found',
                description: 'The network scan completed but no devices were discovered. Try adjusting your subnet or scan settings.',
                compact: true
            });
            return;
        }

        container.innerHTML = devices.map((device, index) => {
            const safeIp = this.escapeHtml(device.ip);
            const safeHostname = device.hostname ? this.escapeHtml(device.hostname) : '';
            const safeSuggestedName = this.escapeHtml(device.suggested_name);

            return `
            <div class="discovered-device" data-index="${index}">
                <div class="device-checkbox">
                    <input type="checkbox" class="device-select-cb" id="device-${index}" checked>
                </div>
                <div class="device-info">
                    <div class="device-header">
                        <span class="device-ip" title="${safeIp}">${safeIp}</span>
                        ${device.hostname ? `<span class="device-hostname" title="${safeHostname}">${safeHostname}</span>` : ''}
                        <span class="device-type-badge">${device.suggested_type.toUpperCase()}</span>
                    </div>
                    <div class="device-details">
                        ${device.http_enabled ? '<span class="device-feature">HTTP</span>' : ''}
                        ${device.https_enabled ? '<span class="device-feature">HTTPS</span>' : ''}
                    </div>
                    <div class="device-config">
                        <label>Name: <input type="text" class="device-name-input" value="${safeSuggestedName}"></label>
                        <label>Type:
                            <select class="device-type-select">
                                <option value="ping" ${device.suggested_type === 'ping' ? 'selected' : ''}>Ping</option>
                                <option value="http" ${device.suggested_type === 'http' ? 'selected' : ''}>HTTP</option>
                                <option value="https" ${device.suggested_type === 'https' ? 'selected' : ''}>HTTPS</option>
                            </select>
                        </label>
                    </div>
                </div>
            </div>
        `}).join('');

        // Store devices for later import
        this.discoveredDevices = devices;
    }

    selectAllDevices() {
        document.querySelectorAll('.device-select-cb').forEach(cb => cb.checked = true);
    }

    deselectAllDevices() {
        document.querySelectorAll('.device-select-cb').forEach(cb => cb.checked = false);
    }

    async importSelectedDevices() {
        const selectedDevices = [];

        document.querySelectorAll('.discovered-device').forEach(deviceEl => {
            const checkbox = deviceEl.querySelector('.device-select-cb');
            if (checkbox.checked) {
                const index = parseInt(deviceEl.dataset.index);
                const device = this.discoveredDevices[index];
                const nameInput = deviceEl.querySelector('.device-name-input');
                const typeSelect = deviceEl.querySelector('.device-type-select');

                selectedDevices.push({
                    ...device.suggested_config,
                    name: nameInput.value,
                    type: typeSelect.value
                });
            }
        });

        if (selectedDevices.length === 0) {
            this.showToast('Please select at least one device', 'error');
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/discover/import`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(selectedDevices)
            });

            if (!response.ok) {
                throw new Error('Import failed');
            }

            const result = await response.json();
            console.log('Import result:', result);

            this.showToast(`Imported ${result.imported} device${result.imported !== 1 ? 's' : ''} successfully`, 'success');

            // Switch to dashboard and reload after a short delay
            setTimeout(() => {
                this.switchTab('dashboard');
                this.loadDashboard();
            }, 1000);
        } catch (error) {
            console.error('Import failed:', error);
            this.showToast('Failed to import devices', 'error');
        }
    }

    // ============= Audio Library Functions =============

    async loadAudioLibrary() {
        try {
            const library = await this.apiGet('/audio/library');
            this.audioLibrary = library;
            this.populateAudioSelects(library.alerts);
            this.populateDefaultSoundSelects(library.alerts, library);
        } catch (error) {
            console.error('Failed to load audio library:', error);
        }
    }

    populateAudioSelects(alerts) {
        const downSelect = document.getElementById('audioDownAlert');
        const upSelect = document.getElementById('audioUpAlert');

        if (!downSelect || !upSelect) return; // Not on target edit page

        // Get default sound names for display
        const defaultDownName = this.audioLibrary?.default_down_alert || 'system_down.aiff';
        const defaultUpName = this.audioLibrary?.default_up_alert || 'system_up.aiff';

        // Find the actual alert names for the defaults
        let defaultDownDisplayName = defaultDownName;
        let defaultUpDisplayName = defaultUpName;

        Object.entries(alerts).forEach(([id, alert]) => {
            if (alert.filename === defaultDownName) {
                defaultDownDisplayName = alert.name;
            }
            if (alert.filename === defaultUpName) {
                defaultUpDisplayName = alert.name;
            }
        });

        // Clear existing options and add "Use Default" with the actual default name
        downSelect.innerHTML = `<option value="">Use Default (${defaultDownDisplayName})</option>`;
        upSelect.innerHTML = `<option value="">Use Default (${defaultUpDisplayName})</option>`;

        // Add alerts
        Object.entries(alerts).forEach(([id, alert]) => {
            if (alert.event_types.includes('down') || alert.event_types.includes('threshold_reached')) {
                const option = document.createElement('option');
                option.value = alert.filename;
                option.textContent = alert.name;
                downSelect.appendChild(option);
            }

            if (alert.event_types.includes('up') || alert.event_types.includes('recovered')) {
                const option = document.createElement('option');
                option.value = alert.filename;
                option.textContent = alert.name;
                upSelect.appendChild(option);
            }
        });
    }

    populateDefaultSoundSelects(alerts, library) {
        const defaultDownSelect = document.getElementById('defaultDownSound');
        const defaultUpSelect = document.getElementById('defaultUpSound');

        if (!defaultDownSelect || !defaultUpSelect) return; // Not on settings page

        // Clear existing options
        defaultDownSelect.innerHTML = '';
        defaultUpSelect.innerHTML = '';

        // Add all available sounds to both selects
        Object.entries(alerts).forEach(([id, alert]) => {
            // Add to down select
            const downOption = document.createElement('option');
            downOption.value = alert.filename;
            downOption.textContent = alert.name;
            defaultDownSelect.appendChild(downOption);

            // Add to up select
            const upOption = document.createElement('option');
            upOption.value = alert.filename;
            upOption.textContent = alert.name;
            defaultUpSelect.appendChild(upOption);
        });

        // Set current defaults from library metadata
        const currentDefaultDown = library.default_down_alert || 'system_down.aiff';
        const currentDefaultUp = library.default_up_alert || 'system_up.aiff';

        defaultDownSelect.value = currentDefaultDown;
        defaultUpSelect.value = currentDefaultUp;
    }


    previewAudio(filename) {
        // Create audio element and play
        const audio = new Audio(`/sounds/${filename}`);
        audio.play().catch(error => {
            console.error('Failed to play audio:', error);
            this.showToast('Failed to play audio', 'error');
        });
    }

    // ============= Settings Audio Library Functions =============

    showAudioUploadForm() {
        document.getElementById('audioUploadForm').style.display = 'block';
        document.getElementById('uploadNewSoundBtn').style.display = 'none';
    }

    hideAudioUploadForm() {
        document.getElementById('audioUploadForm').style.display = 'none';
        document.getElementById('uploadNewSoundBtn').style.display = 'block';
        // Clear form
        document.getElementById('newAudioFile').value = '';
        document.getElementById('newAudioName').value = '';
        document.getElementById('newAudioDescription').value = '';
    }

    async uploadNewAudioToLibrary() {
        const fileInput = document.getElementById('newAudioFile');
        const nameInput = document.getElementById('newAudioName');
        const categorySelect = document.getElementById('newAudioCategory');
        const eventTypesSelect = document.getElementById('newAudioEventTypes');
        const descriptionInput = document.getElementById('newAudioDescription');

        const file = fileInput.files[0];
        if (!file) {
            this.showToast('Please select an audio file', 'error');
            return;
        }

        // Check file size (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
            this.showToast('File too large (max 10MB)', 'error');
            return;
        }

        // Get selected event types
        const selectedEventTypes = Array.from(eventTypesSelect.selectedOptions).map(opt => opt.value);
        if (selectedEventTypes.length === 0) {
            this.showToast('Please select at least one event type', 'error');
            return;
        }

        try {
            this.showToast('Uploading to library...', 'info');

            const formData = new FormData();
            formData.append('file', file);
            formData.append('category', categorySelect.value);
            formData.append('event_types', selectedEventTypes.join(','));

            if (nameInput.value.trim()) {
                formData.append('name', nameInput.value.trim());
            }

            if (descriptionInput.value.trim()) {
                formData.append('description', descriptionInput.value.trim());
            }

            const response = await fetch(`${this.apiBase}/audio/library/upload`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const result = await response.json();
            this.showToast(`Audio "${result.filename}" uploaded successfully!`, 'success');

            // Hide form and reload library
            this.hideAudioUploadForm();
            await this.loadAudioLibrary();
            await this.renderAudioLibraryInSettings();

        } catch (error) {
            this.showToast(`Upload failed: ${error.message}`, 'error');
            console.error(error);
        }
    }

    async renderAudioLibraryInSettings() {
        try {
            const library = await this.apiGet('/audio/library');
            const container = document.getElementById('audioLibraryGrid');

            if (!container) return; // Not on settings page

            const alerts = library.alerts;
            const alertEntries = Object.entries(alerts);

            if (alertEntries.length === 0) {
                container.innerHTML = '<div class="no-results">No audio alerts in library. Upload some sounds to get started!</div>';
                return;
            }

            let html = '<div class="audio-alerts-grid">';

            alertEntries.forEach(([id, alert]) => {
                const isDefault = alert.filename === library.default_down_alert || alert.filename === library.default_up_alert;
                const defaultBadge = isDefault ? '<span class="default-badge">Default</span>' : '';

                html += `
                    <div class="audio-alert-card" data-filename="${alert.filename}">
                        <div class="audio-alert-info">
                            <div class="audio-alert-name">${alert.name} ${defaultBadge}</div>
                            <div class="audio-alert-category">${alert.category}</div>
                            ${alert.description ? `<div class="audio-alert-description">${alert.description}</div>` : ''}
                        </div>
                        <div class="audio-alert-actions">
                            <button type="button" class="btn btn-small btn-secondary play-audio-btn" data-filename="${alert.filename}">
                                <span class="icon-play"></span> Play
                            </button>
                            ${alert.category !== 'default' ? `<button type="button" class="btn btn-small btn-danger delete-audio-btn" data-id="${id}">Delete</button>` : ''}
                        </div>
                    </div>
                `;
            });

            html += '</div>';
            container.innerHTML = html;

            // Add event listeners
            container.querySelectorAll('.play-audio-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const filename = e.currentTarget.dataset.filename;
                    this.previewAudio(filename);
                });
            });

            container.querySelectorAll('.delete-audio-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const alertId = e.currentTarget.dataset.id;
                    if (confirm('Are you sure you want to delete this audio alert?')) {
                        await this.deleteAudioAlert(alertId);
                    }
                });
            });

        } catch (error) {
            console.error('Failed to render audio library:', error);
        }
    }

    async deleteAudioAlert(alertId) {
        try {
            await this.apiDelete(`/audio/library/alert/${alertId}`);
            this.showToast('Audio alert deleted successfully', 'success');
            await this.loadAudioLibrary();
            await this.renderAudioLibraryInSettings();
        } catch (error) {
            this.showToast('Failed to delete audio alert', 'error');
            console.error(error);
        }
    }

    // ============= Theme Functions =============

    loadTheme() {
        // Load theme preference from localStorage (default: 'dark')
        const savedTheme = localStorage.getItem('theme') || 'dark';
        this.applyTheme(savedTheme);
        this.updateThemeButtons(savedTheme);

        // If system theme is selected, listen for system theme changes
        if (savedTheme === 'system') {
            this.watchSystemTheme();
        }
    }

    async setTheme(theme) {
        // Save preference
        localStorage.setItem('theme', theme);

        // Apply theme
        this.applyTheme(theme);
        this.updateThemeButtons(theme);

        // Show toast
        const themeNames = {
            'light': 'Light mode',
            'dark': 'Dark mode',
            'system': 'System default'
        };
        this.showToast(`${themeNames[theme]} enabled`, 'info');

        // Watch system theme if needed
        if (theme === 'system') {
            this.watchSystemTheme();
        }
    }

    async refreshCurrentView() {
        // Get currently active tab
        const activeTab = document.querySelector('.tab-button.active');
        if (!activeTab) return;

        const tabId = activeTab.dataset.tab;

        // Reload content based on current tab
        
        switch (tabId) {
            case 'dashboard':
                
                await this.loadDashboard();
                break;
            case 'uptime':
                
                await this.loadUptimeDashboard();
                break;
            case 'events':
                
                await this.loadEventLog();
                break;
            case 'health':
                
                await this.loadHealthDashboard();
                break;
            case 'settings':
                
                await this.loadSettings();
                break;
        }
    }

    applyTheme(theme) {
        const html = document.documentElement;

        if (theme === 'system') {
            // Detect system preference
            const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            if (systemPrefersDark) {
                document.body.classList.remove('light-mode');
                html.setAttribute('data-theme', 'dark');
            } else {
                document.body.classList.add('light-mode');
                html.setAttribute('data-theme', 'light');
            }
        } else if (theme === 'light') {
            document.body.classList.add('light-mode');
            html.setAttribute('data-theme', 'light');
        } else {
            document.body.classList.remove('light-mode');
            html.setAttribute('data-theme', 'dark');
        }
    }

    updateThemeButtons(activeTheme) {
        // Update active state on theme buttons
        document.querySelectorAll('.theme-option').forEach(btn => {
            if (btn.dataset.theme === activeTheme) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    watchSystemTheme() {
        // Remove existing listener if any
        if (this.systemThemeListener) {
            window.matchMedia('(prefers-color-scheme: dark)').removeEventListener('change', this.systemThemeListener);
        }

        // Add new listener
        this.systemThemeListener = (e) => {
            const currentTheme = localStorage.getItem('theme');
            if (currentTheme === 'system') {
                if (e.matches) {
                    document.body.classList.remove('light-mode');
                } else {
                    document.body.classList.add('light-mode');
                }
            }
        };

        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', this.systemThemeListener);
    }

    async loadFeatureFlags() {
        try {
            this.features = await this.apiGet('/config/features');
            console.log('🚀 Feature flags loaded:', this.features);

            // Apply UI changes based on feature flags
            this.applyFeatureFlagUI();
        } catch (error) {
            console.error('Failed to load feature flags:', error);
            // Default to all features enabled on error
            this.features = {
                discoveryEnabled: true
            };
        }
    }

    applyFeatureFlagUI() {
        // Disable Discovery tab if feature is disabled
        if (!this.features.discoveryEnabled) {
            const discoveryTab = document.querySelector('[data-tab="discovery"]');
            if (discoveryTab) {
                discoveryTab.classList.add('disabled');
                discoveryTab.setAttribute('title', 'Discovery is disabled in this deployment');
            }
        }
    }

    async loadDevicePresets() {
        try {
            const url = this.apiBase + '/device-presets';
            console.log('Fetching device presets from:', url);
            this.devicePresets = await this.apiGet('/device-presets');
            console.log('Device presets loaded:', Object.keys(this.devicePresets).length);
        } catch (error) {
            console.error('Failed to load device presets:', error);
            console.error('apiBase is:', this.apiBase);
        }
    }

    handleDeviceTypeChange(e) {
        const deviceType = e.target.value;
        const preset = this.devicePresets[deviceType];

        if (!preset) {
            console.warn(`No preset found for device type: ${deviceType}`);
            return;
        }

        console.log(`Applying ${deviceType} preset:`, preset);

        // Apply preset values to form fields
        const failureThreshold = document.getElementById('failureThreshold');
        const checkInterval = document.getElementById('checkInterval');
        const audioBehavior = document.getElementById('audioBehavior');

        if (failureThreshold) failureThreshold.value = preset.failure_threshold;
        if (checkInterval) checkInterval.value = preset.check_interval;
        if (audioBehavior) audioBehavior.value = preset.audio_behavior;

        // Show a tooltip or visual feedback
        this.showToast(`Applied ${deviceType} preset: ${preset.description}`, 'info');
    }

    // ============= Sharing Tab Functions =============

    async initSharingTab() {
        await this.loadPublicTokens();
        await this.loadTargetVisibility();
    }

    async loadPublicTokens() {
        const container = document.getElementById('publicLinksContainer');

        // Show skeleton loading
        container.innerHTML = `
            <div class="skeleton-card" style="margin-bottom: 15px;">
                <div class="skeleton-line skeleton-line-title"></div>
                <div class="skeleton-line skeleton-line-full"></div>
                <div class="skeleton-line skeleton-line-medium"></div>
            </div>
        `;

        try {
            const response = await this.apiGet('/sharing/tokens');

            // Update count badge
            const countBadge = document.getElementById('linksCount');
            if (countBadge) {
                const count = response.tokens?.length || 0;
                countBadge.textContent = `${count} ${count === 1 ? 'link' : 'links'}`;
            }

            if (!response.tokens || response.tokens.length === 0) {
                container.innerHTML = this.createEmptyState({
                    icon: '🔗',
                    title: 'No Public Links',
                    description: 'Generate a shareable link to display your monitoring status to others without authentication.',
                    actionText: '+ Generate New Link',
                    actionCallback: 'app.generatePublicToken()',
                    compact: true
                });
                return;
            }

            const tokensHtml = response.tokens.map(token => `
                <div class="public-link-item" data-token="${this.escapeHtml(token.token)}">
                    <div class="link-info">
                        <div class="link-name">
                            <strong>${this.escapeHtml(token.name || 'Unnamed Link')}</strong>
                        </div>
                        <div class="link-url" onclick="app.copyTokenUrlByClick('${this.escapeHtml(token.token)}')" title="Click to copy URL">
                            <input type="text" readonly value="${window.location.origin}${this.escapeHtml(token.url)}"
                                   id="url-${this.escapeHtml(token.token)}" class="url-input url-input-clickable">
                        </div>
                        <div class="link-meta">
                            <span>Created: ${this.formatDate(token.created_at)}</span>
                            <span>•</span>
                            <span>Views: ${token.access_count || 0}</span>
                            ${token.last_accessed ? `<span>•</span><span>Last: ${this.formatTimeSince(token.last_accessed)}</span>` : ''}
                        </div>
                    </div>
                    <div class="link-actions">
                        <button class="btn btn-small btn-secondary" onclick="app.editPublicLink('${this.escapeHtml(token.token)}')" title="Edit target visibility">
                            ✏️ Edit
                        </button>
                        <button class="btn btn-small ${token.enabled ? 'btn-warning' : 'btn-success'}"
                                onclick="app.toggleToken('${this.escapeHtml(token.token)}', ${!token.enabled})"
                                title="${token.enabled ? 'Disable' : 'Enable'} this link">
                            ${token.enabled ? '⏸ Disable' : '▶️ Enable'}
                        </button>
                        <button class="btn btn-small btn-danger" onclick="app.revokeToken('${this.escapeHtml(token.token)}', '${this.escapeHtml(token.name || 'this link')}')" title="Delete">
                            🗑 Delete
                        </button>
                    </div>
                </div>
            `).join('');

            container.innerHTML = tokensHtml;
        } catch (error) {
            console.error('Failed to load public tokens:', error);
            this.showToast('Failed to load public links', 'error');
        }
    }

    async generatePublicToken() {
        // Open slide-out panel
        const panel = document.getElementById('linkConfigPanel');
        if (!panel) return;

        // Show panel with animation
        panel.style.display = 'block';
        setTimeout(() => panel.classList.add('active'), 10);

        // Load target visibility into panel
        await this.loadTargetVisibilityInPanel();

        // Setup generate button
        const generateBtn = document.getElementById('panelGenerateBtn');
        const newHandler = async () => {
            try {
                const name = document.getElementById('panelTokenName').value.trim();
                const viewMode = document.getElementById('panelViewMode').value;

                const response = await this.apiPost('/sharing/tokens', {
                    name: name || '',
                    view_mode: viewMode
                });

                if (response.success) {
                    this.showToast('Public link created successfully!', 'success');
                    this.closeLinkConfigPanel();
                    await this.loadPublicTokens();

                    // Copy URL to clipboard
                    const url = `${window.location.origin}${response.url}`;
                    try {
                        await navigator.clipboard.writeText(url);
                        this.showToast('URL copied to clipboard!', 'success');
                    } catch (err) {
                        console.error('Failed to copy:', err);
                    }
                }
            } catch (error) {
                console.error('Failed to generate token:', error);
                this.showToast('Failed to generate public link', 'error');
            }
        };

        // Remove old listener and add new one
        generateBtn.replaceWith(generateBtn.cloneNode(true));
        document.getElementById('panelGenerateBtn').addEventListener('click', newHandler);
    }

    async editPublicLink(token) {
        try {
            // Fetch the token data to get name and view_mode
            const response = await this.apiGet('/sharing/tokens');
            const tokenData = response.tokens?.find(t => t.token === token);

            if (!tokenData) {
                this.showToast('Token not found', 'error');
                return;
            }

            // Open slide-out panel for editing
            const panel = document.getElementById('linkConfigPanel');
            if (!panel) return;

            // Update header text
            const header = panel.querySelector('.slide-out-header h2');
            if (header) header.textContent = 'Edit Public Link';

            // Show panel with animation
            panel.style.display = 'block';
            setTimeout(() => panel.classList.add('active'), 10);

            // Populate the form fields with current values
            const nameInput = document.getElementById('panelTokenName');
            const viewModeSelect = document.getElementById('panelViewMode');

            if (nameInput) nameInput.value = tokenData.name || '';
            if (viewModeSelect) viewModeSelect.value = tokenData.view_mode || 'both';

            // Keep fields enabled so they can be edited
            nameInput.disabled = false;
            viewModeSelect.disabled = false;

            // Load target visibility into panel
            await this.loadTargetVisibilityInPanel();

            // Change button text
            const generateBtn = document.getElementById('panelGenerateBtn');
            generateBtn.textContent = 'Save Changes';

            // Setup save button to update the token
            const saveHandler = async () => {
                try {
                    const updatedName = nameInput.value.trim();
                    const updatedViewMode = viewModeSelect.value;

                    const updateResponse = await fetch(`${this.apiBase}/sharing/tokens/${token}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: updatedName || null,
                            view_mode: updatedViewMode
                        })
                    });

                    if (updateResponse.ok) {
                        this.showToast('Changes saved successfully!', 'success');
                        this.closeLinkConfigPanel();
                        await this.loadPublicTokens();
                    } else {
                        throw new Error('Failed to update token');
                    }
                } catch (error) {
                    console.error('Failed to save changes:', error);
                    this.showToast('Failed to save changes', 'error');
                }
            };

            generateBtn.replaceWith(generateBtn.cloneNode(true));
            document.getElementById('panelGenerateBtn').addEventListener('click', saveHandler);
        } catch (error) {
            console.error('Failed to load token for editing:', error);
            this.showToast('Failed to load link details', 'error');
        }
    }

    closeLinkConfigPanel() {
        const panel = document.getElementById('linkConfigPanel');
        if (!panel) return;

        panel.classList.remove('active');
        setTimeout(() => {
            panel.style.display = 'none';

            // Reset header
            const header = panel.querySelector('.slide-out-header h2');
            if (header) header.textContent = 'Configure Public Link';

            // Clear and re-enable form
            document.getElementById('panelTokenName').value = '';
            document.getElementById('panelTokenName').disabled = false;
            document.getElementById('panelViewMode').value = 'both';
            document.getElementById('panelViewMode').disabled = false;

            // Reset button text
            const btn = document.getElementById('panelGenerateBtn');
            if (btn) btn.textContent = 'Generate Link';
        }, 300);
    }

    async loadTargetVisibilityInPanel() {
        const container = document.getElementById('panelTargetVisibilityContainer');
        if (!container) return;

        // Show loading
        container.innerHTML = `
            <div class="loading-placeholder">
                <div class="spinner-small"></div>
                <p>Loading targets...</p>
            </div>
        `;

        try {
            const response = await this.apiGet('/targets');

            if (!response || response.length === 0) {
                container.innerHTML = this.createEmptyState({
                    icon: '📡',
                    title: 'No Targets',
                    description: 'Add monitoring targets first.',
                    compact: true
                });
                return;
            }

            const targetsHtml = response.map(target => {
                const isVisible = target.public_visible === 1;
                const publicName = target.public_name || '';
                return `
                    <div class="visibility-card" data-target-id="${this.escapeHtml(target.id)}">
                        <div class="visibility-card-header">
                            <div class="visibility-target-info">
                                <div class="visibility-target-name">${this.escapeHtml(target.name)}</div>
                                <div class="visibility-target-type">${this.escapeHtml(target.type || 'ping').toUpperCase()}</div>
                            </div>
                            <label class="visibility-toggle" onclick="event.stopPropagation()">
                                <input type="checkbox"
                                       ${isVisible ? 'checked' : ''}
                                       data-target-id="${this.escapeHtml(target.id)}"
                                       onclick="event.stopPropagation()">
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        ${isVisible ? `
                            <div class="visibility-public-name">
                                <label>Public Display Name (optional)</label>
                                <input type="text"
                                       class="form-control visibility-public-name-input"
                                       placeholder="Leave blank to use target name"
                                       value="${this.escapeHtml(publicName)}"
                                       onblur="app.updatePublicName('${this.escapeHtml(target.id)}', this.value)">
                                <small class="form-text">Hide internal identifiers from public view</small>
                            </div>
                        ` : ''}
                    </div>
                `;
            }).join('');

            container.innerHTML = targetsHtml;

            // Add event listeners to checkboxes AFTER rendering
            container.querySelectorAll('.visibility-toggle input[type="checkbox"]').forEach(checkbox => {
                checkbox.addEventListener('change', async (e) => {
                    e.stopPropagation();
                    const targetId = e.target.getAttribute('data-target-id');
                    const isChecked = e.target.checked;
                    await this.toggleTargetVisibility(targetId, isChecked);
                });
            });
        } catch (error) {
            console.error('Failed to load targets:', error);
            container.innerHTML = '<p class="text-error">Failed to load targets</p>';
        }
    }

    async copyTokenUrl(token) {
        try {
            const input = document.getElementById(`url-${token}`);
            if (input) {
                await navigator.clipboard.writeText(input.value);
                this.showToast('URL copied to clipboard!', 'success');
            }
        } catch (error) {
            console.error('Failed to copy URL:', error);
            this.showToast('Failed to copy URL', 'error');
        }
    }

    async copyTokenUrlByClick(token) {
        try {
            const input = document.getElementById(`url-${token}`);
            if (input) {
                // Select the text
                input.select();
                input.setSelectionRange(0, 99999); // For mobile

                // Copy to clipboard
                await navigator.clipboard.writeText(input.value);
                this.showToast('✓ URL copied to clipboard!', 'success');
            }
        } catch (error) {
            console.error('Failed to copy URL:', error);
            this.showToast('Failed to copy URL', 'error');
        }
    }

    async toggleToken(token, enabled) {
        try {
            const response = await fetch(`${this.apiBase}/sharing/tokens/${token}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });

            if (response.ok) {
                const action = enabled ? 'enabled' : 'disabled';
                this.showToast(`Link ${action} successfully`, 'success');
                await this.loadPublicTokens();
            } else {
                throw new Error('Failed to toggle token');
            }
        } catch (error) {
            console.error('Failed to toggle token:', error);
            this.showToast('Failed to update link', 'error');
        }
    }

    async revokeToken(token, tokenName) {
        if (!confirm(`Are you sure you want to delete "${tokenName}"? This action cannot be undone.`)) {
            return;
        }

        try {
            await this.apiDelete(`/sharing/tokens/${token}`);
            this.showToast('Link deleted successfully', 'success');
            await this.loadPublicTokens();
        } catch (error) {
            console.error('Failed to revoke token:', error);
            this.showToast('Failed to delete link', 'error');
        }
    }

    async loadTargetVisibility() {
        const container = document.getElementById('targetVisibilityContainer');
        if (!container) {
            console.warn('Target visibility container not found');
            return;
        }

        // Show skeleton loading
        container.innerHTML = this.createSkeletonGrid(3);

        try {
            const response = await this.apiGet('/targets');

            if (!response || response.length === 0) {
                container.innerHTML = this.createEmptyState({
                    icon: '📡',
                    title: 'No Targets Available',
                    description: 'Add monitoring targets first, then configure which ones are visible on public pages.',
                    compact: true
                });
                return;
            }

            const targetsHtml = response.map(target => {
                const isVisible = target.public_visible === 1;
                const publicName = target.public_name || '';

                return `
                    <div class="visibility-card">
                        <div class="visibility-card-header">
                            <div class="visibility-target-info">
                                <div class="visibility-target-name">${this.escapeHtml(target.name)}</div>
                                <div class="visibility-target-type">${this.escapeHtml(target.type || 'ping').toUpperCase()}</div>
                            </div>
                            <label class="visibility-toggle">
                                <input type="checkbox"
                                       id="visible-${target.id}"
                                       ${isVisible ? 'checked' : ''}
                                       onchange="app.toggleTargetVisibility('${target.id}', this.checked)">
                                <span class="toggle-slider"></span>
                                <span class="toggle-label">${isVisible ? 'VISIBLE' : 'HIDDEN'}</span>
                            </label>
                        </div>
                        <div class="visibility-card-body">
                            <label class="visibility-input-label">Public Display Name (Optional)</label>
                            <input type="text"
                                   id="publicName-${target.id}"
                                   value="${this.escapeHtml(publicName)}"
                                   placeholder="${this.escapeHtml(target.name)}"
                                   class="visibility-input"
                                   onchange="app.updatePublicName('${target.id}')">
                            <div class="visibility-hint">Leave blank to use the target name above</div>
                        </div>
                    </div>
                `;
            }).join('');

            container.innerHTML = targetsHtml;
        } catch (error) {
            console.error('Failed to load target visibility:', error);
            this.showToast('Failed to load targets', 'error');
        }
    }

    async toggleTargetVisibility(targetId, visible) {
        // Prevent multiple rapid calls for the same target
        const lockKey = `toggle_${targetId}`;
        if (this[lockKey]) {
            console.log(`Toggle for ${targetId} already in progress, ignoring...`);
            return;
        }

        this[lockKey] = true;

        try {
            console.log(`Toggling target ${targetId} to ${visible}`);

            const response = await fetch(`${this.apiBase}/targets/${targetId}/visibility`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    public_visible: visible
                })
            });

            if (response.ok) {
                const status = visible ? 'visible' : 'hidden';
                this.showToast(`Target set to ${status}`, 'success');

                // Update the UI directly without reloading the entire panel
                const card = document.querySelector(`.visibility-card[data-target-id="${targetId}"]`);
                if (card && visible) {
                    // Add public name input if enabling
                    const existingInput = card.querySelector('.visibility-public-name');
                    if (!existingInput) {
                        const publicNameHtml = `
                            <div class="visibility-public-name">
                                <label>Public Display Name (optional)</label>
                                <input type="text"
                                       class="form-control visibility-public-name-input"
                                       placeholder="Leave blank to use target name"
                                       value=""
                                       onblur="app.updatePublicName('${this.escapeHtml(targetId)}', this.value)">
                                <small class="form-text">Hide internal identifiers from public view</small>
                            </div>
                        `;
                        card.querySelector('.visibility-card-header').insertAdjacentHTML('afterend', publicNameHtml);
                    }
                } else if (card && !visible) {
                    // Remove public name input if disabling
                    const publicNameSection = card.querySelector('.visibility-public-name');
                    if (publicNameSection) {
                        publicNameSection.remove();
                    }
                }

                // Release lock immediately on success
                this[lockKey] = false;
            } else {
                this[lockKey] = false;
                throw new Error('Failed to update visibility');
            }
        } catch (error) {
            console.error('Failed to toggle target visibility:', error);
            this.showToast('Failed to update target visibility', 'error');
            this[lockKey] = false;

            // Reload panel to revert UI state on error
            await this.loadTargetVisibilityInPanel();
        }
    }

    async updatePublicName(targetId, publicName) {
        try {
            const trimmedName = publicName.trim();

            const response = await fetch(`${this.apiBase}/targets/${targetId}/visibility`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    public_name: trimmedName || null
                })
            });

            if (response.ok) {
                // Silent update on blur - no toast needed
                console.log(`Updated public name for ${targetId}: ${trimmedName || '(default)'}`);
            } else {
                throw new Error('Failed to update public name');
            }
        } catch (error) {
            console.error('Failed to update public name:', error);
            this.showToast('Failed to update public name', 'error');
        }
    }

    async previewPublicPage() {
        try {
            const response = await this.apiGet('/sharing/tokens');

            if (!response.tokens || response.tokens.length === 0) {
                this.showToast('Please generate a public link first', 'warning');
                return;
            }

            // Find first enabled token
            const enabledToken = response.tokens.find(t => t.enabled);

            if (!enabledToken) {
                this.showToast('Please enable at least one public link', 'warning');
                return;
            }

            // Open in new tab
            window.open(`/public/${enabledToken.token}`, '_blank');
        } catch (error) {
            console.error('Failed to preview:', error);
            this.showToast('Failed to preview public page', 'error');
        }
    }

    // ========================================================================
    // API KEY MANAGEMENT (External Integrations)
    // ========================================================================

    async loadApiKeys() {
        try {
            const response = await this.apiGet('/api-keys');
            const container = document.getElementById('apiKeysContainer');
            const countBadge = document.getElementById('apiKeysCount');

            if (!container || !countBadge) return;

            // Update count badge
            const count = response.keys?.length || 0;
            countBadge.textContent = `${count} ${count === 1 ? 'key' : 'keys'}`;

            // Render API keys
            if (!response.keys || response.keys.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">🔑</div>
                        <h3>No API Keys Yet</h3>
                        <p>Generate an API key to allow external integrations to access your monitoring data.</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = response.keys.map(key => `
                <div class="api-key-item" data-key-id="${key.id}">
                    <div class="api-key-info">
                        <div class="api-key-name">
                            <strong>${this.escapeHtml(key.name || 'Unnamed Key')}</strong>
                            ${key.enabled ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-secondary">Disabled</span>'}
                        </div>
                        <div class="api-key-meta">
                            <span>Created: ${this.formatDate(key.created_at)}</span>
                            ${key.last_used ? `<span>Last used: ${this.formatDate(key.last_used)}</span>` : '<span>Never used</span>'}
                            <span>Usage: ${key.access_count || 0} requests</span>
                        </div>
                    </div>
                    <div class="api-key-actions">
                        <button class="btn btn-icon" onclick="app.toggleApiKey(${key.id}, ${!key.enabled})" title="${key.enabled ? 'Disable' : 'Enable'} key">
                            <span class="icon-${key.enabled ? 'pause' : 'play'}"></span>
                        </button>
                        <button class="btn btn-icon btn-danger" onclick="app.deleteApiKey(${key.id}, '${this.escapeHtml(key.name || 'this key')}')" title="Delete key">
                            <span class="icon-trash"></span>
                        </button>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            console.error('Failed to load API keys:', error);
            this.showToast('Failed to load API keys', 'error');
        }
    }

    openGenerateApiKeyModal() {
        const modal = document.getElementById('generateApiKeyModal');
        if (!modal) return;

        // Clear input
        const nameInput = document.getElementById('apiKeyName');
        if (nameInput) nameInput.value = '';

        // Show modal
        modal.style.display = 'flex';
    }

    closeGenerateApiKeyModal() {
        const modal = document.getElementById('generateApiKeyModal');
        if (modal) modal.style.display = 'none';
    }

    async createApiKey() {
        try {
            const name = document.getElementById('apiKeyName').value.trim();

            const response = await this.apiPost('/api-keys', {
                name: name || null
            });

            if (response.success) {
                // Close generate modal
                this.closeGenerateApiKeyModal();

                // Show the API key modal with the newly created key
                this.showApiKeyModal(response.key, response.name);

                // Reload API keys list
                await this.loadApiKeys();

                this.showToast('API key created successfully', 'success');
            } else {
                throw new Error(response.message || 'Failed to create API key');
            }
        } catch (error) {
            console.error('Failed to create API key:', error);
            this.showToast('Failed to create API key', 'error');
        }
    }

    showApiKeyModal(apiKey, keyName) {
        const modal = document.getElementById('apiKeyModal');
        const keyInput = document.getElementById('newApiKeyValue');
        const exampleCode = document.getElementById('apiKeyExample');

        if (!modal || !keyInput || !exampleCode) return;

        // Set the API key value
        keyInput.value = apiKey;

        // Generate example curl command
        const hostname = window.location.hostname;
        const port = window.location.port ? `:${window.location.port}` : '';
        const protocol = window.location.protocol;
        exampleCode.textContent = `curl -H "x-api-key: ${apiKey}" \\
  ${protocol}//${hostname}${port}/api/v1/alert-status`;

        // Show modal
        modal.style.display = 'flex';

        // Auto-select the API key for easy copying
        setTimeout(() => keyInput.select(), 100);
    }

    closeApiKeyModal() {
        const modal = document.getElementById('apiKeyModal');
        if (modal) modal.style.display = 'none';
    }

    copyApiKey() {
        const keyInput = document.getElementById('newApiKeyValue');
        if (!keyInput) return;

        keyInput.select();
        document.execCommand('copy');

        this.showToast('API key copied to clipboard', 'success');
    }

    async toggleApiKey(keyId, enabled) {
        try {
            const response = await fetch(`${this.apiBase}/api-keys/${keyId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                await this.loadApiKeys();
                this.showToast(`API key ${enabled ? 'enabled' : 'disabled'}`, 'success');
            } else {
                throw new Error(data.message || 'Failed to toggle API key');
            }
        } catch (error) {
            console.error('Failed to toggle API key:', error);
            this.showToast('Failed to update API key', 'error');
        }
    }

    async deleteApiKey(keyId, keyName) {
        if (!confirm(`Are you sure you want to delete "${keyName}"?\n\nThis action cannot be undone. Any integration using this key will stop working.`)) {
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/api-keys/${keyId}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                await this.loadApiKeys();
                this.showToast('API key deleted successfully', 'success');
            } else {
                throw new Error(data.message || 'Failed to delete API key');
            }
        } catch (error) {
            console.error('Failed to delete API key:', error);
            this.showToast('Failed to delete API key', 'error');
        }
    }
}

// Initialize app
const app = new WebStatusApp();

// ============================================================================
// Navbar Scroll Effect
// ============================================================================

// Handle navbar scroll effect - transparent by default, shows/hides on scroll
const navbar = document.querySelector('.top-nav-bar');
let lastScrollTop = 0;
let scrollTimeout;

function handleScroll() {
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

    // Clear previous timeout
    clearTimeout(scrollTimeout);

    // If at the top, make navbar transparent
    if (scrollTop <= 10) {
        navbar.classList.remove('scrolled');
        navbar.classList.remove('hidden');
    } else {
        // Scrolling down - hide navbar
        if (scrollTop > lastScrollTop && scrollTop > 70) {
            navbar.classList.add('hidden');
            navbar.classList.add('scrolled');
        }
        // Scrolling up - show navbar with solid background
        else if (scrollTop < lastScrollTop) {
            navbar.classList.remove('hidden');
            navbar.classList.add('scrolled');
        }
    }

    lastScrollTop = scrollTop;
}

// Listen to window scroll events
if (navbar) {
    window.addEventListener('scroll', handleScroll);

    // Also check on load in case page is already scrolled
    handleScroll();
}
