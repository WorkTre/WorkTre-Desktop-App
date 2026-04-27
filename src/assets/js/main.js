/**
 * main.js - Complete UI functionality for WorkTre Desktop
 * Handles login, dashboard, breaks, timers, and all UI interactions
 */

// ==================== GLOBAL VARIABLES ====================
let shiftTimerInterval = null;
let breakTimerInterval = null;
let breakMarked = false;
let breakType = "";
let breakComment = "";
let currentHourPassed = 0;
let currentMinutePassed = 0;
let breakMinutesPassed = 0;
let totalBreakMinutes = 60;
let currentPage = 1;
const logsPerPage = 5;

let shiftTicks = [];
let breakTicks = [];
let paginatedLogData = [];

// DOM Elements
let passwordInput, togglePassword, toggleIcon, emailInput, rememberMe, internetOverlay, loginErrorNotify;

// State flags
let isLoggingIn = false;
let initialized = false;

// ==================== INITIALIZATION ====================
document.addEventListener("DOMContentLoaded", async () => {
    // Prevent multiple initializations
    if (initialized) {
        console.log('⚠️ Already initialized, skipping...');
        return;
    }
    initialized = true;

    console.log('📢 WorkTre UI initialized - main.js loaded');

    // Initialize DOM elements
    initializeDOMElements();

    // Setup event listeners
    setupEventListeners();

    // Load remembered credentials
    setTimeout(() => {
        loadRememberMeData();
    }, 1000);

    // Display splash screen
    displaySplashScreen();

    // Check initial connectivity
    if (!navigator.onLine) {
        showConnectivityToast(false);
    }

    console.log('✅ Window functions will be registered at the end of file');
});

// ==================== DOM ELEMENT INITIALIZATION ====================

/**
 * Initialize DOM element references
 */
function initializeDOMElements() {
    passwordInput = document.getElementById("password");
    togglePassword = document.getElementById("togglePassword");
    toggleIcon = togglePassword?.querySelector("i");
    emailInput = document.getElementById("email");
    rememberMe = document.getElementById("remember_me");
    internetOverlay = document.getElementById('internetOverlay');
    loginErrorNotify = document.getElementById("login_error");

    console.log('✅ DOM elements initialized');
}

// ==================== EVENT LISTENERS ====================

/**
 * Setup all event listeners safely (no duplicates)
 */
function setupEventListeners() {
    console.log('🔧 Setting up event listeners...');

    // Login form - use safe attachment
    setupSafeListener('form', 'submit', handleLogin);
    setupSafeListener('button[type="submit"]', 'click', handleLogin);

    // Password toggle
    setupSafeListener('togglePassword', 'click', togglePasswordVisibility);

    // Break actions
    setupSafeListener('play', 'click', showBreakModal);
    setupSafeListener('pause', 'click', handleBreakEnd);

    // Break form submit
    setupSafeListener('#break form', 'submit', handleBreakSubmit, true);

    // Inactivity form submit - for "I'm Still Here"
    setupSafeListener('#inactivityForm', 'submit', handleInactivitySubmit, true);

    // End Break button in inactivity modal
    setupSafeListener('#endBreakBtn', 'click', handleEndBreakFromInactivity);

    // Navigation buttons
    setupSafeListener('break_logs', 'click', showBreakLogs);
    setupSafeListener('notifications', 'click', showNotifications);
    setupSafeListener('settings', 'click', showSettings);
    setupSafeListener('profile', 'click', showProfile);
    setupSafeListener('logout', 'click', handleLogout);
    setupSafeListener('back_button', 'click', goBackToDashboard);
    setupSafeListener('main-dashboard-logo', 'click', goBackToDashboard);
    setupSafeListener('cross-icon', 'click', handleBreakModalClose, false, '.');

    // Network listeners
    window.removeEventListener('online', handleNetworkOnline);
    window.removeEventListener('offline', handleNetworkOffline);
    window.addEventListener('online', handleNetworkOnline);
    window.addEventListener('offline', handleNetworkOffline);

    console.log('✅ All event listeners setup complete');
}

/**
 * Helper function to safely setup event listeners without duplicates
 * @param {string} selector - Element selector
 * @param {string} event - Event type
 * @param {Function} handler - Event handler
 * @param {boolean} isQuerySelector - Use querySelector instead of getElementById
 * @param {string} prefix - Selector prefix (default '#')
 */
function setupSafeListener(selector, event, handler, isQuerySelector = false, prefix = '#') {
    let element;

    if (isQuerySelector) {
        element = document.querySelector(selector);
    } else {
        element = document.getElementById(selector);
    }

    if (!element) {
        // Try with prefix for backward compatibility
        element = document.querySelector(selector);
    }

    if (element) {
        // Clone and replace to remove all existing listeners
        const newElement = element.cloneNode(true);
        element.parentNode?.replaceChild(newElement, element);
        newElement.addEventListener(event, handler);
        console.log(`✅ Listener attached: ${selector} (${event})`);
    } else {
        console.log(`⚠️ Element not found: ${selector}`);
    }
}

// ==================== NETWORK HANDLERS ====================
function handleNetworkOnline() {
    showConnectivityToast(true);
}
window.handleNetworkOnline = handleNetworkOnline;

function handleNetworkOffline() {
    showConnectivityToast(false);
}
window.handleNetworkOffline = handleNetworkOffline;

// ==================== LOGIN HANDLING ====================

/**
 * Handle login with debounce to prevent multiple calls
 */
async function handleLogin(e) {
    e.preventDefault();

    // Prevent multiple simultaneous login attempts
    if (isLoggingIn) {
        console.log('⏳ Login already in progress, ignoring duplicate click');
        return;
    }

    // Get login button for UI feedback
    const loginButton = document.querySelector("button[type='submit']");

    try {
        isLoggingIn = true;

        // Disable button and show loading
        if (loginButton) {
            loginButton.disabled = true;
            loginButton.innerHTML = '<span class="spinner"></span> Logging in...';
        }

        showLoader();

        const email = document.getElementById("email")?.value.trim() || "";
        const password = document.getElementById("password")?.value.trim() || "";
        const rememberMeChecked = document.getElementById("remember_me")?.checked || false;

        // Validation
        if (!email && !password) {
            alert("Please enter username and password.");
            return;
        }
        if (!email) {
            alert("Username cannot be empty.");
            return;
        }
        if (!password) {
            alert("Password cannot be empty.");
            return;
        }

        // Save remembered user
        try {
            if (window.pywebview?.api?.save_remembered_user) {
                await window.pywebview.api.save_remembered_user(
                    rememberMeChecked ? email : "",
                    rememberMeChecked ? password : ""
                );
            }
        } catch (err) {
            console.error("Failed to save remembered user:", err);
        }

        console.log('📤 Calling login API for:', email);

        if (!window.pywebview?.api?.login) {
            throw new Error("Login API not available");
        }

        const response = await window.pywebview.api.login(email, password);
        console.log('📥 Raw login response:', response);

        // Handle response - it could be a string or an object
        let data;
        if (typeof response === 'string') {
            try {
                data = JSON.parse(response);
                console.log('📥 Parsed JSON response:', data);
            } catch (parseError) {
                console.error('❌ Failed to parse response:', parseError);
                alert('Invalid response from server');
                return;
            }
        } else {
            // Response is already an object
            data = response;
            console.log('📥 Object response:', data);
        }

        const { status, data: userData } = data;

        if (status && userData && Object.keys(userData).length > 0) {
            await handleSuccessfulLogin(userData, email);
        } else {
            handleLoginFailure(userData);
        }
    } catch (err) {
        console.error("Login failed:", err);
        alert("Login error: " + err.message);
    } finally {
        // Reset login flag and button after delay
        setTimeout(() => {
            isLoggingIn = false;
            if (loginButton) {
                loginButton.disabled = false;
                loginButton.innerHTML = 'Login';
            }
            hideLoader();
        }, 2000);
    }
}

