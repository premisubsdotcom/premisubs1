#!/usr/bin/env python3
"""
monitor_bot.py

- Creates/activates a venv in ./myenv
- Installs core deps (requests, beautifulsoup4) into the venv
- Every 30s checks https://premisubs1.vercel.app:
   • if <title> changed (or on first run), installs libs from libraries.txt,
     downloads bot.txt, writes bot.py, restarts it as a subprocess.
"""

import os
import sys
import subprocess
import time

VENV_DIR = os.path.join(os.path.dirname(__file__), 'myenv')
MAIN_SCRIPT = os.path.abspath(__file__)
PAGE_URL = 'https://premisubs1.vercel.app'
LIBS_URL = PAGE_URL + '/libraries.txt'
CHECK_INTERVAL = 30  # seconds

def ensure_venv_and_reexec():
    # 1) create venv if missing
    if not os.path.isdir(VENV_DIR):
        print('Creating virtualenv…')
        subprocess.run([sys.executable, '-m', 'venv', VENV_DIR], check=True)
    # path to the python executable inside venv
    venv_py = os.path.join(VENV_DIR, 'bin', 'python')
    # 2) if we're not already running in the venv, re-launch ourselves there
    if os.path.realpath(sys.executable) != os.path.realpath(venv_py):
        print('Re-launching inside venv…')
        os.execv(venv_py, [venv_py, MAIN_SCRIPT])

def install_core_deps():
    # ensure requests & bs4 are present so we can fetch & parse
    print('Installing core dependencies (requests, beautifulsoup4)…')
    subprocess.run([sys.executable, '-m', 'pip', 'install', 
                    'requests', 'beautifulsoup4'], check=True)

def install_external_libs():
    print(f'Fetching dependency list from {LIBS_URL} …')
    import requests  # now safe: venv + core deps installed
    r = requests.get(LIBS_URL)
    r.raise_for_status()
    lines = [
        l.strip() for l in r.text.splitlines()
        if l.strip() and not l.strip().startswith('#')
    ]
    if lines:
        print('Installing external libraries:', lines)
        subprocess.run([sys.executable, '-m', 'pip', 'install'] + lines, check=True)
    else:
        print('No external libraries to install.')

def fetch_page():
    import requests
    return requests.get(PAGE_URL).text

def parse_page(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.string.strip() if soup.title else ''
    a = soup.find('a', href=True)
    link = a['href'] if a else None
    return title, link

def run_bot(code_str, old_proc):
    # write out bot.py
    with open('bot.py', 'w') as f:
        f.write(code_str)
    # kill old if running
    if old_proc and old_proc.poll() is None:
        print('Stopping old bot process…')
        old_proc.terminate()
        try:
            old_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            old_proc.kill()
    # start new
    print('Starting new bot process…')
    return subprocess.Popen([sys.executable, 'bot.py'])

def main():
    last_title = None
    bot_proc = None

    while True:
        try:
            html = fetch_page()
            title, bot_url = parse_page(html)
            if title != last_title and bot_url:
                print(f'>>> Detected title change: "{last_title}" → "{title}"')
                install_external_libs()
                # fetch and run new code
                import requests
                r = requests.get(bot_url)
                r.raise_for_status()
                bot_proc = run_bot(r.text, bot_proc)
                last_title = title
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print('\nShutting down monitor…')
            if bot_proc and bot_proc.poll() is None:
                bot_proc.terminate()
            break
        except Exception as e:
            print('Error:', e)
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    ensure_venv_and_reexec()
    # from here on we're inside the venv
    install_core_deps()
    main()
