#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fileder v1.1 - Ein leistungsstarkes Werkzeug zum Durchsuchen von Dateien nach Textketten.

Durchsucht Dateien, Archive und Verzeichnisse nach bestimmten Textmustern und
stellt Informationen über die Fundstellen bereit.

"""

import os
import re
import json
import argparse
import datetime
import mimetypes
import sys
import configparser
import shutil
import time
import logging
import platform
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed  # <--- NEU für Multithreading

# Optionale Imports - werden später überprüft und bei Bedarf installiert
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_available = True
    colorama_init(autoreset=True)  # autoreset=True für bessere Lesbarkeit
except ImportError:
    # Fallback für fehlende Colorama-Bibliothek
    colorama_available = False
    # Dummy-Klassen für Fore und Style
    class DummyColorClass:
        def __getattr__(self, name):
            return ""
    Fore = DummyColorClass()
    Style = DummyColorClass()

# Weitere optionale Imports - werden in check_dependencies() geprüft
try:
    import chardet
    chardet_available = True
except ImportError:
    chardet_available = False

try:
    from tabulate import tabulate
    tabulate_available = True
except ImportError:
    tabulate_available = False
    # Einfache Ersatzfunktion für tabulate
    def tabulate(data, headers, tablefmt=None):
        result = []
        # Header hinzufügen
        if headers:
            result.append(" | ".join(headers))
            result.append("-" * (sum(len(h) for h in headers) + 3 * (len(headers) - 1)))
        
        # Daten hinzufügen
        for row in data:
            result.append(" | ".join(str(cell) for cell in row))
        
        return "\n".join(result)

# Archive-Module prüfen
try:
    import zipfile
    zipfile_available = True
except ImportError:
    zipfile_available = False

try:
    import gzip
    gzip_available = True
except ImportError:
    gzip_available = False

try:
    import tarfile
    tarfile_available = True
except ImportError:
    tarfile_available = False

# Konfigurationswerte
DEFAULT_CONFIG = {
    "general": {
        "context_chars": 20,
        "max_file_size_mb": 100,
        "search_hidden_files": False,
        "timeout_seconds": 10,
        "log_level": "INFO"
    },
    "filters": {
        "excluded_extensions": ".exe,.dll,.bin,.iso,.img,.zip,.tar.gz,.7z",
        "included_extensions": "",
        "max_depth": 5,
        "excluded_paths": ""
    },
    "output": {
        "save_results": True,
        "results_folder": "search_results",
        "highlight_matches": True
    }
}

script_dir = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(script_dir, "fileder.log")
CONFIG_FILE = os.path.join(script_dir, "fileder_config.ini")

# Logger einrichten
logger = logging.getLogger("Fileder")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Konsolenausgabe
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Dateien, die als Text gelesen werden können
TEXT_EXTENSIONS = {
    '.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv', '.md', 
    '.ini', '.cfg', '.conf', '.log', '.c', '.cpp', '.h', '.hpp', '.java', 
    '.sh', '.bat', '.ps1', '.yaml', '.yml', '.sql', '.php', '.rb'
}

#############################################
# System-Erkennungsmodul
#############################################

class SystemDetector:
    """Erkennt Betriebssystem-Details und gibt plattformspezifische Informationen."""
    
    def __init__(self):
        """Initialisiert den SystemDetector und erkennt Plattforminformationen."""
        # Grundlegende Werte initialisieren
        self.os_name = "Unbekannt"
        self.os_version = "Unbekannt"
        self.os_release = "Unbekannt"
        self.architecture = "Unbekannt"
        self.python_version = "Unbekannt"
        
        # Plattform-Flags
        self.is_windows = False
        self.is_macos = False
        self.is_linux = False
        
        # Zusätzliche Details
        self.has_fulldisc_access = False
        self.is_admin = False
        self.is_root = False
        self.macos_version = "Unbekannt"
        self.distro = "Unbekannt"
        
        try:
            # Grundlegende Plattforminformationen ermitteln
            self.os_name = platform.system()
            self.os_version = platform.version()
            self.os_release = platform.release()
            self.architecture = platform.machine()
            self.python_version = platform.python_version()
            
            # Betriebssystem erkennen
            self.is_windows = self.os_name == 'Windows'
            self.is_macos = self.os_name == 'Darwin'
            self.is_linux = self.os_name == 'Linux'
            
            # Spezifische OS-Details ermitteln
            if self.is_windows:
                self._setup_windows_specifics()
            elif self.is_macos:
                self._setup_macos_specifics()
            elif self.is_linux:
                self._setup_linux_specifics()
                
        except Exception as e:
            logger.error(f"Fehler bei Systemerkennung: {e}")
            # Basis-OS-Erkennung als Fallback
            self.is_windows = "Windows" in platform.system()
            self.is_macos = "Darwin" in platform.system()
            self.is_linux = "Linux" in platform.system()
    
    def _setup_windows_specifics(self):
        """Ermittelt Windows-spezifische Details sicher."""
        try:
            # Sicherere Admin-Rechteerkennung
            self.is_admin = self._check_admin_privileges_safely()
        except Exception as e:
            logger.debug(f"Fehler bei Windows-Admin-Prüfung: {e}")
            self.is_admin = False
    
    def _setup_macos_specifics(self):
        """Ermittelt macOS-spezifische Details."""
        try:
            # Für macOS: Vollzugriff prüfen (vereinfacht)
            self.has_fulldisc_access = self._check_fulldisc_access_safely()
        except Exception as e:
            logger.debug(f"Fehler bei macOS-Erkennung: {e}")
            self.has_fulldisc_access = False
    
    def _setup_linux_specifics(self):
        """Ermittelt Linux-spezifische Details."""
        try:
            # Root-Rechte prüfen (nur unter Linux)
            if hasattr(os, 'geteuid'):
                self.is_root = os.geteuid() == 0
            
            # Linux-Distribution ermitteln
            self.distro = self._get_linux_distro_safely()
        except Exception as e:
            logger.debug(f"Fehler bei Linux-Erkennung: {e}")
            self.is_root = False
    
    def _check_admin_privileges_safely(self):
        """Überprüft Admin-Rechte unter Windows sicher."""
        # Methode 1: ctypes verwenden (sicherer Weg)
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except:
            pass
        
        # Methode 2: Sicherer Test über Dateisystem
        try:
            # Weniger invasiver Test - System32 nur auf Existenz prüfen
            system32_path = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32')
            return os.path.exists(system32_path) and os.access(system32_path, os.W_OK)
        except:
            pass
        
        # Wenn alle Tests fehlschlagen, gehen wir vom ungünstigeren Fall aus
        return False
    
    def _check_fulldisc_access_safely(self):
        """Überprüft macOS Festplattenvollzugriff sicher."""
        try:
            # Sicherere Überprüfung über Standard-Bibliotheksverzeichnisse
            test_path = '/Library/Application Support'
            
            if os.path.exists(test_path):
                try:
                    # Nur prüfen, ob wir lesen können (nicht scandir)
                    os.listdir(test_path)
                    return True
                except PermissionError:
                    return False
        except:
            pass
        
        return False
    
    def _get_linux_distro_safely(self):
        """Ermittelt die Linux-Distribution auf sichere Weise."""
        try:
            # Standardweg: /etc/os-release
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    for line in f:
                        if line.startswith('PRETTY_NAME='):
                            return line.split('=')[1].strip().strip('"')
            
            return "Unbekannte Linux-Distribution"
        except:
            return "Unbekannt"
    
    def show_system_info(self):
        """Zeigt Informationen zum Betriebssystem an."""
        info_text = f"\n    === System-Informationen ===\n"
        info_text += f"    Betriebssystem: {self.os_name} {self.os_release}\n"
        info_text += f"    Python-Version: {self.python_version}\n"
        
        if self.is_macos:
            info_text += f"    Festplattenvollzugriff: {'Wahrscheinlich ja' if self.has_fulldisc_access else 'Wahrscheinlich nein'}\n"
        
        if self.is_windows:
            info_text += f"    Admin-Rechte: {'Ja' if self.is_admin else 'Nein'}\n"
        
        if self.is_linux:
            info_text += f"    Linux-Distribution: {self.distro}\n"
            info_text += f"    Root-Rechte: {'Ja' if self.is_root else 'Nein'}\n"
        
        return info_text
    
    def get_platform_specific_tips(self):
        """Gibt plattformspezifische Tipps zurück."""
        tips = "\n    === Tipps für Ihr Betriebssystem ===\n"
        
        if self.is_macos:
            tips += "    • macOS-spezifische Tipps:\n"
            tips += "      - Für vollen Zugriff auf geschützte Ordner müssen Sie Terminal oder Python in\n"
            tips += "        Systemeinstellungen > Sicherheit > Datenschutz > Festplattenvollzugriff hinzufügen.\n"
            
            if not self.has_fulldisc_access:
                tips += "      ! Hinweis: Fileder hat wahrscheinlich KEINEN Festplattenvollzugriff. Einige Verzeichnisse werden nicht durchsucht.\n"
        
        elif self.is_windows:
            tips += "    • Windows-spezifische Tipps:\n"
            tips += "      - Für Zugriff auf geschützte System-Ordner führen Sie das Programm als Administrator aus.\n"
            
            if not self.is_admin:
                tips += "      ! Hinweis: Fileder läuft NICHT mit Administratorrechten. Einige Systemordner werden nicht durchsucht.\n"
        
        elif self.is_linux:
            tips += "    • Linux-spezifische Tipps:\n"
            tips += "      - Für Zugriff auf geschützte Ordner führen Sie das Programm mit sudo aus (falls notwendig).\n"
            
            if not self.is_root:
                tips += "      ! Hinweis: Fileder läuft NICHT mit Root-Rechten. Einige Systemordner werden nicht durchsucht.\n"
        
        return tips

    def suggest_excluded_paths(self):
        """Gibt für das aktuelle System empfohlene auszuschließende Pfade zurück."""
        excluded_paths = []
        
        if self.is_macos:
            excluded_paths = [
                "/System",
                "/private/var/vm",
                "/Library/Caches",
                "~/Library/Caches"
            ]
        
        elif self.is_windows:
            excluded_paths = [
                "C:\\Windows\\System32",
                "C:\\Windows\\SysWOW64",
                "C:\\$Recycle.Bin"
            ]
        
        elif self.is_linux:
            excluded_paths = [
                "/proc",
                "/sys",
                "/dev",
                "/run",
                "/tmp"
            ]
        
        return excluded_paths

#############################################
# Berechtigungsmodul
#############################################

class PermissionHandler:
    """Behandelt plattformspezifische Berechtigungsprobleme."""
    
    def __init__(self):
        """Initialisierung des PermissionHandler."""
        self.is_macos = platform.system() == 'Darwin'
        self.requested_directories = set()  # Verzeichnisse, für die bereits Zugriff angefragt wurde
    
    def check_permission(self, directory):
        """Überprüft, ob das Verzeichnis zugänglich ist."""
        try:
            return os.access(directory, os.R_OK)
        except Exception:
            return False
    
    def show_permission_instructions(self, directory):
        """Zeigt dem Benutzer Anweisungen, wie er Berechtigungen erteilen kann."""
        if not self.is_macos:
            print(f"\n    Sie haben keine Leseberechtigungen für: {directory}")
            print("    Bitte führen Sie das Programm mit höheren Berechtigungen aus oder ändern Sie die Dateiberechtigungen.")
            return False
        
        # Spezieller Hinweis für macOS
        print("\n    Zugriff auf geschützten Ordner benötigt:")
        print("    1. Öffnen Sie die Systemeinstellungen")
        print("    2. Gehen Sie zu 'Sicherheit & Datenschutz' > 'Datenschutz' > 'Festplattenvollzugriff'")
        print("    3. Fügen Sie Terminal oder Python zur Liste hinzu")
        print("    4. Starten Sie Terminal und dieses Programm neu")
        
        return False
    
    def should_request_permission(self, directory):
        """Prüft, ob für dieses Verzeichnis bereits Berechtigungen angefragt wurden."""
        directory = os.path.normpath(directory)
        
        # Prüfen, ob für dieses Verzeichnis oder ein übergeordnetes bereits angefragt wurde
        for requested_dir in self.requested_directories:
            if directory.startswith(requested_dir):
                return False
        
        # Zu den angefragten Verzeichnissen hinzufügen
        self.requested_directories.add(directory)
        return True
    
    def try_get_permission(self, directory):
        """Versucht, Berechtigungen für ein Verzeichnis zu erhalten."""
        # Prüfen, ob wir bereits Zugriff haben
        if self.check_permission(directory):
            return True
        
        # Nur Anweisungen anzeigen, wenn wir noch nicht danach gefragt haben
        if self.should_request_permission(directory):
            return self.show_permission_instructions(directory)
        
        return False


class RetryHandler:
    """Behandelt das erneute Versuchen nach Timeouts oder Berechtigungsproblemen."""
    
    def __init__(self, timeout_seconds=10):
        """Initialisierung des RetryHandler."""
        self.timeout_seconds = timeout_seconds
        self.skip_directories = set()  # Verzeichnisse, die übersprungen werden sollen
        self.permission_handler = PermissionHandler()
    
    def add_skip_directory(self, directory):
        """Fügt ein Verzeichnis zur Liste der zu überspringenden Verzeichnisse hinzu."""
        self.skip_directories.add(os.path.normpath(directory))
    
    def should_skip_directory(self, directory):
        """Prüft, ob ein Verzeichnis übersprungen werden soll."""
        normalized_dir = os.path.normpath(directory)
        for skip_dir in self.skip_directories:
            if normalized_dir.startswith(skip_dir):
                logger.debug(f"Überspringe Verzeichnis aufgrund vorheriger Probleme: {directory}")
                return True
        return False
    
    def handle_directory_access(self, directory):
        """Behandelt den Zugriff auf ein Verzeichnis mit Timeout und Berechtigungsprüfung."""
        if self.should_skip_directory(directory):
            return False
        
        # Berechtigungen prüfen
        if not self.permission_handler.check_permission(directory):
            self.permission_handler.try_get_permission(directory)
            self.add_skip_directory(directory)
            return False
        
        # Versuchen, mit Timeout auf das Verzeichnis zuzugreifen
        try:
            if self.timeout_seconds > 0:
                start_time = time.time()
                
                # Nur einen kurzen Test durchführen
                for i, _ in enumerate(os.scandir(directory)):
                    if i > 5:  # Nur die ersten Einträge prüfen
                        break
                    
                    if time.time() - start_time > self.timeout_seconds:
                        logger.warning(f"Zeitüberschreitung beim Zugriff auf {directory}")
                        self.add_skip_directory(directory)
                        print(f"\n    Zeitüberschreitung beim Zugriff auf: {directory}")
                        print("    Das Verzeichnis wird für diese Suche übersprungen.")
                        return False
            
            return True
        except PermissionError:
            logger.warning(f"Keine Berechtigungen für {directory}")
            self.permission_handler.try_get_permission(directory)
            self.add_skip_directory(directory)
            return False
        except Exception as e:
            logger.error(f"Fehler beim Zugriff auf {directory}: {e}")
            self.add_skip_directory(directory)
            return False


class ProgressTracker:
    """Verfolgt den Fortschritt der Suche und zeigt regelmäßige Updates an."""
    
    def __init__(self, update_interval=1.0):
        """Initialisierung des ProgressTracker."""
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.update_interval = update_interval
        
        self.files_searched = 0
        self.files_skipped = 0
        self.dirs_searched = 0
        self.dirs_skipped = 0
        self.matches_found = 0
        
        self.current_directory = ""
    
    def update_current_directory(self, directory):
        """Aktualisiert das aktuelle Verzeichnis und zeigt Updates an, wenn nötig."""
        self.current_directory = directory
        self.dirs_searched += 1
        self._show_progress_if_needed()
    
    def increment_files_searched(self, count=1):
        """Erhöht den Zähler der durchsuchten Dateien."""
        self.files_searched += count
        self._show_progress_if_needed()
    
    def increment_files_skipped(self, count=1):
        """Erhöht den Zähler der übersprungenen Dateien."""
        self.files_skipped += count
        self._show_progress_if_needed()
    
    def increment_dirs_skipped(self, count=1):
        """Erhöht den Zähler der übersprungenen Verzeichnisse."""
        self.dirs_skipped += count
        self._show_progress_if_needed()
    
    def increment_matches_found(self, count=1):
        """Erhöht den Zähler der gefundenen Übereinstimmungen."""
        self.matches_found += count
        self._show_progress_if_needed()
    
    def _show_progress_if_needed(self):
        """Zeigt den Fortschritt an, wenn genügend Zeit vergangen ist."""
        current_time = time.time()
        if current_time - self.last_update_time > self.update_interval:
            self._show_progress()
            self.last_update_time = current_time
    
    def _show_progress(self):
        """Zeigt den aktuellen Fortschritt an."""
        elapsed_time = time.time() - self.start_time
        
        # Fortschrittsanzeige
        directory_short = self.current_directory
        if len(directory_short) > 50:
            directory_short = "..." + directory_short[-47:]
        
        # Überschreiben der aktuellen Zeile
        sys.stdout.write("\r" + " " * 80 + "\r")  # Zeile löschen
        sys.stdout.write(f"Durchsuche: {directory_short} | ")
        sys.stdout.write(f"Dateien: {self.files_searched} | ")
        sys.stdout.write(f"Treffer: {self.matches_found} | ")
        sys.stdout.write(f"Zeit: {elapsed_time:.1f}s")
        sys.stdout.flush()
    
    def get_stats(self):
        """Gibt die gesammelten Statistiken zurück."""
        return {
            "files_searched": self.files_searched,
            "files_skipped": self.files_skipped,
            "dirs_searched": self.dirs_searched,
            "dirs_skipped": self.dirs_skipped,
            "matches_found": self.matches_found,
            "duration_seconds": time.time() - self.start_time
        }
    
    def show_final_stats(self):
        """Zeigt die endgültigen Statistiken an."""
        stats = self.get_stats()
        
        print("\n\n    === Suchstatistik ===")
        print(f"    Durchsuchte Verzeichnisse: {stats['dirs_searched']}")
        print(f"    Übersprungene Verzeichnisse: {stats['dirs_skipped']}")
        print(f"    Durchsuchte Dateien: {stats['files_searched']}")
        print(f"    Übersprungene Dateien: {stats['files_skipped']}")
        print(f"    Gefundene Übereinstimmungen: {stats['matches_found']}")
        print(f"    Dauer: {stats['duration_seconds']:.2f} Sekunden")


#############################################
# Hauptprogramm - Abhängigkeitsprüfung
#############################################

def check_dependencies():
    """Überprüft, ob alle benötigten Abhängigkeiten installiert sind und bietet an, sie zu installieren."""
    global Fore, Style, colorama_available, tabulate, tabulate_available, chardet, chardet_available
    
    missing_packages = []
    required_packages = {
        'chardet': 'chardet',
        'colorama': 'colorama',
        'tabulate': 'tabulate'
    }
    
    # Standardpakete prüfen
    for module, package in required_packages.items():
        try:
            __import__(module)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("\n    Fehlende Abhängigkeiten gefunden:")
        for package in missing_packages:
            print(f"    - {package}")
        
        try_install = input("\n    Möchten Sie versuchen, die fehlenden Abhängigkeiten zu installieren? (j/n): ").lower() == 'j'
        
        if try_install:
            try:
                import subprocess
                
                print("\n    Installiere fehlende Abhängigkeiten...")
                subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
                print("    Installation abgeschlossen!")
                
                # Module nach Installation importieren
                if 'colorama' in missing_packages:
                    try:
                        from colorama import Fore, Style, init
                        init(autoreset=True)
                        colorama_available = True
                    except ImportError:
                        pass
                
                if 'tabulate' in missing_packages:
                    try:
                        from tabulate import tabulate
                        tabulate_available = True
                    except ImportError:
                        pass
                
                if 'chardet' in missing_packages:
                    try:
                        import chardet
                        chardet_available = True
                    except ImportError:
                        pass
                
                return True
            except Exception as e:
                print(f"\n    Fehler bei der Installation: {e}")
                show_manual_install_instructions(missing_packages)
                return False
        else:
            show_manual_install_instructions(missing_packages)
            return False
    
    return True

def show_manual_install_instructions(packages):
    """Zeigt Anweisungen zur manuellen Installation von Paketen an."""
    print("\n    Bitte installieren Sie die fehlenden Abhängigkeiten manuell:")
    
    # Befehl für verschiedene Betriebssysteme
    print("\n    Für Windows (als Administrator):")
    print(f"    python -m pip install {' '.join(packages)}")
    
    print("\n    Für Linux/macOS:")
    print(f"    pip install {' '.join(packages)}")
    print(f"    oder")
    print(f"    python3 -m pip install {' '.join(packages)}")
    
    print("\n    Falls Sie keine Administratorrechte haben, können Sie auch versuchen:")
    print(f"    pip install --user {' '.join(packages)}")

#############################################
# Hauptklasse - Fileder
#############################################

class Fileder:
    def __init__(self, config=None):
        """Initialisiert den Fileder mit den angegebenen Konfigurationswerten."""
        self.config = DEFAULT_CONFIG.copy() if config is None else config
        
        # System-Informationen erfassen
        self.system_detector = SystemDetector()
        
        # Verfügbarkeit der Archive-Module prüfen
        self.has_zipfile = zipfile_available
        self.has_gzip = gzip_available
        self.has_tarfile = tarfile_available
        
        self.max_threads = min(32, (os.cpu_count() or 4) * 2)  # Standardwert für Threadpool

        self.setup_logging()
    
    def setup_logging(self):
        """Richtet das Logging basierend auf der Konfiguration ein."""
        try:
            log_level = getattr(logging, self.config["general"]["log_level"].upper())
            logger.setLevel(log_level)
            
            # Dateiausgabe, falls noch nicht eingerichtet
            if not hasattr(self, 'file_handler'):
                file_handler = logging.FileHandler(LOG_FILE)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                self.file_handler = file_handler
        except Exception as e:
            print(f"Warnung: Logging konnte nicht eingerichtet werden: {e}")
            # Fallback auf Standardlevel
            logger.setLevel(logging.INFO)
    
    def load_config(self):
        """Lädt die Konfiguration aus der Datei."""
        if os.path.exists(CONFIG_FILE):
            try:
                config = configparser.ConfigParser()
                config.read(CONFIG_FILE)
                
                # Konfiguration laden
                if "general" in config:
                    for key in self.config["general"]:
                        if key in config["general"]:
                            # Typen richtig umwandeln
                            if key in ["context_chars", "max_file_size_mb", "timeout_seconds"]:
                                self.config["general"][key] = config["general"].getint(key)
                            elif key == "search_hidden_files":
                                self.config["general"][key] = config["general"].getboolean(key)
                            else:
                                self.config["general"][key] = config["general"][key]
                
                if "filters" in config:
                    for key in self.config["filters"]:
                        if key in config["filters"]:
                            if key == "max_depth":
                                self.config["filters"][key] = config["filters"].getint(key)
                            else:
                                self.config["filters"][key] = config["filters"][key]
                
                if "output" in config:
                    for key in self.config["output"]:
                        if key in config["output"]:
                            if key in ["save_results", "highlight_matches"]:
                                self.config["output"][key] = config["output"].getboolean(key)
                            else:
                                self.config["output"][key] = config["output"][key]
                
                logger.info(f"Konfiguration aus {CONFIG_FILE} geladen")
                return True
            except Exception as e:
                logger.error(f"Fehler beim Laden der Konfiguration: {e}")
                return False
        else:
            logger.info(f"Keine Konfigurationsdatei gefunden, Standard-Konfiguration wird verwendet")
            return False
    
    def save_config(self):
        """Speichert die aktuelle Konfiguration in eine Datei."""
        try:
            config = configparser.ConfigParser()
            
            # Abschnitte erstellen
            for section in self.config:
                config[section] = {}
                for key, value in self.config[section].items():
                    config[section][key] = str(value)
            
            with open(CONFIG_FILE, 'w') as configfile:
                config.write(configfile)
            
            logger.info(f"Konfiguration in {CONFIG_FILE} gespeichert")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Konfiguration: {e}")
            return False

    def detect_encoding(self, file_path):
        """Erkennt die Kodierung einer Datei."""
        try:
            # Falls chardet nicht verfügbar ist, UTF-8 als Standard verwenden
            if not chardet_available:
                return 'utf-8'
            
            # Maximal 1MB für Kodierungserkennung lesen
            max_size = min(1024*1024, os.path.getsize(file_path))
            with open(file_path, 'rb') as f:
                rawdata = f.read(max_size)
            result = chardet.detect(rawdata)
            return result['encoding'] if result['encoding'] is not None else 'utf-8'
        except Exception as e:
            logger.debug(f"Fehler bei der Kodierungserkennung von {file_path}: {e}")
            return 'utf-8'

    def should_process_file(self, file_path):
        """Überprüft, ob eine Datei nach den Konfigurationsfiltern verarbeitet werden soll."""
        try:
            # Prüfen, ob es sich um eine versteckte Datei handelt
            filename = os.path.basename(file_path)
            if filename.startswith('.') and not self.config["general"]["search_hidden_files"]:
                logger.debug(f"Überspringe versteckte Datei: {file_path}")
                return False
            
            # Dateigröße prüfen - mit sicherer Prüfung
            try:
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if file_size_mb > self.config["general"]["max_file_size_mb"]:
                    logger.debug(f"Überspringe zu große Datei: {file_path} ({file_size_mb:.2f} MB)")
                    return False
            except (OSError, IOError):
                logger.debug(f"Konnte Größe von {file_path} nicht bestimmen")
                return False
            
            # Ausgeschlossene Pfade prüfen
            excluded_paths = [path.strip() for path in self.config["filters"]["excluded_paths"].split(',') if path.strip()]
            for excluded_path in excluded_paths:
                if excluded_path and os.path.normpath(file_path).startswith(os.path.normpath(excluded_path)):
                    logger.debug(f"Überspringe Datei in ausgeschlossenem Pfad: {file_path}")
                    return False
            
            # Dateiendungen prüfen
            extension = os.path.splitext(file_path)[1].lower()
            
            # Ausgeschlossene Erweiterungen
            excluded_extensions = [ext.strip() for ext in self.config["filters"]["excluded_extensions"].split(',') if ext.strip()]
            if any(file_path.lower().endswith(ext) for ext in excluded_extensions):
                logger.debug(f"Überspringe Datei mit ausgeschlossener Erweiterung: {file_path}")
                return False
            
            # Eingeschlossene Erweiterungen (wenn angegeben)
            included_extensions = [ext.strip() for ext in self.config["filters"]["included_extensions"].split(',') if ext.strip()]
            if included_extensions and not any(file_path.lower().endswith(ext) for ext in included_extensions):
                logger.debug(f"Überspringe Datei, die nicht in eingeschlossenen Erweiterungen ist: {file_path}")
                return False
            
            return True
        except Exception as e:
            logger.debug(f"Fehler beim Prüfen der Datei {file_path}: {e}")
            return False

    def is_binary_file(self, file_path):
        """Überprüft, ob eine Datei binär ist."""
        # Bekannte Texterweiterungen direkt als nicht-binär erkennen
        extension = os.path.splitext(file_path)[1].lower()
        if extension in TEXT_EXTENSIONS:
            return False
        
        # MIME-Type prüfen
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith(('text/', 'application/json', 'application/xml')):
            return False
        
        # Die ersten Bytes auf NULL-Bytes prüfen
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                # Binärdateien enthalten typischerweise NULL-Bytes
                if b'\x00' in chunk:
                    return True
                
                # Versuchen, Text zu dekodieren
                try:
                    chunk.decode('utf-8')
                    return False
                except UnicodeDecodeError:
                    return True
        except Exception as e:
            logger.debug(f"Fehler beim Prüfen, ob {file_path} binär ist: {e}")
            # Im Zweifelsfall als binär betrachten
            return True

    def search_in_file(self, file_path, pattern, case_sensitive=False):
        """Durchsucht eine Datei nach einem Muster und gibt Ergebnisse zurück."""
        results = []
        
        # Prüfen, ob die Datei verarbeitet werden soll
        if not self.should_process_file(file_path):
            return results
        
        try:
            # Prüfen, ob Datei existiert und lesbar ist
            if not os.path.exists(file_path) or not os.access(file_path, os.R_OK):
                logger.debug(f"Datei {file_path} existiert nicht oder ist nicht lesbar")
                return results
                
            # Binärdatei oder Textdatei?
            if self.is_binary_file(file_path):
                # Binärsuche mit sicherer Größenprüfung
                try:
                    file_size = os.path.getsize(file_path)
                    # Sehr große Binärdateien überspringen
                    if file_size > self.config["general"]["max_file_size_mb"] * 1024 * 1024:
                        logger.debug(f"Überspringe zu große Binärdatei: {file_path}")
                        return results
                    
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    
                    search_pattern = pattern.encode('utf-8', errors='ignore')
                    if not case_sensitive:
                        content_lower = content.lower()
                        search_pattern = search_pattern.lower()
                        positions = [m.start() for m in re.finditer(re.escape(search_pattern), content_lower)]
                    else:
                        positions = [m.start() for m in re.finditer(re.escape(search_pattern), content)]
                    
                    context_chars = self.config["general"]["context_chars"]
                    for pos in positions:
                        # Kontext extrahieren
                        start = max(0, pos - context_chars)
                        end = min(len(content), pos + len(search_pattern) + context_chars)
                        context = content[start:end]
                        
                        # Ergebnis hinzufügen
                        results.append({
                            'file': file_path,
                            'line_number': -1,  # Keine Zeilennummer in Binärdateien
                            'position': pos,
                            'context': context.hex(),  # Binärdaten als Hex-String
                            'is_binary': True
                        })
                except MemoryError:
                    logger.warning(f"Nicht genügend Speicher zum Durchsuchen von {file_path}")
                    return results
            else:
                # Textdatei durchsuchen
                encoding = self.detect_encoding(file_path)
                try:
                    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                        for line_number, line in enumerate(f, 1):
                            # Zeile auf Vorkommen prüfen
                            search_line = line if case_sensitive else line.lower()
                            search_pattern = pattern if case_sensitive else pattern.lower()
                            
                            # Verwende reguläre Ausdrücke für die Suche
                            try:
                                positions = [m.start() for m in re.finditer(re.escape(search_pattern), search_line)]
                                context_chars = self.config["general"]["context_chars"]
                                
                                for pos in positions:
                                    # Kontext extrahieren
                                    start = max(0, pos - context_chars)
                                    end = min(len(line), pos + len(pattern) + context_chars)
                                    context = line[start:end].strip()
                                    
                                    # Ergebnis hinzufügen
                                    results.append({
                                        'file': file_path,
                                        'line_number': line_number,
                                        'position': pos,
                                        'context': context,
                                        'is_binary': False
                                    })
                            except Exception as inner_e:
                                logger.debug(f"Fehler bei regex-Suche in {file_path}, Zeile {line_number}: {inner_e}")
                except UnicodeDecodeError:
                    logger.debug(f"Kodierungsproblem bei {file_path} mit Kodierung {encoding}")
                    # Alternative: Als Binärdatei behandeln
                    return self.search_in_file_as_binary(file_path, pattern, case_sensitive)
        except Exception as e:
            logger.warning(f"Fehler beim Durchsuchen der Datei {file_path}: {e}")
        
        return results
        
    def search_in_file_as_binary(self, file_path, pattern, case_sensitive=False):
        """Notfall-Methode: Durchsucht eine Datei als Binärdatei, wenn die Textsuche fehlschlägt."""
        results = []
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            search_pattern = pattern.encode('utf-8', errors='ignore')
            if not case_sensitive:
                content_lower = content.lower()
                search_pattern = search_pattern.lower()
                positions = [m.start() for m in re.finditer(re.escape(search_pattern), content_lower)]
            else:
                positions = [m.start() for m in re.finditer(re.escape(search_pattern), content)]
            
            context_chars = self.config["general"]["context_chars"]
            for pos in positions:
                # Kontext extrahieren
                start = max(0, pos - context_chars)
                end = min(len(content), pos + len(search_pattern) + context_chars)
                context = content[start:end]
                
                # Ergebnis hinzufügen
                results.append({
                    'file': file_path,
                    'line_number': -1,
                    'position': pos,
                    'context': context.hex(),
                    'is_binary': True
                })
        except Exception as e:
            logger.warning(f"Auch Binärsuche in {file_path} fehlgeschlagen: {e}")
            
        return results
    
    def search_in_directory(self, directory, pattern, case_sensitive=False, recursive=True):
        """Durchsucht ein Verzeichnis nach Dateien, die das Muster enthalten (Multi-Threaded)."""
        progress = ProgressTracker()
        retry_handler = RetryHandler(timeout_seconds=self.config["general"]["timeout_seconds"])
        results = []
        errors = 0
        directory = os.path.normpath(directory)

        if not os.path.isdir(directory):
            logger.error(f"Verzeichnis existiert nicht: {directory}")
            progress.increment_dirs_skipped()
            stats = progress.get_stats()
            stats['errors'] = 1
            return results, stats

        # ThreadPoolExecutor für parallele Dateisuche
        def traverse_dir(current_dir, current_depth=0):
            nonlocal results, errors

            max_depth = int(self.config["filters"]["max_depth"])
            if max_depth > 0 and current_depth > max_depth:
                logger.debug(f"Maximale Tiefe erreicht ({max_depth}), überspringe {current_dir}")
                progress.increment_dirs_skipped()
                return

            if not retry_handler.handle_directory_access(current_dir):
                progress.increment_dirs_skipped()
                return

            progress.update_current_directory(current_dir)

            try:
                try:
                    entries = list(os.scandir(current_dir))
                except PermissionError:
                    logger.warning(f"Keine Berechtigungen für {current_dir}")
                    progress.increment_dirs_skipped()
                    return
                except Exception as e:
                    logger.error(f"Fehler beim Scannen von {current_dir}: {e}")
                    progress.increment_dirs_skipped()
                    errors += 1
                    return

                # Dateien und Verzeichnisse trennen
                files = [entry for entry in entries if entry.is_file()]
                dirs = [entry for entry in entries if entry.is_dir()]

                # Multi-Threaded Suche in Dateien
                file_results = []
                with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                    future_to_file = {
                        executor.submit(self.search_in_file, entry.path, pattern, case_sensitive): entry.path
                        for entry in files if self.should_process_file(entry.path)
                    }
                    for future in as_completed(future_to_file):
                        entry_path = future_to_file[future]
                        try:
                            res = future.result()
                            if res:
                                file_results.extend(res)
                                progress.increment_matches_found(len(res))
                            progress.increment_files_searched()
                        except Exception as e:
                            logger.error(f"Fehler bei der Verarbeitung von {entry_path}: {e}")
                            errors += 1
                            progress.increment_files_skipped()

                results.extend(file_results)

                # Übersprungene Dateien zählen
                skipped_files = len([entry for entry in files if not self.should_process_file(entry.path)])
                if skipped_files:
                    progress.increment_files_skipped(skipped_files)

                # Rekursiv in Verzeichnisse gehen (sequenziell, um Thread-Explosion zu vermeiden)
                for entry in dirs:
                    dir_name = os.path.basename(entry.path)
                    if not dir_name.startswith('.') or self.config["general"]["search_hidden_files"]:
                        traverse_dir(entry.path, current_depth + 1)

            except Exception as e:
                logger.error(f"Unerwarteter Fehler beim Durchsuchen des Verzeichnisses {current_dir}: {e}")
                errors += 1
                progress.increment_dirs_skipped()

        traverse_dir(directory)
        stats = progress.get_stats()
        stats['errors'] = errors
        print("\r" + " " * 80, end="\r")
        return results, stats

    def extract_archived_file(self, archive_path, extract_dir):
        """Extrahiert eine Archivdatei in ein temporäres Verzeichnis."""
        try:
            # Überprüfe, ob die Datei existiert und lesbar ist
            if not os.path.exists(archive_path) or not os.access(archive_path, os.R_OK):
                logger.warning(f"Archivdatei {archive_path} existiert nicht oder ist nicht lesbar")
                return False
                
            # Überprüfe die Dateigröße
            file_size_mb = os.path.getsize(archive_path) / (1024 * 1024)
            if file_size_mb > self.config["general"]["max_file_size_mb"]:
                logger.warning(f"Archiv zu groß: {archive_path} ({file_size_mb:.2f} MB)")
                return False
            
            # Je nach Archivtyp extrahieren
            if archive_path.lower().endswith('.zip'):
                if not self.has_zipfile:
                    logger.warning(f"Zipfile-Modul nicht verfügbar. Kann {archive_path} nicht extrahieren.")
                    return False
                
                try:
                    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                        # Listengröße prüfen und ggf. begrenzen
                        file_list = zip_ref.namelist()
                        if len(file_list) > 1000:  # Schutz vor Zip-Bomben
                            logger.warning(f"Zu viele Dateien in {archive_path}: {len(file_list)}")
                            return False
                        
                        # Extrahierte Größe prüfen
                        total_size = sum(info.file_size for info in zip_ref.infolist())
                        if total_size > self.config["general"]["max_file_size_mb"] * 1024 * 1024 * 10:
                            logger.warning(f"Entpackte Größe zu groß: {total_size/1024/1024:.2f} MB")
                            return False
                            
                        # Extrahieren
                        zip_ref.extractall(extract_dir)
                    return True
                except zipfile.BadZipFile:
                    logger.warning(f"Ungültiges ZIP-Archiv: {archive_path}")
                    return False
                
            elif archive_path.lower().endswith(('.tar.gz', '.tgz')):
                if not self.has_tarfile:
                    logger.warning(f"Tarfile-Modul nicht verfügbar. Kann {archive_path} nicht extrahieren.")
                    return False
                    
                try:
                    with tarfile.open(archive_path, 'r:gz') as tar_ref:
                        # Sicherheitsprüfungen
                        members = tar_ref.getmembers()
                        if len(members) > 1000:
                            logger.warning(f"Zu viele Dateien in {archive_path}: {len(members)}")
                            return False
                            
                        # Auf absolute Pfade prüfen (Sicherheitsrisiko)
                        unsafe_members = [m for m in members if m.name.startswith('/') or '..' in m.name]
                        if unsafe_members:
                            logger.warning(f"Unsichere Pfade in {archive_path} gefunden")
                            return False
                            
                        # Extrahieren
                        tar_ref.extractall(extract_dir)
                    return True
                except tarfile.ReadError:
                    logger.warning(f"Ungültiges TAR-Archiv: {archive_path}")
                    return False
                
            elif archive_path.lower().endswith('.gz') and not archive_path.lower().endswith('.tar.gz'):
                if not self.has_gzip:
                    logger.warning(f"Gzip-Modul nicht verfügbar. Kann {archive_path} nicht extrahieren.")
                    return False
                    
                # Einzelne .gz-Datei
                output_file = os.path.join(extract_dir, os.path.basename(archive_path)[:-3])
                try:
                    with gzip.open(archive_path, 'rb') as f_in:
                        with open(output_file, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    return True
                except gzip.BadGzipFile:
                    logger.warning(f"Ungültige GZIP-Datei: {archive_path}")
                    return False
                
            else:
                logger.warning(f"Nicht unterstütztes Archivformat: {archive_path}")
                return False
                
        except MemoryError:
            logger.error(f"Nicht genügend Speicher zum Extrahieren von {archive_path}")
            return False
        except Exception as e:
            logger.error(f"Fehler beim Extrahieren von {archive_path}: {e}")
            return False

    def search_in_archives(self, directory, pattern, case_sensitive=False):
        """Durchsucht Archive nach Dateien, die das Muster enthalten."""
        # Fortschritts-Tracker initialisieren
        progress = ProgressTracker()
        
        # Retry-Handler initialisieren
        retry_handler = RetryHandler(timeout_seconds=self.config["general"]["timeout_seconds"])
        
        results = []
        stats = {
            'archives_searched': 0, 
            'files_in_archives_searched': 0, 
            'matches_found': 0, 
            'errors': 0,
            'archives_skipped': 0
        }
        
        # Prüfen, ob Archive-Module verfügbar sind
        missing_modules = []
        if not self.has_zipfile:
            missing_modules.append("zipfile")
        if not self.has_gzip:
            missing_modules.append("gzip")
        if not self.has_tarfile:
            missing_modules.append("tarfile")
        
        if missing_modules:
            print(Fore.YELLOW + f"\n    Warnung: Die folgenden Module sind nicht verfügbar: {', '.join(missing_modules)}" + Style.RESET_ALL)
            print("    Einige Archive können nicht durchsucht werden.")
            
            if not self.has_zipfile and not self.has_gzip and not self.has_tarfile:
                print(Fore.RED + "    Keine Archive-Module verfügbar. Archivsuche nicht möglich." + Style.RESET_ALL)
                return results, stats
        
        # Temporäres Verzeichnis für extrahierte Dateien
        temp_dir = os.path.join(os.getcwd(), "temp_extracted_archives")
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)  # Verzeichnis leeren, falls es bereits existiert
            os.makedirs(temp_dir)
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des temporären Verzeichnisses: {e}")
            stats['errors'] += 1
            return results, stats
        
        # Archive suchen
        archives = []
        try:
            # Sicheres Durchlaufen mit Fehlerbehandlung
            for root, _, files in os.walk(directory):
                # Prüfen, ob wir auf das Verzeichnis zugreifen können
                if not retry_handler.handle_directory_access(root):
                    stats['archives_skipped'] += 1
                    continue
                    
                progress.update_current_directory(root)
                
                for file in files:
                    # Globales Timeout prüfen
                    if self.config["general"]["timeout_seconds"] > 0 and \
                    time.time() - progress.start_time > self.config["general"]["timeout_seconds"] * 5:
                        logger.warning(f"Globale Zeitüberschreitung bei der Archivsuche")
                        break
                        
                    file_path = os.path.join(root, file)
                    if file.lower().endswith(('.zip', '.tar.gz', '.tgz', '.gz')) and self.should_process_file(file_path):
                        archives.append(file_path)
        except Exception as e:
            logger.error(f"Fehler beim Suchen nach Archiven: {e}")
            stats['errors'] += 1
        
        # Archive durchsuchen
        for archive_path in archives:
            # Fortschritt aktualisieren
            progress.update_current_directory(f"Archiv: {archive_path}")
            
            logger.info(f"Durchsuche Archiv: {archive_path}")
            stats['archives_searched'] += 1
            
            # Temporäres Verzeichnis für dieses Archiv
            archive_temp_dir = os.path.join(temp_dir, f"archive_{stats['archives_searched']}")
            try:
                if not os.path.exists(archive_temp_dir):
                    os.makedirs(archive_temp_dir)
                
                # Archiv extrahieren
                if self.extract_archived_file(archive_path, archive_temp_dir):
                    # Extrahierte Dateien durchsuchen
                    archive_results, archive_stats = self.search_in_directory(
                        archive_temp_dir, pattern, case_sensitive
                    )
                    
                    # Pfade anpassen, um das Archiv zu reflektieren
                    for result in archive_results:
                        # Pfad im Archiv bestimmen
                        rel_path = os.path.relpath(result['file'], archive_temp_dir)
                        result['file'] = f"{archive_path}::{rel_path}"
                    
                    results.extend(archive_results)
                    stats['files_in_archives_searched'] += archive_stats['files_searched']
                    stats['matches_found'] += archive_stats['matches_found']
                    stats['errors'] += archive_stats['errors']
                else:
                    stats['errors'] += 1
                    stats['archives_skipped'] += 1
                
                # Temporäres Verzeichnis aufräumen
                try:
                    shutil.rmtree(archive_temp_dir)
                except Exception as e:
                    logger.warning(f"Fehler beim Aufräumen des temporären Verzeichnisses {archive_temp_dir}: {e}")
            except Exception as e:
                logger.error(f"Fehler bei der Verarbeitung des Archivs {archive_path}: {e}")
                stats['errors'] += 1
                stats['archives_skipped'] += 1
        
        # Haupttemporärverzeichnis aufräumen
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            logger.warning(f"Fehler beim Aufräumen des temporären Verzeichnisses {temp_dir}: {e}")
        
        # Fortschrittsanzeige abschließen
        print("\r" + " " * 80, end="\r")  # Zeile löschen
        
        # Füge zusätzliche Statistiken aus dem ProgressTracker hinzu
        progress_stats = progress.get_stats()
        stats['dirs_searched'] = progress_stats['dirs_searched']
        stats['dirs_skipped'] = progress_stats['dirs_skipped']
        stats['duration_seconds'] = progress_stats['duration_seconds']
        
        return results, stats

    def format_results(self, results):
        """Formatiert die Suchergebnisse für die Anzeige."""
        if not results:
            return "Keine Ergebnisse gefunden."
        
        formatted_results = []
        for result in results:
            file_path = result['file']
            line_number = result['line_number']
            context = result['context']
            
            if result['is_binary']:
                line_info = "Binärdaten"
                # Begrenzen der Länge für Binärdaten
                if len(context) > 60:
                    context = f"Position {result['position']}: {context[:60]}..."
                else:
                    context = f"Position {result['position']}: {context}"
            else:
                line_info = f"Zeile {line_number}"
                # Highlight-Funktion, wenn aktiviert
                if self.config["output"]["highlight_matches"] and colorama_available:
                    try:
                        pattern_pos = result['position'] - max(0, result['position'] - self.config["general"]["context_chars"])
                        pattern_len = len(context) - pattern_pos if pattern_pos + 20 > len(context) else 20
                        if 0 <= pattern_pos < len(context) and pattern_pos + pattern_len <= len(context):
                            context = (
                                context[:pattern_pos] + 
                                Fore.GREEN + context[pattern_pos:pattern_pos+pattern_len] + Style.RESET_ALL + 
                                context[pattern_pos+pattern_len:]
                            )
                    except:
                        # Bei Fehler bei der Hervorhebung ohne Hervorhebung fortfahren
                        pass
            
            formatted_results.append([file_path, line_info, context])
        
        # Tabelle formatieren
        return tabulate(formatted_results, headers=["Datei", "Position", "Kontext"], tablefmt="grid")

    def save_results(self, results, stats, search_pattern, directory):
        """Speichert die Suchergebnisse in eine Datei."""
        if not self.config["output"]["save_results"]:
            return None
        
        # Ergebnisverzeichnis erstellen
        script_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.join(script_dir, self.config["output"]["results_folder"])
        try:
            if not os.path.exists(results_dir):
                os.makedirs(results_dir)
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Ergebnisverzeichnisses: {e}")
            return None
        
        # Dateiname generieren
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_pattern = re.sub(r'[^\w]', '_', search_pattern)
        if len(safe_pattern) > 20:
            safe_pattern = safe_pattern[:20]
        
        results_file = os.path.join(results_dir, f"search_{safe_pattern}_{timestamp}.json")
        
        # Ergebnisse speichern
        try:
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'search_pattern': search_pattern,
                    'directory': directory,
                    'timestamp': timestamp,
                    'stats': stats,
                    'results': results
                }, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Ergebnisse gespeichert in: {results_file}")
            return results_file
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Ergebnisse: {e}")
            return None

    def load_results(self, results_file):
        """Lädt gespeicherte Suchergebnisse."""
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Ergebnisse geladen aus: {results_file}")
            return data.get('results', []), data.get('stats', {}), data.get('search_pattern', ''), data.get('directory', '')
        except Exception as e:
            logger.error(f"Fehler beim Laden der Ergebnisse: {e}")
            return [], {}, '', ''




#############################################
# Hauptmenüfunktionen
#############################################

def print_header():
    """Gibt den Programmheader aus."""
    header = """
    ╔═══════════════════════════════════════════════════╗
    ║              FILEfinDER - filder v1.1             ║
    ║         Spürt Textketten in Dateien auf           ║
    ║              © 2025 Simon Gutjahr                 ║
    ╚═══════════════════════════════════════════════════╝
    """
    print(Fore.CYAN + header + Style.RESET_ALL)

def print_menu():
    """Gibt das Hauptmenü aus."""
    menu = """
    1. Dateien nach Textkette durchsuchen
    2. Archive durchsuchen
    3. Konfiguration anzeigen/bearbeiten
    4. Gespeicherte Ergebnisse laden
    5. System-Informationen anzeigen
    6. Hilfe
    0. Beenden
    """
    print(Fore.YELLOW + menu + Style.RESET_ALL)
    return input("    Wählen Sie eine Option (0-6): ")

def print_config_menu(finder):
    """Gibt das Konfigurationsmenü aus."""
    print(Fore.CYAN + "\n    === KONFIGURATION ===" + Style.RESET_ALL)
    
    # Allgemeine Einstellungen
    print(Fore.YELLOW + "\n    Allgemeine Einstellungen:" + Style.RESET_ALL)
    print(f"    1. Kontextzeichen: {finder.config['general']['context_chars']}")
    print(f"    2. Max. Dateigröße (MB): {finder.config['general']['max_file_size_mb']}")
    print(f"    3. Versteckte Dateien durchsuchen: {finder.config['general']['search_hidden_files']}")
    print(f"    4. Timeout (Sekunden): {finder.config['general']['timeout_seconds']}")
    print(f"    5. Log-Level: {finder.config['general']['log_level']}")
    
    # Filter-Einstellungen
    print(Fore.YELLOW + "\n    Filter-Einstellungen:" + Style.RESET_ALL)
    print(f"    6. Ausgeschlossene Dateierweiterungen: {finder.config['filters']['excluded_extensions']}")
    print(f"    7. Eingeschlossene Dateierweiterungen: {finder.config['filters']['included_extensions']}")
    print(f"    8. Max. Verzeichnistiefe: {finder.config['filters']['max_depth']}")
    print(f"    9. Ausgeschlossene Pfade: {finder.config['filters']['excluded_paths']}")
    
    # Ausgabe-Einstellungen
    print(Fore.YELLOW + "\n    Ausgabe-Einstellungen:" + Style.RESET_ALL)
    print(f"   10. Ergebnisse speichern: {finder.config['output']['save_results']}")
    print(f"   11. Ergebnisverzeichnis: {finder.config['output']['results_folder']}")
    print(f"   12. Übereinstimmungen hervorheben: {finder.config['output']['highlight_matches']}")
    
    print(Fore.YELLOW + "\n    Aktionen:" + Style.RESET_ALL)
    print("   13. Konfiguration speichern")
    print("   14. Konfiguration zurücksetzen")
    print("   15. Empfohlene Pfade ausschließen")
    print("    0. Zurück zum Hauptmenü")
    
    return input("\n    Wählen Sie eine Option (0-15): ")

def edit_config(finder):
    """Bearbeitet die Konfiguration."""
    while True:
        choice = print_config_menu(finder)
        
        try:
            if choice == '0':
                break
            elif choice == '1':
                value = int(input("    Neue Anzahl Kontextzeichen: "))
                finder.config["general"]["context_chars"] = value
            elif choice == '2':
                value = int(input("    Neue max. Dateigröße (MB): "))
                finder.config["general"]["max_file_size_mb"] = value
            elif choice == '3':
                value = input("    Versteckte Dateien durchsuchen (j/n): ").lower() == 'j'
                finder.config["general"]["search_hidden_files"] = value
            elif choice == '4':
                value = int(input("    Neuer Timeout-Wert (Sekunden, 0 für kein Timeout): "))
                finder.config["general"]["timeout_seconds"] = value
            elif choice == '5':
                levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
                print("    Verfügbare Log-Level: " + ", ".join(levels))
                value = input("    Neuer Log-Level: ").upper()
                if value in levels:
                    finder.config["general"]["log_level"] = value
                    finder.setup_logging()
                else:
                    print(Fore.RED + f"    Ungültiger Log-Level. Bitte wählen Sie aus: {', '.join(levels)}" + Style.RESET_ALL)
            elif choice == '6':
                value = input("    Neue ausgeschlossene Dateierweiterungen (kommagetrennt): ")
                finder.config["filters"]["excluded_extensions"] = value
            elif choice == '7':
                value = input("    Neue eingeschlossene Dateierweiterungen (kommagetrennt, leer = alle): ")
                finder.config["filters"]["included_extensions"] = value
            elif choice == '8':
                value = int(input("    Neue max. Verzeichnistiefe (0 für unbegrenzt): "))
                finder.config["filters"]["max_depth"] = value
            elif choice == '9':
                value = input("    Neue ausgeschlossene Pfade (kommagetrennt): ")
                finder.config["filters"]["excluded_paths"] = value
            elif choice == '10':
                value = input("    Ergebnisse speichern (j/n): ").lower() == 'j'
                finder.config["output"]["save_results"] = value
            elif choice == '11':
                value = input("    Neues Ergebnisverzeichnis: ")
                finder.config["output"]["results_folder"] = value
            elif choice == '12':
                value = input("    Übereinstimmungen hervorheben (j/n): ").lower() == 'j'
                finder.config["output"]["highlight_matches"] = value
            elif choice == '13':
                if finder.save_config():
                    print(Fore.GREEN + "    Konfiguration gespeichert!" + Style.RESET_ALL)
                else:
                    print(Fore.RED + "    Fehler beim Speichern der Konfiguration!" + Style.RESET_ALL)
            elif choice == '14':
                confirm = input("    Sind Sie sicher, dass Sie die Konfiguration zurücksetzen möchten? (j/n): ").lower()
                if confirm == 'j':
                    finder.config = DEFAULT_CONFIG.copy()
                    finder.setup_logging()
                    print(Fore.GREEN + "    Konfiguration zurückgesetzt!" + Style.RESET_ALL)
            elif choice == '15':
                # Empfohlene Pfade ausschließen
                suggested_paths = finder.system_detector.suggest_excluded_paths()
                if suggested_paths:
                    print(Fore.CYAN + "\n    Empfohlene auszuschließende Pfade für Ihr System:" + Style.RESET_ALL)
                    for i, path in enumerate(suggested_paths, 1):
                        print(f"    {i}. {path}")
                    
                    confirm = input("\n    Möchten Sie diese Pfade ausschließen? (j/n): ").lower()
                    if confirm == 'j':
                        # Bestehende Pfade beibehalten
                        current_paths = [p.strip() for p in finder.config["filters"]["excluded_paths"].split(',') if p.strip()]
                        # Neue Pfade hinzufügen (Duplikate vermeiden)
                        for path in suggested_paths:
                            if path not in current_paths:
                                current_paths.append(path)
                        
                        # Zurück in die Konfiguration schreiben
                        finder.config["filters"]["excluded_paths"] = ','.join(current_paths)
                        print(Fore.GREEN + "    Empfohlene Pfade wurden ausgeschlossen!" + Style.RESET_ALL)
                else:
                    print(Fore.YELLOW + "    Keine Pfade für Ihr System empfohlen." + Style.RESET_ALL)
        except ValueError:
            print(Fore.RED + "    Ungültige Eingabe! Bitte geben Sie einen gültigen Wert ein." + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + f"    Fehler beim Bearbeiten der Konfiguration: {e}" + Style.RESET_ALL)

def search_files(finder):
    """Führt eine Suche in Dateien durch."""
    directory = input("\n    Verzeichnis, das durchsucht werden soll (leer = aktuelles Verzeichnis): ") or os.getcwd()
    if not os.path.isdir(directory):
        print(Fore.RED + f"    Verzeichnis nicht gefunden: {directory}" + Style.RESET_ALL)
        return
    
    pattern = input("    Nach welcher Textkette soll gesucht werden? ")
    if not pattern:
        print(Fore.RED + "    Keine Suchmuster angegeben!" + Style.RESET_ALL)
        return
    
    case_sensitive = input("    Groß-/Kleinschreibung beachten? (j/n): ").lower() == 'j'
    recursive = input("    Unterverzeichnisse durchsuchen? (j/n): ").lower() == 'j'
    
    print(Fore.CYAN + f"\n    Suche nach '{pattern}' in {directory}..." + Style.RESET_ALL)
    
    # Bei macOS: Warnung anzeigen, wenn Zugriffsprobleme wahrscheinlich sind
    if finder.system_detector.is_macos and not finder.system_detector.has_fulldisc_access:
        print(Fore.YELLOW + "\n    Hinweis: Auf macOS könnten Berechtigungsprobleme auftreten." + Style.RESET_ALL)
        print("    Wenn Sie Zugriffsprobleme bemerken, prüfen Sie die System-Informationen (Option 5 im Hauptmenü).")
    
    results, stats = finder.search_in_directory(directory, pattern, case_sensitive, recursive)
    
    print("\n" + finder.format_results(results))
    
    print(Fore.CYAN + "\n    === Suchstatistik ===" + Style.RESET_ALL)
    print(f"    Durchsuchte Verzeichnisse: {stats.get('dirs_searched', 0)}")
    print(f"    Übersprungene Verzeichnisse: {stats.get('dirs_skipped', 0)}")
    print(f"    Durchsuchte Dateien: {stats['files_searched']}")
    print(f"    Gefundene Übereinstimmungen: {stats['matches_found']}")
    print(f"    Fehler: {stats['errors']}")
    print(f"    Dauer: {stats['duration_seconds']:.2f} Sekunden")
    
    if finder.config["output"]["save_results"]:
        results_file = finder.save_results(results, stats, pattern, directory)
        if results_file:
            print(Fore.GREEN + f"\n    Ergebnisse gespeichert in: {results_file}" + Style.RESET_ALL)

def search_archives(finder):
    """Führt eine Suche in Archiven durch."""
    directory = input("\n    Verzeichnis mit Archiven, das durchsucht werden soll (leer = aktuelles Verzeichnis): ") or os.getcwd()
    if not os.path.isdir(directory):
        print(Fore.RED + f"    Verzeichnis nicht gefunden: {directory}" + Style.RESET_ALL)
        return
    
    pattern = input("    Nach welcher Textkette soll gesucht werden? ")
    if not pattern:
        print(Fore.RED + "    Keine Suchmuster angegeben!" + Style.RESET_ALL)
        return
    
    case_sensitive = input("    Groß-/Kleinschreibung beachten? (j/n): ").lower() == 'j'
    
    print(Fore.CYAN + f"\n    Suche nach '{pattern}' in Archiven in {directory}..." + Style.RESET_ALL)
    results, stats = finder.search_in_archives(directory, pattern, case_sensitive)
    
    print("\n" + finder.format_results(results))
    
    print(Fore.CYAN + "\n    === Suchstatistik ===" + Style.RESET_ALL)
    print(f"    Durchsuchte Verzeichnisse: {stats.get('dirs_searched', 0)}")
    print(f"    Durchsuchte Archive: {stats['archives_searched']}")
    print(f"    Übersprungene Archive: {stats.get('archives_skipped', 0)}")
    print(f"    Durchsuchte Dateien in Archiven: {stats['files_in_archives_searched']}")
    print(f"    Gefundene Übereinstimmungen: {stats['matches_found']}")
    print(f"    Fehler: {stats['errors']}")
    print(f"    Dauer: {stats['duration_seconds']:.2f} Sekunden")
    
    if finder.config["output"]["save_results"]:
        results_file = finder.save_results(results, stats, pattern, directory)
        if results_file:
            print(Fore.GREEN + f"\n    Ergebnisse gespeichert in: {results_file}" + Style.RESET_ALL)

def load_saved_results(finder):
    """Lädt gespeicherte Suchergebnisse."""
    # Pfad des aktuellen Skripts
    script_dir = os.path.dirname(os.path.realpath(sys.argv[0]))

    # results_folder aus der Konfiguration (z. B. "search_results")
    results_dir_name = finder.config["output"]["results_folder"]

    # Vollständiger Pfad zum Ergebnisverzeichnis im Skriptverzeichnis
    results_dir = os.path.join(script_dir, results_dir_name)

    if not os.path.exists(results_dir):
        print(Fore.RED + f"    Ergebnisverzeichnis nicht gefunden: {results_dir}" + Style.RESET_ALL)
        return
    
    # Verfügbare Ergebnisdateien anzeigen
    results_files = [f for f in os.listdir(results_dir) if f.startswith("search_") and f.endswith(".json")]
    
    if not results_files:
        print(Fore.RED + "    Keine gespeicherten Ergebnisse gefunden!" + Style.RESET_ALL)
        return
    
    print(Fore.CYAN + "\n    Verfügbare Ergebnisdateien:" + Style.RESET_ALL)
    for i, file in enumerate(results_files, 1):
        print(f"    {i}. {file}")
    
    try:
        choice = int(input("\n    Wählen Sie eine Datei (Nummer): "))
        if choice < 1 or choice > len(results_files):
            print(Fore.RED + "    Ungültige Auswahl!" + Style.RESET_ALL)
            return
        
        # Vollständiger Pfad zur gewählten Datei
        selected_file = os.path.join(results_dir, results_files[choice - 1])

        results, stats, pattern, directory = finder.load_results(selected_file)
        
        print("\n" + finder.format_results(results))
        
        print(Fore.CYAN + "\n    === Suchstatistik ===" + Style.RESET_ALL)
        print(f"    Suchmuster: {pattern}")
        print(f"    Verzeichnis: {directory}")
        if 'dirs_searched' in stats:
            print(f"    Durchsuchte Verzeichnisse: {stats['dirs_searched']}")
        if 'dirs_skipped' in stats:
            print(f"    Übersprungene Verzeichnisse: {stats['dirs_skipped']}")
        if 'files_searched' in stats:
            print(f"    Durchsuchte Dateien: {stats['files_searched']}")
        if 'archives_searched' in stats:
            print(f"    Durchsuchte Archive: {stats['archives_searched']}")
            print(f"    Durchsuchte Dateien in Archiven: {stats['files_in_archives_searched']}")
        print(f"    Gefundene Übereinstimmungen: {stats.get('matches_found', len(results))}")
        print(f"    Fehler: {stats.get('errors', 0)}")
        if 'duration_seconds' in stats:
            print(f"    Dauer: {stats['duration_seconds']:.2f} Sekunden")
    except ValueError:
        print(Fore.RED + "    Ungültige Eingabe! Bitte geben Sie eine Zahl ein." + Style.RESET_ALL)
    except Exception as e:
        print(Fore.RED + f"    Fehler beim Laden der Ergebnisse: {e}" + Style.RESET_ALL)


def show_system_info(finder):
    """Zeigt System-Informationen an."""
    print(finder.system_detector.show_system_info())
    print(finder.system_detector.get_platform_specific_tips())

def print_help():
    """Zeigt die Hilfe an."""
    help_text = """
    === HILFE ===
    
    Fileder ist ein leistungsstarkes Werkzeug zum Durchsuchen von Dateien nach bestimmten Textketten.
    
    Hauptfunktionen:
    1. Dateien nach Textkette durchsuchen:
       - Sucht in einem Verzeichnis und optional in Unterverzeichnissen nach Dateien,
         die eine bestimmte Textkette enthalten.
       - Zeigt Kontext um die gefundene Textkette an.
    
    2. Archive durchsuchen:
       - Extrahiert Zip-, Tar.gz- und GZ-Archive und durchsucht die darin enthaltenen Dateien.
    
    3. Konfiguration anzeigen/bearbeiten:
       - Ermöglicht die Anpassung verschiedener Einstellungen wie Kontextlänge,
         durchsuchte Dateitypen, etc.
    
    4. Gespeicherte Ergebnisse laden:
       - Lädt zuvor gespeicherte Suchergebnisse.
    
    5. System-Informationen anzeigen:
       - Zeigt Details zu Ihrem Betriebssystem und gibt spezifische Tipps zur Verwendung.
    
    Tipps zur Verwendung:
    - Um bestimmte Dateitypen zu durchsuchen, verwenden Sie die Filter-Einstellungen.
    - Die Kontextlänge bestimmt, wie viele Zeichen um den gefundenen Text angezeigt werden.
    - Für große Verzeichnisse können Sie ein Timeout festlegen.
    - Die Ergebnisse werden im JSON-Format gespeichert und können später wieder geladen werden.
    - Auf macOS sollten Sie Berechtigungen für Zugriff auf geschützte Ordner erteilen.
    
    Bekannte Einschränkungen:
    - Sehr große Binärdateien können zu Speicherproblemen führen.
    - Die Suche in verschlüsselten Archiven wird nicht unterstützt.
    - Auf macOS sind für einige Verzeichnisse zusätzliche Berechtigungen erforderlich.
    """
    print(Fore.CYAN + help_text + Style.RESET_ALL)

def main():
    """Hauptfunktion des Programms."""
    # Konfiguriere Fehlerbehandlung von Anfang an
    sys.excepthook = lambda exc_type, exc_value, exc_traceback: (
        logger.critical("Unbehandelter Fehler!", exc_info=(exc_type, exc_value, exc_traceback)),
        print(f"\n\n    Kritischer Fehler: {exc_value}\n    Details sind in der Logdatei: {LOG_FILE}")
    )

    # Minimal-Setup für Colorama, falls es vorhanden ist
    try:
        from colorama import init
        init(autoreset=True)  # Autoreset für bessere Lesbarkeit
    except ImportError:
        pass
    
    print("\n    Fileder wird initialisiert...")
    
    # Abhängigkeiten prüfen
    if not check_dependencies():
        print("\n    Programm wird im Basismodus gestartet (einige Funktionen sind eingeschränkt).")
    
    # Safe-Mode-Flag
    safe_mode_enabled = False
    
    # Fileder initialisieren - mit mehreren Stufen der Fehlerbehandlung
    try:
        finder = Fileder()
        finder.load_config()
    except Exception as e:
        logger.error(f"Kritischer Fehler bei der Initialisierung: {e}")
        print(Fore.RED + f"\n    Fehler beim Start: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "\n    Starte im abgesicherten Modus..." + Style.RESET_ALL)
        safe_mode_enabled = True
        try:
            # Versuche es mit einem einfacheren SystemDetector
            class SafeSystemDetector:
                def __init__(self):
                    self.os_name = "Unbekannt"
                    self.is_windows = "Windows" in platform.system() 
                    self.is_macos = "Darwin" in platform.system()
                    self.is_linux = "Linux" in platform.system()
                    self.has_fulldisc_access = False
                    self.is_admin = False
                    self.is_root = False
             
                def show_system_info(self):
                    return "\n    === System-Informationen ===\n    Im abgesicherten Modus verfügbar."
                 
                def get_platform_specific_tips(self):
                    return "\n    === Tipps für Ihr Betriebssystem ===\n    Abgesicherter Modus aktiviert."
                 
                def suggest_excluded_paths(self):
                    return []
            
            # SystemDetector durch die sichere Version ersetzen
            global SystemDetector
            SystemDetector = SafeSystemDetector
            
            # Erneut versuchen
            finder = Fileder()
            finder.load_config()
        except Exception as e2:
            logger.critical(f"Absolut kritischer Fehler, auch im Safe-Mode: {e2}")
            print(Fore.RED + f"\n    Fehler auch im abgesicherten Modus: {e2}" + Style.RESET_ALL)
            print(Fore.RED + "\n    Programm wird beendet." + Style.RESET_ALL)
            return
    
    # Hauptmenü-Schleife
    while True:
        try:
            print_header()
            if safe_mode_enabled:
                print(Fore.YELLOW + "    [ABGESICHERTER MODUS AKTIV]" + Style.RESET_ALL)
                
            choice = print_menu()
            
            if choice == '0':
                print(Fore.GREEN + "\n    Programm wird beendet. Auf Wiedersehen!" + Style.RESET_ALL)
                break
            elif choice == '1':
                search_files(finder)
            elif choice == '2':
                search_archives(finder)
            elif choice == '3':
                edit_config(finder)
            elif choice == '4':
                load_saved_results(finder)
            elif choice == '5':
                show_system_info(finder)
            elif choice == '6':
                print_help()
            else:
                print(Fore.RED + "\n    Ungültige Auswahl! Bitte wählen Sie eine Option zwischen 0 und 6." + Style.RESET_ALL)
            
            input("\n    Drücken Sie Enter, um fortzufahren...")
        except Exception as e:
            logger.error(f"Fehler im Hauptmenü: {e}")
            print(Fore.RED + f"\n    Ein Fehler ist aufgetreten: {e}" + Style.RESET_ALL)
            print(Fore.YELLOW + "    Das Programm versucht, weiterzulaufen." + Style.RESET_ALL)
            input("\n    Drücken Sie Enter, um fortzufahren...")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n    Programm durch Benutzer beendet." + Style.RESET_ALL)
    except Exception as e:
        logger.critical(f"Unbehandelter Fehler: {e}")
        print(Fore.RED + f"\n\n    Unbehandelter Fehler: {e}" + Style.RESET_ALL)
        print(f"    Details finden Sie in der Logdatei: {LOG_FILE}")