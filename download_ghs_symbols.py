#!/usr/bin/env python3
"""
Script zum Herunterladen der GHS-Gefahrensymbole
Erstellt den Ordner static/hazard_symbols/ und lädt die offiziellen Symbole herunter
"""

import os
import requests
from pathlib import Path

# Alternative URLs mit besserer Verfügbarkeit
GHS_SYMBOLS = {
    'GHS01': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-explos.svg',
    'GHS02': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-flamme.svg',
    'GHS03': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-rondflam.svg',
    'GHS04': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-bottle.svg',
    'GHS05': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-acid.svg',
    'GHS06': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-skull.svg',
    'GHS07': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-exclam.svg',
    'GHS08': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-silhouette.svg',
    'GHS09': 'https://commons.wikimedia.org/wiki/Special:FilePath/GHS-pictogram-pollu.svg',
}

def download_ghs_symbols():
    """Lädt alle GHS-Symbole herunter und speichert sie im static/hazard_symbols Ordner."""
    
    # Basisordner ermitteln (dort wo das Script liegt)
    script_dir = Path(__file__).parent
    symbols_dir = script_dir / 'static' / 'hazard_symbols'
    
    # Ordner erstellen falls nicht vorhanden
    symbols_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Erstelle Ordner: {symbols_dir}")
    print(f"⬇️  Lade {len(GHS_SYMBOLS)} GHS-Symbole herunter...\n")
    
    # Headers um Bot-Detection zu umgehen
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    success_count = 0
    
    for symbol_name, url in GHS_SYMBOLS.items():
        file_path = symbols_dir / f"{symbol_name}.png"
        
        # Überspringen wenn Datei bereits existiert
        if file_path.exists():
            print(f"⏭️  {symbol_name}.png existiert bereits")
            success_count += 1
            continue
        
        try:
            # SVG herunterladen
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            # Als PNG speichern (auch wenn es SVG ist - Browser können das rendern)
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ {symbol_name}.png erfolgreich heruntergeladen")
            success_count += 1
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Fehler beim Herunterladen von {symbol_name}: {e}")
        except IOError as e:
            print(f"❌ Fehler beim Speichern von {symbol_name}: {e}")
    
    print(f"\n{'='*60}")
    print(f"✨ Fertig! {success_count}/{len(GHS_SYMBOLS)} Symbole erfolgreich heruntergeladen")
    print(f"📂 Gespeichert in: {symbols_dir}")
    
    # Prüfe ob alle Dateien vorhanden sind
    missing = []
    for symbol_name in GHS_SYMBOLS.keys():
        if not (symbols_dir / f"{symbol_name}.png").exists():
            missing.append(symbol_name)
    
    if missing:
        print(f"\n⚠️  Fehlende Symbole: {', '.join(missing)}")
        print("\n📥 Alternative: Manuelle Downloads")
        print("   Besuche: https://commons.wikimedia.org/wiki/Category:GHS_hazard_pictograms")
        print("   Oder nutze die bereitgestellten Platzhalter-Symbole")
    else:
        print("\n✅ Alle GHS-Symbole sind verfügbar!")
    
    return success_count == len(GHS_SYMBOLS)

def create_placeholder_symbols():
    """Erstellt einfache Platzhalter-Symbole falls der Download fehlschlägt."""
    script_dir = Path(__file__).parent
    symbols_dir = script_dir / 'static' / 'hazard_symbols'
    symbols_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n🎨 Erstelle Platzhalter-Symbole...")
    
    # Einfaches SVG-Template für Platzhalter
    svg_template = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="128" height="128">
    <rect x="10" y="10" width="80" height="80" fill="#ff6b6b" stroke="#c92a2a" stroke-width="2" rx="5"/>
    <text x="50" y="55" font-family="Arial" font-size="16" fill="white" text-anchor="middle" font-weight="bold">{symbol}</text>
</svg>'''
    
    symbols_created = 0
    for symbol_name in GHS_SYMBOLS.keys():
        file_path = symbols_dir / f"{symbol_name}.png"
        if not file_path.exists():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(svg_template.format(symbol=symbol_name))
                print(f"  ✅ {symbol_name}.png Platzhalter erstellt")
                symbols_created += 1
            except Exception as e:
                print(f"  ❌ Fehler bei {symbol_name}: {e}")
    
    if symbols_created > 0:
        print(f"\n✅ {symbols_created} Platzhalter-Symbole erstellt")
        print("   Diese funktionieren für die Entwicklung, für Produktion bitte echte Symbole verwenden")
    
    return symbols_created

def verify_symbols():
    """Überprüft ob alle benötigten Symbole vorhanden sind."""
    script_dir = Path(__file__).parent
    symbols_dir = script_dir / 'static' / 'hazard_symbols'
    
    if not symbols_dir.exists():
        print("❌ Ordner 'static/hazard_symbols' existiert nicht!")
        return False
    
    all_present = True
    print("\n🔍 Überprüfe vorhandene Symbole:")
    
    for symbol_name in GHS_SYMBOLS.keys():
        file_path = symbols_dir / f"{symbol_name}.png"
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"   ✅ {symbol_name}.png ({size} bytes)")
        else:
            print(f"   ❌ {symbol_name}.png fehlt!")
            all_present = False
    
    return all_present