/**
 * Handle successful login
 */
async function handleSuccessfulLogin(userData, email) {
    console.log('✅ Login successful, processing user data:', userData);

    let breakFlag = "False";
    let crashLoginResponse = "";

    // Handle AlreadyLogin case
    if (userData?.LoginStatus === "AlreadyLogin" && typeof userData.AttendanceCrashStatus !== 'undefined') {
        const status = userData.AttendanceCrashStatus;

        if (status === "1") {
            hideLoader();
            const result = await getSystemActionFromUser();
            if (result) {
                showLoader();
                breakFlag = userData.OnBreakStatus === "True" ? "True" : "False";

                if (window.pywebview?.api?.crashlogin) {
                    crashLoginResponse = await window.pywebview.api.crashlogin(userData.EID, result, breakFlag);
                }

                if (crashLoginResponse) {
                    await showLoginSuccessNotification(email);
                }
            } else {
                return;
            }
        } else {
            if (window.pywebview?.api?.crashlogin) {
                crashLoginResponse = await window.pywebview.api.crashlogin(userData.EID, status, breakFlag);
            }
            await showLoginSuccessNotification(email);
        }
    } else {
        console.log("✅ First time login, no crash recovery needed");
        await showLoginSuccessNotification(email);
    }

    // Process crash login response if any
    if (crashLoginResponse) {
        let parseData;
        if (typeof crashLoginResponse === 'string') {
            parseData = JSON.parse(crashLoginResponse);
        } else {
            parseData = crashLoginResponse;
        }

        if (parseData?.status) {
            if (parseData.data?.Status !== "Success") {
                hideLoader();
                if (userData?.AttendanceCrashStatus === "ManualLogout" || (parseData.data?.Msg && parseData.data.Msg.includes("Not Found"))) {
                    console.warn("Ignoring crash login error: " + parseData.data?.Msg);
                } else {
                    alert(parseData.data?.Msg || "Crash login failed");
                    return;
                }
            }
        }
    }

    // Handle FirstTimeLogin and AlreadyLogin sequences according to requirements
    // Sequence required: 
    // AlreadyLogin: 1-login, 2-crashlogin, 3-lastactivitydate, 4-getservice
    // FirstTimeLogin: 1-login, 2-lastactivitydate, 3-getservice

    // 3 - lastactivitydate (Explicit)
    if (window.pywebview?.api?.manually_call_last_activity) {
        console.log('📞 Calling lastactivitydate API explicitly...');
        await window.pywebview.api.manually_call_last_activity("False");
    }

    // 4 - getservice
    console.log('📞 Calling getservice API...');
    const getServiceResponse = await getServiceAPI(userData.EID);
    console.log('📊 Final getServiceResponse:', getServiceResponse);

    // After the required APIs are called, start background intervals and fetch extra UI data
    if (window.pywebview?.api?.start_app_intervals) {
        await window.pywebview.api.start_app_intervals(userData);
    }

    // Get break types
    await getBreakTypes(userData.EID);

    // Save user data to localStorage
    localStorage.setItem("user_data", JSON.stringify(userData));

    // Set total break minutes from user data
    totalBreakMinutes = parseInt(userData.OtherBreakLogoutTime) || 60;

    // Update dashboard with user data
    await updateDashboardWithUserData(userData, getServiceResponse);
}

/**
 * Show login success notification
 */
async function showLoginSuccessNotification(email) {
    if (window.pywebview?.api?.show_login_success_notification) {
        await window.pywebview.api.show_login_success_notification(email);
    }
}

/**
 * Handle login failure
 */
function handleLoginFailure(userData) {
    if (userData?.IPAddresNotFound === 'Invalid IP Address') {
        alert("Your IP address is not registered.");

        if (loginErrorNotify) {
            loginErrorNotify.innerHTML = `Your IP is not registered with WorkTre. Please <a href="#" id="ip_request">Click Here</a> to send a request for access.`;

            setTimeout(() => {
                const ipLink = document.getElementById('ip_request');
                if (ipLink) {
                    ipLink.addEventListener('click', async (e) => {
                        e.preventDefault();
                        await requestForAccessAPI(userData.EID);
                    });
                }
            }, 0);
        }
    } else if (userData?.SystemChangeStatus === "1") {
        alert("You are already logged in on another device with these credentials.");
        if (loginErrorNotify) {
            loginErrorNotify.innerHTML = "You are already logged in to another system, please logout there to login here.";
        }
    } else {
        alert("Invalid username or password.");
    }
}

/**
 * Get system action from user for crash recovery
 */
async function getSystemActionFromUser() {
    const brandColor = '#21a78e';

    const inputOptions = {
        'crash': 'Crash',
        'network crash': 'Network Crash',
        'hibernate/sleep': 'Hibernate / Sleep',
        'shutdown': 'Shutdown / Restart'
    };

    const result = await Swal.fire({
        title: 'Select Crash Reason',
        input: 'radio',
        inputOptions,
        inputValue: 'crash',
        inputValidator: (value) => {
            if (!value) return 'You need to choose an option!';
        },
        allowOutsideClick: false,
        allowEscapeKey: false,
        allowEnterKey: true,
        showCancelButton: false,
        confirmButtonText: 'Submit',
        confirmButtonColor: brandColor,
        customClass: {
            popup: 'custom-swal-popup'
        }
    });

    return result.value;
}

// ==================== API CALLS ====================

/**
 * Get service API data with proper error handling
 */
