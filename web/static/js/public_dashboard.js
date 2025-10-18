/**
 * Public Dashboard JavaScript
 * Handles data fetching, rendering, and interactions for the public dashboard
 */

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Format date/time to readable format
 */
function formatDateTime(isoString) {
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

/**
 * Format relative time (e.g., "5m", "3h 15m", "2d 5h")
 */
function formatRelativeTime(isoString) {
    if (!isoString) return '--';
    try {
        const date = new Date(isoString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        const diffMonths = Math.floor(diffDays / 30);
        const diffYears = Math.floor(diffDays / 365);

        // Less than 1 minute
        if (diffMins < 1) return 'now';

        // Less than 1 hour - show minutes only
        if (diffMins < 60) return `${diffMins}m`;

        // Less than 24 hours - show hours and minutes
        if (diffHours < 24) {
            const mins = diffMins % 60;
            return mins > 0 ? `${diffHours}h ${mins}m` : `${diffHours}h`;
        }

        // Less than 30 days - show days and hours
        if (diffDays < 30) {
            const hours = diffHours % 24;
            return hours > 0 ? `${diffDays}d ${hours}h` : `${diffDays}d`;
        }

        // Less than 1 year - show months and days
        if (diffDays < 365) {
            const days = diffDays % 30;
            return days > 0 ? `${diffMonths}mo ${days}d` : `${diffMonths}mo`;
        }

        // 1 year or more - show years and months
        const months = diffMonths % 12;
        return months > 0 ? `${diffYears}y ${months}mo` : `${diffYears}y`;
    } catch (e) {
        return '--';
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show error message
 */
function showError(container, message) {
    container.innerHTML = `
        <div class="loading-placeholder">
            <p style="color: var(--danger);">${escapeHtml(message)}</p>
        </div>
    `;
}

// ============================================================================
// Dashboard Tab - Render Target Cards
// ============================================================================

/**
 * Render the dashboard grid with target cards
 */
function renderDashboard(data) {
    const container = document.getElementById('targetsGrid');

    if (!data.services || data.services.length === 0) {
        container.innerHTML = `
            <div class="no-services-message">
                <p>No services are currently being monitored.</p>
            </div>
        `;
        return;
    }

    const cards = data.services.map(service => {
        const statusClass = service.status === 'up' ? 'status-up' : 'status-down';
        const statusText = service.status === 'up' ? 'Operational' : 'Down';
        const uptime = service.uptime_percentage || 0;

        return `
            <div class="target-card ${statusClass}">
                <div class="target-header">
                    <h3 class="target-name">${escapeHtml(service.name)}</h3>
                    <span class="target-status-badge ${statusClass}">${statusText}</span>
                </div>
                <div class="target-metrics">
                    <span class="metric-value">${uptime.toFixed(0)}% <span class="metric-label-inline">(24h)</span></span>
                    <span class="metric-value">
                        <span class="status-arrow ${statusClass}">▲</span>
                        ${service.last_status_change ? formatRelativeTime(service.last_status_change) : '--'}
                    </span>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = cards;
}

// ============================================================================
// Timeline Tab - Render Uptime History
// ============================================================================

/**
 * Render the timeline view with uptime history
 */
function renderTimeline(historyData) {
    const container = document.getElementById('timelineGrid');

    if (!historyData || historyData.length === 0) {
        container.innerHTML = `
            <div class="no-services-message">
                <p>No timeline data available.</p>
            </div>
        `;
        return;
    }

    const rows = historyData.map(target => {
        const uptime = target.uptime_percentage || 0;

        // Generate timeline bars from history
        let bars = '';
        let currentStatus = 'unknown';
        if (target.history && target.history.length > 0) {
            bars = target.history.map(point => {
                const status = point.status || 'unknown';
                const tooltip = `${formatDateTime(point.timestamp)} - ${status}`;
                return `<div class="timeline-bar status-${status}" title="${tooltip}"></div>`;
            }).join('');
            // Get the most recent status from buckets that have data (checks_count > 0)
            // Iterate backwards to find the last bucket with actual data
            for (let i = target.history.length - 1; i >= 0; i--) {
                if (target.history[i].checks_count > 0) {
                    currentStatus = target.history[i].status || 'unknown';
                    console.log(`Found status for ${target.name}: ${currentStatus} (checks: ${target.history[i].checks_count})`);
                    break;
                }
            }
            if (currentStatus === 'unknown') {
                console.log(`No data found for ${target.name}, defaulting to unknown`);
            }
        } else {
            // No history data available - show placeholder
            bars = '<div class="timeline-bar status-unknown" style="flex: 1;"></div>';
        }

        // Show only the current status badge
        const statusBadge = currentStatus === 'up'
            ? '<span class="target-status-badge status-up">UP</span>'
            : currentStatus === 'down'
            ? '<span class="target-status-badge status-down">DOWN</span>'
            : '<span class="target-status-badge status-unknown">UNKNOWN</span>';

        return `
            <div class="timeline-row">
                <div class="timeline-header">
                    <h3 class="timeline-target-name">${escapeHtml(target.name)}</h3>
                    <span class="timeline-uptime">${uptime.toFixed(2)}%</span>
                </div>
                <div class="timeline-chart">
                    ${bars}
                </div>
                <div class="timeline-legend">
                    ${statusBadge}
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = rows;
}

// ============================================================================
// Overall Status Indicator
// ============================================================================

/**
 * Render overall status indicator
 */
function renderOverallStatus(data) {
    const container = document.getElementById('overallStatus');
    const statusMap = {
        'operational': {
            text: 'All Systems Operational',
            class: 'operational',
            icon: '✓'
        },
        'partial_outage': {
            text: 'Partial System Outage',
            class: 'degraded',
            icon: '!'
        },
        'major_outage': {
            text: 'Major System Outage',
            class: 'down',
            icon: '×'
        },
        'no_data': {
            text: 'No Data Available',
            class: 'loading',
            icon: '?'
        }
    };

    const status = statusMap[data.overall_status] || statusMap['no_data'];

    container.innerHTML = `
        <div class="status-indicator ${status.class}">
            <span class="status-dot">${status.icon}</span>
            <span class="status-text">${status.text}</span>
        </div>
    `;
}

// ============================================================================
// API Data Fetching
// ============================================================================

/**
 * Load status data from API
 */
async function loadStatus() {
    try {
        const response = await fetch(STATUS_API);

        if (!response.ok) {
            if (response.status === 429) {
                showError(
                    document.getElementById('targetsGrid'),
                    'Rate limit exceeded. Please wait before refreshing.'
                );
                stopAutoRefresh();
                return null;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Update overall status
        renderOverallStatus(data);

        // Update timestamp
        document.getElementById('lastUpdated').textContent = formatDateTime(data.last_updated);

        return data;

    } catch (error) {
        console.error('Error loading status:', error);
        showError(
            document.getElementById('targetsGrid'),
            'Unable to load status. Retrying...'
        );
        return null;
    }
}

/**
 * Load history data from API
 */
async function loadHistory(range = '24h') {
    try {
        const response = await fetch(`${HISTORY_API}?range=${range}`);

        if (!response.ok) {
            if (response.status === 429) {
                showError(
                    document.getElementById('timelineGrid'),
                    'Rate limit exceeded. Please wait before refreshing.'
                );
                return null;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        return data.targets || [];

    } catch (error) {
        console.error('Error loading history:', error);
        showError(
            document.getElementById('timelineGrid'),
            'Unable to load timeline. Retrying...'
        );
        return null;
    }
}

/**
 * Update the current active tab's data
 */
async function updateCurrentTab() {
    if (currentTab === 'dashboard') {
        const data = await loadStatus();
        if (data) {
            renderDashboard(data);
        }
    } else if (currentTab === 'timeline') {
        const historyData = await loadHistory(currentRange);
        if (historyData) {
            renderTimeline(historyData);
        }
    }
}

// ============================================================================
// Auto-refresh
// ============================================================================

/**
 * Start auto-refresh
 */
function startAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
    }
    refreshTimer = setInterval(updateCurrentTab, REFRESH_INTERVAL);
}

/**
 * Stop auto-refresh
 */
function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

/**
 * Handle visibility change (pause refresh when tab hidden)
 */
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        updateCurrentTab();
        startAutoRefresh();
    }
});

// ============================================================================
// Tab Switching
// ============================================================================

/**
 * Switch between tabs
 */
function switchTab(tabName) {
    currentTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        }
    });

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });

    if (tabName === 'dashboard') {
        document.getElementById('dashboardTab').classList.add('active');
    } else if (tabName === 'timeline') {
        document.getElementById('timelineTab').classList.add('active');
    }

    // Load data for the new tab
    updateCurrentTab();
}

