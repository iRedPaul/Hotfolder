"""
PDF-Verarbeitungsfunktionen - Vereinfachte Version mit nur 3 Export-Formaten
"""
import os
import shutil
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import PyPDF2
from PIL import Image
import sys
import xml.etree.ElementTree as ET
import subprocess
import tempfile
import uuid
import logging
from datetime import datetime
import fitz  # PyMuPDF für bessere PDF-Analyse
import ocrmypdf
from ocrmypdf import PdfContext
from core.logging_config import setup_logging
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.xml_field_processor import XMLFieldProcessor, FieldMapping
from core.ocr_processor import OCRProcessor
from core.export_processor import ExportProcessor
from models.hotfolder_config import HotfolderConfig, ProcessingAction, DocumentPair
from models.export_config import ExportSettings

logger = logging.getLogger(__name__)

class PDFProcessor:
    """Vereinfachter PDF-Prozessor mit nur 3 Export-Formaten"""
    
    # Komprimierungsprofile für verschiedene Dokumenttypen
    COMPRESSION_PROFILES = {
        "rechnung": {
            "name": "Rechnung/Geschäftsdokument",
            "color_dpi": 300,
            "gray_dpi": 300,
            "mono_dpi": 600,
            "jpeg_quality": 85,
            "downsample_images": True,
            "subset_fonts": True,
            "remove_duplicates": True,
            "optimize": True,
            "preserve_quality": True,
            "description": "Optimiert für Lesbarkeit von Text und Zahlen, erhält Stempel und Unterschriften"
        },
        "archiv": {
            "name": "Langzeitarchiv",
            "color_dpi": 200,
            "gray_dpi": 200,
            "mono_dpi": 400,
            "jpeg_quality": 80,
            "downsample_images": True,
            "subset_fonts": True,
            "remove_duplicates": True,
            "optimize": True,
            "preserve_quality": True,
            "description": "Ausgewogene Komprimierung für Langzeitarchivierung"
        },
        "scan": {
            "name": "Gescanntes Dokument",
            "color_dpi": 150,
            "gray_dpi": 150,
            "mono_dpi": 300,
            "jpeg_quality": 75,
            "downsample_images": True,
            "subset_fonts": True,
            "remove_duplicates": True,
            "optimize": True,
            "preserve_quality": False,
            "description": "Stärkere Komprimierung für bereits gescannte Dokumente"
        },
        "email": {
            "name": "E-Mail-Versand",
            "color_dpi": 100,
            "gray_dpi": 100,
            "mono_dpi": 200,
            "jpeg_quality": 65,
            "downsample_images": True,
            "subset_fonts": True,
            "remove_duplicates": True,
            "optimize": True,
            "preserve_quality": False,
            "description": "Maximale Komprimierung für E-Mail-Versand"
        }
    }
    
    def __init__(self):
        self.xml_processor = XMLFieldProcessor()
        self.ocr_processor = OCRProcessor()
        self.export_processor = ExportProcessor()
        self.function_parser = None
        self.variable_extractor = None
        self._ocr_cache = {}
        self._zone_cache = {}
        
        self.supported_actions = {
            ProcessingAction.COMPRESS: self._compress_pdf
        }
        
        # Erstelle zentralen temporären Arbeitsordner
        self.temp_base_dir = os.path.join(tempfile.gettempdir(), "hotfolder_pdf_processor")
        os.makedirs(self.temp_base_dir, exist_ok=True)
        
        # Lade Einstellungen
        self.settings = self._load_settings()
        
        # Prüfe Abhängigkeiten beim Start
        self._check_dependencies()
    
    def _load_settings(self) -> ExportSettings:
        """Lädt Einstellungen aus settings.json"""
        try:
            settings_file = "config/settings.json"
            
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return ExportSettings.from_dict(data)
            else:
                # Erstelle Default-Settings
                settings = ExportSettings()
                self._save_settings(settings)
                return settings
        except Exception as e:
            logger.error(f"Fehler beim Laden der Einstellungen: {e}")
            return ExportSettings()

    def _save_settings(self, settings: ExportSettings):
        """Speichert Einstellungen"""
        try:
            settings_file = "config/settings.json"
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Einstellungen: {e}")
    
    def _check_dependencies(self):
        """Prüft ob alle benötigten Abhängigkeiten verfügbar sind"""
        warnings = []
        
        # Basis-Verzeichnis für dependencies
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dependencies_dir = os.path.join(base_dir, 'dependencies')
        
        # Prüfe Ghostscript (nur für Komprimierung)
        if not self._is_ghostscript_available():
            warnings.append("Ghostscript nicht gefunden - PDF-Komprimierung nicht möglich")
            warnings.append(f"Bitte Ghostscript im dependencies Ordner platzieren: {dependencies_dir}")
        
        # Prüfe Tesseract (für PDF/A-Export)
        if not self._is_tesseract_available():
            warnings.append("Tesseract nicht gefunden - PDF/A (Durchsuchbar) Export eingeschränkt")
            warnings.append(f"Bitte Tesseract im dependencies Ordner platzieren: {dependencies_dir}")
        
        # Prüfe OCRmyPDF (für PDF/A-Export)
        try:
            import ocrmypdf
        except ImportError:
            warnings.append("OCRmyPDF nicht installiert - PDF/A (Durchsuchbar) Export nicht möglich")
        
        if warnings:
            logger.warning("Konfigurationswarnungen:\n" + "\n".join(warnings))
    
    def _is_tesseract_available(self) -> bool:
        """Prüft ob Tesseract verfügbar ist"""
        # Basis-Verzeichnis für dependencies
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dependencies_dir = os.path.join(base_dir, 'dependencies')
        
        # Prüfe dependencies Ordner
        tesseract_path = os.path.join(dependencies_dir, 'Tesseract-OCR', 'tesseract.exe')
        if os.path.exists(tesseract_path):
            self._tesseract_path = tesseract_path
            # Setze Umgebungsvariable für OCRmyPDF
            os.environ['TESSERACT_PATH'] = os.path.dirname(tesseract_path)
            logger.debug(f"Tesseract gefunden: {tesseract_path}")
            return True
        
        # Prüfe Installation im Programmverzeichnis
        program_paths = [
            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'belegpilot', 'dependencies', 'Tesseract-OCR', 'tesseract.exe'),
            os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'belegpilot', 'dependencies', 'Tesseract-OCR', 'tesseract.exe')
        ]
        
        for path in program_paths:
            if os.path.exists(path):
                self._tesseract_path = path
                os.environ['TESSERACT_PATH'] = os.path.dirname(path)
                logger.debug(f"Tesseract gefunden in Installationsverzeichnis: {path}")
                return True
        
        # Fallback auf System-PATH
        try:
            result = subprocess.run(["tesseract", "--version"], 
                                  capture_output=True, check=True)
            if result.returncode == 0:
                self._tesseract_path = "tesseract"
                return True
        except:
            pass
        
        return False
    
    def _is_ghostscript_available(self) -> bool:
        """Prüft ob Ghostscript verfügbar ist"""
        # Basis-Verzeichnis für dependencies
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dependencies_dir = os.path.join(base_dir, 'dependencies')
        
        # Prüfe dependencies Ordner mit Glob für verschiedene Versionen
        import glob
        gs_patterns = [
            os.path.join(dependencies_dir, 'gs', 'gs*', 'bin', 'gswin64c.exe'),
            os.path.join(dependencies_dir, 'gs', 'gs*', 'bin', 'gswin32c.exe'),
        ]
        
        for pattern in gs_patterns:
            for gs_path in glob.glob(pattern):
                if os.path.exists(gs_path):
                    self._ghostscript_path = gs_path
                    logger.debug(f"Ghostscript gefunden: {gs_path}")
                    return True
        
        # Prüfe Installation im Programmverzeichnis
        program_patterns = [
            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'belegpilot', 'dependencies', 'gs', 'gs*', 'bin', 'gswin64c.exe'),
            os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'belegpilot', 'dependencies', 'gs', 'gs*', 'bin', 'gswin32c.exe')
        ]
        
        for pattern in program_patterns:
            for gs_path in glob.glob(pattern):
                if os.path.exists(gs_path):
                    self._ghostscript_path = gs_path
                    logger.debug(f"Ghostscript gefunden in Installationsverzeichnis: {gs_path}")
                    return True
        
        # Standard-Prüfung
        try:
            if os.name == 'nt':
                # Windows
                for cmd in ['gswin64c', 'gswin32c']:
                    try:
                        result = subprocess.run([cmd, '--version'], 
                                              capture_output=True, text=True)
                        if result.returncode == 0:
                            self._ghostscript_path = cmd
                            return True
                    except:
                        continue
                return False
            else:
                # Unix/Linux
                result = subprocess.run(['gs', '--version'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    self._ghostscript_path = 'gs'
                    return True
        except:
            pass
        
        return False
    
    def _get_ghostscript_cmd(self) -> str:
        """Gibt den Ghostscript-Befehl zurück"""
        if hasattr(self, '_ghostscript_path'):
            return self._ghostscript_path
        elif os.name == 'nt':
            return 'gswin64c'
        else:
            return 'gs'
    
    def process_document(self, doc_pair: DocumentPair, hotfolder: HotfolderConfig) -> bool:
        """
        Verarbeitet ein Dokument mit vereinfachter Logik
        """
        work_dir = os.path.join(self.temp_base_dir, f"work_{uuid.uuid4().hex}")
        os.makedirs(work_dir, exist_ok=True)
        
        # Variable für verarbeitete XML
        processed_xml_path = None
        
        try:
            # Verschiebe Dateien in temporären Arbeitsordner
            temp_pdf_path = os.path.join(work_dir, os.path.basename(doc_pair.pdf_path))
            shutil.move(doc_pair.pdf_path, temp_pdf_path)
            
            temp_xml_path = None
            if doc_pair.has_xml and doc_pair.xml_path is not None:
                temp_xml_path = os.path.join(work_dir, os.path.basename(doc_pair.xml_path))
                shutil.move(doc_pair.xml_path, temp_xml_path)
            
            # Qualitätskontrolle vor Verarbeitung
            if not self._validate_pdf(temp_pdf_path):
                raise Exception("PDF-Validierung fehlgeschlagen - Datei möglicherweise beschädigt")
            
            # Analysiere PDF für optimale Verarbeitung
            pdf_info = self._analyze_pdf(temp_pdf_path)
            logger.info(f"PDF-Analyse: {pdf_info}")
            
            # XML-Feld-Mappings anwenden - auch ohne XML-Datei verarbeiten
            if hotfolder.xml_field_mappings:
                mappings = [FieldMapping.from_dict(m) for m in hotfolder.xml_field_mappings]
                ocr_zones = [
                    zone if isinstance(zone, dict) else zone.to_dict()
                    for zone in hotfolder.ocr_zones
                ]
                
                # Wenn keine XML vorhanden, erstelle eine temporäre XML
                if not temp_xml_path:
                    # Erstelle eine minimale XML-Datei für die Feldverarbeitung
                    temp_xml_path = os.path.join(work_dir, "temp_fields.xml")
                    with open(temp_xml_path, 'w', encoding='utf-8') as f:
                        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                        f.write('<root>\n')
                        f.write('  <Document>\n')
                        f.write('    <Fields>\n')
                        # Erstelle leere Felder für alle definierten Mappings
                        for mapping in mappings:
                            f.write(f'      <{mapping.field_name}></{mapping.field_name}>\n')
                        f.write('    </Fields>\n')
                        f.write('  </Document>\n')
                        f.write('</root>\n')
                
                # Verarbeite XML-Felder
                success = self.xml_processor.process_xml_with_mappings(
                    temp_xml_path, temp_pdf_path, mappings, ocr_zones, 
                    input_path=hotfolder.input_path,
                    original_pdf_path=doc_pair.pdf_path
                )
                
                if success:
                    logger.info(f"XML-Felder erfolgreich verarbeitet")
                    processed_xml_path = temp_xml_path
                else:
                    logger.error("XML-Feldverarbeitung fehlgeschlagen")
            
            # Führe nur noch unterstützte PDF-Aktionen aus (nur COMPRESS)
            compression_enabled = False
            for action in hotfolder.actions:
                if action in self.supported_actions:
                    params = hotfolder.action_params.get(action.value, {})
                    
                    # Füge PDF-Info zu Parametern hinzu für intelligente Verarbeitung
                    params['pdf_info'] = pdf_info
                    
                    logger.info(f"Führe Aktion aus: {action.value}")
                    success = self.supported_actions[action](temp_pdf_path, params)
                    
                    if not success:
                        raise Exception(f"Aktion {action.value} fehlgeschlagen")
                    
                    if action == ProcessingAction.COMPRESS:
                        compression_enabled = True
                    
                    # Qualitätskontrolle nach jeder Aktion
                    if not self._validate_pdf(temp_pdf_path):
                        raise Exception(f"PDF-Validierung nach {action.value} fehlgeschlagen")
            
            # Führe Exporte durch
            if hasattr(hotfolder, 'export_configs') and hotfolder.export_configs:
                ocr_zones = [
                    zone if isinstance(zone, dict) else zone.to_dict()
                    for zone in hotfolder.ocr_zones
                ]
                
                export_results = self.export_processor.process_exports(
                    temp_pdf_path,
                    processed_xml_path or temp_xml_path,
                    hotfolder.export_configs,
                    ocr_zones,
                    hotfolder.xml_field_mappings,
                    original_pdf_path=doc_pair.pdf_path,
                    input_path=hotfolder.input_path,
                    compression_enabled=compression_enabled
                )
                
                all_successful = all(success for success, _ in export_results)
                if not all_successful:
                    failed_exports = [msg for success, msg in export_results if not success]
                    raise Exception(f"Export-Fehler: {', '.join(failed_exports)}")
            
            # Abschließende Qualitätskontrolle
            final_info = self._analyze_pdf(temp_pdf_path)
            logger.info(f"Finale PDF-Analyse: {final_info}")
            
            # Leere Caches
            self._ocr_cache.clear()
            self._zone_cache.clear()
            
            logger.info(f"Erfolgreich verarbeitet: {os.path.basename(doc_pair.pdf_path)}")
            return True
            
        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung: {e}")
            
            # Verschiebe in Fehlerpfad
            error_path = self._get_error_path(doc_pair, hotfolder)
            os.makedirs(error_path, exist_ok=True)
            
            try:
                if os.path.exists(temp_pdf_path):
                    error_pdf = os.path.join(error_path, os.path.basename(doc_pair.pdf_path))
                    if os.path.exists(error_pdf):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        base, ext = os.path.splitext(error_pdf)
                        error_pdf = f"{base}_{timestamp}{ext}"
                    shutil.move(temp_pdf_path, error_pdf)
                    
                if temp_xml_path and os.path.exists(temp_xml_path):
                    error_xml = os.path.join(error_path, os.path.basename(doc_pair.xml_path or "temp_fields.xml"))
                    if os.path.exists(error_xml):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        base, ext = os.path.splitext(error_xml)
                        error_xml = f"{base}_{timestamp}{ext}"
                    shutil.move(temp_xml_path, error_xml)
                    
                logger.info(f"Dateien in Fehlerpfad verschoben: {error_path}")
                
            except Exception as move_error:
                logger.error(f"Fehler beim Verschieben in Fehlerpfad: {move_error}")
            
            return False
            
        finally:
            # Aufräumen
            try:
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir)
            except Exception as cleanup_error:
                logger.error(f"Fehler beim Aufräumen: {cleanup_error}")
            
    def _validate_pdf(self, pdf_path: str) -> bool:
        """Validiert ob PDF gültig und nicht beschädigt ist"""
        try:
            # Versuche PDF mit PyMuPDF zu öffnen
            doc = fitz.open(pdf_path)
            page_count = doc.page_count
            
            # Prüfe ob mindestens eine Seite vorhanden
            if page_count == 0:
                doc.close()
                return False
            
            # Versuche erste Seite zu laden
            page = doc[0]
            _ = page.get_pixmap()
            
            doc.close()
            return True
            
        except Exception as e:
            logger.error(f"PDF-Validierung fehlgeschlagen: {e}")
            return False
    
    def _analyze_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Analysiert PDF für optimale Verarbeitung"""
        try:
            doc = fitz.open(pdf_path)
            
            info = {
                "pages": doc.page_count,
                "has_text": False,
                "has_images": False,
                "has_forms": False,
                "is_scanned": True,
                "avg_dpi": 0,
                "file_size_mb": os.path.getsize(pdf_path) / (1024 * 1024),
                "needs_ocr": False
            }
            
            total_dpi = 0
            image_count = 0
            text_chars = 0
            
            for page_num in range(min(5, doc.page_count)):  # Analysiere erste 5 Seiten
                page = doc[page_num]
                
                # Text prüfen
                text = page.get_text()
                text_chars += len(text.strip())
                
                # Bilder analysieren
                image_list = page.get_images()
                if image_list:
                    info["has_images"] = True
                    for img in image_list:
                        try:
                            xref = img[0]
                            pix = fitz.Pixmap(doc, xref)
                            if pix.width > 0 and pix.height > 0:
                                # Schätze DPI basierend auf Bildgröße
                                bbox = page.get_image_bbox(img)
                                if bbox:
                                    width_inch = (bbox.x1 - bbox.x0) / 72
                                    height_inch = (bbox.y1 - bbox.y0) / 72
                                    if width_inch > 0 and height_inch > 0:
                                        dpi_x = pix.width / width_inch
                                        dpi_y = pix.height / height_inch
                                        total_dpi += (dpi_x + dpi_y) / 2
                                        image_count += 1
                            pix = None
                        except Exception as img_error:
                            logger.debug(f"Fehler bei Bildanalyse: {img_error}")
                            continue
                
                # Formulare prüfen
                if page.widgets():
                    info["has_forms"] = True
            
            # Auswertung
            info["has_text"] = text_chars > 100
            info["is_scanned"] = info["has_images"] and not info["has_text"]
            info["needs_ocr"] = info["is_scanned"]
            
            if image_count > 0:
                info["avg_dpi"] = int(total_dpi / image_count)
            
            doc.close()
            return info
            
        except Exception as e:
            logger.error(f"PDF-Analyse fehlgeschlagen: {e}")
            return {
                "pages": 0,
                "has_text": False,
                "has_images": False,
                "has_forms": False,
                "is_scanned": False,
                "avg_dpi": 0,
                "file_size_mb": 0,
                "needs_ocr": False
            }
    
    def _compress_pdf(self, pdf_path: str, params: Dict[str, Any]) -> bool:
        """Intelligente PDF-Komprimierung basierend auf Dokumenttyp"""
        try:
            if not self._is_ghostscript_available():
                raise Exception("Ghostscript nicht verfügbar - bitte im dependencies Ordner platzieren")
            
            original_size = os.path.getsize(pdf_path)
            pdf_info = params.get('pdf_info', {})
            
            # Bestimme optimales Komprimierungsprofil
            profile = self._determine_compression_profile(params, pdf_info)
            logger.info(f"Verwende Komprimierungsprofil: {profile['name']}")
            
            # Führe Komprimierung durch
            success = self._compress_with_ghostscript_advanced(pdf_path, profile, pdf_info)
            
            if success:
                compressed_size = os.path.getsize(pdf_path)
                reduction_percent = (1 - compressed_size/original_size) * 100
                logger.info(f"Komprimierung erfolgreich: {reduction_percent:.1f}% Reduktion")
                
                # Warne wenn Qualitätsverlust zu hoch
                if reduction_percent > 70 and profile.get('preserve_quality', True):
                    logger.warning("Hohe Komprimierung - Qualität prüfen!")
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Komprimierung fehlgeschlagen: {e}")
            return False
    
    def _determine_compression_profile(self, params: Dict[str, Any], pdf_info: Dict[str, Any]) -> Dict[str, Any]:
        """Bestimmt das optimale Komprimierungsprofil"""
        # Prüfe ob explizites Profil gewählt wurde
        profile_name = params.get('compression_profile', 'auto')
        
        if profile_name != 'auto' and profile_name in self.COMPRESSION_PROFILES:
            profile = self.COMPRESSION_PROFILES[profile_name].copy()
        else:
            # Automatische Profil-Auswahl basierend auf PDF-Eigenschaften
            if pdf_info.get('is_scanned', False):
                profile = self.COMPRESSION_PROFILES['scan'].copy()
            elif pdf_info.get('file_size_mb', 0) > 10:
                profile = self.COMPRESSION_PROFILES['email'].copy()
            elif pdf_info.get('has_forms', False):
                profile = self.COMPRESSION_PROFILES['rechnung'].copy()
            else:
                profile = self.COMPRESSION_PROFILES['archiv'].copy()
        
        # Überschreibe mit benutzerdefinierten Parametern
        for key in ['color_dpi', 'gray_dpi', 'mono_dpi', 'jpeg_quality']:
            if key in params:
                profile[key] = params[key]
        
        return profile
    
    def _compress_with_ghostscript_advanced(self, pdf_path: str, profile: Dict[str, Any], pdf_info: Dict[str, Any]) -> bool:
        """Erweiterte Ghostscript-Komprimierung mit Qualitätskontrolle"""
        try:
            gs_cmd = self._get_ghostscript_cmd()
            
            # Prüfe nochmal ob Ghostscript funktioniert
            try:
                result = subprocess.run([gs_cmd, '--version'], capture_output=True, check=True)
                if result.returncode != 0:
                    raise Exception("Ghostscript nicht ausführbar")
            except:
                raise Exception("Ghostscript konnte nicht gestartet werden")
            
            temp_output = pdf_path + '.compressed'
            
            # Basis-Befehl
            cmd = [
                gs_cmd,
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.7',  # Neuere PDF-Version für bessere Komprimierung
                '-dNOPAUSE',
                '-dBATCH',
                '-dQUIET',
                '-dSAFER',  # Sicherheitsmodus
                f'-sOutputFile={temp_output}'
            ]
            
            # Auflösungseinstellungen
            cmd.extend([
                f"-dColorImageResolution={profile['color_dpi']}",
                f"-dGrayImageResolution={profile['gray_dpi']}",
                f"-dMonoImageResolution={profile['mono_dpi']}"
            ])
            
            # Downsampling-Einstellungen
            if profile.get('downsample_images', True):
                # Intelligentes Downsampling nur wenn Bild-DPI höher als Ziel-DPI
                if pdf_info.get('avg_dpi', 0) > profile['color_dpi']:
                    cmd.extend([
                        '-dDownsampleColorImages=true',
                        '-dDownsampleGrayImages=true',
                        '-dDownsampleMonoImages=true',
                        '-dColorImageDownsampleType=/Bicubic',
                        '-dGrayImageDownsampleType=/Bicubic',
                        '-dMonoImageDownsampleType=/Bicubic',
                        f"-dColorImageDownsampleThreshold=1.0",
                        f"-dGrayImageDownsampleThreshold=1.0",
                        f"-dMonoImageDownsampleThreshold=1.0"
                    ])
                else:
                    cmd.extend([
                        '-dDownsampleColorImages=false',
                        '-dDownsampleGrayImages=false',
                        '-dDownsampleMonoImages=false'
                    ])
            
            # Komprimierungseinstellungen
            if profile.get('preserve_quality', True):
                # Qualitätserhaltende Komprimierung
                cmd.extend([
                    '-dAutoFilterColorImages=true',
                    '-dAutoFilterGrayImages=true',
                    f"-dJPEGQ={profile['jpeg_quality']/100.0:.2f}",
                    '-dColorImageFilter=/DCTEncode',
                    '-dGrayImageFilter=/DCTEncode',
                    '-dMonoImageFilter=/CCITTFaxEncode',
                    '-dEncodeColorImages=true',
                    '-dEncodeGrayImages=true',
                    '-dEncodeMonoImages=true'
                ])
            else:
                # Aggressive Komprimierung
                cmd.extend([
                    '-dAutoFilterColorImages=false',
                    '-dAutoFilterGrayImages=false',
                    f"-dJPEGQ={profile['jpeg_quality']/100.0:.2f}",
                    '-dColorImageFilter=/DCTEncode',
                    '-dGrayImageFilter=/DCTEncode',
                    '-dMonoImageFilter=/CCITTFaxEncode'
                ])
            
            # Font-Optimierungen
            if profile.get('subset_fonts', True):
                cmd.extend([
                    '-dSubsetFonts=true',
                    '-dEmbedAllFonts=true',
                    '-dCompressFonts=true'
                ])
            
            # Weitere Optimierungen
            if profile.get('optimize', True):
                cmd.extend([
                    '-dOptimize=true',
                    '-dCompressPages=true',
                    '-dUseFlateCompression=true'
                ])
            
            if profile.get('remove_duplicates', True):
                cmd.append('-dDetectDuplicateImages=true')
            
            # PDF/A-Kompatibilität beibehalten wenn vorhanden
            if pdf_info.get('is_pdfa', False):
                cmd.append('-dPDFA=2')
                cmd.append('-dPDFACompatibilityPolicy=1')
            
            # Input-Datei
            cmd.append(pdf_path)
            
            # Ausführen
            logger.debug(f"Ghostscript-Befehl: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Ghostscript-Fehler: {result.stderr}")
                return False
            
            # Prüfe Ergebnis
            if os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
                # Validiere komprimierte PDF
                if self._validate_pdf(temp_output):
                    shutil.move(temp_output, pdf_path)
                    return True
                else:
                    logger.error("Komprimierte PDF ist ungültig")
                    os.remove(temp_output)
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Ghostscript-Komprimierung fehlgeschlagen: {e}")
            return False
    
    def _build_context(self, pdf_path: str, xml_path: Optional[str], 
                       xml_field_mappings: List[Dict], ocr_zones: List[Dict],
                       original_pdf_path: str = None, input_path: str = None) -> Dict[str, Any]:
        """Baut den Kontext für Variablen-Evaluation auf"""
        context = {}
        
        # Basis-Variablen
        if original_pdf_path:
            context['FileName'] = os.path.splitext(os.path.basename(original_pdf_path))[0]
            context['FileExtension'] = os.path.splitext(original_pdf_path)[1]
            context['FilePath'] = original_pdf_path
            context['FullFileName'] = os.path.basename(original_pdf_path)
        else:
            context['FileName'] = os.path.splitext(os.path.basename(pdf_path))[0]
            context['FileExtension'] = '.pdf'
            context['FilePath'] = pdf_path
            context['FullFileName'] = os.path.basename(pdf_path)
        
        # Erweiterte Dateiinformationen
        context['FileSize'] = str(os.path.getsize(pdf_path)) if os.path.exists(pdf_path) else '0'
        context['FileSizeMB'] = f"{os.path.getsize(pdf_path) / (1024*1024):.2f}" if os.path.exists(pdf_path) else '0'
        
        # Datum und Zeit
        now = datetime.now()
        context['Date'] = now.strftime('%d.%m.%Y')
        context['DateDE'] = now.strftime('%d.%m.%Y')
        context['DateISO'] = now.strftime('%Y-%m-%d')
        context['Time'] = now.strftime('%H:%M:%S')
        context['TimeShort'] = now.strftime('%H-%M-%S')
        context['DateTime'] = now.strftime('%d.%m.%Y %H:%M:%S')
        context['DateTimeISO'] = now.strftime('%Y-%m-%d_%H-%M-%S')
        context['Year'] = now.strftime('%Y')
        context['Month'] = now.strftime('%m')
        context['MonthName'] = now.strftime('%B')
        context['Day'] = now.strftime('%d')
        context['Hour'] = now.strftime('%H')
        context['Minute'] = now.strftime('%M')
        context['Second'] = now.strftime('%S')
        context['Weekday'] = now.strftime('%A')
        context['WeekdayShort'] = now.strftime('%a')
        context['WeekNumber'] = now.strftime('%V')
        context['Timestamp'] = str(int(now.timestamp()))
        
        # Level-Variablen
        if input_path and original_pdf_path:
            # Verwende function_parser für Level-Variablen
            if self.variable_extractor is None:
                from core.function_parser import VariableExtractor
                self.variable_extractor = VariableExtractor()
            
            level_vars = self.variable_extractor.get_level_variables(original_pdf_path, input_path)
            context.update(level_vars)
            context['InputPath'] = input_path
        else:
            # Leere Level-Variablen
            for i in range(6):
                context[f'level{i}'] = ""
        
        # OCR-Text falls vorhanden
        if hasattr(self, '_ocr_cache') and pdf_path in self._ocr_cache:
            context['OCR_FullText'] = self._ocr_cache[pdf_path]
        else:
            # Versuche OCR-Text zu extrahieren
            try:
                full_text = self.ocr_processor.extract_text_from_pdf(pdf_path)
                context['OCR_FullText'] = full_text
                self._ocr_cache[pdf_path] = full_text
            except:
                context['OCR_FullText'] = ""
        
        # OCR-Zonen
        if ocr_zones:
            for zone_dict in ocr_zones:
                zone_name = zone_dict.get('name', 'Unnamed')
                
                # Prüfe ob Zone bereits im Cache ist
                cache_key = f"{pdf_path}_{zone_name}"
                if hasattr(self, '_zone_cache') and cache_key in self._zone_cache:
                    context[zone_name] = self._zone_cache[cache_key]
                else:
                    # Extrahiere Text aus Zone
                    try:
                        page_num = zone_dict.get('page_num', 1)
                        zone_coords = zone_dict.get('zone', (0, 0, 100, 100))
                        
                        zone_text = self.ocr_processor.extract_text_from_zone(
                            pdf_path, page_num, zone_coords
                        )
                        
                        context[zone_name] = zone_text
                        if hasattr(self, '_zone_cache'):
                            self._zone_cache[cache_key] = zone_text
                    except:
                        context[zone_name] = ""
        
        # XML-Felder
        if xml_field_mappings:
            # Wenn XML vorhanden, lade Werte daraus
            if xml_path and os.path.exists(xml_path):
                try:
                    tree = ET.parse(xml_path)
                    root = tree.getroot()
                    
                    fields_elem = root.find(".//Fields")
                    if fields_elem is not None:
                        for field in fields_elem:
                            if field.text:
                                context[field.tag] = field.text
                except Exception as e:
                    logger.error(f"XML-Parsing fehlgeschlagen: {e}")
            
            # Füge alle definierten Felder zum Kontext hinzu (mit leeren Werten wenn nicht vorhanden)
            for mapping in xml_field_mappings:
                field_name = mapping.get('field_name', '')
                if field_name and field_name not in context:
                    context[field_name] = ""  # Leerer String als Default
        
        return context
  
    def _get_error_path(self, doc_pair: DocumentPair, hotfolder: HotfolderConfig) -> str:
        """Bestimmt den Fehlerpfad"""
        context = {}
        if self.function_parser is None:
            from core.function_parser import FunctionParser, VariableExtractor
            self.function_parser = FunctionParser()
            self.variable_extractor = VariableExtractor()
        
        context.update(self.variable_extractor.get_standard_variables())
        context.update(self.variable_extractor.get_file_variables(doc_pair.pdf_path))
        context.update(self.variable_extractor.get_level_variables(doc_pair.pdf_path, hotfolder.input_path))
        context['InputPath'] = hotfolder.input_path
        
        error_path_expr = hotfolder.error_path if hasattr(hotfolder, 'error_path') else ""
        return self.export_processor.get_error_path(error_path_expr, context)
    
    def cleanup_temp_dir(self):
        """Räumt temporäre Dateien auf"""
        try:
            if os.path.exists(self.temp_base_dir):
                import time
                now = time.time()
                
                for work_dir in os.listdir(self.temp_base_dir):
                    dir_path = os.path.join(self.temp_base_dir, work_dir)
                    if os.path.isdir(dir_path):
                        dir_age = now - os.path.getmtime(dir_path)
                        if dir_age > 86400:  # 24 Stunden
                            try:
                                shutil.rmtree(dir_path)
                                logger.info(f"Temporärer Ordner gelöscht: {work_dir}")
                            except Exception as e:
                                logger.error(f"Fehler beim Löschen von {work_dir}: {e}")
        except Exception as e:
            logger.error(f"Fehler beim Aufräumen: {e}")