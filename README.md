# Fileder - Textkettensuche in Dateien und Archiven

![Lizenz: MIT](https://img.shields.io/badge/Lizenz-MIT-green.svg)
![Python: 3.6+](https://img.shields.io/badge/Python-3.6+-blue.svg)

**Fileder** ist ein leistungsstarkes Python-Tool zur Suche nach Textketten in Dateien und Archiven. Es durchsucht Verzeichnisse und Archive nach bestimmten Textketten und gibt die gefundenen Übereinstimmungen mit Kontext übersichtlich aus.

**Beta - work in progress**

## Funktionen

- **Durchsuchen von Dateien und Verzeichnissen** nach spezifischen Textketten
- **Archivsuche** in ZIP, TAR.GZ und GZ-Dateien
- **Erweiterte Konfigurationsoptionen** für eine anpassbare Suche
- **Fortschrittsanzeige in Echtzeit** während der Suche
- **Automatische Erkennung von Dateikodierungen**
- **Binärdateisuche**
- **Systemspezifische Optimierungen** für Windows, macOS und Linux
- **Berechtigungsmanagement** insbesondere für macOS-geschützte Ordner
- **Farbcodierte Ausgabe** für bessere Lesbarkeit
- **Speichern und Laden von Suchergebnissen** im JSON-Format

### Abhängigkeiten

- Python 3.6 oder höher
- colorama (für farbige Konsolenausgabe)
- chardet (für Zeichenkodierungserkennung)
- tabulate (für formatierte Tabellenausgabe)

Diese werden automatisch bei der ersten Ausführung geprüft und bei Bedarf installiert, wenn der Benutzer zustimmt.


### Hauptmenü

Nach dem Start zeigt Fileder das Hauptmenü:

```
    ╔═══════════════════════════════════════════════════╗
    ║              FILEfinDER - filder v1.0             ║
    ║         Spürt Textketten in Dateien auf           ║
    ║              © 2025 Simon Gutjahr                 ║
    ╚═══════════════════════════════════════════════════╝

    1. Dateien nach Textkette durchsuchen
    2. Archive durchsuchen
    3. Konfiguration anzeigen/bearbeiten
    4. Gespeicherte Ergebnisse laden
    5. System-Informationen anzeigen
    6. Hilfe
    0. Beenden
```

### Beispielsuche

1. Wähle Option 1, um Dateien zu durchsuchen
2. Gib das zu durchsuchende Verzeichnis ein (oder drücke Enter für das aktuelle Verzeichnis)
3. Gib die zu suchende Textkette ein
4. Wähle, ob die Groß-/Kleinschreibung beachtet werden soll
5. Wähle, ob Unterverzeichnisse durchsucht werden sollen

### Konfiguration

Über Option 3 im Hauptmenü kannst du zahlreiche Einstellungen anpassen:
- Größe des angezeigten Kontexts um Suchergebnisse
- Maximale Dateigröße zum Durchsuchen
- Ausgeschlossene/eingeschlossene Dateitypen
- Timeout-Einstellungen
- Ausgeschlossene Pfade (mit systemspezifischen Vorschlägen)
- und vieles mehr

## Plattformspezifische Funktionen

### macOS
- Erkennung des Festplattenvollzugriffs
- Anleitung zur Erteilung von Berechtigungen für geschützte Ordner
- Spezieller Umgang mit iCloud Drive

### Windows
- Erkennung von Administratorrechten
- Optimierte Pfadvorschläge für Systemordner

### Linux
- Root-Rechteerkennung
- Vorschläge für auszuschließende Systemordner

## Entwicklung

Dieses Projekt ist unter der MIT-Lizenz veröffentlicht und Beiträge sind willkommen! Pull Requests, Fehlermeldungen und Verbesserungsvorschläge werden gerne gesehen.

### Künstliche Intelligenz

Bei der Entwicklung dieses Tools hat künstliche Intelligenz unterstützt, insbesondere bei der Implementierung der plattformspezifischen Erkennungsfunktionen und dem Berechtigungsmanagement.

## Lizenz

MIT Lizenz - Siehe die Datei [LICENSE](LICENSE) für Details.
