/**
 * updater.js - Professional update dialogs for WorkTre
 * USING MESSAGE QUEUE PATTERN
 */

 // Check if main.js functions are available
console.log('🔍 updater.js loaded, checking for main.js functions:');
setTimeout(() => {
    console.log('🔍 window.showInactivityWarningModal:', typeof window.showInactivityWarningModal);
    console.log('🔍 window.inactivityTimeExceed:', typeof window.inactivityTimeExceed);
    console.log('🔍 window.autoFillCredentials:', typeof window.autoFillCredentials);

    if (typeof window.showInactivityWarningModal !== 'function') {
        console.error('❌ showInactivityWarningModal not found - check script loading order');
    }
}, 500);

// Store the current modal reference
let currentUpdateModal = null;
let progressPollingInterval = null;
let messagePollingInterval = null;

/**
 * Initialize message polling
 */
function initMessagePolling() {
    if (messagePollingInterval) {
        clearInterval(messagePollingInterval);
    }

    messagePollingInterval = setInterval(() => {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.get_messages()
                .then(messages => {
                    messages.forEach(processMessage);
                })
                .catch(error => {
                    console.error('Message polling error:', error);
                });
        }
    }, 1000); // Poll every second
}

/**
 * Process incoming messages from Python
 */
function processMessage(message) {
    console.log('📨 Received message:', message);

    switch(message.type) {
        case 'update_available':
            showUpdateAvailableModal(message.data);
            break;
        case 'auto_fill_credentials':
            if (typeof window.autoFillCredentials === 'function') {
                window.autoFillCredentials(message.data);
            } else {
                console.error('❌ autoFillCredentials not found in window object');
            }
            break;
        case 'inactivity_warning':
            console.log('⏰ Inactivity warning received, forwarding to main app');
            console.log('🔍 Checking if showInactivityWarningModal exists:', typeof window.showInactivityWarningModal);

            if (typeof window.showInactivityWarningModal === 'function') {
                console.log('✅ Calling window.showInactivityWarningModal()');
                window.showInactivityWarningModal();
            } else {
                console.error('❌ showInactivityWarningModal not found in window object');
                console.log('🔍 Available window functions:', Object.keys(window).filter(key =>
                    typeof window[key] === 'function' && key.includes('Inactivity')
                ));
            }
            break;
        case 'inactivity_logout':
            if (typeof window.inactivityTimeExceed === 'function') {
                window.inactivityTimeExceed();
            } else {
                console.error('❌ inactivityTimeExceed not found in window object');
            }
            break;
        case 'network_online':
            console.log('Network online');
            if (typeof window.handleNetworkOnline === 'function') {
                window.handleNetworkOnline();
            }
            break;
        case 'network_offline':
            console.log('Network offline');
            if (typeof window.handleNetworkOffline === 'function') {
                window.handleNetworkOffline();
            }
            break;
        case 'disconnect_logout':
            console.log('Disconnect logout message received');
            if (typeof window.onInternetDisconnectedTimeExceed === 'function') {
                window.onInternetDisconnectedTimeExceed();
            }
            break;
    }
}

/**
 * Show the update available modal
 */
