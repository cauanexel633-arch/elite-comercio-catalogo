
"""
ELITE COMÉRCIO - APLICATIVO PARA PC DE VERDADE
Com ícone do selo anexado - Não abre navegador!
Janela nativa desktop com PyQt6 / pywebview
"""

import os, sys, pathlib, threading, time

BASE = pathlib.Path(__file__).parent
sys.path.insert(0, str(BASE))

# Esconde console no Windows
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

# Porta fixa
PORT = 5000

def run_flask_backend():
    """Roda o Flask em segundo plano sem abrir navegador"""
    try:
        import app as elite_app
        # Ativa auto sync
        elite_app.auto_sync_config["enabled"] = True
        elite_app.auto_sync_config["auto_push"] = True
        elite_app.auto_sync_config["auto_pull"] = True
        print(f"🚀 Flask backend rodando em http://127.0.0.1:{PORT}")
        elite_app.app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"Erro Flask: {e}")
        import traceback
        traceback.print_exc()

def run_as_desktop_app():
    """Cria janela de aplicativo de PC de verdade - com ícone do selo"""
    
    # Espera Flask iniciar
    time.sleep(1.5)
    
    # Tenta PyQt6 primeiro (melhor experiência desktop)
    try:
        from PyQt6.QtWidgets import QApplication, QMainWindow, QSplashScreen
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtCore import QUrl, Qt, QTimer
        from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
        import os
        
        print("🖥️ Criando app nativo com PyQt6...")
        
        app = QApplication(sys.argv)
        app.setApplicationName("Elite Comércio")
        app.setApplicationDisplayName("Elite Comércio")
        
        # Ícone do selo
        icon_path = BASE / "elite_icon.ico"
        if not icon_path.exists():
            icon_path = BASE / "logo.jpg"
        if not icon_path.exists():
            icon_path = BASE / "logo_novo.png"
        
        # Splash screen com logo enquanto carrega
        if icon_path.exists():
            try:
                pixmap = QPixmap(str(icon_path))
                if not pixmap.isNull():
                    # Cria splash
                    splash_pix = pixmap.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    splash = QSplashScreen(splash_pix)
                    splash.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
                    splash.show()
                    app.processEvents()
                    time.sleep(1)
                    splash.close()
            except:
                pass
        
        # Janela principal - APP DE VERDADE
        window = QMainWindow()
        window.setWindowTitle("Elite Comércio - Irecê BA")
        window.resize(1400, 900)
        window.setMinimumSize(1200, 700)
        
        # Define ícone da janela e da barra de tarefas
        if icon_path.exists():
            try:
                icon = QIcon(str(icon_path))
                window.setWindowIcon(icon)
                app.setWindowIcon(icon)
                print(f"✅ Ícone carregado: {icon_path}")
            except Exception as e:
                print(f"Erro ícone: {e}")
        
        # Webview que carrega o Flask - sem barra de endereço, parece app nativo
        webview = QWebEngineView()
        
        # Desabilita menu de contexto (clique direito) para parecer mais app
        webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        
        # Carrega o app local
        webview.setUrl(QUrl(f"http://127.0.0.1:{PORT}"))
        
        # Estilo da janela
        window.setCentralWidget(webview)
        
        # Mostra janela maximizada ou normal
        window.show()
        
        # Centraliza na tela
        try:
            screen = app.primaryScreen().geometry()
            window.move((screen.width() - window.width()) // 2, (screen.height() - window.height()) // 2)
        except:
            pass
        
        print("✅ App nativo Elite Comércio aberto! Janela própria, não é navegador!")
        print(f"🎨 Ícone: {icon_path} anexado na barra de tarefas")
        
        sys.exit(app.exec())
        
    except ImportError as e:
        print(f"PyQt6 não encontrado: {e}")
        print("Tentando pywebview...")
        
        try:
            import webview
            
            icon_path = BASE / "elite_icon.ico"
            
            print("🖥️ Criando app nativo com pywebview...")
            
            # Cria janela nativa sem navegador
            window = webview.create_window(
                title='Elite Comércio - Irecê BA',
                url=f'http://127.0.0.1:{PORT}',
                width=1400,
                height=900,
                min_size=(1200, 700),
                resizable=True,
                fullscreen=False,
                frameless=False,
                easy_drag=False,
                minimized=False,
                on_top=False,
                confirm_close=True,
                background_color='#080808',
                text_select=True
            )
            
            # Tenta setar ícone (pywebview usa ícone do sistema em algumas plataformas)
            print(f"✅ Janela nativa criada com ícone {icon_path}")
            print("✅ App de PC de verdade, não abre aba do Chrome!")
            
            webview.start(debug=False, http_server=False, icon=str(icon_path) if icon_path.exists() else None)
            
        except ImportError as e2:
            print(f"pywebview também não encontrado: {e2}")
            print("❌ Instale uma das opções:")
            print("   pip install PyQt6 PyQtWebEngine")
            print("   ou")
            print("   pip install pywebview")
            print("\n🌐 Fallback: Abrindo no navegador...")
            import webbrowser
            time.sleep(0.5)
            webbrowser.open(f"http://127.0.0.1:{PORT}")
            # Mantém rodando
            while True:
                time.sleep(1)

if __name__ == "__main__":
    print("="*70)
    print("🚀 ELITE COMÉRCIO - APLICATIVO PARA PC COM ÍCONE ANEXADO")
    print("="*70)
    print("✨ Janela própria, NÃO abre localhost no navegador")
    print("🎨 Ícone do selo Elite na barra de tarefas")
    print("💙💛 Liquid sync com bolhas azul/amarelo")
    print("🤖 Auto sync GitHub automático")
    print("="*70)
    
    # Inicia Flask em thread separada (backend)
    flask_thread = threading.Thread(target=run_flask_backend, daemon=True)
    flask_thread.start()
    
    # Inicia janela desktop nativa
    run_as_desktop_app()
