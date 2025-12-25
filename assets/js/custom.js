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

function displaySplashForApi(display) {
   const splash = document.getElementById("splash-screen");
   splash.style.display = display;
}

function startTimer() {
   const timerEl = document.getElementById("timer");
   const timeLabel = document.getElementById("time");

   // Create 60 ticks
   for (let i = 0; i < 60; i++) {
      const tick = document.createElement("div");
      tick.classList.add("tick");
      tick.style.transform = `rotate(${i * 6}deg) translateX(-50%)`;
      timerEl.appendChild(tick);
   }

   let minute = 0;
   const ticks = document.querySelectorAll(".tick");

   function updateTimer() {
      if (minute < 60) {
         ticks[minute].classList.add("active");
         timeLabel.textContent = 60 - (minute + 1);
         minute++;
      } else {
         clearInterval(timerInterval);
      }
   }

   const timerInterval = setInterval(updateTimer, 1000); // 1 tick = 1 second (for demo)
}

document.addEventListener("DOMContentLoaded", () => {
   displaySplashScreen()

   // Elements
   const emailInput = document.getElementById("email");
   const passwordInput = document.getElementById("password");
   const rememberCheckbox = document.getElementById("remember_me");
   const loginBtn = document.querySelector("button[type='submit']");
   const forgetLink = document.getElementById("forget_password");
   const registerLink = document.getElementById("register");

   // Login event
   loginBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      const email = emailInput.value;
      const password = passwordInput.value;
      const remember = rememberCheckbox.checked;

      const data = {
         email,
         password,
         remember
      };

      try {
         console.log("login API triggered")
         displaySplashForApi("block")
         const response = await window.pywebview.api.login(email, password);
         if (response) {
            const responseJson = JSON.parse(response)
            const {
               status,
               data
            } = responseJson
            console.log(responseJson)

            if (status) {
               displaySplashForApi("none")
               let empName = `${data.EmpFirstName} ${data.EmpLastName}`
               let empShift = `${data.ShiftStartTime} ${data.ShiftEndTime}`

               document.getElementById("empName").innerText = empName
               document.getElementById("empShift").innerText = empShift

               window.localStorage.setItem("user_data", JSON.stringify(data))

               document.getElementById("loginPage").style.display = "none";
               document.getElementById("dashboard").style.display = "block";
               startTimer()
            } else {
               displaySplashForApi("none")
               displaySplashForApi(display)
            }
         }

      } catch (err) {
         console.error("Login failed:", err);
      }
   });

   // Remember me (optional standalone handler)
   rememberCheckbox.addEventListener("change", () => {
      console.log("Remember me checked:", rememberCheckbox.checked);
   });

   // Forget password
   forgetLink.addEventListener("click", (e) => {
      e.preventDefault();
      const email = emailInput.value;
      window.pywebview.api.handleForgetPassword(email);
   });

   // Register
   registerLink.addEventListener("click", (e) => {
      e.preventDefault();
      const email = emailInput.value;
      window.pywebview.api.handleRegister(email);
   });
});

// Password toggle
const togglePassword = document.querySelector("#togglePassword")
const password = document.querySelector("#password");

togglePassword.addEventListener("click", function () {
   const type = password.getAttribute("type") === "password" ? "text" : "password";
   password.setAttribute("type", type);
   this.querySelector("i").classList.toggle("fa-eye-slash");
});


<!--dashboard events-- >

const breakLogsBtn = document.getElementById("break_logs");
const notificationsBtn = document.getElementById("notifications");
const settingsBtn = document.getElementById("settings");
const profileBtn = document.getElementById("profile");
const logoutBtn = document.getElementById("logout");
const mainDashboardLogo = document.getElementById("main-dashboard-logo");


// Prevent default link behavior
const navLinks = [breakLogsBtn, notificationsBtn, settingsBtn, profileBtn, logoutBtn];
navLinks.forEach(link => {
   link.addEventListener("click", (e) => e.preventDefault());
});

mainDashboardLogo.addEventListener("click", (e) => {
   console.log("main logo dashboard");
   document.getElementById("loginPage").style.display = "none";
   document.getElementById("dashboard_content").style.display = "block";
   document.getElementById("break_logs_content").style.display = "none";
   // Show notifications section
});

// Add actions for each
breakLogsBtn.addEventListener("click", (e) => {
   e.preventDefault()
   console.log("Break Logs clicked");
   document.getElementById("loginPage").style.display = "none";
   document.getElementById("dashboard_content").style.display = "none";
   document.getElementById("break_logs_content").style.display = "block";
   // Show break logs section or modal
});

notificationsBtn.addEventListener("click", (e) => {
   console.log("Notifications clicked");
   // Show notifications section
});

settingsBtn.addEventListener("click", () => {
   console.log("Settings clicked");
   // Show settings section
});

profileBtn.addEventListener("click", () => {
   console.log("Profile clicked");
   // Show profile section or user details
});

logoutBtn.addEventListener("click", async () => {
   console.log("Logout clicked");
   // Switch to login screen
   const userData = window.localStorage.getItem("user_data")
   if (userData) {
      let userDataJson = JSON.parse(userData)
      let {
         EID,
         EOD,
         TotalChats,
         TotalBillableChat
      } = userDataJson
      console.log(userDataJson)


      try {
         console.log("logout API triggered")
         const response = await window.pywebview.api.logout(EID, EOD, TotalChats, TotalBillableChat);
         if (response) {
            const responseJson = JSON.parse(response)
            const {
               status,
               data
            } = responseJson
            console.log(responseJson)
            document.getElementById("dashboard").style.display = "none";
            document.getElementById("loginPage").style.display = "block";
            return

         }

      } catch (err) {
         console.error("Login failed:", err);
      }

   }


});