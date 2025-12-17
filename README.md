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

---

## License

MIT License