async function getServiceAPI(userId) {
    try {
        console.log('📊 Calling getservice API for user:', userId);

        if (!window.pywebview?.api?.getservice) {
            console.error('❌ getservice API not available');
            return null;
        }

        const response = await window.pywebview.api.getservice(userId);
        console.log('📊 Raw getservice response:', response);

        // Handle response - it could be a string or object
        let parsed;
        if (typeof response === 'string') {
            try {
                parsed = JSON.parse(response);
                console.log('📊 Parsed getservice response:', parsed);
            } catch (parseError) {
                console.error('❌ Failed to parse getservice response:', parseError);
                return null;
            }
        } else {
            parsed = response;
            console.log('📊 Object getservice response:', parsed);
        }

        if (parsed?.status === true && parsed?.data) {
            console.log('✅ getservice successful, data:', parsed.data);
            return parsed.data;
        } else {
            console.warn("⚠️ getservice returned status false:", parsed?.message || parsed);
            return getDefaultServiceData();
        }
    } catch (err) {
        console.error("❌ getservice API error:", err);
        return getDefaultServiceData();
    }
}

/**
 * Get default service data structure
 */
function getDefaultServiceData() {
    return {
        "8)- totalDuration": "0:00",
        "3)- breakDetails": "",
        "7)- ProfileImage": "",
        "6)- timeIn": new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true }),
        "2)- totalBreakTime": "0"
    };
}

/**
 * Request for access API
 */
async function requestForAccessAPI(uid) {
    showLoader();

    try {
        if (!window.pywebview?.api?.requestforaccess) {
            throw new Error("Request access API not available");
        }

        const response = await window.pywebview.api.requestforaccess(uid);

        if (!response) {
            throw new Error("No response from backend.");
        }

        // Handle response - it could be a string or object
        let resData;
        if (typeof response === 'string') {
            resData = JSON.parse(response);
        } else {
            resData = response;
        }

        if (resData.status) {
            alert(`Your request for login with ${resData.data?.ip || 'unknown'} IP has been sent successfully. You will get a confirmation email once your request is approved.`);
        } else {
            alert(`Request failed: ${resData.message || "Unknown error."}`);
        }
    } catch (err) {
        console.error("IP request error:", err);
        alert("An error occurred while sending the IP request. Please try again.");
    } finally {
        hideLoader();
    }
}

/**
 * Load remembered user data
 */
async function loadRememberMeData() {
    try {
        if (!window.pywebview?.api?.get_remembered_user) {
            console.warn("get_remembered_user API not available");
            return;
        }

        const saved = await window.pywebview.api.get_remembered_user();

        if (saved?.email && saved?.password) {
            if (emailInput) emailInput.value = saved.email;
            if (passwordInput) passwordInput.value = saved.password;
            if (rememberMe) rememberMe.checked = true;
            console.log('✅ Remembered credentials loaded');
        }
    } catch (err) {
        console.error("Failed to load remembered user", err);
    }
}

/**
 * Get break types
 */
async function getBreakTypes(uid) {
    try {
        if (!window.pywebview?.api?.getBreakTypes) {
            console.warn("getBreakTypes API not available");
            return;
        }

        const response = await window.pywebview.api.getBreakTypes(uid);
        if (response) {
            populateBreakTypes(response);
        }
    } catch (err) {
        console.error("getBreakTypes API error", err);
    }
}

// ==================== DASHBOARD UPDATE ====================

/**
 * Update dashboard with user data
 */
async function updateDashboardWithUserData(userData, serviceData) {
    console.log('🔄 Updating dashboard with user data:', userData);
    console.log('🔄 Service data:', serviceData);

    const empName = `${userData.EmpFirstName || ''} ${userData.EmpLastName || ''}`.trim() || 'User';
    const empShift = convertTimeRangeFromGMT(
        `${formatTimeForDisplay(userData.ShiftStartTime)} - ${formatTimeForDisplay(userData.ShiftEndTime)}`
    );

    const { hours: startHrs, minutes: startMins } = parseTime(userData.ShiftStartTime);
    const { hours: endHrs, minutes: endMins } = parseTime(userData.ShiftEndTime);

    const now = new Date();
    const startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), startHrs, startMins);
    let endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), endHrs, endMins);

    if (endDate <= startDate) {
        endDate.setDate(endDate.getDate() + 1);
    }

    let passedTime = serviceData?.["8)- totalDuration"] ?? "0:00";
    const breakDetails = serviceData?.["3)- breakDetails"] || "";
    const profileAvatar = serviceData?.["7)- ProfileImage"] || userData.ProfileImage;
    const logData = convertLogToFormattedObjects(breakDetails);
    const loginTime = convertGMTTimeToLocal(serviceData?.["6)- timeIn"] || formatTime(new Date()));
    const totalBreak = secondsToHrsMins(serviceData?.["2)- totalBreakTime"] || 0);

    if (profileAvatar) {
        const profileImg = document.getElementById("profile_img");
        if (profileImg) {
            profileImg.src = `https://worktre.com/assets/uploads/avatars/${profileAvatar}`;
        }
    }

    // Save globally
    paginatedLogData = logData;
    currentPage = 1;

    // First page render
    renderLogsToTable(paginatedLogData, '.logs-tbl tbody', currentPage);

    const totalShiftMinutes = Math.floor((endDate - startDate) / (1000 * 60));
    const { hours: resumeHour, minutes: resumeMinute } = parsePassedTime(passedTime);

    if (loginErrorNotify) loginErrorNotify.innerHTML = "&nbsp;";

    // Update UI elements
    updateElementText("total_break", totalBreak);
    updateElementText("login_time", loginTime);
    updateElementText("empName", empName);
    updateElementText("empShift", empShift);

    const openInWeb = document.getElementById("open_in_web");
    if (openInWeb && userData.EID && userData.Loginkey) {
        openInWeb.href = `https://worktre.com/autologin/index/${userData.EID}/${userData.Loginkey}`;
    }

    // Show dashboard
    setElementDisplay("loginPage", "none");
    setElementDisplay("dashboard", "block");
    setElementDisplay("dashboard_content", "block");

    const loginCircle = document.getElementById("loginCircle");
    if (loginCircle) loginCircle.classList.add("active");

    setElementDisplay("back_button", "none");

    hideLoader();
    resetAllTimers();
    createShiftTicks(totalShiftMinutes);
    createBreakTicks();
    startShiftTimer(totalShiftMinutes, resumeHour, resumeMinute);

    console.log('✅ Dashboard updated successfully');
}

/**
 * Helper to update element text safely
 */
function updateElementText(id, text) {
    const element = document.getElementById(id);
    if (element) {
        element.innerText = text;
    }
}

/**
 * Helper to set element display safely
 */
function setElementDisplay(id, displayValue) {
    const element = document.getElementById(id);
    if (element) {
        element.style.display = displayValue;
    }
}

// ==================== TIME CONVERSION FUNCTIONS ====================

/**
 * Convert GMT time to local time
 */
