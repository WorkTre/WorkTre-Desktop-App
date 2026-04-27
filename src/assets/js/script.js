
    let api;
    let shiftTimerInterval = null;
    let breakTimerInterval = null;
    let breakStartTime = null;
    let breakEndTime = null;
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

    const passwordInput = document.getElementById("password");
    const togglePassword = document.getElementById("togglePassword");
    const toggleIcon = togglePassword.querySelector("i");
    const emailInput = document.getElementById("email");
    const rememberMe = document.getElementById("remember_me");

    const internetOverlay = document.getElementById('internetOverlay');
    const loginErrorNotify = document.getElementById("login_error")





    new QWebChannel(qt.webChannelTransport, function (channel) {
        api = channel.objects.api;

        // Example: receive message immediately from Python on load
        api.getMessageFromPython(function (msg) {
            console.log("Received from Python on load:", msg);
//            document.getElementById("response").innerText = "On load: " + msg;
        });
    });

    function sendMessageToPython() {
        if (api) {
            api.receiveFromJs("Hello Python, from JavaScript!");
        }
    }

    function getMessageFromPython() {
        if (api) {
            api.getMessageFromPython(function (response) {
                console.log("Message from Python:", response);
                document.getElementById("response").append("<h1>helo</h1>");
            });
        }
    }


    async function login() {
        const response = await api.fetchData("user_info");
        const data = JSON.parse(response);
        console.log("User name:", data.name, data.role);
    }









    function createShiftTicks(totalShiftMinutes) {
      const timer = document.getElementById("shiftTimer");
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

    function createBreakTicks() {
        const breakTimer = document.getElementById("breakTimer");
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

    function startShiftTimer(totalShiftMinutes, resumeHour = 0, resumeMinute = 0) {
      const shiftTimer = document.getElementById("shiftTimer");
      const fillRing = document.getElementById("fillRing");
      const hourLabel = document.getElementById("hourLabel");

      currentHourPassed = resumeHour;
      currentMinutePassed = resumeMinute;

      shiftTimer.style.display = "block";
      document.getElementById("breakTimer").style.display = "none";

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
      }, 60000); // Update every minute
    }

    function parsePassedTime(passedStr) {
      const [hours, minutes] = passedStr.split(":").map(Number);
      return { hours, minutes };
    }


    function formatTimeForDisplay(timeStr) {
        const [time, modifier] = timeStr.split(" ");
        let [hours, minutes] = time.split(":").map(Number);
        hours = hours % 12 || 12; // Convert 0/12 to 12-hour format
        const displayMinutes = minutes.toString().padStart(2, '0');
        return `${hours}:${displayMinutes} ${modifier}`;
    }


    function startBreakTimer() {

        const breakTimer = document.getElementById("breakTimer");
        const timeLabel = document.getElementById("time");
        const fillRing = document.getElementById("breakFillRing");

        breakMinutesPassed = 0;
        breakTicks.forEach(tick => tick.classList.remove("active"));
        if (fillRing) {
            fillRing.style.background = "conic-gradient(#0aebc1 0deg, white 0deg)";
        }
        if (timeLabel) {
            timeLabel.innerText = totalBreakMinutes;
        }

        document.getElementById("shiftTimer").style.display = "none";
        breakTimer.style.display = "block";

        if (!breakTicks.length) createBreakTicks();

        const breakStartTime = new Date();
        const breakStartElem = document.getElementById("break_startime");
        if (breakStartElem) {
            breakStartElem.innerText = formatTime(breakStartTime);
        }

        const breakEndElem = document.getElementById("break_endtime");
        if (breakEndElem) {
            breakEndElem.innerText = "";
        }

        breakTimerInterval = setInterval(async () => {
            if (breakMinutesPassed < totalBreakMinutes) {
                breakTicks[breakMinutesPassed]?.classList.add("active");

                const angle = ((breakMinutesPassed + 1) / totalBreakMinutes) * 360;
                fillRing.style.background = `conic-gradient(#0aebc1 ${angle}deg, white ${angle}deg)`;

                breakMinutesPassed++;
                timeLabel.innerText = totalBreakMinutes - breakMinutesPassed;

                if(totalBreakMinutes === breakMinutesPassed){
                    setTimeout(()=>{
                        document.getElementById("breakCircle").classList.remove("active");
                        resetMarkedBreak()
                        clearInterval(breakTimerInterval);
                        breakTimerInterval = null;
                        redirectLogin()
                    }, 1500)

                }

            } else {
                resetMarkedBreak()
                clearInterval(breakTimerInterval);
                breakTimerInterval = null;
                redirectLogin()
            }
        }, 60000);
    }

    function formatTime(date) {
        let hrs = date.getHours();
        const mins = date.getMinutes().toString().padStart(2, '0');
        const ampm = hrs >= 12 ? 'pm' : 'am';
        hrs = hrs % 12 || 12;
        return `${hrs}:${mins} ${ampm}`;
    }

    function resumeShiftTimer(){
        const userData = JSON.parse(localStorage.getItem("user_data") || "{}");

        const { hours: startHrs, minutes: startMins } = parseTime(userData.ShiftStartTime);
        const { hours: endHrs, minutes: endMins } = parseTime(userData.ShiftEndTime);

        const now = new Date();
        const startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), startHrs, startMins);
        let endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), endHrs, endMins);
        if (endDate <= startDate) endDate.setDate(endDate.getDate() + 1);

        const totalShiftMinutes = Math.floor((endDate - startDate) / (1000 * 60));
        startShiftTimer(totalShiftMinutes, currentHourPassed, currentMinutePassed);
    }

    function pauseBreakTimer() {
        clearInterval(breakTimerInterval);
        breakTimerInterval = null;
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

        const breakEndTime = new Date();
        const breakEndElem = document.getElementById("break_endtime");
        if (breakEndElem) {
            breakEndElem.innerText = " - " + formatTime(breakEndTime);
        }
    }

    function stopShiftTimer() {
        clearInterval(shiftTimerInterval);
        shiftTimerInterval = null;
    }

    function resetAllTimers() {
        clearInterval(shiftTimerInterval);
        clearInterval(breakTimerInterval);

        currentHourPassed = 0;
        currentMinutePassed = 0;
        breakMinutesPassed = 0;

        document.getElementById("hourLabel").innerText = "0:00";
        document.getElementById("time").innerText = "15";

        document.getElementById("fillRing").style.background = "conic-gradient(#0aebc1 0deg, white 0deg)";
        document.getElementById("breakFillRing")?.style?.setProperty("background", "conic-gradient(#0aebc1 0deg, white 0deg)");

        document.querySelectorAll(".tick").forEach(t => t.classList.remove("active"));
        shiftTicks = [];
        breakTicks = [];

        document.querySelector("#break form")?.reset();
    }

    function displaySplashScreen() {
        const splash = document.getElementById("splash-screen");
        const loginPage = document.getElementById("loginPage");
        setTimeout(() => {
            splash.style.opacity = 0;
            setTimeout(() => {
                splash.style.display = "none";
                loginPage.style.display = "block";
            }, 500);
        }, 1000);
    }

    function parseTime(timeStr) {
        const [time, modifier] = timeStr.split(" ");
        let [hours, minutes] = time.split(":").map(Number);
        if (modifier.toLowerCase() === "pm" && hours !== 12) hours += 12;
        if (modifier.toLowerCase() === "am" && hours === 12) hours = 0;
        return { hours, minutes };
    }

    displaySplashScreen();

    function showLoader() {
      const loader = document.getElementById("simple-loader");
      if (loader) {
<!--        loader.style.display = "block";-->
        loader.style.display = "flex";
      }
    }

    function hideLoader() {
      const loader = document.getElementById("simple-loader");
      if (loader) {
        loader.style.display = "none";
      }
    }

    function redirectLogin(){
        api.clear_app_data();
        stopShiftTimer();
        pauseBreakTimer();


        document.getElementById("dashboard").style.display = "none";
        document.getElementById("loginPage").style.display = "block";

        document.getElementById("play").style.pointerEvents = "auto";
        document.getElementById("play").style.opacity = "1";
        localStorage.clear();
    }

    function convertTimeRangeFromGMT(timeRangeStr) {
      const [startStr, endStr] = timeRangeStr.split(' - ');

      const today = new Date().toISOString().split('T')[0]; // e.g., "2025-07-05"

      const parseGMTTime = (timeStr) => {
        const date = new Date(`${today}T${convertTo24Hour(timeStr)}:00Z`); // Treat as UTC
        return date.toLocaleTimeString([], {
          hour: 'numeric',     // <-- use 'numeric' instead of '2-digit'
          minute: '2-digit',
          hour12: true,
        });
      };

      const convertTo24Hour = (time12h) => {
        const [time, modifier] = time12h.split(' ');
        let [hours, minutes] = time.split(':');
        if (modifier.toLowerCase() === 'pm' && hours !== '12') {
          hours = String(parseInt(hours, 10) + 12);
        }
        if (modifier.toLowerCase() === 'am' && hours === '12') {
          hours = '00';
        }
        return `${hours.padStart(2, '0')}:${minutes}`;
      };

      const localStart = parseGMTTime(startStr);
      const localEnd = parseGMTTime(endStr);

      return `${localStart} - ${localEnd}`;
    }

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
          <td>${item.time}</td>
          <td>${item.type}</td>
          <td>${item.duration}</td>
        `;
        tbody.appendChild(row);
      });

      renderPaginationControls(data.length);
    }

    function renderPaginationControls(totalItems) {
      const totalPages = Math.ceil(totalItems / logsPerPage);
      const pagination = document.querySelector('.logs-pagination .pagination');
      if (!pagination) return;

      // Clear old items except previous and next
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

    function convertLogToFormattedObjects(input) {
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
            if (period.toLowerCase() === 'pm' && hour !== 12) hour += 12;
            if (period.toLowerCase() === 'am' && hour === 12) hour = 0;
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

    function hideBreakModal() {
        const modal = bootstrap.Modal.getInstance(document.getElementById('breakModal'));
        if (modal) {
          modal.hide();
        } else {
          // If it's not already instantiated (e.g., opened via JS), do this:
          const instance = new bootstrap.Modal(document.getElementById('breakModal'));
          instance.hide();
        }
    }

     function hideInactivityModal() {
        document.getElementById('comment2').value = ""
        const modal = bootstrap.Modal.getInstance(document.getElementById('inactivityModal'));
        if (modal) {
          modal.hide();
        } else {
          // If it's not already instantiated (e.g., opened via JS), do this:
          const instance = new bootstrap.Modal(document.getElementById('inactivityModal'));
          instance.hide();
        }
     }

     function resetMarkedBreak(){
        breakMarked = false
        breakType = ""
        breakComment = ""
     }

    function populateBreakTypes(dataArray) {
      const select = document.getElementById("break_type");


      select.innerHTML = '';


      dataArray.forEach(item => {
        const option = document.createElement('option');
        option.value = item.break_type;
        option.textContent = capitalizeWords(item.break_type.replace(/[_/]/g, ' '));
        select.appendChild(option);
      });
    }


    function capitalizeWords(str) {
      return str.replace(/\b\w/g, char => char.toUpperCase());
    }


    document.querySelector("button[type='submit']").addEventListener("click", async (e) => {
         e.preventDefault();

//         showLoader()
        const email = emailInput.value.trim();
        const password = passwordInput.value.trim();
        const rememberMe = document.getElementById("remember_me").checked;

        // Validation
        if (!email && !password) {
            alert("Please enter username and password.");
            hideLoader()
            return;
        }
        if (!email) {
            alert("Username cannot be empty.");
            hideLoader()
            return;
        }
        if (!password) {
            alert("Password cannot be empty.");
            hideLoader()
            return;
        }

//        if (rememberMe) {
//            await api.save_remembered_user(email, password);
//        } else {
//            await api.save_remembered_user("", "");
//        }

        const now = new Date();
        let hours = now.getHours();
        const minutes = now.getMinutes().toString().padStart(2, '0');
        const ampm = hours >= 12 ? 'pm' : 'am';
        hours = hours % 12 || 12;
        const formattedLoginTime = `${hours}:${minutes} ${ampm}`;

        try {

            const response = await api.login(email, password, rememberMe);
            console.log("Response: ", response)
//            return;
            const { status, data } = JSON.parse(response);

            console.log(data)
//            return
            if (status && Object.keys(data).length>0) {

                localStorage.setItem("user_data", JSON.stringify(data));




                totalBreakMinutes = parseInt(data.OtherBreakLogoutTime)

                const empName = `${data.EmpFirstName} ${data.EmpLastName}`;
                const empShift = convertTimeRangeFromGMT(`${formatTimeForDisplay(data.ShiftStartTime)} - ${formatTimeForDisplay(data.ShiftEndTime)}`);


                const { hours: startHrs, minutes: startMins } = parseTime(data.ShiftStartTime);
                const { hours: endHrs, minutes: endMins } = parseTime(data.ShiftEndTime);

                const now = new Date();
                const startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), startHrs, startMins);
                let endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), endHrs, endMins);

                if (endDate <= startDate) {
                    endDate.setDate(endDate.getDate() + 1); // Cross-midnight fix
                }


                const getServiceResponse = await api.getservice(data.EID)
                let passedTime = ""



                if(getServiceResponse){
                  passedTime = getServiceResponse["8)- totalDuration"] ?? "0:00";
                  const breakDetails = getServiceResponse["3)- breakDetails"];
                  const logData = convertLogToFormattedObjects(breakDetails);

                  // Save globally
                  paginatedLogData = logData;
                  currentPage = 1;

                  // First page render
                  renderLogsToTable(paginatedLogData, '.logs-tbl tbody', currentPage);

                  hideLoader();
                }

                const totalShiftMinutes = Math.floor((endDate - startDate) / (1000 * 60));
                const { hours: resumeHour, minutes: resumeMinute } = parsePassedTime(passedTime);

                loginErrorNotify.innerHTML = "&nbsp;";
                document.getElementById("login_time").innerText = formattedLoginTime;
                document.getElementById("empName").innerText = empName;
                document.getElementById("empShift").innerText = empShift;

                document.getElementById("loginPage").style.display = "none";
                document.getElementById("dashboard").style.display = "block";
                document.getElementById("loginCircle").classList.add("active");
                document.getElementById("back_button").style.display = "none";

                resetAllTimers();
                createShiftTicks(totalShiftMinutes);
                createBreakTicks();
                startShiftTimer(totalShiftMinutes, resumeHour, resumeMinute);


            } else {
                if(data.IPAddresNotFound === 'Invalid IP Address'){
                     alert("Your IP address is not registered.");
                    loginErrorNotify.innerHTML = `Your IP is not registered with WORKTRE. Please <a href="#" id="ip_request">Click Here</a> to send a request for access.`;

                    setTimeout(() => {
                        const ipLink = document.getElementById('ip_request');

                        if (!ipLink) {
                            console.error("Could not find the IP request link element.");
                            return;
                        }

                        ipLink.addEventListener('click', async function (e) {
                            e.preventDefault();
                            await requestForAccessAPI(data.EID)
                        });

                    }, 0);

                    hideLoader();


                }else if(data.SystemChangeStatus === "1"){
                    alert("You are already logged in on another device with these credentials.");
                    loginErrorNotify.innerHTML = "You are already login to another system, please logout there to login here"
                }else{
                    alert("Invalid username or password.");
                }
                hideLoader()
            }
        } catch (err) {
            hideLoader()
            console.error("Login failed:", err);
        }
    });




    const form = document.querySelector('#inactivityModal form');

    form.addEventListener('submit', async function (e) {
      e.preventDefault(); // Prevent form from reloading the page
      showLoader()

      const comment = document.getElementById('comment2').value.trim();



      // Log or send data (optional)
      console.log("Break reason submitted:", comment);

      // Call your function to hide the modal
      hideInactivityModal();
      resumeShiftTimer();
      await callBreakOutAPI(comment)
      api.resetInactivityTimer()
    });

    document.getElementById("play").addEventListener("click", async () => {
        showBreakModal();
    });

    document.querySelector("#break form").addEventListener("submit", async (e) => {
        e.preventDefault();
        showLoader()
        stopShiftTimer();

        const breakType_ = document.getElementById("break_type").value;
        const comment = document.getElementById("comment").value;
        breakType = breakType_
        breakMarked = true
        breakComment = comment

        console.log("Break form submitted", { breakType, comment });

        document.getElementById("dashboard_content").style.display = "block";

        document.getElementById("play").style.pointerEvents = "none";
        document.getElementById("play").style.opacity = "0.5";


        try{
            const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
            const response = await api.breakin(
                userData.EID || "",
                breakType_ || "",
                comment || ""
            );

            if(response){
                hideLoader()
                document.getElementById('break_type').selectedIndex = 0;
                document.getElementById("comment").value = "";
                document.getElementById("breakCircle").classList.add("active");
                console.log(totalBreakMinutes)
                startBreakTimer();
            }
            console.log(response)
        }catch(err){
            hideLoader()
            console.err("Break in API error")
        }


    });

    document.getElementById("pause").addEventListener("click", async () => {
        if (breakTimerInterval) {
            showLoader()
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

            document.getElementById("play").style.pointerEvents = "auto";
            document.getElementById("play").style.opacity = "1";
            document.getElementById("breakCircle").classList.remove("active");



            const response = await callBreakOutAPI()
            if(response){
                hideLoader()
            }

            resetMarkedBreak()
        }
    });

    document.getElementById("logout").addEventListener("click", async () => {
        document.getElementById("breakCircle").classList.remove("active");
        resetMarkedBreak()
        showLoader()
        await logoutAPI()
    });

    document.querySelector(".cross-icon").addEventListener("click", () => {
        if (!shiftTimerInterval) {
            const userData = JSON.parse(localStorage.getItem("user_data") || "{}");

            const { hours: startHrs, minutes: startMins } = parseTime(userData.ShiftStartTime);
            const { hours: endHrs, minutes: endMins } = parseTime(userData.ShiftEndTime);

            const now = new Date();
            const startDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), startHrs, startMins);
            let endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), endHrs, endMins);
            if (endDate <= startDate) endDate.setDate(endDate.getDate() + 1);

            const totalShiftMinutes = Math.floor((endDate - startDate) / (1000 * 60));
            startShiftTimer(totalShiftMinutes, currentHourPassed, currentMinutePassed);
        }

        document.querySelector("#break form")?.reset();
    });

    document.getElementById("break_logs").addEventListener("click", () => {
        document.getElementById("break_logs_content").style.display = "block";
        document.getElementById("dashboard_content").style.display = "none";
        document.getElementById("notifications_content").style.display = "none";
        document.getElementById("settings_content").style.display = "none";
        document.getElementById("profile_content").style.display = "none";
        document.getElementById("back_button").style.display = "block";
    });

    document.getElementById("main-dashboard-logo").addEventListener("click", () => {
        document.getElementById("break_logs_content").style.display = "none";
        document.getElementById("dashboard_content").style.display = "block";
        document.getElementById("notifications_content").style.display = "none";
        document.getElementById("settings_content").style.display = "none";
        document.getElementById("profile_content").style.display = "none";
        document.getElementById("back_button").style.display = "none";
    });

    document.getElementById("notifications").addEventListener("click", () => {
        document.getElementById("break_logs_content").style.display = "none";
        document.getElementById("dashboard_content").style.display = "none";
        document.getElementById("notifications_content").style.display = "block";
        document.getElementById("settings_content").style.display = "none";
        document.getElementById("profile_content").style.display = "none";
        document.getElementById("back_button").style.display = "block";
    });

    document.getElementById("settings").addEventListener("click", () => {
        document.getElementById("break_logs_content").style.display = "none";
        document.getElementById("dashboard_content").style.display = "none";
        document.getElementById("notifications_content").style.display = "none";
        document.getElementById("settings_content").style.display = "block";
        document.getElementById("profile_content").style.display = "none";
        document.getElementById("back_button").style.display = "block";
    });

    document.getElementById("profile").addEventListener("click", () => {
        document.getElementById("break_logs_content").style.display = "none";
        document.getElementById("dashboard_content").style.display = "none";
        document.getElementById("notifications_content").style.display = "none";
        document.getElementById("settings_content").style.display = "none";
        document.getElementById("profile_content").style.display = "block";
        document.getElementById("back_button").style.display = "block";
    });

    document.getElementById("back_button").addEventListener("click", () => {
        document.getElementById("break_logs_content").style.display = "none";
        document.getElementById("dashboard_content").style.display = "block";
        document.getElementById("notifications_content").style.display = "none";
        document.getElementById("settings_content").style.display = "none";
        document.getElementById("profile_content").style.display = "none";
        document.getElementById("back_button").style.display = "none";
    });

    togglePassword.addEventListener("click", () => {
        const isPassword = passwordInput.type === "password";
        passwordInput.type = isPassword ? "text" : "password";
        toggleIcon.classList.toggle("fa-eye");
        toggleIcon.classList.toggle("fa-eye-slash");
    });


    async function callBreakOutAPI(comment="", inactivity=false){
        try{
            const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
            let response = ""

            if(breakMarked){
                response = await api.breakout(
                    userData.EID,
                    breakType,
                    breakComment
                );



            }else{
                response = await api.breakout(
                    userData.EID,
                    "inactivity",
                    comment,
                    inactivity
                );
            }

            if(response){
                console.log("callBreakOutAPI called...", response)
                hideLoader()
            }

            console.log("callBreakOutAPI: ", response)
        }catch(err){
            hideLoader()
            console.error("Break out API error")
        }
    }

    async function callInactivityAPI(){
        try{
            const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
            const comment = document.getElementById("comment2").value;
               console.log(comment)

            const response = await api.inactivity(
                userData.EID,
                "inactivity"
            );
            if(response){
                console.log("callInactivityAPI called...", response)
                hideLoader()
            }
            console.log("callInactivityAPI: ", response)
        }catch(err){
            hideLoader()
            console.error("Inactivity API error")
        }
    }

    async function callLogoutInactivityAPI(){
        try{
            const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
            const comment = document.getElementById("comment2").value;
               console.log(comment)
            const response = await api.logoutinactivity(
                userData.EID
            );
            if(response){
                console.log("callLogoutInactivityAPI called...", response)
                hideLoader()
            }
            console.log("callLogoutInactivityAPI: ", response)
        }catch(err){
            hideLoader()
            console.error("callLogoutInactivityAPI API error")
        }
    }

    async function logoutInactivityAPI(){
        try{
            const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
            const response = await api.logoutinactivity(
                userData.EID
            );
            if(response){
                console.log("logoutInactivityAPI called...", response)
                hideLoader()
            }
            console.log("logoutInactivityAPI: ", response)
        }catch(err){
            hideLoader()
            console.error("Inactivity API error")
        }
    }

    async function getServiceAPI(userId) {
        try {
            const response = await api.getservice(userId);
            const parsed = JSON.parse(response);

            if (parsed.status === true) {
                console.log("getServiceAPI called...", response)
                return parsed.data;
            } else {
                console.warn("getServiceAPI returned status false:", parsed.message || parsed);
                return null;
            }
        } catch (err) {
            hideLoader();
            console.error("getServiceAPI API error", err);
            return null;
        }
    }



    async function logoutAPI(){
        try {
            stopShiftTimer();
            pauseBreakTimer();

            const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
            const response = await api.logout(
                userData.EID || "",
                userData.EOD || "",
                userData.TotalChats || 0,
                userData.TotalBillableChat || 0
            );
            if(response){
                console.log("logoutAPI called...", response)
                hideLoader()
            }

            document.getElementById("dashboard").style.display = "none";
            document.getElementById("loginPage").style.display = "block";
            document.getElementById("back_button").style.display = "none";

            document.getElementById("play").style.pointerEvents = "auto";
            document.getElementById("play").style.opacity = "1";
            localStorage.clear();

        } catch (err) {
            hideLoader()
            console.warn("Logout API failed, proceeding anyway");
        }
    }

    async function requestForAccessAPI(uid){
        showLoader();

        try {
            if (!window.pywebview || !api || typeof api.requestforaccess !== 'function') {
                throw new Error("PyWebView API is not available.");
            }

            const response = await api.requestforaccess(uid);

            if (!response) {
                throw new Error("No response from backend.");
            }

            const resData = JSON.parse(response);

            if (resData.status) {
                alert(`Your request for login with ${resData.data.ip} IP has been sent successfully. You will get a confirmation email once your request is approved.`);
            } else {
                alert(`Request failed: ${resData.message || "Unknown error."}`);
            }

            console.log("Python response:", resData);
        } catch (err) {
            console.error("IP request error:", err);
            alert("An error occurred while sending the IP request. Please try again.");
        } finally {
            hideLoader();
        }
    }

    async function loadRememberMeData(){
        try {
            const saved = await api.get_remembered_user();
            console.log("Loaded saved user:", saved); // Debug output

            if (saved.email && saved.password) {

                emailInput.value = saved.email;
                passwordInput.value = saved.password;
                rememberMe.checked = true;
            }
        } catch (err) {
            console.error("Failed to load remembered user", err);
        }
    }

    async function getBreakTypes(){
        try{
            const userData = JSON.parse(localStorage.getItem("user_data") || "{}");
            const response = await api.getBreakTypes(
                userData.EID
            );
            if(response){
                console.log("getBreakTypes called...", response)
                populateBreakTypes(response)
                hideLoader()
            }

        }catch(err){
            hideLoader()
            console.error("Inactivity API error")
        }
    }



    async function versionCheck(){
        try {
            const version_info = await api.version_check();
            console.log("version_info:", version_info); // Debug output
            if(version_info.status){
<!--                document.getElementById("app_version").innerText = "version: " + version_info.data.version;-->
            }

        } catch (err) {
            console.error("Failed to load remembered user", err);
        }
    }

    async function getAppVersion(){
        const version = await api.get_version();

        console.log(version)
        document.getElementById("app_version").textContent = `Version: ${version}`;
    }

    async function checkForUpdates() {
        const result = await api.manual_check_update();
        document.getElementById("update-result").textContent = result;
    }


    setTimeout(async () => {
      const el = document.getElementById("empty_element");
      if (el) {
        el.click();
        loadRememberMeData()
        versionCheck()
        await getAppVersion()
        await getBreakTypes();
      }
    }, 1000);


    window.showInactivityWarningModal = async function () {
        showInactivityModal()
        stopShiftTimer()
        await callInactivityAPI()
        console.log("⚠️ Inactivity triggered from Python");

    }

    window.inactivityTimeExceed = async function () {
        console.log("⚠️ inactivityTimeExceed");
        hideInactivityModal()
        redirectLogin()
        await callBreakOutAPI("", true)
        await callLogoutInactivityAPI()


    }

<!--    function showInactivityModal() {-->
<!--        const modalEl = document.getElementById('exampleModal');-->
<!--        if (!modalEl) return;-->

<!--        const modal = new bootstrap.Modal(modalEl);-->
<!--        modal.show();-->
<!--    }-->

    window.showBreakModal = function (inactivity=false) {
        const modalEl = document.getElementById('breakModal');
        let modalInstance = bootstrap.Modal.getInstance(modalEl);
        if (!modalInstance) {
          modalInstance = new bootstrap.Modal(modalEl);
        }
        modalInstance.show();
      };

      window.showInactivityModal = function (inactivity = false) {
          const modalEl = document.getElementById('inactivityModal');
          let modalInstance = bootstrap.Modal.getInstance(modalEl);

          if (!modalInstance) {
            modalInstance = new bootstrap.Modal(modalEl, {
              backdrop: 'static', // Don't close on click outside
              keyboard: false     // Don't close on ESC key
            });
          }

          modalInstance.show();
        };









    function showConnectivityToast(isOnline) {
<!--      toastEl.classList.remove('bg-success', 'bg-danger');-->

      if (isOnline) {
<!--        toastEl.classList.add('bg-success');-->
<!--        toastBody.textContent = '✅ You are back online';-->
        internetOverlay.classList.add('d-none'); // Hide overlay
<!--        connectivityToast.show();-->
<!--        setTimeout(() => connectivityToast.hide(), 3000);-->
      } else {
<!--        toastEl.classList.add('bg-danger');-->
<!--        toastBody.textContent = '❌ You are offline';-->
        internetOverlay.classList.remove('d-none'); // Show overlay
<!--        connectivityToast.show(); // Stays until manually closed-->
      }
    }

    // Detect real browser connection status
    window.addEventListener('online', () => showConnectivityToast(true));
    window.addEventListener('offline', () => showConnectivityToast(false));

    // Initial state check on page load
    window.addEventListener('DOMContentLoaded', () => {
      if (!navigator.onLine) {
        showConnectivityToast(false);
      }
    });

    // Optional: simulate events for testing
<!--    document.getElementById('testOffline').addEventListener('click', () => showConnectivityToast(false));-->
<!--    document.getElementById('testOnline').addEventListener('click',  () => showConnectivityToast(true));-->

    window.onInternetDisconnectedTimeExceed = function onInternetDisconnectedTimeexceed() {
<!--        console.log("⚠️ No internet connection logging out. Please check your connection.");-->
        redirectLogin()
    }

    window.redirectLogin = function() {
        console.log("Redirecting due to system event...");
        redirectLogin()
    }





