# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

import os
import sys
from pathlib import Path
from typing import Optional, Callable

# Safe import to handle headless environments
try:
    from PyQt6.QtCore import Qt, QUrl, QTimer, QEventLoop
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


class ManifestorAutomator:
    """
    Automates downloading .lua manifest files from openlua.cloud using a hidden WebEngine browser.
    """
    TARGET_URL = "https://openlua.cloud/"

    def __init__(self, download_dir: Path):
        self.download_dir = download_dir
        self.hidden_browser: Optional[QWebEngineView] = None
        self.pending_appid: Optional[int] = None
        self.manifestor_loaded = False
        self.downloaded_file: Optional[Path] = None
        self.loop: Optional[QEventLoop] = None
        self.error_msg: Optional[str] = None
        self.on_progress: Optional[Callable[[str], None]] = None

    def _log(self, msg: str):
        if self.on_progress:
            self.on_progress(msg)
        else:
            print(f"[Manifestor] {msg}")

    def download_lua_sync(self, appid: int, timeout_sec: int = 30) -> Optional[Path]:
        """
        Bloqueia (sincronamente) até que o arquivo lua do appid seja baixado.
        Retorna o caminho para o arquivo baixado ou None em caso de falha/timeout.
        """
        if not PYQT_AVAILABLE:
            self._log("PyQt6 ou PyQt6-WebEngine não estão instalados.")
            return None

        app = QApplication.instance()
        created_app = False
        if app is None:
            # We are running from CLI without an active GUI
            # Needs dummy args because QApplication takes sys.argv
            app = QApplication(sys.argv)
            created_app = True

        self.pending_appid = appid
        self.downloaded_file = None
        self.error_msg = None

        self._log("Iniciando browser oculto...")
        self.hidden_browser = QWebEngineView()
        self.hidden_browser.hide()
        self.hidden_browser.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

        self.web_profile = self.hidden_browser.page().profile()
        self.web_profile.clearHttpCacheCompleted.connect(self._on_cache_cleared)
        self.web_profile.clearHttpCache()

        # Usar um EventLoop para tornar a função síncrona enquanto a GUI roda em background
        self.loop = QEventLoop()
        
        # Setup timeout
        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(self._on_timeout)
        timeout_timer.start(timeout_sec * 1000)

        # Inicia loop (bloqueia aqui)
        self.loop.exec()

        timeout_timer.stop()
        
        # Cleanup
        self.hidden_browser.deleteLater()
        self.hidden_browser = None
        
        if created_app:
            app.quit()
            
        if self.error_msg:
            self._log(f"Erro: {self.error_msg}")
            
        return self.downloaded_file

    def _on_cache_cleared(self):
        self._log("Conectando a openlua.cloud...")
        self.web_profile.downloadRequested.connect(self._handle_download_request)
        self.hidden_browser.loadFinished.connect(self._on_manifestor_load_finished)
        self.hidden_browser.setUrl(QUrl(self.TARGET_URL))

    def _on_manifestor_load_finished(self, success: bool):
        if not success:
            self.error_msg = "Falha ao carregar openlua.cloud"
            if self.loop:
                self.loop.quit()
            return

        self._log("OpenLua.cloud carregado. Injetando automação...")
        self.manifestor_loaded = True

        js_close_modal = """
            setTimeout(function() {
                var closeButton = document.getElementById('welcome-close');
                if (closeButton) {
                    closeButton.click();
                }
                document.body.classList.remove('modal-open');
            }, 800);
        """
        self.hidden_browser.page().runJavaScript(js_close_modal)

        if self.pending_appid is not None:
            appid = self.pending_appid
            self.pending_appid = None
            self._inject_and_download(appid)

    def _inject_and_download(self, appid: int):
        js_code = f"""
            (function() {{
                try {{
                    // Encontra o campo de busca
                    var input = document.querySelector('input[placeholder*="Search for a game"]')
                               || document.querySelector('input[placeholder*="Search for a game or enter AppID"]')
                               || document.querySelector('input');

                    if (!input) return 'no-input';

                    input.focus();
                    input.value = '{appid}';

                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));

                    var evDown = new KeyboardEvent('keydown', {{ key: 'Enter', keyCode: 13, which: 13, bubbles: true }});
                    var evUp   = new KeyboardEvent('keyup',   {{ key: 'Enter', keyCode: 13, which: 13, bubbles: true }});
                    input.dispatchEvent(evDown);
                    input.dispatchEvent(evUp);

                    // Tenta achar e clicar no botão de Download
                    setTimeout(function() {{
                        var btn = null;
                        var candidates = document.querySelectorAll('button, a');
                        candidates.forEach(function(el) {{
                            if (!btn && /download/i.test(el.textContent || '')) {{
                                btn = el;
                            }}
                        }});
                        if (btn) btn.click();
                    }}, 1500);

                    return 'ok';
                }} catch (e) {{
                    return 'error';
                }}
            }})();
        """
        self.hidden_browser.page().runJavaScript(js_code)
        self._log(f"Automação injetada para o AppID {appid}. Aguardando download...")

    def _handle_download_request(self, download: QWebEngineDownloadRequest):
        self.download_dir.mkdir(parents=True, exist_ok=True)
        suggested_filename = download.suggestedFileName()
        
        # Verifica se realmente é o .lua que queremos
        if not suggested_filename.endswith(".lua"):
            self._log(f"Aviso: Interceptado arquivo ignorado: {suggested_filename}")
            return

        final_path = self.download_dir / suggested_filename
        
        download_dir_qt = str(self.download_dir).replace("\\", "/")
        download.setDownloadDirectory(download_dir_qt)
        download.setDownloadFileName(suggested_filename)
        self._log(f"Interceptando manifest: {suggested_filename}")

        def download_state_changed(state):
            if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                if final_path.exists():
                    self._log(f"Sucesso! Arquivo salvo em: {final_path}")
                    self.downloaded_file = final_path
                else:
                    self.error_msg = "Download reportado como completo mas arquivo não foi encontrado."
                if self.loop:
                    self.loop.quit()

            elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
                self.error_msg = f"Download interrompido para {suggested_filename}"
                if self.loop:
                    self.loop.quit()

        download.stateChanged.connect(download_state_changed)
        download.accept()

    def _on_timeout(self):
        if self.loop and self.loop.isRunning():
            self.error_msg = "Timeout alcançado (30s). Manifestor ou Cloudflare pode ter bloqueado."
            self.loop.quit()