function convertGMTTimeToLocal(timeStr) {
    if (!timeStr) return formatTime(new Date());

    try {
        // Parse the input time
        const [time, modifier] = timeStr.split(' ');
        let [hours, minutes] = time.split(':').map(Number);

        // Convert to 24-hour format
        if (modifier?.toLowerCase() === 'pm' && hours !== 12) {
            hours += 12;
        } else if (modifier?.toLowerCase() === 'am' && hours === 12) {
            hours = 0;
        }

        // Create a date object for today at the given UTC time
        const now = new Date();
        const utcDate = new Date(Date.UTC(
            now.getUTCFullYear(),
            now.getUTCMonth(),
            now.getUTCDate(),
            hours,
            minutes,
            0
        ));

        // Convert to local time string
        return utcDate.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        });
    } catch (error) {
        console.error('Error converting time:', error);
        return timeStr;
    }
}

/**
 * Format time for display
 */
function formatTimeForDisplay(timeStr) {
    if (!timeStr) return "12:00 am";

    const [time, modifier] = timeStr.split(" ");
    let [hours, minutes] = time.split(":").map(Number);
    hours = hours % 12 || 12;
    const displayMinutes = minutes.toString().padStart(2, '0');
    return `${hours}:${displayMinutes} ${modifier}`;
}

/**
 * Convert time range from GMT to local
 */
function convertTimeRangeFromGMT(timeRangeStr) {
    if (!timeRangeStr) return "";

    const [startStr, endStr] = timeRangeStr.split(' - ');

    const parseGMTTime = (timeStr) => {
        if (!timeStr) return "";

        const [time, modifier] = timeStr.split(' ');
        let [hours, minutes] = time.split(':').map(Number);

        // Convert to 24-hour
        if (modifier?.toLowerCase() === 'pm' && hours !== 12) hours += 12;
        if (modifier?.toLowerCase() === 'am' && hours === 12) hours = 0;

        const now = new Date();
        const utcDate = new Date(Date.UTC(
            now.getUTCFullYear(),
            now.getUTCMonth(),
            now.getUTCDate(),
            hours,
            minutes,
            0
        ));

        return utcDate.toLocaleTimeString([], {
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    };

    const localStart = parseGMTTime(startStr);
    const localEnd = parseGMTTime(endStr);

    return `${localStart} - ${localEnd}`;
}

/**
 * Parse time string
 */
function parseTime(timeStr) {
    if (!timeStr) return { hours: 0, minutes: 0 };

    const [time, modifier] = timeStr.split(" ");
    let [hours, minutes] = time.split(":").map(Number);
    if (modifier?.toLowerCase() === "pm" && hours !== 12) hours += 12;
    if (modifier?.toLowerCase() === "am" && hours === 12) hours = 0;
    return { hours, minutes };
}

/**
 * Parse passed time string
 */
function parsePassedTime(passedStr) {
    if (!passedStr) return { hours: 0, minutes: 0 };
    const [hours, minutes] = passedStr.split(":").map(Number);
    return { hours, minutes };
}

/**
 * Format date to time string
 */
function formatTime(date) {
    if (!date) return "";
    let hrs = date.getHours();
    const mins = date.getMinutes().toString().padStart(2, '0');
    const ampm = hrs >= 12 ? 'pm' : 'am';
    hrs = hrs % 12 || 12;
    return `${hrs}:${mins} ${ampm}`;
}

/**
 * Convert seconds to hours and minutes
 */
function secondsToHrsMins(totalSeconds) {
    if (!totalSeconds) return "00 Hrs : 00 Mins";

    const hours = String(Math.floor(totalSeconds / 3600)).padStart(2, '0');
    const minutes = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, '0');
    return `${hours} Hrs : ${minutes} Mins`;
}

// ==================== TIMER FUNCTIONS ====================

/**
 * Create shift timer ticks
 */
function createShiftTicks(totalShiftMinutes) {
    const timer = document.getElementById("shiftTimer");
    if (!timer) return;

    shiftTicks = [];
    timer.querySelectorAll(".tick").forEach(el => el.remove());

    const totalHours = Math.ceil(totalShiftMinutes / 60);
    const degreePerHour = 360 / totalHours;

    for (let i = 0; i < totalHours; i++) {
        const tick = document.createElement("div");
        tick.classList.add("tick");
        tick.style.transform = `rotate(${i * degreePerHour}deg)`;
        timer.appendChild(tick);
        shiftTicks.push(tick);
    }
}

/**
 * Create break timer ticks
 */
function createBreakTicks() {
    const breakTimer = document.getElementById("breakTimer");
    if (!breakTimer) return;

    breakTicks = [];
    breakTimer.querySelectorAll(".tick").forEach(el => el.remove());

    const degreePerTick = 360 / totalBreakMinutes;

    for (let i = 0; i < totalBreakMinutes; i++) {
        const tick = document.createElement("div");
        tick.classList.add("tick");
        tick.style.transform = `rotate(${i * degreePerTick}deg) translateX(-50%)`;
        tick.style.transformOrigin = "center 95px";
        breakTimer.appendChild(tick);
        breakTicks.push(tick);
    }

    if (!document.getElementById("breakFillRing")) {
        const fillRing = document.createElement("div");
        fillRing.id = "breakFillRing";
        fillRing.classList.add("fill-ring");
        breakTimer.prepend(fillRing);
    }
}

/**
 * Start shift timer
 */
function startShiftTimer(totalShiftMinutes, resumeHour = 0, resumeMinute = 0) {
    const shiftTimer = document.getElementById("shiftTimer");
    const fillRing = document.getElementById("fillRing");
    const hourLabel = document.getElementById("hourLabel");

    if (!shiftTimer || !fillRing || !hourLabel) return;

    currentHourPassed = resumeHour;
    currentMinutePassed = resumeMinute;

    shiftTimer.style.display = "block";
    const breakTimer = document.getElementById("breakTimer");
    if (breakTimer) breakTimer.style.display = "none";

    if (!shiftTicks.length) createShiftTicks(totalShiftMinutes);

    let elapsed = currentHourPassed * 60 + currentMinutePassed;
    let remaining = totalShiftMinutes - elapsed;

    // Mark previously completed ticks
    for (let i = 0; i < Math.floor(elapsed / 60); i++) {
        if (shiftTicks[i]) shiftTicks[i].classList.add("active");
    }

    // Initial ring update
    const angle = (elapsed / totalShiftMinutes) * 360;
    fillRing.style.background = `conic-gradient(#0aebc1 ${angle}deg, white ${angle}deg)`;

    // Update label
    let hrs = Math.floor(remaining / 60);
    let mins = remaining % 60;
    hourLabel.innerText = `${hrs}:${mins.toString().padStart(2, '0')}`;

    // Clear existing interval
    if (shiftTimerInterval) clearInterval(shiftTimerInterval);

    // Start interval
    shiftTimerInterval = setInterval(() => {
        elapsed = currentHourPassed * 60 + currentMinutePassed;
        remaining = totalShiftMinutes - elapsed;

        const angle = (elapsed / totalShiftMinutes) * 360;
        fillRing.style.background = `conic-gradient(#0aebc1 ${angle}deg, white ${angle}deg)`;

        const completedHour = Math.floor(elapsed / 60);
        if (completedHour < shiftTicks.length) {
            shiftTicks[completedHour].classList.add("active");
        }

        hrs = Math.floor(remaining / 60);
        mins = remaining % 60;
        hourLabel.innerText = `${hrs}:${mins.toString().padStart(2, '0')}`;

        currentMinutePassed++;
        if (currentMinutePassed >= 60) {
            currentMinutePassed = 0;
            currentHourPassed++;
        }

        if (elapsed >= totalShiftMinutes) {
            clearInterval(shiftTimerInterval);
            hourLabel.innerText = `0:00`;
        }
    }, 60000);
}

/**
 * Start break timer
 */
function startBreakTimer() {
    const breakTimer = document.getElementById("breakTimer");
    const timeLabel = document.getElementById("time");
    const fillRing = document.getElementById("breakFillRing");

    if (!breakTimer || !timeLabel || !fillRing) return;

    breakMinutesPassed = 0;
    breakTicks.forEach(tick => tick.classList.remove("active"));
    fillRing.style.background = "conic-gradient(#0aebc1 0deg, white 0deg)";
    timeLabel.innerText = totalBreakMinutes;

    const shiftTimer = document.getElementById("shiftTimer");
    if (shiftTimer) shiftTimer.style.display = "none";
    breakTimer.style.display = "block";

    if (!breakTicks.length) createBreakTicks();

    if (breakTimerInterval) clearInterval(breakTimerInterval);

    breakTimerInterval = setInterval(async () => {
        if (breakMinutesPassed < totalBreakMinutes) {
            if (breakTicks[breakMinutesPassed]) {
                breakTicks[breakMinutesPassed].classList.add("active");
            }

            const angle = ((breakMinutesPassed + 1) / totalBreakMinutes) * 360;
            fillRing.style.background = `conic-gradient(#0aebc1 ${angle}deg, white ${angle}deg)`;

            breakMinutesPassed++;
            timeLabel.innerText = totalBreakMinutes - breakMinutesPassed;

            if (totalBreakMinutes === breakMinutesPassed) {
                setTimeout(() => {
                    const breakCircle = document.getElementById("breakCircle");
                    if (breakCircle) breakCircle.classList.remove("active");
                    resetMarkedBreak();
                    clearInterval(breakTimerInterval);
                    breakTimerInterval = null;
                    redirectLogin();
                }, 1500);
            }
        } else {
            resetMarkedBreak();
            clearInterval(breakTimerInterval);
            breakTimerInterval = null;
            redirectLogin();
        }
    }, 60000);
}

/**
 * Pause break timer
 */
function pauseBreakTimer() {
    if (breakTimerInterval) {
        clearInterval(breakTimerInterval);
        breakTimerInterval = null;
    }

    breakMinutesPassed = 0;
    breakTicks.forEach(tick => tick.classList.remove("active"));

    const fillRing = document.getElementById("breakFillRing");
    if (fillRing) {
        fillRing.style.background = "conic-gradient(#0aebc1 0deg, white 0deg)";
    }

    const timeLabel = document.getElementById("time");
    if (timeLabel) {
        timeLabel.innerText = totalBreakMinutes;
    }
}

/**
 * Stop shift timer
 */
function stopShiftTimer() {
    if (shiftTimerInterval) {
        clearInterval(shiftTimerInterval);
        shiftTimerInterval = null;
    }
}

/**
 * Reset all timers
 */
function resetAllTimers() {
    stopShiftTimer();
    pauseBreakTimer();

    currentHourPassed = 0;
    currentMinutePassed = 0;
    breakMinutesPassed = 0;

    updateElementText("hourLabel", "0:00");
    updateElementText("time", "15");

    const fillRing = document.getElementById("fillRing");
    if (fillRing) fillRing.style.background = "conic-gradient(#0aebc1 0deg, white 0deg)";

    const breakFillRing = document.getElementById("breakFillRing");
    if (breakFillRing) breakFillRing.style.background = "conic-gradient(#0aebc1 0deg, white 0deg)";

    document.querySelectorAll(".tick").forEach(t => t.classList.remove("active"));
    shiftTicks = [];
    breakTicks = [];

    const breakForm = document.querySelector("#break form");
    if (breakForm) breakForm.reset();
}

/**
 * Resume shift timer
 */
function resumeShiftTimer() {
    const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
    if (!userData.ShiftStartTime || !userData.ShiftEndTime) return;

    const { hours: startHrs, minutes: startMins } = parseTime(userData.ShiftStartTime);
    const { hours: endHrs, minutes: endMins } = parseTime(userData.ShiftEndTime);

    const now = new Date();
    const startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), startHrs, startMins);
    let endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), endHrs, endMins);
    if (endDate <= startDate) endDate.setDate(endDate.getDate() + 1);

    const totalShiftMinutes = Math.floor((endDate - startDate) / (1000 * 60));
    startShiftTimer(totalShiftMinutes, currentHourPassed, currentMinutePassed);
}

