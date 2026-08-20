/**
 * Radio Free Luna - Web Interface JavaScript
 * Handles all client-side interactions with the AI DJ system
 */

class RadioFreeLunaUI {
    constructor() {
        this.baseURL = window.location.origin;
        this.apiURL = `${this.baseURL}/api`;
        this.isOnline = false;
        
        this.init();
    }

    init() {
        console.log('🎵 Radio Free Luna UI initializing...');
        
        // Bind event listeners
        this.bindEventListeners();
        
        // Initial system check
        this.checkSystemStatus();
        
        // Set up periodic status updates
        setInterval(() => this.updateSystemStatus(), 30000); // Every 30 seconds
        
        // Load initial context
        this.loadContext();
    }

    bindEventListeners() {
        // Session form (dry-run)
        const sessionForm = document.getElementById('sessionForm');
        if (sessionForm) {
            sessionForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.createSession();
            });
        }

        // Live broadcast controls
        const streamForm = document.getElementById('streamForm');
        if (streamForm) {
            streamForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.startBroadcast();
            });
        }
        const streamStopBtn = document.getElementById('streamStopBtn');
        if (streamStopBtn) {
            streamStopBtn.addEventListener('click', () => this.stopBroadcast());
        }
        const streamSkipBtn = document.getElementById('streamSkipBtn');
        if (streamSkipBtn) {
            streamSkipBtn.addEventListener('click', () => this.skipTrack());
        }

        // Request line
        const requestForm = document.getElementById('requestForm');
        if (requestForm) {
            requestForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.requestSong();
            });
        }

        // Voice testing
        const testVoiceBtn = document.getElementById('testVoiceBtn');
        if (testVoiceBtn) {
            testVoiceBtn.addEventListener('click', () => this.testVoice());
        }

        // Commentary generation
        const generateContextualBtn = document.getElementById('generateContextualBtn');
        if (generateContextualBtn) {
            generateContextualBtn.addEventListener('click', () => this.generateCommentary('contextual'));
        }

        const generateOpeningBtn = document.getElementById('generateOpeningBtn');
        if (generateOpeningBtn) {
            generateOpeningBtn.addEventListener('click', () => this.generateCommentary('opening'));
        }

        // API testing buttons
        const healthCheckBtn = document.getElementById('healthCheckBtn');
        if (healthCheckBtn) {
            healthCheckBtn.addEventListener('click', () => this.healthCheck());
        }

        const systemStatusBtn = document.getElementById('systemStatusBtn');
        if (systemStatusBtn) {
            systemStatusBtn.addEventListener('click', () => this.getSystemStatus());
        }

        const contextCheckBtn = document.getElementById('contextCheckBtn');
        if (contextCheckBtn) {
            contextCheckBtn.addEventListener('click', () => this.loadContext());
        }
    }

    async makeRequest(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Request failed:', error);
            throw error;
        }
    }

    async checkSystemStatus() {
        try {
            const health = await this.makeRequest(`${this.baseURL}/health`);
            
            if (health.status === 'healthy') {
                this.isOnline = true;
                this.updateStatusIndicator('online', 'System Online');
                await this.updateComponentStatus();
            } else {
                this.isOnline = false;
                this.updateStatusIndicator('offline', 'System Offline');
            }
        } catch (error) {
            this.isOnline = false;
            this.updateStatusIndicator('offline', 'Connection Failed');
            console.error('Health check failed:', error);
        }
    }

    async updateComponentStatus() {
        try {
            const status = await this.makeRequest(`${this.baseURL}/status`);
            
            // Update AI status
            const aiStatus = status.ai_systems?.analysis_engine ? 'Online' : 'Offline';
            this.updateStatusField('aiStatus', aiStatus, status.ai_systems?.analysis_engine);

            // Update voice status
            const voiceStatus = status.ai_systems?.voice_synthesis ? 'Online' : 'Offline';
            this.updateStatusField('voiceStatus', voiceStatus, status.ai_systems?.voice_synthesis);

            // Update context status
            const contextStatus = status.context?.description ? 'Active' : 'Inactive';
            this.updateStatusField('contextStatus', contextStatus, !!status.context?.description);

            // Update music library status
            const musicStatus = status.music_library?.monitoring ? 'Monitoring' : 'Not Monitoring';
            this.updateStatusField('musicStatus', musicStatus, status.music_library?.monitoring);

        } catch (error) {
            console.error('Component status update failed:', error);
            this.updateStatusField('aiStatus', 'Unknown', false);
            this.updateStatusField('voiceStatus', 'Unknown', false);
            this.updateStatusField('contextStatus', 'Unknown', false);
            this.updateStatusField('musicStatus', 'Unknown', false);
        }
    }

    updateStatusField(fieldId, text, isOnline) {
        const field = document.getElementById(fieldId);
        if (field) {
            field.textContent = text;
            field.className = isOnline ? 'status-online' : 'status-offline';
        }
    }

    updateStatusIndicator(status, text) {
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        
        if (statusDot) {
            statusDot.className = `status-dot ${status}`;
        }
        
        if (statusText) {
            statusText.textContent = text;
        }
    }

    async updateSystemStatus() {
        if (this.isOnline) {
            await this.updateComponentStatus();
        } else {
            await this.checkSystemStatus();
        }
    }

    async loadContext() {
        try {
            const contextContent = document.getElementById('contextContent');
            if (contextContent) {
                contextContent.innerHTML = '<p class="loading">Loading context...</p>';
            }

            const context = await this.makeRequest(`${this.apiURL}/context`);
            
            if (context.error) {
                if (contextContent) {
                    contextContent.innerHTML = `
                        <div class="result-error">
                            <strong>Context Error:</strong> ${context.error}
                            <p style="margin-top: 10px; font-size: 0.9em;">
                                This is expected if the system is not fully configured with API keys and music library.
                            </p>
                        </div>
                    `;
                }
                return;
            }

            if (contextContent) {
                const themesHTML = context.themes && context.themes.length > 0 
                    ? context.themes.map(theme => `<span class="theme-tag">${theme}</span>`).join('')
                    : '<span class="theme-tag">No specific themes</span>';

                contextContent.innerHTML = `
                    <div class="result-success">
                        <p><strong>Description:</strong> ${context.description || 'No description available'}</p>
                        <div class="context-themes">
                            <strong>Current Themes:</strong><br>
                            ${themesHTML}
                        </div>
                        <p><strong>Music Guidance:</strong> ${context.music_guidance?.mood_preference || 'No guidance available'}</p>
                        <p style="font-size: 0.9em; margin-top: 10px;">
                            <strong>Last Updated:</strong> ${context.updated_at ? new Date(context.updated_at).toLocaleString() : 'Unknown'}
                        </p>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Failed to load context:', error);
            const contextContent = document.getElementById('contextContent');
            if (contextContent) {
                contextContent.innerHTML = `
                    <div class="result-error">
                        <strong>Error:</strong> Failed to load context information.
                        <p style="margin-top: 10px; font-size: 0.9em;">
                            ${error.message}
                        </p>
                    </div>
                `;
            }
        }
    }

    async createSession() {
        const theme = document.getElementById('sessionTheme')?.value || 'contextual';
        const duration = parseInt(document.getElementById('sessionDuration')?.value) || 60;
        const resultDiv = document.getElementById('sessionResult');
        
        if (resultDiv) {
            resultDiv.className = 'session-result show loading';
            resultDiv.innerHTML = '<p>Creating session...</p>';
        }

        try {
            const session = await this.makeRequest(`${this.apiURL}/sessions?theme=${theme}&duration_minutes=${duration}`, {
                method: 'POST'
            });

            if (session.error) {
                if (resultDiv) {
                    resultDiv.className = 'session-result show result-error';
                    resultDiv.innerHTML = `
                        <strong>Session Creation Failed:</strong> ${session.error}
                        <p style="margin-top: 10px; font-size: 0.9em;">
                            This may be expected if the music library is empty or AI services are not configured.
                        </p>
                    `;
                }
                return;
            }

            if (resultDiv) {
                resultDiv.className = 'session-result show result-success';
                resultDiv.innerHTML = `
                    <strong>Session Created Successfully!</strong>
                    <p><strong>Session ID:</strong> ${session.session_id}</p>
                    <p><strong>Theme:</strong> ${session.theme}</p>
                    <p><strong>Status:</strong> ${session.status}</p>
                    <p><strong>Tracks:</strong> ${session.track_count}</p>
                    <p><strong>Duration:</strong> ${Math.round(session.estimated_duration / 60)} minutes</p>
                    <p style="margin-top: 10px; font-size: 0.9em;">
                        <strong>Context:</strong> ${session.context}
                    </p>
                `;
            }
        } catch (error) {
            console.error('Session creation failed:', error);
            if (resultDiv) {
                resultDiv.className = 'session-result show result-error';
                resultDiv.innerHTML = `
                    <strong>Error:</strong> ${error.message}
                    <p style="margin-top: 10px; font-size: 0.9em;">
                        Make sure the system is properly configured and running.
                    </p>
                `;
            }
        }
    }

    async testVoice() {
        const text = document.getElementById('voiceText')?.value || 'Hello from Radio Free Luna';
        const resultDiv = document.getElementById('voiceResult');
        const testBtn = document.getElementById('testVoiceBtn');
        
        if (testBtn) testBtn.disabled = true;
        
        if (resultDiv) {
            resultDiv.className = 'voice-result show loading';
            resultDiv.innerHTML = '<p>Generating voice...</p>';
        }

        try {
            const result = await this.makeRequest(`${this.apiURL}/test-voice`, {
                method: 'POST',
                body: JSON.stringify({ text })
            });

            if (result.status === 'success') {
                if (resultDiv) {
                    resultDiv.className = 'voice-result show result-success';
                    resultDiv.innerHTML = `
                        <strong>Voice Synthesis Successful!</strong>
                        <p>Audio generated successfully (${result.audio_length} bytes)</p>
                        <p style="margin-top: 10px; font-size: 0.9em;">
                            Note: Audio playback not implemented in this test interface.
                        </p>
                    `;
                }
            } else {
                if (resultDiv) {
                    resultDiv.className = 'voice-result show result-error';
                    resultDiv.innerHTML = `
                        <strong>Voice Synthesis Failed:</strong> ${result.message}
                        <p style="margin-top: 10px; font-size: 0.9em;">
                            This is expected if TTS-WebUI is not running or configured.
                        </p>
                    `;
                }
            }
        } catch (error) {
            console.error('Voice test failed:', error);
            if (resultDiv) {
                resultDiv.className = 'voice-result show result-error';
                resultDiv.innerHTML = `
                    <strong>Error:</strong> ${error.message}
                    <p style="margin-top: 10px; font-size: 0.9em;">
                        Check if TTS-WebUI is running on the configured port.
                    </p>
                `;
            }
        } finally {
            if (testBtn) testBtn.disabled = false;
        }
    }

    async generateCommentary(type = 'contextual') {
        const resultDiv = document.getElementById('commentaryResult');
        const btn = type === 'contextual' 
            ? document.getElementById('generateContextualBtn')
            : document.getElementById('generateOpeningBtn');
        
        if (btn) btn.disabled = true;
        
        if (resultDiv) {
            resultDiv.className = 'commentary-result show loading';
            resultDiv.innerHTML = '<p>Generating commentary...</p>';
        }

        try {
            const commentary = await this.makeRequest(`${this.apiURL}/commentary`, {
                method: 'POST',
                body: JSON.stringify({ text_type: type })
            });

            if (commentary.error) {
                if (resultDiv) {
                    resultDiv.className = 'commentary-result show result-error';
                    resultDiv.innerHTML = `
                        <strong>Commentary Generation Failed:</strong> ${commentary.error}
                        <p style="margin-top: 10px; font-size: 0.9em;">
                            This may be expected if OpenAI API is not configured or context is unavailable.
                        </p>
                    `;
                }
                return;
            }

            if (resultDiv) {
                resultDiv.className = 'commentary-result show result-success';
                resultDiv.innerHTML = `
                    <strong>${type === 'contextual' ? 'Contextual' : 'Opening'} Commentary Generated!</strong>
                    <div class="commentary-content">
                        "${commentary.content}"
                    </div>
                    <p><strong>Type:</strong> ${commentary.type}</p>
                    <p><strong>Duration:</strong> ~${commentary.duration_estimate} seconds</p>
                    <p style="margin-top: 10px; font-size: 0.9em;">
                        <strong>Context:</strong> ${commentary.context}
                    </p>
                `;
            }
        } catch (error) {
            console.error('Commentary generation failed:', error);
            if (resultDiv) {
                resultDiv.className = 'commentary-result show result-error';
                resultDiv.innerHTML = `
                    <strong>Error:</strong> ${error.message}
                    <p style="margin-top: 10px; font-size: 0.9em;">
                        Make sure OpenAI API is configured and the system is running.
                    </p>
                `;
            }
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async startBroadcast() {
        const theme = document.getElementById('streamTheme')?.value || 'contextual';
        const duration = parseInt(document.getElementById('streamDuration')?.value) || 30;
        const resultDiv = document.getElementById('streamResult');
        const audioEl = document.getElementById('streamAudio');
        const startBtn = document.getElementById('streamStartBtn');

        if (startBtn) startBtn.disabled = true;
        if (resultDiv) {
            resultDiv.className = 'session-result show loading';
            resultDiv.innerHTML = '<p>Starting broadcast (loading tracks)...</p>';
        }

        try {
            const info = await this.makeRequest(`${this.apiURL}/streaming/start`, {
                method: 'POST',
                body: JSON.stringify({ theme, duration_minutes: duration })
            });

            if (info.error) {
                if (resultDiv) {
                    resultDiv.className = 'session-result show result-error';
                    resultDiv.innerHTML = `<strong>Failed to start broadcast:</strong> ${info.error}${info.detail ? '<br>' + info.detail : ''}`;
                }
                return;
            }

            if (resultDiv) {
                resultDiv.className = 'session-result show result-success';
                resultDiv.innerHTML = `
                    <strong>Broadcasting!</strong>
                    <p><strong>Session:</strong> ${info.session_id}</p>
                    <p><strong>Theme:</strong> ${info.theme}</p>
                    <p><strong>Tracks:</strong> ${info.track_count}</p>
                    <p><strong>Estimated:</strong> ${Math.round((info.estimated_duration || 0) / 60)} minutes</p>
                `;
            }

            if (audioEl) {
                audioEl.src = `${this.baseURL}/stream.mp3?t=${Date.now()}`;
                try {
                    await audioEl.play();
                } catch (e) {
                    console.warn('Autoplay blocked; user must press play on the audio element.', e);
                }
            }

            this.startNowPlayingUpdates();
        } catch (error) {
            console.error('Broadcast start failed:', error);
            if (resultDiv) {
                resultDiv.className = 'session-result show result-error';
                resultDiv.innerHTML = `<strong>Error:</strong> ${error.message}`;
            }
        } finally {
            if (startBtn) startBtn.disabled = false;
        }
    }

    async stopBroadcast() {
        const audioEl = document.getElementById('streamAudio');
        const resultDiv = document.getElementById('streamResult');
        try {
            const result = await this.makeRequest(`${this.apiURL}/streaming/stop`, { method: 'POST' });
            this.stopNowPlayingUpdates();
            if (audioEl) {
                audioEl.pause();
                audioEl.removeAttribute('src');
                audioEl.load();
            }
            if (resultDiv) {
                resultDiv.className = 'session-result show result-info';
                resultDiv.innerHTML = `<strong>Broadcast stopped.</strong> ${result.session_id ? '(' + result.session_id + ')' : ''}`;
            }
        } catch (error) {
            console.error('Broadcast stop failed:', error);
            if (resultDiv) {
                resultDiv.className = 'session-result show result-error';
                resultDiv.innerHTML = `<strong>Stop error:</strong> ${error.message}`;
            }
        }
    }

    async requestSong() {
        const query = document.getElementById('requestQuery')?.value?.trim();
        const requested_by = document.getElementById('requestName')?.value?.trim() || null;
        const resultDiv = document.getElementById('requestResult');
        const btn = document.getElementById('requestBtn');

        if (!query) return;
        if (btn) btn.disabled = true;
        if (resultDiv) {
            resultDiv.className = 'session-result show loading';
            resultDiv.innerHTML = '<p>Calling in your request...</p>';
        }

        try {
            const result = await this.makeRequest(`${this.apiURL}/requests`, {
                method: 'POST',
                body: JSON.stringify({ query, requested_by })
            });

            if (result.error || !result.queued) {
                if (resultDiv) {
                    resultDiv.className = 'session-result show result-error';
                    const matches = (result.matches || [])
                        .map(m => `${m.title} — ${m.artist}`).join('<br>');
                    resultDiv.innerHTML = `
                        <strong>Request not queued:</strong> ${result.error || 'Unknown error'}
                        ${matches ? '<p style="margin-top: 10px; font-size: 0.9em;"><strong>Closest matches:</strong><br>' + matches + '</p>' : ''}
                    `;
                }
                return;
            }

            if (resultDiv) {
                resultDiv.className = 'session-result show result-success';
                resultDiv.innerHTML = `
                    <strong>Request queued!</strong>
                    <p><strong>Coming up:</strong> ${result.track.title} — ${result.track.artist}</p>
                    <p><strong>Queue position:</strong> ${result.position_in_queue}</p>
                    ${result.acknowledgment ? `<div class="commentary-content">"${result.acknowledgment}"</div>` : ''}
                `;
            }
            const queryEl = document.getElementById('requestQuery');
            if (queryEl) queryEl.value = '';
        } catch (error) {
            console.error('Request failed:', error);
            if (resultDiv) {
                resultDiv.className = 'session-result show result-error';
                resultDiv.innerHTML = `<strong>Error:</strong> ${error.message}`;
            }
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async skipTrack() {
        const resultDiv = document.getElementById('streamResult');
        try {
            const result = await this.makeRequest(`${this.apiURL}/streaming/skip`, { method: 'POST' });
            if (resultDiv) {
                resultDiv.className = 'session-result show result-info';
                resultDiv.innerHTML = `<strong>Skip:</strong> ${result.skipped ? 'queued' : 'no active session'}`;
            }
        } catch (error) {
            console.error('Skip failed:', error);
        }
    }

    startNowPlayingUpdates() {
        this.stopNowPlayingUpdates();
        this.updateNowPlaying();
        this.nowPlayingTimer = setInterval(() => this.updateNowPlaying(), 5000);
    }

    stopNowPlayingUpdates() {
        if (this.nowPlayingTimer) {
            clearInterval(this.nowPlayingTimer);
            this.nowPlayingTimer = null;
        }
        const panel = document.getElementById('nowPlaying');
        if (panel) panel.style.display = 'none';
    }

    async updateNowPlaying() {
        const panel = document.getElementById('nowPlaying');
        if (!panel) return;

        try {
            const status = await this.makeRequest(`${this.apiURL}/streaming/status`);

            if (!status.active || !status.current_track) {
                if (!status.active) this.stopNowPlayingUpdates();
                return;
            }

            const track = status.current_track;
            panel.style.display = 'block';
            document.getElementById('nowPlayingTitle').textContent =
                `${track.title} — ${track.artist}` +
                (track.requested_by ? ` (for ${track.requested_by})` : '');

            const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
            document.getElementById('nowPlayingMeta').textContent =
                `Track ${status.track_index + 1} of ${status.total_tracks} · ` +
                `${fmt(Math.min(track.elapsed, track.duration))} / ${fmt(track.duration)} · ` +
                `${status.listener_count} listener${status.listener_count === 1 ? '' : 's'}`;

            const pct = track.duration > 0
                ? Math.min(100, (track.elapsed / track.duration) * 100)
                : 0;
            document.getElementById('nowPlayingProgress').style.width = `${pct}%`;
        } catch (error) {
            console.warn('Now-playing update failed:', error);
        }
    }

    async healthCheck() {
        const resultDiv = document.getElementById('apiResult');
        
        if (resultDiv) {
            resultDiv.className = 'api-result show loading';
            resultDiv.innerHTML = '<p>Checking health...</p>';
        }

        try {
            const health = await this.makeRequest(`${this.baseURL}/health`);
            
            if (resultDiv) {
                resultDiv.className = 'api-result show result-success';
                resultDiv.innerHTML = `
                    <strong>Health Check Result:</strong>
                    <pre>${JSON.stringify(health, null, 2)}</pre>
                `;
            }
        } catch (error) {
            if (resultDiv) {
                resultDiv.className = 'api-result show result-error';
                resultDiv.innerHTML = `
                    <strong>Health Check Failed:</strong> ${error.message}
                `;
            }
        }
    }

    async getSystemStatus() {
        const resultDiv = document.getElementById('apiResult');
        
        if (resultDiv) {
            resultDiv.className = 'api-result show loading';
            resultDiv.innerHTML = '<p>Getting system status...</p>';
        }

        try {
            const status = await this.makeRequest(`${this.baseURL}/status`);
            
            if (resultDiv) {
                resultDiv.className = 'api-result show result-info';
                resultDiv.innerHTML = `
                    <strong>System Status:</strong>
                    <pre>${JSON.stringify(status, null, 2)}</pre>
                `;
            }
        } catch (error) {
            if (resultDiv) {
                resultDiv.className = 'api-result show result-error';
                resultDiv.innerHTML = `
                    <strong>System Status Failed:</strong> ${error.message}
                `;
            }
        }
    }

    // Utility methods
    formatTimestamp(timestamp) {
        if (!timestamp) return 'Unknown';
        return new Date(timestamp).toLocaleString();
    }

    showNotification(message, type = 'info') {
        // Simple notification system
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 5000);
    }
}

// CSS for status indicators
const additionalCSS = `
.status-online {
    color: var(--success-color);
    font-weight: 600;
}

.status-offline {
    color: var(--danger-color);
    font-weight: 600;
}

.notification {
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 15px 20px;
    border-radius: var(--border-radius);
    color: white;
    font-weight: 500;
    z-index: 1000;
    min-width: 250px;
    box-shadow: var(--shadow-medium);
}

.notification-info {
    background: var(--secondary-color);
}

.notification-success {
    background: var(--success-color);
}

.notification-error {
    background: var(--danger-color);
}
`;

// Add additional CSS
const style = document.createElement('style');
style.textContent = additionalCSS;
document.head.appendChild(style);

// Initialize the UI when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.radioFreeLuna = new RadioFreeLunaUI();
});

// Handle page visibility changes to pause/resume updates
document.addEventListener('visibilitychange', () => {
    if (window.radioFreeLuna) {
        if (document.hidden) {
            console.log('Page hidden - pausing updates');
        } else {
            console.log('Page visible - resuming updates');
            window.radioFreeLuna.checkSystemStatus();
        }
    }
});