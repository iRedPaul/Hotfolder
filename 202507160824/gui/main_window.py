"""
Hauptfenster der Hotfolder-Anwendung
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys
import os
from typing import Optional
from PIL import Image, ImageTk

# Systempfad-Anpassung, um auf übergeordnete Module zugreifen zu können
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.hotfolder_dialog import HotfolderDialog
from gui.database_config_dialog import DatabaseConfigDialog
from core.hotfolder_manager import HotfolderManager
from models.hotfolder_config import ProcessingAction
from core.license_manager import get_license_manager


class MainWindow:
    """Hauptfenster der Anwendung"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("belegpilot")
        self.root.geometry("950x650")
        self.root.minsize(800, 500)
        self.root.configure(bg='#ECECEC')

        # Fenster-Icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
        icon_image = ImageTk.PhotoImage(Image.open(icon_path))
        self.root.iconphoto(False, icon_image)

        # Manager
        self.manager = HotfolderManager()

        # UI-Erstellung
        self._configure_styles()
        self._create_menu()
        self._create_top_bar()
        self._create_main_content()
        self._create_statusbar()

        # Lade Hotfolder-Daten
        self._refresh_list()

        # Starte Manager und prüfe, ob ein GUI-Update nötig ist
        license_deactivated = self.manager.start()
        if license_deactivated:
            self.root.after(100, self._refresh_list)

        # Binde Events
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._bind_keyboard_shortcuts()

        # Initialisiere Statusleiste
        self._update_status()



    def _configure_styles(self):
        """Konfiguriert alle ttk-Stile für ein modernes Aussehen."""
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # Schriftarten definieren
        self.default_font = ("Segoe UI", 10)
        self.bold_font = ("Segoe UI", 10, "bold")
        self.banner_font = ("Segoe UI", 26)

        # Globale Stile anpassen
        self.style.configure('.',
                             background='#FFFFFF',
                             foreground='#333333',
                             font=self.default_font,
                             fieldbackground='#FFFFFF')
        
        self.root.option_add('*TCombobox*Listbox.font', self.default_font)

        # Spezifische Widget-Stile
        self.style.configure("TFrame", background='#FFFFFF')
        self.style.configure("Top.TFrame", background='#FFFFFF')
        self.style.configure("Content.TFrame", background='#ECECEC')

        self.style.configure("TButton", padding=(12, 6), font=self.default_font, relief="flat", borderwidth=0)
        self.style.map("TButton",
            background=[('active', '#E0E0E0'), ('!active', '#F0F0F0')],
            foreground=[('!disabled', '#333333')]
        )
        
        self.style.configure("Treeview", rowheight=30, font=self.default_font)
        self.style.configure("Treeview.Heading", font=self.bold_font, padding=(10, 8))
        self.style.map('Treeview',
                       background=[('selected', '#233462')],
                       foreground=[('selected', 'white')])

        # Entfernt den gestrichelten Fokus-Rahmen um die Treeview-Items
        self.style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

    def _create_top_bar(self):
        """Erstellt die obere Leiste mit Buttons und Banner."""
        top_frame = ttk.Frame(self.root, style="Top.TFrame", height=80, padding=(10, 10))
        top_frame.pack(side=tk.TOP, fill=tk.X)
        top_frame.pack_propagate(False)

        # Toolbar für Buttons
        toolbar = ttk.Frame(top_frame, style="Top.TFrame")
        toolbar.pack(side=tk.LEFT)

        self.new_button = ttk.Button(toolbar, text="➕ Neuer Hotfolder", command=self._new_hotfolder)
        self.new_button.pack(side=tk.LEFT, padx=(0, 6))

        self.edit_button = ttk.Button(toolbar, text="✏️ Bearbeiten", command=self._edit_hotfolder, state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=(0, 6))

        self.delete_button = ttk.Button(toolbar, text="🗑️ Löschen", command=self._delete_hotfolder, state=tk.DISABLED)
        self.delete_button.pack(side=tk.LEFT)

        # Banner
        self._create_banner(top_frame)

    def _create_banner(self, parent):
        """Erstellt den Banner-Bereich rechts in der Top-Bar."""
        banner_frame = tk.Frame(parent, bg='white')
        banner_frame.pack(side=tk.RIGHT)
        
        try:
            banner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "banner.png")
            if os.path.exists(banner_path):
                img = Image.open(banner_path)
                aspect_ratio = img.width / img.height
                new_height = 50
                new_width = int(new_height * aspect_ratio)
                banner_image = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                self.banner_photo = ImageTk.PhotoImage(banner_image)
                banner_label = tk.Label(banner_frame, image=self.banner_photo, bg='white')
                banner_label.pack()
            else:
                self._create_text_banner(banner_frame)
        except Exception:
            self._create_text_banner(banner_frame)

    def _create_text_banner(self, parent):
        """Erstellt einen Text-Banner als Fallback."""
        text_frame = tk.Frame(parent, bg='white')
        text_frame.pack(padx=10)
        
        beleg_label = tk.Label(text_frame, text="beleg", font=(self.banner_font[0], self.banner_font[1], "bold"), fg="#1a365d", bg='white')
        beleg_label.pack(side=tk.LEFT)
        
        pilot_label = tk.Label(text_frame, text="pilot", font=self.banner_font, fg="#4299e1", bg='white')
        pilot_label.pack(side=tk.LEFT)

    def _create_menu(self):
        """Erstellt die Menüleiste."""
        menubar = tk.Menu(self.root, font=self.default_font)
        self.root.config(menu=menubar)
        
        # Menü-Struktur (vereinfacht zur Lesbarkeit)
        menus = {
            "Datei": [
                ("Neuer Hotfolder", "Ctrl+N", self._new_hotfolder),
                "---",
                ("Hotfolder importieren...", "Ctrl+I", self._import_hotfolder),
                ("Hotfolder exportieren...", "Ctrl+E", self._export_hotfolder),
                "---",
                ("Beenden", "Alt+F4", self._on_closing)
            ],
            "Bearbeiten": [
                ("Hotfolder bearbeiten", "F2", self._edit_hotfolder),
                ("Hotfolder löschen", "Del", self._delete_hotfolder),
                "---",
                ("Aktivieren/Deaktivieren", "Leertaste", self._toggle_hotfolder),
                "---",
                ("Einstellungen", "", self._show_settings)
            ],
            "Extras": [
                ("Counter-Management", "", self._manage_counters),
                ("Datenbank-Verbindungen...", "", self._manage_databases)
            ],
            "Hilfe": [
                ("Über", "", self._show_about)
            ]
        }

        for menu_name, items in menus.items():
            menu = tk.Menu(menubar, tearoff=0, font=self.default_font)
            menubar.add_cascade(label=menu_name, menu=menu)
            for item in items:
                if item == "---":
                    menu.add_separator()
                else:
                    label, accelerator, command = item
                    menu.add_command(label=label, accelerator=accelerator, command=command)

    def _bind_keyboard_shortcuts(self):
        """Binde alle Tastaturkürzel."""
        self.root.bind("<Control-n>", lambda e: self._new_hotfolder())
        self.root.bind("<Control-i>", lambda e: self._import_hotfolder())
        self.root.bind("<Control-e>", lambda e: self._export_hotfolder())
        self.root.bind("<F2>", lambda e: self._edit_hotfolder())
        self.root.bind("<Delete>", lambda e: self._delete_hotfolder())
        self.root.bind("<space>", lambda e: self._toggle_hotfolder())

    def _create_main_content(self):
        """Erstellt den Hauptbereich mit der Hotfolder-Liste."""
        self.main_frame = ttk.Frame(self.root, style="Content.TFrame", padding=(10,0,10,10))
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Treeview für die Hotfolder-Liste
        self.tree = ttk.Treeview(self.main_frame, columns=("Aktiv", "Name", "Beschreibung"), show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew")

        # Spaltenkonfiguration
        self.tree.heading("Aktiv", text="Aktiv")
        self.tree.heading("Name", text="Name")
        self.tree.heading("Beschreibung", text="Beschreibung")
        self.tree.column("Aktiv", width=60, minwidth=60, anchor=tk.CENTER)
        self.tree.column("Name", width=250, minwidth=150)
        self.tree.column("Beschreibung", width=500, minwidth=200)

        # Scrollbars
        vsb = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(self.main_frame, orient="horizontal", command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Kontextmenü
        self.context_menu = tk.Menu(self.root, tearoff=0, font=self.default_font)
        self.context_menu.add_command(label="Bearbeiten", command=self._edit_hotfolder)
        self.context_menu.add_command(label="Löschen", command=self._delete_hotfolder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Aktivieren/Deaktivieren", command=self._toggle_hotfolder)
        
        # Events für die Treeview
        self.tree.bind("<Double-Button-1>", lambda e: self._edit_hotfolder())
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)

    def _create_statusbar(self):
        """Erstellt die untere Statusleiste."""
        statusbar_frame = ttk.Frame(self.root, style="Top.TFrame", padding=(10, 5))
        statusbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = ttk.Label(statusbar_frame, text="Bereit", style="Top.TLabel")
        self.status_label.pack(side=tk.LEFT)

    def _refresh_list(self):
        """Aktualisiert die Hotfolder-Liste in der Treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Tags für die Farbgebung konfigurieren
        self.tree.tag_configure("disabled", foreground="#888888")
        self.tree.tag_configure("enabled", foreground="#333333")

        for hotfolder in self.manager.get_hotfolders():
            aktiv_symbol = "✓" if hotfolder.enabled else "✗"
            tag = "enabled" if hotfolder.enabled else "disabled"
            
            description = hotfolder.description or "Keine Beschreibung"
            
            # Füge Item mit ID und Farb-Tag hinzu
            self.tree.insert("", "end", iid=hotfolder.id, values=(aktiv_symbol, hotfolder.name, description), tags=(tag,))

    def _on_selection_changed(self, event=None):
        """Aktualisiert den Zustand der Buttons basierend auf der Auswahl."""
        is_selection = bool(self.tree.selection())
        state = tk.NORMAL if is_selection else tk.DISABLED
        self.edit_button.config(state=state)
        self.delete_button.config(state=state)

    def _get_selected_hotfolder_id(self) -> Optional[str]:
        """Gibt die ID des ersten ausgewählten Hotfolders zurück."""
        selection = self.tree.selection()
        return selection[0] if selection else None

    # --- Backend- und Dialog-Methoden (unverändert in der Logik) ---

    def _new_hotfolder(self):
        dialog = HotfolderDialog(self.root)
        result = dialog.show()
        if result:
            success, message = self.manager.create_hotfolder(
                name=str(result["name"] or ""), input_path=str(result["input_path"] or ""),
                description=str(result.get("description", "") or ""), actions=result["actions"],
                action_params=result["action_params"], xml_field_mappings=result.get("xml_field_mappings", []),
                output_filename_expression=str(result.get("output_filename_expression", "<FileName>") or "<FileName>"),
                ocr_zones=result.get("ocr_zones", []), export_configs=result.get("export_configs", []),
                stamp_configs=result.get("stamp_configs", []), error_path=str(result.get("error_path", "") or "")
            )
            if success:
                self._refresh_list()
                self._update_status("Hotfolder erstellt")
            else: messagebox.showerror("Fehler", message)

    def _edit_hotfolder(self):
        hotfolder_id = self._get_selected_hotfolder_id()
        if not hotfolder_id: return
        hotfolder = self.manager.get_hotfolder(hotfolder_id)
        if not hotfolder: return

        dialog = HotfolderDialog(self.root, hotfolder)
        result = dialog.show()
        if result:
            success, message = self.manager.update_hotfolder(
                hotfolder_id, name=str(result["name"] or ""),
                input_path=str(result["input_path"] or ""), description=str(result.get("description", "") or ""),
                process_pairs=result["process_pairs"], actions=result["actions"],
                action_params=result["action_params"], xml_field_mappings=result.get("xml_field_mappings", []),
                output_filename_expression=str(result.get("output_filename_expression", "<FileName>") or "<FileName>"),
                ocr_zones=result.get("ocr_zones", []), export_configs=result.get("export_configs", []),
                stamp_configs=result.get("stamp_configs", []), error_path=str(result.get("error_path", "") or "")
            )
            if success:
                self._refresh_list()
                self._update_status("Hotfolder aktualisiert")
            else: messagebox.showerror("Fehler", message)

    def _delete_hotfolder(self):
        hotfolder_id = self._get_selected_hotfolder_id()
        if not hotfolder_id: return
        hotfolder = self.manager.get_hotfolder(hotfolder_id)
        if not hotfolder: return

        if messagebox.askyesno("Hotfolder löschen", f"Möchten Sie den Hotfolder '{hotfolder.name}' wirklich löschen?"):
            success, message = self.manager.delete_hotfolder(hotfolder_id)
            if success:
                self._refresh_list()
                self._update_status("Hotfolder gelöscht")
            else: messagebox.showerror("Fehler", message)
    
    def _toggle_hotfolder(self):
        hotfolder_id = self._get_selected_hotfolder_id()
        if not hotfolder_id: return
        hotfolder = self.manager.get_hotfolder(hotfolder_id)
        if not hotfolder: return
        
        new_state = not hotfolder.enabled
        if new_state:
            license_manager = get_license_manager()
            if not license_manager.is_licensed():
                messagebox.showerror("Keine gültige Lizenz", "Sie können keine Hotfolder ohne gültige Lizenz aktivieren.")
                return
            duplicate_name = self.manager.config_manager.is_input_path_used(hotfolder.input_path, exclude_id=hotfolder_id)
            if duplicate_name:
                messagebox.showerror("Doppelter Input-Ordner", f"Der Input-Ordner wird bereits vom Hotfolder '{duplicate_name}' verwendet.")
                return

        success, message = self.manager.toggle_hotfolder(hotfolder_id, new_state)
        if success:
            self._refresh_list()
            self._update_status(message)
        else: messagebox.showerror("Fehler", message)
        
    def _import_hotfolder(self):
        filename = filedialog.askopenfilename(parent=self.root, title="Hotfolder importieren", filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")])
        if filename:
            success, message = self.manager.config_manager.import_hotfolder(filename, generate_new_id=True)
            if success:
                self._refresh_list()
                self._update_status(message)
                messagebox.showinfo("Import erfolgreich", message + "\n\nDer Hotfolder wurde deaktiviert importiert.")
            else: messagebox.showerror("Fehler beim Import", message)

    def _export_hotfolder(self):
        hotfolder_id = self._get_selected_hotfolder_id()
        if not hotfolder_id:
            messagebox.showwarning("Kein Hotfolder ausgewählt", "Bitte wählen Sie einen Hotfolder für den Export aus.")
            return
        hotfolder = self.manager.get_hotfolder(hotfolder_id)
        if not hotfolder: return

        default_filename = f"{hotfolder.name.replace(' ', '_')}_hotfolder.json"
        filename = filedialog.asksaveasfilename(parent=self.root, title="Hotfolder exportieren", defaultextension=".json", initialfile=default_filename, filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")])
        if filename:
            success, message = self.manager.config_manager.export_hotfolder(hotfolder_id, filename)
            if success:
                self._update_status(message)
                messagebox.showinfo("Export erfolgreich", message)
            else: messagebox.showerror("Fehler beim Export", message)

    def _manage_counters(self):
        try:
            from gui.counter_management_dialog import CounterManagementDialog
            dialog = CounterManagementDialog(self.root)
            dialog.show()
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Öffnen des Counter-Managements: {e}")

    def _manage_databases(self):
        try:
            dialog = DatabaseConfigDialog(self.root)
            self.root.wait_window(dialog.dialog)
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Öffnen der Datenbank-Verwaltung: {e}")

    def _show_settings(self):
        try:
            from gui.settings_dialog import SettingsDialog
            dialog = SettingsDialog(self.root)
            if dialog.show():
                self._update_status("Einstellungen gespeichert")
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Öffnen der Einstellungen: {e}")

    def _show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            if item_id not in self.tree.selection():
                self.tree.selection_set(item_id)
            self.context_menu.post(event.x_root, event.y_root)
    
    def _show_about(self):
        messagebox.showinfo(
            "Über belegpilot",
            "belegpilot v1.0.0\n\n"
            "Ein skalierbares Tool zur automatischen PDF-Verarbeitung."
        )

    def _update_status(self, message: str = None):
        """Aktualisiert die Statusleiste."""
        if message:
            self.status_label.config(text=message)
            self.root.after(4000, self._update_status) # Nachricht nach 4s zurücksetzen
        else:
            active_count = len([h for h in self.manager.get_hotfolders() if h.enabled])
            total_count = len(self.manager.get_hotfolders())
            self.status_label.config(text=f"{active_count} von {total_count} Hotfoldern aktiv")

    def _on_closing(self):
        """Wird beim Schließen des Fensters aufgerufen."""
        self.manager.stop()
        self.root.destroy()

    def run(self):
        """Startet die Anwendung."""
        self.root.mainloop()