// ==================== BREAK HANDLING ====================

/**
 * Handle break submit
 */
async function handleBreakSubmit(e) {
    e.preventDefault();
    showLoader();
    stopShiftTimer();

    const breakType_ = document.getElementById("break_type")?.value || "";
    const comment = document.getElementById("comment")?.value || "";
    breakType = breakType_;
    breakMarked = true;
    breakComment = comment;

    setElementDisplay("dashboard_content", "block");

    const playBtn = document.getElementById("play");
    if (playBtn) {
        playBtn.style.pointerEvents = "none";
        playBtn.style.opacity = "0.5";
    }

    try {
        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");

        if (!window.pywebview?.api?.breakin) {
            throw new Error("Break API not available");
        }

        const response = await window.pywebview.api.breakin(
            userData.EID || "",
            breakType_ || "",
            comment || ""
        );

        if (response) {
            hideLoader();
            const breakTypeSelect = document.getElementById('break_type');
            if (breakTypeSelect) breakTypeSelect.selectedIndex = 0;

            const commentField = document.getElementById("comment");
            if (commentField) commentField.value = "";

            const breakCircle = document.getElementById("breakCircle");
            if (breakCircle) breakCircle.classList.add("active");

            startBreakTimer();
        }
    } catch (err) {
        hideLoader();
        console.error("Break in API error", err);
        alert("Failed to start break: " + err.message);
    }
}

/**
 * Handle break end
 */
