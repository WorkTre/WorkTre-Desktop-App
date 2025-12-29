#!/usr/bin/env python3
import sass
import os
from pathlib import Path
import sys


def compile_scss():
    # Define paths
    scss_dir = Path('scss')
    css_dir = Path('assets/css')

    # Ensure CSS directory exists
    css_dir.mkdir(parents=True, exist_ok=True)

    # Main SCSS file
    main_scss = scss_dir / 'main.scss'
    output_css = css_dir / 'style.css'

    if not main_scss.exists():
        print(f"Error: {main_scss} not found!")
        return False

    try:
        # Compile SCSS to CSS
        css = sass.compile(filename=str(main_scss), output_style='compressed')

        # Write to CSS file
        with open(output_css, 'w') as f:
            f.write(css)

        print(f"✅ SCSS compiled successfully to {output_css}")
        return True

    except Exception as e:
        print(f"❌ Error compiling SCSS: {e}")
        return False


def watch_scss():
    """Watch for SCSS file changes (requires watchdog)"""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class SCSSHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.src_path.endswith('.scss'):
                    print(f"📁 {event.src_path} changed. Recompiling...")
                    compile_scss()

        event_handler = SCSSHandler()
        observer = Observer()
        observer.schedule(event_handler, path='scss', recursive=True)
        observer.start()

        print("👀 Watching SCSS files for changes... (Press Ctrl+C to stop)")

        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    except ImportError:
        print("⚠️  Install watchdog for live reload: pip install watchdog")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'watch':
        # Install required package if not present
        try:
            import watchdog
        except ImportError:
            print("Installing watchdog...")
            import subprocess

            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'watchdog'])

        watch_scss()
    else:
        compile_scss()