/**
 * Change timeline range
 */
async function changeTimelineRange(range) {
    currentRange = range;

    // Update filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.range === range) {
            btn.classList.add('active');
        }
    });

    // Reload timeline data
    const historyData = await loadHistory(range);
    if (historyData) {
        renderTimeline(historyData);
    }
}

// ============================================================================
// Event Listeners
// ============================================================================

/**
 * Initialize event listeners
 */
function initializeEventListeners() {
    // Tab switching
    document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            switchTab(btn.dataset.tab);
        });
    });

    // Timeline range filters
    document.querySelectorAll('.filter-btn[data-range]').forEach(btn => {
        btn.addEventListener('click', () => {
            changeTimelineRange(btn.dataset.range);
        });
    });
}

// ============================================================================
// Audio Enable Handling
// ============================================================================

let audioEnabled = false;

/**
 * Enable audio alerts and hide the overlay
 */
function enableAudio() {
    audioEnabled = true;

    // Create a silent audio context to satisfy browser autoplay policies
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        audioContext.resume().then(() => {
            console.log('Audio context initialized and resumed');
        });
    } catch (e) {
        console.warn('Could not initialize audio context:', e);
    }

    // Hide the overlay with fade out animation
    const overlay = document.getElementById('audioEnableOverlay');
    overlay.style.animation = 'fadeOut 0.3s ease';

    setTimeout(() => {
        overlay.classList.add('hidden');
    }, 300);

    // Store preference in sessionStorage
    sessionStorage.setItem('audioEnabled', 'true');

    console.log('Audio alerts enabled');
}

/**
 * Check if audio was already enabled in this session
 */
function checkAudioEnabled() {
    const wasEnabled = sessionStorage.getItem('audioEnabled') === 'true';
    if (wasEnabled) {
        audioEnabled = true;
        document.getElementById('audioEnableOverlay').classList.add('hidden');
    }
}

// ============================================================================
// Initialization
// ============================================================================

/**
 * Initialize the dashboard
 */
async function initialize() {
    console.log('Public Dashboard initializing...');

    // Check if audio was already enabled
    checkAudioEnabled();

    // Set up audio enable overlay
    const enableAudioBtn = document.getElementById('enableAudioBtn');
    const overlay = document.getElementById('audioEnableOverlay');

    // Enable audio when button is clicked
    enableAudioBtn.addEventListener('click', enableAudio);

    // Also enable audio when clicking anywhere on the overlay
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            enableAudio();
        }
    });

    // Set up event listeners
    initializeEventListeners();

    // Load initial data based on current tab
    await updateCurrentTab();

    // Start auto-refresh
    startAutoRefresh();

    console.log('Public Dashboard initialized successfully');
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded', initialize);
