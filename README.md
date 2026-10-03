# Desktop Application (Python + PyWebView)

This is a Python-based desktop application built using PyWebView and packaged into a standalone executable using PyInstaller.

---

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

---

## Install Dependencies

Install all required dependencies by running:

pip install pywebview requests portalocker pillow cryptography psutil pyinstaller

---

## Run Application Locally

To run the application in local development mode:

python main.py

---

## Build Executable

To generate a single-file executable, use the following command:

pyinstaller --onefile --noconsole --icon=setup.ico --add-data "setup.ico;." --add-data "index.html;." --add-data "splash.png;." --add-data "assets;assets" main.py

After the build is complete, the executable will be created inside the `dist` directory.

---

## Included Files

The following resources are bundled into the executable:

- setup.ico (Application icon)
- index.html (UI entry file)
- splash.png (Splash screen)
- assets/ (Static files and resources)

---

## Dependencies

- pywebview
- requests
- portalocker
- pillow
- cryptography
- psutil
- pyinstaller

---

## Platform Support

- Windows

---

## Notes

- Run all commands from the project root directory.
- Make sure all required files exist before building the executable.
- Recommended Python version is 3.8 or higher.
- Screenshot uploads may include a desk token (`POST /desktoken/issue` on `https://worktre.com`). The token, username, and password are form fields only — never query parameters, and desk-token logs record an employee id at most, never the username, password, token, or raw server error text. The upload stays `requests.post(..., data=dict)` so base64 `+` is sent as `%2B`. A capture whose base64 is over 6 MB is re-encoded as JPEG (quality 80) and downscaled until it fits. 6 MB is a conservative backstop because the live `post_max_size` is not known and may be PHP's default 8M. An upload that comes back HTTP 413, or HTTP 400 with `too_large`, `payload_too_large`, or `file_too_large`, is retried once as a JPEG downscaled under 3 MB. Any other `400` is not retried. A `/desktoken` `503` with `busy` waits for `Retry-After` (30 seconds if the header is missing) and does not use the outage backoff. Remember me and the token are stored with Windows DPAPI. A legacy Fernet remember-me file is migrated once, read back, and only then deleted. Heartbeats keep running if a token cannot be obtained; the upload then omits the token. SOAP login is unchanged.

## Tests

```
pip install pytest
pytest
python -m py_compile src/utils/dpapi.py src/utils/desk_token.py src/utils/security.py src/utils/screenshot.py src/main.py
```

---

## License

MIT License