async function handleBreakEnd() {
    if (breakTimerInterval) {
        showLoader();
        pauseBreakTimer();

        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");

        const { hours: startHrs, minutes: startMins } = parseTime(userData.ShiftStartTime);
        const { hours: endHrs, minutes: endMins } = parseTime(userData.ShiftEndTime);

        const now = new Date();
        const startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), startHrs, startMins);
        let endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), endHrs, endMins);
        if (endDate <= startDate) endDate.setDate(endDate.getDate() + 1);

        const totalShiftMinutes = Math.floor((endDate - startDate) / (1000 * 60));
        startShiftTimer(totalShiftMinutes, currentHourPassed, currentMinutePassed);

        const playBtn = document.getElementById("play");
        if (playBtn) {
            playBtn.style.pointerEvents = "auto";
            playBtn.style.opacity = "1";
        }

        const breakCircle = document.getElementById("breakCircle");
        if (breakCircle) breakCircle.classList.remove("active");

        const response = await callBreakOutAPI();
        if (response) {
            hideLoader();
        }

        resetMarkedBreak();
    }
}

/**
 * Call break out API
 */
async function callBreakOutAPI(comment = "", inactivity = false) {
    try {
        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
        let response = "";

        if (!window.pywebview?.api?.breakout) {
            throw new Error("Breakout API not available");
        }

        if (breakMarked) {
            response = await window.pywebview.api.breakout(
                userData.EID,
                breakType,
                breakComment
            );
        } else {
            response = await window.pywebview.api.breakout(
                userData.EID,
                "inactivity",
                comment,
                inactivity
            );
        }

        if (response) {
            hideLoader();
        }
        return response;
    } catch (err) {
        hideLoader();
        console.error("Break out API error", err);
        return null;
    }
}

/**
 * Reset marked break
 */
function resetMarkedBreak() {
    breakMarked = false;
    breakType = "";
    breakComment = "";
}

// ==================== INACTIVITY HANDLING ====================

/**
 * Handle inactivity submit (I'm Still Here button)
 */
async function handleInactivitySubmit(e) {
    e.preventDefault();
    console.log('I\'m Still Here button clicked');

    showLoader();

    const comment = document.getElementById('comment2')?.value.trim() || "";

    hideInactivityModal();
    resumeShiftTimer();

    // Call breakout API with inactivity flag to end the inactivity break
    await callBreakOutAPI(comment, true);

    if (window.pywebview?.api?.resetInactivityTimer) {
        window.pywebview.api.resetInactivityTimer();
    }

    hideLoader();
}

/**
 * Handle End Break button from inactivity modal
 */
async function handleEndBreakFromInactivity(e) {
    e.preventDefault();
    console.log('End Break button clicked from inactivity modal');

    showLoader();

    const comment = document.getElementById('comment2')?.value.trim() || "";

    try {
        // Get user data
        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");

        if (!userData.EID) {
            throw new Error("User not logged in");
        }

        // Call breakout API to end the inactivity break
        console.log('Calling breakout API from inactivity...');
        const result = await window.pywebview.api.breakout(
            userData.EID,
            "inactivity",
            comment,
            true  // inactivity flag
        );

        console.log('Breakout API result:', result);

        if (result && result.status === true) {
            // Success - hide modal and resume
            console.log('Breakout successful, hiding modal');
            hideInactivityModal();

            // Reset inactivity timer
            if (window.pywebview?.api?.resetInactivityTimer) {
                await window.pywebview.api.resetInactivityTimer();
            }

            // Resume shift timer
            resumeShiftTimer();

            // Show success message
            alert('Break ended successfully');
        } else {
            // Failed
            console.error('Breakout failed:', result);
            alert(result?.msg || 'Failed to end break');
        }
    } catch (err) {
        console.error('Error ending break:', err);
        alert('Error: ' + err.message);
    } finally {
        hideLoader();
    }
}

// ==================== LOGS FUNCTIONS ====================

/**
 * Convert log to formatted objects
 */
function convertLogToFormattedObjects(input) {
    if (!input || typeof input !== 'string') return [];

    return input
        .split(/\[\d+\] => /)
        .slice(1)
        .map(line => {
            const regex = /(\d{2}):(\d{2}) (am|pm)\* to \*(\d{2}):(\d{2}) (am|pm)\* \(([^)]+)\) -- (\d{2}) Minute\(s\)/;
            const match = line.match(regex);
            if (!match) return null;

            const [, sh, sm, sp, eh, em, ep, type, duration] = match;

            const toDate = (h, m, period) => {
                let hour = parseInt(h);
                if (period?.toLowerCase() === 'pm' && hour !== 12) hour += 12;
                if (period?.toLowerCase() === 'am' && hour === 12) hour = 0;
                const now = new Date();
                return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate(), hour, parseInt(m)));
            };

            const formatTime = date =>
                date.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: true,
                });

            const start = formatTime(toDate(sh, sm, sp));
            const end = formatTime(toDate(eh, em, ep));

            return {
                time: `${start} to ${end}`,
                type,
                duration: `${duration} Minute(s)`
            };
        })
        .filter(Boolean);
}

/**
 * Render logs to table
 */
function renderLogsToTable(data, tableBodySelector, page = 1) {
    const tbody = document.querySelector(tableBodySelector);
    if (!tbody) return;

    const startIndex = (page - 1) * logsPerPage;
    const endIndex = startIndex + logsPerPage;
    const currentData = data.slice(startIndex, endIndex);

    // Clear existing rows
    tbody.innerHTML = '';

    if (currentData.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="3" style="text-align:center; color: #888;">No break logs</td>
        `;
        tbody.appendChild(row);
        return;
    }

    // Populate rows if data exists
    currentData.forEach(item => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${item.time || ''}</td>
            <td>${item.type || ''}</td>
            <td>${item.duration || ''}</td>
        `;
        tbody.appendChild(row);
    });

    renderPaginationControls(data.length);
}

/**
 * Render pagination controls
 */
function renderPaginationControls(totalItems) {
    const totalPages = Math.ceil(totalItems / logsPerPage);
    const pagination = document.querySelector('.logs-pagination .pagination');
    if (!pagination) return;

    // Clear old items
    pagination.innerHTML = '';

    // Previous Button
    const prev = document.createElement('li');
    prev.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
    prev.innerHTML = `<a class="page-link" href="#">Previous</a>`;
    prev.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentPage > 1) {
            currentPage--;
            renderLogsToTable(paginatedLogData, '.logs-tbl tbody', currentPage);
        }
    });
    pagination.appendChild(prev);

    // Page Numbers
    for (let i = 1; i <= totalPages; i++) {
        const li = document.createElement('li');
        li.className = `page-item ${i === currentPage ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#">${i}</a>`;
        li.addEventListener('click', (e) => {
            e.preventDefault();
            currentPage = i;
            renderLogsToTable(paginatedLogData, '.logs-tbl tbody', currentPage);
        });
        pagination.appendChild(li);
    }

    // Next Button
    const next = document.createElement('li');
    next.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
    next.innerHTML = `<a class="page-link" href="#">Next</a>`;
    next.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentPage < totalPages) {
            currentPage++;
            renderLogsToTable(paginatedLogData, '.logs-tbl tbody', currentPage);
        }
    });
    pagination.appendChild(next);
}