function showUpdateAvailableModal(versionInfo) {
    console.log('📢 showUpdateAvailableModal called with:', versionInfo);

    const { latestVersion, currentVersion, downloadUrl, releaseNotes } = versionInfo;

    // Remove existing modal if present
    if (currentUpdateModal && document.body.contains(currentUpdateModal)) {
        document.body.removeChild(currentUpdateModal);
        currentUpdateModal = null;
    }

    // Create modal
    const modal = document.createElement('div');
    modal.id = 'updateModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    `;

    const dialog = document.createElement('div');
    dialog.style.cssText = `
        background: linear-gradient(135deg, rgb(1 167 141) 0%, rgb(0 47 52) 100%);
        padding: 2px;
        border-radius: 12px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
        max-width: 500px;
        width: 90%;
        overflow: hidden;
    `;

    const content = document.createElement('div');
    content.style.cssText = `
        background: white;
        padding: 25px 40px;
        border-radius: 10px;
        text-align: center;
    `;

    const notes = releaseNotes ?
        releaseNotes.split('\n').map(line => `<li>${line}</li>`).join('') :
        `
        <li>Performance improvements</li>
        <li>Bug fixes and stability enhancements</li>
        <li>New features and optimizations</li>
        `;

    content.innerHTML = `
        <!-- WorkTre Logo -->
        <div style="margin-bottom: 25px;">
            <img alt="WorkTre Logo" src="../assets/images/logo.png" style="width: 50%;">
        </div>

        <!-- Title -->
        <h2 style="margin: 0 0 15px 0; color: #1ea88e; font-size: 21px; font-weight: 600;">
            Update Available
        </h2>

        <!-- Description -->
        <p style="margin: 0 0 25px 0; color: #5d6d7e; font-size: 14px; line-height: 1.5;">
            A new version is ready for installation
        </p>

        <!-- Version Info Box -->
        <div style="
            background: #f8f9fa;
            border-radius: 8px;
            padding: 12px;
            margin: 25px 0;
            text-align: left;
            border-left: 4px solid #1ca990;
            font-size: 14px;
        ">
            <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                <span style="color: #5d6d7e; font-weight: 500;">Current Version:</span>
                <span style="color: #e74c3c; font-weight: 600;">v${currentVersion}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
                <span style="color: #5d6d7e; font-weight: 500;">Latest Version:</span>
                <span style="color: #27ae60; font-weight: 600;">v${latestVersion}</span>
            </div>
        </div>

        <!-- Update Notes -->
        <div style="
            background: #f0f7ff;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            text-align: left;
            border: 1px solid #d1e3ff;
        ">
            <div style="color: #1fa88f; font-weight: 600; margin-bottom: 8px;">
                What's New:
            </div>
            <ul style="
                margin: 0;
                padding-left: 20px;
                color: #5d6d7e;
                font-size: 14px;
                line-height: 1.5;
            ">
                ${notes}
            </ul>
        </div>

        <!-- Buttons -->
        <div style="margin-top: 30px; display: flex; gap: 15px;">
            <button id="updateNow" style="
                flex: 1;
                background: linear-gradient(135deg, #032d35 0%, #1ea892 100%);
                color: white;
                border: none;
                padding: 12px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            ">
                <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                        <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                    </svg>
                    Update Now
                </div>
            </button>

            <button id="updateLater" style="
                flex: 1;
                background: transparent;
                color: #1baa90;
                border: 2px solid #1baa90;
                padding: 10px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.3s ease;
            ">
                Later
            </button>
        </div>

        <!-- Footer Note -->
        <div style="margin-top: 25px; color: #95a5a6; font-size: 12px;">
            The app will restart automatically after installation
        </div>
    `;

    dialog.appendChild(content);
    modal.appendChild(dialog);
    document.body.appendChild(modal);
    currentUpdateModal = modal;

    // Handle Update Now button
    document.getElementById('updateNow').onclick = function() {
        console.log('🖱️ Update Now button clicked');
        this.disabled = true;
        this.style.opacity = '0.6';

        // Transform to download view
        showDownloadProgressModal(downloadUrl, latestVersion);

        // Start the download
        startDownload(downloadUrl, latestVersion);
    };

    // Handle Later button
    document.getElementById('updateLater').onclick = function() {
        console.log('🖱️ Update Later button clicked');
        closeUpdateModal();
    };
}

/**
 * Start the download process
 */
function startDownload(url, version) {
    console.log('📥 Starting download...');

    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.downloadUpdate(url, version)
            .then(result => {
                console.log('Download started:', result);
                if (result.status) {
                    // Start polling for progress
                    startProgressPolling();
                } else {
                    showUpdateErrorModal('Failed to start download: ' + result.message);
                }
            })
            .catch(error => {
                console.error('Download error:', error);
                showUpdateErrorModal('Failed to start download: ' + error);
            });
    } else {
        showUpdateErrorModal('Application backend not available');
    }
}

/**
 * Start polling for download progress
 */
function startProgressPolling() {
    if (progressPollingInterval) {
        clearInterval(progressPollingInterval);
    }

    progressPollingInterval = setInterval(() => {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.get_download_status()
                .then(status => {
                    updateDownloadProgress(status.progress);

                    if (status.error) {
                        clearInterval(progressPollingInterval);
                        showUpdateErrorModal(status.error);
                    }

                    if (status.progress >= 100) {
                        clearInterval(progressPollingInterval);
                    }
                })
                .catch(error => {
                    console.error('Progress polling error:', error);
                });
        }
    }, 500);
}

/**
 * Show download progress modal
 */
function showDownloadProgressModal(url, version) {
    console.log('📢 showDownloadProgressModal called');

    if (!currentUpdateModal) {
        console.error('❌ No modal found');
        return;
    }

    const content = currentUpdateModal.querySelector('div > div > div');
    if (!content) {
        console.error('❌ Could not find modal content');
        return;
    }

    content.innerHTML = `
        <!-- Download Icon -->
        <div style="
            border-radius: 50%;
            margin: 0 auto 35px auto;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: pulse 2s infinite;
        ">
            <img alt="Downloading" src="../assets/images/setup.ico" style="width: 27%;">
        </div>

        <!-- Title -->
        <h2 style="margin: 0 0 15px 0; color: #002f34; font-size: 24px; font-weight: 600;">
            Downloading Update
        </h2>

        <!-- Version Info -->
        <p style="margin: 0 0 30px 0; color: #02a88e; font-size: 16px;">
            Installing version <span style="font-weight: 600; color: #002f34;">v${version}</span>
        </p>

        <!-- Progress Container -->
        <div style="
            background: #f0f0f0;
            border-radius: 10px;
            height: 12px;
            width: 100%;
            margin: 30px 0 15px 0;
            overflow: hidden;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
        ">
            <div id="progressBar" style="
                background: linear-gradient(90deg, rgb(1 167 141) 0%, rgb(0 47 52) 100%);
                height: 100%;
                width: 0%;
                border-radius: 10px;
                transition: width 0.3s ease;
            "></div>
        </div>

        <!-- Progress Text -->
        <div style="display: flex; justify-content: space-between; margin: 10px 0 25px 0;">
            <span style="color: #032e33; font-size: 14px;">0%</span>
            <span id="progressPercentage" style="color: #667eea; font-weight: 600; font-size: 16px;">0%</span>
            <span style="color: #032e33; font-size: 14px;">100%</span>
        </div>

        <!-- Status Text -->
        <div id="statusText" style="
            color: rgb(2 168 142);
            font-size: 14px;
            margin: 20px 0;
            min-height: 20px;
        ">
            Preparing download...
        </div>

        <!-- Loading animation -->
        <div id="loadingAnimation" style="margin: 20px 0;">
            <div style="
                border: 3px solid #f0f0f0;
                border-top: 3px solid #01a78d;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto;
            "></div>
        </div>

        <style>
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.05); }
                100% { transform: scale(1); }
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    `;
}

