#!/usr/bin/env python3
"""
monitor_bot.py (robust)

- Creates/activates a venv in ./myenv (tries stdlib venv, then virtualenv)
- If venv isn't possible, falls back to local --target deps in ./_deps
- Installs core deps (requests, beautifulsoup4)
- Every 30s checks https://premisubs1.vercel.app:
   • if <title> changed (or on first run), installs libs from libraries.txt,
     downloads bot code from the first <a href>, writes bot.py, restarts it.
"""
import os
import sys
import subprocess
import time
from urllib.parse import urljoin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, 'myenv')
LOCAL_DEPS = os.path.join(BASE_DIR, '_deps')
MAIN_SCRIPT = os.path.abspath(__file__)
PAGE_URL = 'https://premisubs1.vercel.app'
LIBS_URL = PAGE_URL + '/libraries.txt'
CHECK_INTERVAL = 30  # seconds

def _venv_python_path(venv_dir: str) -> str:
    if os.name == 'nt':
        return os.path.join(venv_dir, 'Scripts', 'python.exe')
    else:
        return os.path.join(venv_dir, 'bin', 'python')

def _try_create_venv():
    """Try stdlib venv first; if ensurepip is missing, fall back to virtualenv."""
    if os.path.isdir(VENV_DIR):
        return True
    try:
        print('Creating virtualenv via stdlib venv…')
        subprocess.run([sys.executable, '-m', 'venv', VENV_DIR], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print('Stdlib venv failed (likely ensurepip missing):', e)
        # Fallback to virtualenv
        try:
            print('Attempting fallback to virtualenv…')
            subprocess.run([sys.executable, '-m', 'pip', 'install', '--user', 'virtualenv'], check=True)
            subprocess.run([sys.executable, '-m', 'virtualenv', VENV_DIR], check=True)
            return True
        except Exception as e2:
            print('virtualenv fallback failed:', e2)
            return False

def _activate_local_target_site():
    """Use a local site-packages via pip --target as last resort."""
    print('Using local --target dependency dir at', LOCAL_DEPS)
    os.makedirs(LOCAL_DEPS, exist_ok=True)
    # Prepend to sys.path so imports work immediately
    if LOCAL_DEPS not in sys.path:
        sys.path.insert(0, LOCAL_DEPS)

def ensure_env_and_reexec():
    """
    Ensure we run inside an isolated environment if possible.
    Order: stdlib venv -> virtualenv -> local --target
    """
    # Already inside our venv?
    if os.path.abspath(getattr(sys, 'prefix', '')) == os.path.abspath(VENV_DIR):
        return  # we’re in the venv already

    if _try_create_venv():
        venv_py = _venv_python_path(VENV_DIR)
        if not os.path.exists(venv_py):
            raise RuntimeError(f"Venv python not found at {venv_py}")
        print('Re-launching inside venv…')
        os.execv(venv_py, [venv_py, MAIN_SCRIPT])

    # If we reached here, no venv could be created → fallback to local target
    _activate_local_target_site()

def _pip_install(args):
    """Run pip install with sane defaults."""
    cmd = [sys.executable, '-m', 'pip', 'install', '--no-input', '--disable-pip-version-check']
    subprocess.run(cmd + args, check=True)

def install_core_deps():
    print('Ensuring core dependencies (requests, beautifulsoup4)…')
    try:
        import requests  # noqa: F401
        from bs4 import BeautifulSoup  # noqa: F401
        print('Core dependencies already present.')
        return
    except Exception:
        pass
    try:
        _pip_install(['requests', 'beautifulsoup4'])
    except subprocess.CalledProcessError:
        # If we’re on fallback mode, ensure local target exists and try --target
        print('Standard install failed; trying --target local deps…')
        os.makedirs(LOCAL_DEPS, exist_ok=True)
        _pip_install(['--target', LOCAL_DEPS, 'requests', 'beautifulsoup4'])

def install_external_libs():
    print(f'Fetching dependency list from {LIBS_URL} …')
    import requests
    r = requests.get(LIBS_URL, timeout=30)
    r.raise_for_status()
    lines = [l.strip() for l in r.text.splitlines() if l.strip() and not l.strip().startswith('#')]
    if lines:
        print('Installing external libraries:', lines)
        try:
            _pip_install(lines)
        except subprocess.CalledProcessError:
            print('Standard external install failed; trying --target local deps…')
            os.makedirs(LOCAL_DEPS, exist_ok=True)
            _pip_install(['--target', LOCAL_DEPS] + lines)
    else:
        print('No external libraries to install.')

def fetch_page():
    import requests
    return requests.get(PAGE_URL, timeout=30).text

def parse_page(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    title = (soup.title.string.strip() if soup.title and soup.title.string else '')
    a = soup.find('a', href=True)
    link = urljoin(PAGE_URL, a['href']) if a else None  # resolve relative URLs
    return title, link

def run_bot(code_str, old_proc):
    with open('bot.py', 'w', encoding='utf-8') as f:
        f.write(code_str)
    if old_proc and old_proc.poll() is None:
        print('Stopping old bot process…')
        old_proc.terminate()
        try:
            old_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            old_proc.kill()
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
                import requests
                r = requests.get(bot_url, timeout=30)
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
    ensure_env_and_reexec()
    # from here on we're inside the venv OR using local --target deps
    install_core_deps()
    main()