/**
 * Populate break types dropdown
 */
function populateBreakTypes(dataArray) {
    const select = document.getElementById("break_type");
    if (!select) return;

    select.innerHTML = '';

    if (!dataArray || !Array.isArray(dataArray)) return;

    dataArray.forEach(item => {
        const option = document.createElement('option');
        option.value = item.break_type || '';
        option.textContent = capitalizeWords((item.break_type || '').replace(/[_/]/g, ' '));
        select.appendChild(option);
    });
}

/**
 * Capitalize words
 */
function capitalizeWords(str) {
    if (!str) return '';
    return str.replace(/\b\w/g, char => char.toUpperCase());
}

// ==================== UI FUNCTIONS ====================

/**
 * Show loader
 */
function showLoader() {
    const loader = document.getElementById("simple-loader");
    if (loader) {
        loader.style.display = "flex";
    }
}

/**
 * Hide loader
 */
function hideLoader() {
    const loader = document.getElementById("simple-loader");
    if (loader) {
        loader.style.display = "none";
    }
}

/**
 * Display splash screen
 */
function displaySplashScreen() {
    const splash = document.getElementById("splash-screen");
    const loginPage = document.getElementById("loginPage");

    setTimeout(() => {
        if (splash) splash.style.opacity = 0;
        setTimeout(() => {
            if (splash) splash.style.display = "none";
            if (loginPage) loginPage.style.display = "block";
        }, 500);
    }, 1000);
}

/**
 * Redirect to login
 */
function redirectLogin() {
    if (window.pywebview?.api?.clear_app_data) {
        window.pywebview.api.clear_app_data();
    }

    stopShiftTimer();
    pauseBreakTimer();

    setElementDisplay("break_logs_content", "none");
    setElementDisplay("notifications_content", "none");
    setElementDisplay("settings_content", "none");
    setElementDisplay("profile_content", "none");
    setElementDisplay("dashboard", "none");
    setElementDisplay("loginPage", "block");

    const playBtn = document.getElementById("play");
    if (playBtn) {
        playBtn.style.pointerEvents = "auto";
        playBtn.style.opacity = "1";
    }

    localStorage.clear();
}

/**
 * Show connectivity toast
 */
function showConnectivityToast(isOnline) {
    if (!internetOverlay) return;

    if (isOnline) {
        internetOverlay.classList.add('d-none');
        callLastInactivity();
    } else {
        internetOverlay.classList.remove('d-none');
    }
}

/**
 * Call last inactivity
 */
async function callLastInactivity() {
    if (window.pywebview?.api?.manually_call_lastInactivity) {
        await window.pywebview.api.manually_call_lastInactivity(breakMarked);
    }
}

/**
 * Toggle password visibility
 */
function togglePasswordVisibility() {
    if (!passwordInput || !toggleIcon) return;

    const isPassword = passwordInput.type === "password";
    passwordInput.type = isPassword ? "text" : "password";
    toggleIcon.classList.toggle("fa-eye");
    toggleIcon.classList.toggle("fa-eye-slash");
}

/**
 * Show break modal
 */
function showBreakModal() {
    const modalEl = document.getElementById('breakModal');
    if (!modalEl) return;

    let modalInstance = bootstrap.Modal.getInstance(modalEl);
    if (!modalInstance) {
        modalInstance = new bootstrap.Modal(modalEl);
    }
    modalInstance.show();
}

/**
 * Show inactivity modal - Calls inactivity API and shows modal with dim backdrop
 */
async function showInactivityModal() {
    console.log('🔄 showInactivityModal called');

    // First, call inactivity API to mark the inactivity break
    console.log('📞 Calling inactivity API to mark inactivity break...');
    const apiResult = await callInactivityAPI();
    console.log('📞 Inactivity API result:', apiResult);

    // Now show the modal
    const modalEl = document.getElementById('inactivityModal');
    if (!modalEl) {
        console.error('❌ Inactivity modal element not found');
        return;
    }

    // Reset form
    const commentField = document.getElementById('comment2');
    if (commentField) commentField.value = '';

    // Store current window size before showing modal
    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;

    let modalInstance = bootstrap.Modal.getInstance(modalEl);
    if (!modalInstance) {
        modalInstance = new bootstrap.Modal(modalEl, {
            backdrop: 'static',  // This creates the dim backdrop
            keyboard: false
        });
    }
    modalInstance.show();

    // Force window to maintain its size
    setTimeout(() => {
        if (window.innerWidth !== windowWidth || window.innerHeight !== windowHeight) {
            console.log('Window size changed, restoring...');
            if (window.pywebview?.api?.restore_window) {
                window.pywebview.api.restore_window();
            }
        }
    }, 100);

    return true;
}

/**
 * Hide inactivity modal
 */
function hideInactivityModal() {
    const modalEl = document.getElementById('inactivityModal');
    if (modalEl) {
        const modalInstance = bootstrap.Modal.getInstance(modalEl);
        if (modalInstance) {
            modalInstance.hide();
        }
    }
}

/**
 * Handle break modal close
 */
function handleBreakModalClose() {
    if (!shiftTimerInterval) {
        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
        if (!userData.ShiftStartTime || !userData.ShiftEndTime) return;

        const { hours: startHrs, minutes: startMins } = parseTime(userData.ShiftStartTime);
        const { hours: endHrs, minutes: endMins } = parseTime(userData.ShiftEndTime);

        const now = new Date();
        const startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), startHrs, startMins);
        let endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), endHrs, endMins);
        if (endDate <= startDate) endDate.setDate(endDate.getDate() + 1);

        const totalShiftMinutes = Math.floor((endDate - startDate) / (1000 * 60));
        startShiftTimer(totalShiftMinutes, currentHourPassed, currentMinutePassed);
    }

    const breakForm = document.querySelector("#break form");
    if (breakForm) breakForm.reset();
}

// ==================== NAVIGATION FUNCTIONS ====================

/**
 * Show break logs
 */
function showBreakLogs() {
    setElementDisplay("break_logs_content", "block");
    setElementDisplay("dashboard_content", "none");
    setElementDisplay("notifications_content", "none");
    setElementDisplay("settings_content", "none");
    setElementDisplay("profile_content", "none");
    setElementDisplay("back_button", "block");
}

/**
 * Show notifications
 */
function showNotifications() {
    setElementDisplay("break_logs_content", "none");
    setElementDisplay("dashboard_content", "none");
    setElementDisplay("notifications_content", "block");
    setElementDisplay("settings_content", "none");
    setElementDisplay("profile_content", "none");
    setElementDisplay("back_button", "block");
}