/**
 * Update download progress
 */
function updateDownloadProgress(percentage) {
    console.log('📊 Progress update:', percentage);

    const progressBar = document.getElementById('progressBar');
    const progressPercentage = document.getElementById('progressPercentage');
    const statusText = document.getElementById('statusText');
    const loadingAnimation = document.getElementById('loadingAnimation');

    if (progressBar && progressPercentage) {
        const percent = Math.min(100, Math.max(0, percentage));
        progressBar.style.width = percent + '%';
        progressPercentage.textContent = percent.toFixed(1) + '%';

        if (percent < 100) {
            if (statusText) {
                statusText.innerHTML = `Downloading... ${percent.toFixed(1)}%`;
            }
        } else {
            if (statusText) {
                statusText.innerHTML = 'Download complete! Installing...';
            }
            if (loadingAnimation) {
                loadingAnimation.style.display = 'none';
            }
        }
    }
}

/**
 * Show error modal
 */
function showUpdateErrorModal(errorMessage) {
    console.error('❌ Update error:', errorMessage);

    closeUpdateModal();

    // Create error modal
    const modal = document.createElement('div');
    modal.id = 'updateErrorModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(231, 76, 60, 0.1);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 99999;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    `;

    const dialog = document.createElement('div');
    dialog.style.cssText = `
        background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
        padding: 2px;
        border-radius: 12px;
        box-shadow: 0 10px 40px rgba(231, 76, 60, 0.3);
        max-width: 450px;
        width: 90%;
        overflow: hidden;
    `;

    const content = document.createElement('div');
    content.style.cssText = `
        background: white;
        padding: 30px;
        border-radius: 10px;
        text-align: center;
    `;

    content.innerHTML = `
        <!-- Error Icon -->
        <div style="
            width: 70px;
            height: 70px;
            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
            border-radius: 50%;
            margin: 0 auto 20px auto;
            display: flex;
            align-items: center;
            justify-content: center;
        ">
            <svg width="35" height="35" viewBox="0 0 24 24" fill="white">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
            </svg>
        </div>

        <!-- Title -->
        <h3 style="margin: 0 0 15px 0; color: #2c3e50; font-size: 22px; font-weight: 600;">
            Update Failed
        </h3>

        <!-- Error Message -->
        <div style="
            background: #ffeaea;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            text-align: left;
            border-left: 4px solid #e74c3c;
        ">
            <p style="margin: 0; color: #c0392b; font-size: 14px; line-height: 1.5;">
                ${errorMessage}
            </p>
        </div>

        <!-- Action Button -->
        <button onclick="this.closest('#updateErrorModal').remove()"
                style="
                    background: #e74c3c;
                    color: white;
                    border: none;
                    padding: 12px 30px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 15px;
                    font-weight: 600;
                    transition: all 0.3s ease;
                    margin-top: 10px;
                ">
            Close
        </button>

        <!-- Try Again Suggestion -->
        <div style="margin-top: 20px; color: #95a5a6; font-size: 13px;">
            You can try updating again from the Help menu
        </div>
    `;

    dialog.appendChild(content);
    modal.appendChild(dialog);
    document.body.appendChild(modal);
}

/**
 * Close update modal
 */
function closeUpdateModal() {
    if (progressPollingInterval) {
        clearInterval(progressPollingInterval);
        progressPollingInterval = null;
    }

    if (currentUpdateModal && document.body.contains(currentUpdateModal)) {
        document.body.removeChild(currentUpdateModal);
        currentUpdateModal = null;
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('📢 updater.js loaded and ready');
    initMessagePolling();
});

// Clean up on page unload
window.addEventListener('beforeunload', function() {
    if (progressPollingInterval) {
        clearInterval(progressPollingInterval);
    }
    if (messagePollingInterval) {
        clearInterval(messagePollingInterval);
    }
});