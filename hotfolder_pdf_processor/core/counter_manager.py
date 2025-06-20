"""
Counter-Manager für persistente Auto-Inkrement Funktionalität
"""
import json
import os
import threading
from typing import Dict, Any
from pathlib import Path


class CounterManager:
    """Verwaltet persistente Counter für Auto-Inkrement Funktionen"""
    
    def __init__(self, counter_file: str = "counters.json"):
        self.counter_file = counter_file
        self.counters: Dict[str, int] = {}
        self._lock = threading.Lock()
        self.load_counters()
    
    def load_counters(self) -> None:
        """Lädt die Counter aus der Datei"""
        try:
            if os.path.exists(self.counter_file):
                with open(self.counter_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        self.counters = json.loads(content)
                    else:
                        self.counters = {}
            else:
                self.counters = {}
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Fehler beim Laden der Counter-Datei: {e}")
            self.counters = {}
        except Exception as e:
            print(f"Unerwarteter Fehler beim Laden der Counter: {e}")
            self.counters = {}
    
    def save_counters(self) -> None:
        """Speichert die Counter in die Datei"""
        try:
            # Erstelle Backup der aktuellen Datei
            if os.path.exists(self.counter_file):
                backup_file = self.counter_file + ".backup"
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                os.rename(self.counter_file, backup_file)
            
            # Speichere neue Counter
            with open(self.counter_file, 'w', encoding='utf-8') as f:
                json.dump(self.counters, f, indent=2, ensure_ascii=False)
            
            # Entferne Backup wenn erfolgreich
            backup_file = self.counter_file + ".backup"
            if os.path.exists(backup_file):
                os.remove(backup_file)
                
        except Exception as e:
            print(f"Fehler beim Speichern der Counter: {e}")
            # Stelle Backup wieder her wenn vorhanden
            backup_file = self.counter_file + ".backup"
            if os.path.exists(backup_file):
                if os.path.exists(self.counter_file):
                    os.remove(self.counter_file)
                os.rename(backup_file, self.counter_file)
    
    def get_and_increment(self, counter_name: str, start_value: int = 1, step: int = 1) -> int:
        """
        Gibt den aktuellen Counter-Wert zurück und erhöht ihn
        
        Args:
            counter_name: Name des Counters
            start_value: Startwert falls Counter nicht existiert
            step: Schrittweite für Erhöhung
            
        Returns:
            Der aktuelle Wert vor der Erhöhung
        """
        with self._lock:
            # Initialisiere Counter falls nicht vorhanden
            if counter_name not in self.counters:
                self.counters[counter_name] = start_value
            
            # Hole aktuellen Wert
            current_value = self.counters[counter_name]
            
            # Erhöhe Counter
            self.counters[counter_name] += step
            
            # Speichere sofort
            self.save_counters()
            
            return current_value
    
    def set_counter(self, counter_name: str, value: int) -> None:
        """
        Setzt einen Counter auf einen bestimmten Wert
        
        Args:
            counter_name: Name des Counters
            value: Neuer Wert
        """
        with self._lock:
            self.counters[counter_name] = value
            self.save_counters()
    
    def get_counter(self, counter_name: str, default: int = 0) -> int:
        """
        Gibt den aktuellen Counter-Wert zurück ohne ihn zu ändern
        
        Args:
            counter_name: Name des Counters
            default: Standardwert falls Counter nicht existiert
            
        Returns:
            Der aktuelle Counter-Wert
        """
        with self._lock:
            return self.counters.get(counter_name, default)
    
    def reset_counter(self, counter_name: str, new_value: int = 1) -> None:
        """
        Setzt einen Counter zurück
        
        Args:
            counter_name: Name des Counters
            new_value: Neuer Startwert
        """
        with self._lock:
            self.counters[counter_name] = new_value
            self.save_counters()
    
    def delete_counter(self, counter_name: str) -> bool:
        """
        Löscht einen Counter
        
        Args:
            counter_name: Name des Counters
            
        Returns:
            True wenn Counter existierte und gelöscht wurde
        """
        with self._lock:
            if counter_name in self.counters:
                del self.counters[counter_name]
                self.save_counters()
                return True
            return False
    
    def list_counters(self) -> Dict[str, int]:
        """
        Gibt alle Counter zurück
        
        Returns:
            Dictionary mit allen Counter-Namen und ihren Werten
        """
        with self._lock:
            return self.counters.copy()
    
    def clear_all_counters(self) -> None:
        """Löscht alle Counter"""
        with self._lock:
            self.counters.clear()
            self.save_counters()


# Globale Instanz für die Anwendung
_global_counter_manager = None

def get_counter_manager() -> CounterManager:
    """Gibt die globale CounterManager-Instanz zurück"""
    global _global_counter_manager
    if _global_counter_manager is None:
        _global_counter_manager = CounterManager()
    return _global_counter_manager