/**
 * Show settings
 */
function showSettings() {
    setElementDisplay("break_logs_content", "none");
    setElementDisplay("dashboard_content", "none");
    setElementDisplay("notifications_content", "none");
    setElementDisplay("settings_content", "block");
    setElementDisplay("profile_content", "none");
    setElementDisplay("back_button", "block");
}

/**
 * Show profile
 */
function showProfile() {
    setElementDisplay("break_logs_content", "none");
    setElementDisplay("dashboard_content", "none");
    setElementDisplay("notifications_content", "none");
    setElementDisplay("settings_content", "none");
    setElementDisplay("profile_content", "block");
    setElementDisplay("back_button", "block");
}

/**
 * Go back to dashboard
 */
function goBackToDashboard() {
    setElementDisplay("break_logs_content", "none");
    setElementDisplay("dashboard_content", "block");
    setElementDisplay("notifications_content", "none");
    setElementDisplay("settings_content", "none");
    setElementDisplay("profile_content", "none");
    setElementDisplay("back_button", "none");
}

/**
 * Handle logout
 */
async function handleLogout() {
    if (breakMarked) {
        alert("Please end your break before logging out of the application.");
        return;
    }

    showLoader();
    resetMarkedBreak();

    await logoutAPI();

    const breakCircle = document.getElementById("breakCircle");
    if (breakCircle) breakCircle.classList.remove("active");

    setElementDisplay("break_logs_content", "none");
    setElementDisplay("notifications_content", "none");
    setElementDisplay("settings_content", "none");
    setElementDisplay("profile_content", "none");
}

/**
 * Logout API
 */
async function logoutAPI() {
    try {
        stopShiftTimer();
        pauseBreakTimer();

        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");

        if (window.pywebview?.api?.logout) {
            await window.pywebview.api.logout(
                userData.EID || "",
                userData.EOD || "",
                userData.TotalChats || 0,
                userData.TotalBillableChat || 0
            );
        }

        setElementDisplay("dashboard", "none");
        setElementDisplay("loginPage", "block");
        setElementDisplay("back_button", "none");

        const playBtn = document.getElementById("play");
        if (playBtn) {
            playBtn.style.pointerEvents = "auto";
            playBtn.style.opacity = "1";
        }

        localStorage.clear();
        hideLoader();
    } catch (err) {
        hideLoader();
        console.warn("Logout API failed, proceeding anyway");
    }
}

// ==================== WINDOW FUNCTIONS (CALLED FROM PYTHON) ====================

/**
 * Show inactivity warning modal (called from Python)
 */
window.showInactivityWarningModal = async function() {
    console.log('⚠️ Inactivity warning received from Python');
    console.log('🔍 window.showInactivityWarningModal called');

    // This will call inactivity API and show modal with dim backdrop
    await showInactivityModal();
    stopShiftTimer();
};

/**
 * Handle inactivity timeout (called from Python)
 */
window.inactivityTimeExceed = async function() {
    console.log('⏰ Inactivity timeout exceeded');
    hideInactivityModal();
    await callBreakOutAPI("", true);
    await callLogoutInactivityAPI();
    redirectLogin();
};

/**
 * Call inactivity API
 */
async function callInactivityAPI() {
    console.log('🔍 callInactivityAPI called');

    try {
        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
        console.log('📊 User data for inactivity API:', userData);

        if (!userData.EID) {
            console.error('❌ No user EID found for inactivity API');
            return { status: false, error: 'No user logged in' };
        }

        if (window.pywebview?.api?.inactivity) {
            console.log('📞 Calling inactivity API for user:', userData.EID);
            const result = await window.pywebview.api.inactivity(
                userData.EID,
                "inactivity"
            );
            console.log('✅ Inactivity API result:', result);
            return result;
        } else {
            console.error('❌ inactivity API not available in pywebview');
            return { status: false, error: 'API not available' };
        }
    } catch (err) {
        console.error("❌ Inactivity API error:", err);
        return { status: false, error: err.message };
    }
}

/**
 * Call logout inactivity API
 */
async function callLogoutInactivityAPI() {
    try {
        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");

        if (window.pywebview?.api?.logoutinactivity) {
            await window.pywebview.api.logoutinactivity(
                userData.EID
            );
        }
    } catch (err) {
        console.error("Logout inactivity API error", err);
    }
}

/**
 * Internet disconnected time exceed (called from Python)
 */
window.onInternetDisconnectedTimeExceed = function() {
    console.log('🌐 Internet disconnected timeout exceeded');
    redirectLogin();
};

/**
 * Redirect login (called from Python)
 */
window.redirectLogin = function() {
    redirectLogin();
};

/**
 * Auto-fill credentials (called from Python)
 */
window.autoFillCredentials = function(credentials) {
    console.log('📝 Auto-filling credentials:', credentials?.email);

    const emailField = document.getElementById('email');
    const passwordField = document.getElementById('password');

    if (emailField && passwordField && credentials) {
        emailField.value = credentials.email || '';
        passwordField.value = credentials.password || '';

        emailField.dispatchEvent(new Event('input', { bubbles: true }));
        passwordField.dispatchEvent(new Event('input', { bubbles: true }));

        const rememberCheckbox = document.getElementById('remember_me');
        if (rememberCheckbox) {
            rememberCheckbox.checked = true;
        }

        console.log('✅ Credentials auto-filled');
    } else {
        console.log('❌ Could not find login fields or credentials');
    }
};

// Add spinner CSS if not present
if (!document.getElementById('spinner-style')) {
    const style = document.createElement('style');
    style.id = 'spinner-style';
    style.textContent = `
        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid #f3f3f3;
            border-top: 2px solid #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 8px;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
}

// Add CSS for inactivity modal backdrop
if (!document.getElementById('inactivity-modal-style')) {
    const style = document.createElement('style');
    style.id = 'inactivity-modal-style';
    style.textContent = `
        /* Ensure modal backdrop is dim */
        .modal-backdrop.show {
            opacity: 0.5 !important;
            background-color: #000 !important;
        }

        /* Ensure modal content is clear and visible */
        #inactivityModal .modal-content {
            background: white;
            border: 2px solid #01a78d;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
        }

        /* Make buttons clearly clickable */
        #endBreakBtn, #inactivityForm button[type="submit"] {
            cursor: pointer !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            position: relative;
            z-index: 1060;
        }

        #endBreakBtn:hover, #inactivityForm button[type="submit"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(1,167,141,0.3);
        }

        /* Ensure modal is above backdrop */
        #inactivityModal {
            z-index: 1055;
        }

        #inactivityModal .modal-dialog {
            z-index: 1056;
        }
    `;
    document.head.appendChild(style);
}