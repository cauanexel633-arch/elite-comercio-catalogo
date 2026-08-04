
# -*- coding: utf-8 -*-
import os, sys, pathlib, threading, time

# Fix encoding para evitar charmap error no Windows
if sys.platform == "win32":
    try:
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
        sys.stderr.reconfigure(encoding='utf-8', errors='ignore')
    except:
        pass
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

BASE = pathlib.Path(__file__).parent
sys.path.insert(0, str(BASE))

PORT = 5000

def run_flask_backend():
    try:
        import app as elite_app
        elite_app.auto_sync_config["enabled"] = True
        elite_app.auto_sync_config["auto_push"] = True
        elite_app.auto_sync_config["auto_pull"] = True
        elite_app.app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        # Sem acento para evitar charmap
        try:
            print(f"Erro Flask: {e}")
        except:
            pass

def run_desktop():
    time.sleep(2)
    try:
        import webview
        icon_path = BASE / "elite_icon.ico"
        if not icon_path.exists():
            icon_path = None
        
        # Cria janela nativa - usa Edge do Windows, sem Qt
        window = webview.create_window(
            title='Elite Comercio - Irece BA',
            url=f'http://127.0.0.1:{PORT}',
            width=1400,
            height=900,
            min_size=(1200, 700),
            resizable=True,
            background_color='#080808',
            text_select=True
        )
        
        # Inicia com Edge, sem debug
        webview.start(debug=False, http_server=False)
        
    except Exception as e:
        # Fallback sem acento
        try:
            print(f"Erro webview: {e}")
        except:
            pass
        try:
            import webbrowser
            time.sleep(0.5)
            webbrowser.open(f"http://127.0.0.1:{PORT}")
            while True:
                time.sleep(1)
        except:
            pass

if __name__ == "__main__":
    t = threading.Thread(target=run_flask_backend, daemon=True)
    t.start()
    run_desktop()
