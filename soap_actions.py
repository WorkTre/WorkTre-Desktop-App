class SOAPActionBuilder:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def action(self, name: str) -> str:
        if not name:
            raise ValueError("SOAP action name cannot be empty")
        return f"{self.base_url}/{name}"

    # ---- Authentication & Login ----
    def login(self):
        return self.action("login")

    def logout(self):
        return self.action("logout")

    def crashlogin(self):
        return self.action("crashlogin")

    def requestforaccess(self):
        return self.action("requestforaccess")

    # ---- Activity & Monitoring ----
    def lastactivitydate(self):
        return self.action("lastactivitydate")

    def getservice(self):
        return self.action("getservice")

    def inactivity(self):
        return self.action("inactivity")

    def logoutinactivity(self):
        return self.action("logoutinactivity")

    # ---- Break Management ----
    def breakin(self):
        return self.action("breakin")

    def breakout(self):
        return self.action("breakout")

    def getBreakTypes(self):
        return self.action("getBreakTypes")

    # ---- System & Version ----
    def versioncheck(self):
        return self.action("versioncheck")

    # ---- Helper Methods ----
    def get_user_data(self):
        return self.action("getUserData")

    def update_status(self):
        return self.action("updateStatus")
