"""Clickless - GTK Config Editor

A GUI for editing clickless config, similar to Mouseless's in-app config editor.
Opens the config.yaml and provides sections for Grid, Behavior, Style, Keybindings.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango
import yaml
import os
import copy


class ConfigEditor(Gtk.Window):

    def __init__(self, config, config_path=None):
        super().__init__(title="Clickless - Config Editor")
        self.set_default_size(700, 800)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.config = copy.deepcopy(config)
        self.original_config = config

        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, 'config.yaml')
            user_config = os.path.expanduser('~/.config/clickless/config.yaml')
            if os.path.exists(user_config):
                config_path = user_config
        self.config_path = config_path

        # Search
        self._search_text = ""

        self._build_ui()
        self.connect('key-press-event', self._on_key_press)

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        self.add(vbox)

        # Header bar with search and save
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title = Gtk.Label(label="Clickless Configuration")
        title.set_markup("<b>Clickless Configuration</b>")
        header.pack_start(title, True, True, 0)

        search_entry = Gtk.SearchEntry()
        search_entry.set_placeholder_text("Search settings... (Ctrl+F)")
        search_entry.connect('search-changed', self._on_search)
        self._search_entry = search_entry
        header.pack_start(search_entry, True, True, 0)

        save_btn = Gtk.Button(label="Save")
        save_btn.get_style_context().add_class('suggested-action')
        save_btn.connect('clicked', self._on_save)
        header.pack_end(save_btn, False, False, 0)

        restore_btn = Gtk.Button(label="Restore Defaults")
        restore_btn.connect('clicked', self._on_restore)
        header.pack_end(restore_btn, False, False, 0)

        vbox.pack_start(header, False, False, 0)

        # Scrolled notebook with sections
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        notebook = Gtk.Notebook()
        notebook.set_scrollable(True)
        self._notebook = notebook

        # Add sections
        notebook.append_page(self._build_keybindings_page(), Gtk.Label(label="Keybindings"))
        notebook.append_page(self._build_grid_page(), Gtk.Label(label="Grid Options"))
        notebook.append_page(self._build_behavior_page(), Gtk.Label(label="Behavior"))
        notebook.append_page(self._build_style_page(), Gtk.Label(label="Style"))

        scroll.add(notebook)
        vbox.pack_start(scroll, True, True, 0)

        # Status bar
        self._status = Gtk.Label(label="")
        self._status.set_halign(Gtk.Align.START)
        vbox.pack_start(self._status, False, False, 0)

    # ── Section builders ─────────────────────────────────────────

    def _build_keybindings_page(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(6)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)

        kb = self.config.get('keybindings', {})
        row = 0

        sections = {
            "Overlay": ['show_overlay', 'hide_overlay', 'move_to_next_monitor',
                        'move_to_prev_monitor', 'edit_config', 'toggle_continuous_mode',
                        'cycle_grid_action_level', 'toggle_overlay_lock'],
            "Mouse Actions": ['execute_mouse_action', 'execute_mouse_move', 'undo_last_key',
                              'release_hold_drag', 'repeat_last_action',
                              'hold_for_move', 'hold_for_drag',
                              'hold_for_right_button', 'hold_for_middle_button',
                              'hold_for_back_button', 'hold_for_forward_button',
                              'cycle_mouse_action', 'cycle_mouse_button', 'cycle_click_count'],
            "Subgrid Nudge": ['subgrid_nudge_up', 'subgrid_nudge_down',
                              'subgrid_nudge_left', 'subgrid_nudge_right'],
            "Free Mode": ['toggle_free_mode', 'enter_free_mode', 'exit_free_mode',
                          'free_move_up', 'free_move_down', 'free_move_left', 'free_move_right'],
            "Free Mode Mouse": ['free_click_left', 'free_click_right', 'free_click_middle',
                                'free_click_back', 'free_click_forward'],
            "Free Mode Scroll": ['free_wheel_up', 'free_wheel_down',
                                 'free_wheel_left', 'free_wheel_right'],
            "Global Mouse Buttons": ['global_left_click', 'global_right_click', 'global_middle_click'],
        }

        for section_name, keys in sections.items():
            label = Gtk.Label()
            label.set_markup(f"<b>{section_name}</b>")
            label.set_halign(Gtk.Align.START)
            grid.attach(label, 0, row, 2, 1)
            row += 1

            for key_name in keys:
                val = kb.get(key_name, '')
                if isinstance(val, list):
                    val = ', '.join(val)
                name_label = Gtk.Label(label=self._pretty_name(key_name))
                name_label.set_halign(Gtk.Align.START)
                name_label.set_tooltip_text(key_name)
                entry = Gtk.Entry()
                entry.set_text(str(val))
                entry.set_hexpand(True)
                entry.connect('changed', self._on_kb_changed, key_name)

                grid.attach(name_label, 0, row, 1, 1)
                grid.attach(entry, 1, row, 1, 1)
                row += 1

            # Spacer
            grid.attach(Gtk.Label(), 0, row, 2, 1)
            row += 1

        return grid

    def _build_grid_page(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(6)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)

        row = 0
        configs = self.config.get('grid', {}).get('configs', [{}])

        for ci, cfg in enumerate(configs):
            label = Gtk.Label()
            label.set_markup(f"<b>Grid Config: {cfg.get('name', f'config_{ci}')}</b>")
            label.set_halign(Gtk.Align.START)
            grid.attach(label, 0, row, 2, 1)
            row += 1

            fields = [
                ('level1_columns', 'int'), ('level1_rows', 'int'), ('level1_keys', 'str'),
                ('level2_columns', 'int'), ('level2_rows', 'int'), ('level2_keys', 'str'),
                ('subgrid_columns', 'int'), ('subgrid_rows', 'int'), ('subgrid_keys', 'str'),
                ('always_show_subgrid', 'bool'),
                ('hold_subgrid_key_for_nudge', 'bool'),
                ('nudges_per_cell', 'int'),
            ]

            for fname, ftype in fields:
                val = cfg.get(fname, '')
                name_label = Gtk.Label(label=self._pretty_name(fname))
                name_label.set_halign(Gtk.Align.START)

                if ftype == 'bool':
                    widget = Gtk.Switch()
                    widget.set_active(bool(val))
                    widget.connect('state-set', self._on_grid_bool_changed, ci, fname)
                else:
                    widget = Gtk.Entry()
                    widget.set_text(str(val))
                    widget.set_hexpand(True)
                    widget.connect('changed', self._on_grid_changed, ci, fname, ftype)

                grid.attach(name_label, 0, row, 1, 1)
                grid.attach(widget, 1, row, 1, 1)
                row += 1

            row += 1

        # Monitor assignment
        label = Gtk.Label()
        label.set_markup("<b>Monitor Assignment</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        row += 1

        for fname in ['monitor_assignment_mode', 'custom_monitor_assignments']:
            val = self.config.get('grid', {}).get(fname, '')
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            entry = Gtk.Entry()
            entry.set_text(str(val))
            entry.set_hexpand(True)
            entry.connect('changed', self._on_top_grid_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            row += 1

        return grid

    def _build_behavior_page(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(6)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)

        row = 0
        b = self.config.get('behavior', {})

        # Overlay / cursor
        label = Gtk.Label()
        label.set_markup("<b>Overlay / Cursor</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        row += 1

        str_fields = [
            'initial_overlay_monitor', 'initial_action_location',
            'grid_action_level', 'hide_location',
        ]
        bool_fields = ['hide_cursor_on_click', 'continuous_mode']

        for fname in str_fields:
            val = b.get(fname, '')
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            entry = Gtk.Entry()
            entry.set_text(str(val))
            entry.set_hexpand(True)
            entry.connect('changed', self._on_behavior_changed, fname, 'str')
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            row += 1

        for fname in bool_fields:
            val = b.get(fname, False)
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            widget = Gtk.Switch()
            widget.set_active(bool(val))
            widget.connect('state-set', self._on_behavior_bool_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            row += 1

        # Movement / timing
        grid.attach(Gtk.Label(), 0, row, 2, 1)
        row += 1
        label = Gtk.Label()
        label.set_markup("<b>Movement / Timing</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        row += 1

        int_fields = ['move_duration_ms', 'multi_click_threshold_ms', 'tap_threshold_ms']
        for fname in int_fields:
            val = b.get(fname, 0)
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            spin = Gtk.SpinButton.new_with_range(0, 5000, 10)
            spin.set_value(float(val))
            spin.connect('value-changed', self._on_behavior_spin_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(spin, 1, row, 1, 1)
            row += 1

        bool_fields2 = ['move_system_cursor_with_virtual']
        for fname in bool_fields2:
            val = b.get(fname, False)
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            widget = Gtk.Switch()
            widget.set_active(bool(val))
            widget.connect('state-set', self._on_behavior_bool_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
            row += 1

        # Free mode
        grid.attach(Gtk.Label(), 0, row, 2, 1)
        row += 1
        label = Gtk.Label()
        label.set_markup("<b>Free Mode</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        row += 1

        fm = b.get('free_mode', {})
        fm_fields = [
            ('base_move_speed', 1, 100, 1),
            ('move_speed_multiplier', 0.1, 10, 0.1),
            ('movement_easing_factor', 0.01, 1.0, 0.01),
            ('base_wheel_speed', 1, 50, 1),
            ('wheel_speed_multiplier', 0.1, 10, 0.1),
            ('wheel_easing_factor', 0.01, 1.0, 0.01),
            ('wheel_step_size', 1, 50, 1),
            ('wheel_step_size_large', 1, 100, 1),
            ('auto_off_seconds', 0, 120, 1),
        ]

        for fname, lo, hi, step in fm_fields:
            val = fm.get(fname, lo)
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            spin = Gtk.SpinButton.new_with_range(lo, hi, step)
            spin.set_digits(2 if step < 1 else 0)
            spin.set_value(float(val))
            spin.connect('value-changed', self._on_free_mode_spin_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(spin, 1, row, 1, 1)
            row += 1

        return grid

    def _build_style_page(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(6)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)

        row = 0
        s = self.config.get('style', {})

        # Opacity
        label = Gtk.Label()
        label.set_markup("<b>Opacity</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        row += 1

        for fname in ['master_opacity', 'overlay_opacity']:
            val = s.get(fname, 1.0)
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
            scale.set_value(float(val))
            scale.set_hexpand(True)
            scale.connect('value-changed', self._on_style_scale_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(scale, 1, row, 1, 1)
            row += 1

        # Font
        grid.attach(Gtk.Label(), 0, row, 2, 1)
        row += 1
        label = Gtk.Label()
        label.set_markup("<b>Text</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        row += 1

        for fname in ['font', 'font_weight']:
            val = s.get(fname, '')
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            entry = Gtk.Entry()
            entry.set_text(str(val))
            entry.set_hexpand(True)
            entry.connect('changed', self._on_style_str_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            row += 1

        for fname in ['font_size_multiplier', 'subgrid_font_size_multiplier']:
            val = s.get(fname, 1.0)
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            spin = Gtk.SpinButton.new_with_range(0.1, 5, 0.1)
            spin.set_digits(1)
            spin.set_value(float(val))
            spin.connect('value-changed', self._on_style_spin_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(spin, 1, row, 1, 1)
            row += 1

        # Grid lines
        grid.attach(Gtk.Label(), 0, row, 2, 1)
        row += 1
        label = Gtk.Label()
        label.set_markup("<b>Grid Lines</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        row += 1

        for fname in ['grid_line_style']:
            val = s.get(fname, 'lines')
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            combo = Gtk.ComboBoxText()
            combo.append_text('lines')
            combo.append_text('dots')
            combo.set_active(0 if val == 'lines' else 1)
            combo.connect('changed', self._on_style_combo_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(combo, 1, row, 1, 1)
            row += 1

        for fname in ['grid_line_width']:
            val = s.get(fname, 1)
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            spin = Gtk.SpinButton.new_with_range(0, 5, 1)
            spin.set_value(float(val))
            spin.connect('value-changed', self._on_style_spin_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(spin, 1, row, 1, 1)
            row += 1

        # Cursor
        grid.attach(Gtk.Label(), 0, row, 2, 1)
        row += 1
        label = Gtk.Label()
        label.set_markup("<b>Virtual Cursor</b>")
        label.set_halign(Gtk.Align.START)
        grid.attach(label, 0, row, 2, 1)
        row += 1

        for fname in ['cursor_size']:
            val = s.get(fname, 12)
            name_label = Gtk.Label(label=self._pretty_name(fname))
            name_label.set_halign(Gtk.Align.START)
            spin = Gtk.SpinButton.new_with_range(4, 40, 1)
            spin.set_value(float(val))
            spin.connect('value-changed', self._on_style_spin_changed, fname)
            grid.attach(name_label, 0, row, 1, 1)
            grid.attach(spin, 1, row, 1, 1)
            row += 1

        return grid

    # ── Change handlers ──────────────────────────────────────────

    def _on_kb_changed(self, entry, key_name):
        self.config.setdefault('keybindings', {})[key_name] = entry.get_text()

    def _on_grid_changed(self, entry, ci, fname, ftype):
        val = entry.get_text()
        if ftype == 'int':
            try:
                val = int(val)
            except ValueError:
                return
        self.config.setdefault('grid', {}).setdefault('configs', [{}])[ci][fname] = val

    def _on_grid_bool_changed(self, switch, state, ci, fname):
        self.config.setdefault('grid', {}).setdefault('configs', [{}])[ci][fname] = state

    def _on_top_grid_changed(self, entry, fname):
        self.config.setdefault('grid', {})[fname] = entry.get_text()

    def _on_behavior_changed(self, entry, fname, ftype):
        self.config.setdefault('behavior', {})[fname] = entry.get_text()

    def _on_behavior_bool_changed(self, switch, state, fname):
        self.config.setdefault('behavior', {})[fname] = state

    def _on_behavior_spin_changed(self, spin, fname):
        self.config.setdefault('behavior', {})[fname] = int(spin.get_value())

    def _on_free_mode_spin_changed(self, spin, fname):
        self.config.setdefault('behavior', {}).setdefault('free_mode', {})[fname] = spin.get_value()

    def _on_style_scale_changed(self, scale, fname):
        self.config.setdefault('style', {})[fname] = round(scale.get_value(), 2)

    def _on_style_str_changed(self, entry, fname):
        self.config.setdefault('style', {})[fname] = entry.get_text()

    def _on_style_spin_changed(self, spin, fname):
        self.config.setdefault('style', {})[fname] = spin.get_value()

    def _on_style_combo_changed(self, combo, fname):
        self.config.setdefault('style', {})[fname] = combo.get_active_text()

    # ── Actions ──────────────────────────────────────────────────

    def _on_save(self, button):
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            self._status.set_text(f"Saved to {self.config_path}")
            # Update the live config reference
            self.original_config.clear()
            self.original_config.update(self.config)
        except Exception as e:
            self._status.set_text(f"Error saving: {e}")

    def _on_restore(self, button):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Restore default configuration?",
        )
        dialog.format_secondary_text("This will overwrite your current config.")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            self._status.set_text("Defaults restored. Save to apply.")

    def _on_search(self, entry):
        self._search_text = entry.get_text().lower()

    def _on_key_press(self, widget, event):
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            name = Gdk.keyval_name(event.keyval)
            if name and name.lower() == 'f':
                self._search_entry.grab_focus()
                return True
            if name and name.lower() == 's':
                self._on_save(None)
                return True
        return False

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _pretty_name(key):
        return key.replace('_', ' ').title()
