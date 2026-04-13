import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkintermapview
from datetime import datetime, date, time, timedelta
from collections import defaultdict
import csv
import os
import sys

from data_loader import (
    load_events, load_selections, save_selections,
    load_tiers, save_tiers, load_excluded, save_excluded,
    save_profile, load_profile, list_profiles, delete_profile,
    get_unique_sports, get_unique_zones, get_unique_dates,
    get_unique_session_types, get_unique_venues,
    PRICE_CATS, NON_LA_ZONES, VENUE_COORDS,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

MEDAL_SESSION_TYPES = {"Final", "Bronze"}


class MultiSelectPicker(ctk.CTkFrame):
    """A button that opens a scrollable checkbox popup for multi-select."""

    def __init__(self, master, values, on_change=None, placeholder="All", width=220, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._values = list(values)
        self._selected = set()
        self._on_change = on_change
        self._placeholder = placeholder
        self._popup = None
        self._width = width

        self._button = ctk.CTkButton(self, text=placeholder, width=width, anchor="w",
                                      fg_color="#343638", hover_color="#404040",
                                      text_color="white", command=self._toggle_popup)
        self._button.pack()

    def _toggle_popup(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        self._show_popup()

    def _show_popup(self):
        self._popup = ctk.CTkToplevel(self)
        self._popup.overrideredirect(True)
        self._popup.attributes("-topmost", True)

        x = self._button.winfo_rootx()
        y = self._button.winfo_rooty() + self._button.winfo_height()
        self._popup.geometry(f"+{x}+{y}")

        btn_frame = ctk.CTkFrame(self._popup, fg_color="#2b2b2b")
        btn_frame.pack(fill="x", padx=2, pady=(2, 0))
        ctk.CTkButton(btn_frame, text="All", width=55, height=24, font=("Segoe UI", 11),
                       command=self._select_all).pack(side="left", padx=2, pady=2)
        ctk.CTkButton(btn_frame, text="None", width=55, height=24, font=("Segoe UI", 11),
                       command=self._select_none).pack(side="left", padx=2, pady=2)
        ctk.CTkButton(btn_frame, text="Done", width=55, height=24, font=("Segoe UI", 11),
                       fg_color="#4ade80", hover_color="#22c55e", text_color="black",
                       command=self._close_popup).pack(side="right", padx=2, pady=2)

        scroll = ctk.CTkScrollableFrame(self._popup, width=self._width, height=min(300, len(self._values) * 28 + 10))
        scroll.pack(fill="both", expand=True, padx=2, pady=2)

        self._check_vars = {}
        for val in self._values:
            var = tk.BooleanVar(value=(len(self._selected) == 0 or val in self._selected))
            cb = ctk.CTkCheckBox(scroll, text=val, variable=var, font=("Segoe UI", 11),
                                  height=24, command=self._on_check_change)
            cb.pack(anchor="w", padx=4, pady=1)
            self._check_vars[val] = var

        self._popup.bind("<FocusOut>", lambda e: self._popup.after(200, self._check_focus))

    def _check_focus(self):
        if self._popup and self._popup.winfo_exists():
            try:
                focused = self._popup.focus_get()
                if focused is None or not str(focused).startswith(str(self._popup)):
                    self._close_popup()
            except (KeyError, tk.TclError):
                pass

    def _on_check_change(self):
        self._sync_selected()
        self._update_label()

    def _select_all(self):
        for var in self._check_vars.values():
            var.set(True)
        self._sync_selected()
        self._update_label()

    def _select_none(self):
        for var in self._check_vars.values():
            var.set(False)
        self._sync_selected()
        self._update_label()

    def _sync_selected(self):
        self._selected = {val for val, var in self._check_vars.items() if var.get()}

    def _close_popup(self):
        if self._popup and self._popup.winfo_exists():
            self._sync_selected()
            self._popup.destroy()
            self._popup = None
        self._update_label()
        if self._on_change:
            self._on_change()

    def _update_label(self):
        if len(self._selected) == 0 or len(self._selected) == len(self._values):
            self._button.configure(text=self._placeholder)
        elif len(self._selected) <= 2:
            self._button.configure(text=", ".join(sorted(self._selected)))
        else:
            self._button.configure(text=f"{len(self._selected)} selected")

    def get_selected(self):
        if len(self._selected) == 0 or len(self._selected) == len(self._values):
            return None  # None means "all"
        return self._selected


def format_price(p):
    if p is None or p == 0:
        return "-"
    return f"${p:,.2f}"


def format_time(t):
    if t is None:
        return "TBD"
    return t.strftime("%I:%M %p").lstrip("0")


def format_date(d):
    if d is None:
        return "TBD"
    return d.strftime("%a %b %d")


def time_to_minutes(t):
    if t is None:
        return None
    return t.hour * 60 + t.minute


def events_overlap(e1, e2):
    if e1["date"] is None or e2["date"] is None:
        return False
    if e1["date"] != e2["date"]:
        return False
    if e1["start_time"] is None or e2["start_time"] is None:
        return False
    if e1["end_time"] is None or e2["end_time"] is None:
        return False
    return e1["start_time"] < e2["end_time"] and e2["start_time"] < e1["end_time"]


def has_3hr_gap(e1, e2):
    """Check that there's at least 3 hours between events on the same day."""
    if e1["date"] != e2["date"]:
        return True
    end1 = time_to_minutes(e1["end_time"])
    start1 = time_to_minutes(e1["start_time"])
    end2 = time_to_minutes(e2["end_time"])
    start2 = time_to_minutes(e2["start_time"])
    if any(v is None for v in (end1, start1, end2, start2)):
        return True
    if start1 < start2:
        return (start2 - end1) >= 180
    else:
        return (start1 - end2) >= 180


def price_cats_key(prices):
    """Return a hashable key representing which price categories exist."""
    return tuple(sorted(cat for cat in PRICE_CATS if cat in prices))


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LA 2028 Olympics Schedule Builder")
        self.geometry("1600x900")
        self.minsize(1200, 700)

        self.events = load_events()
        self.selections = {}
        self.load_saved_selections()
        self.sport_tiers = load_tiers()
        self.excluded_events = load_excluded()
        self.la_only = tk.BooleanVar(value=True)
        self.filtered_events = []
        self.optimized_plan = []

        self.build_ui()
        self.apply_filters()

    def load_saved_selections(self):
        saved = load_selections()
        for code, data in saved.items():
            self.selections[code] = data

    def build_ui(self):
        self.tabview = ctk.CTkTabview(self, anchor="nw")
        self.tabview.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_browse = self.tabview.add("Browse Events")
        self.tab_schedule = self.tabview.add("My Schedule")
        self.tab_tiers = self.tabview.add("Sport Tiers")
        self.tab_shopping = self.tabview.add("Shopping List")
        self.tab_map = self.tabview.add("Venue Map")

        self.build_browse_tab()
        self.build_schedule_tab()
        self.build_tiers_tab()
        self.build_shopping_tab()
        self.build_map_tab()

    # ── Browse Events Tab ──────────────────────────────────────────────
    def build_browse_tab(self):
        top = ctk.CTkFrame(self.tab_browse)
        top.pack(fill="x", padx=6, pady=(6, 3))

        row1 = ctk.CTkFrame(top, fg_color="transparent")
        row1.pack(fill="x", pady=2)

        ctk.CTkLabel(row1, text="Sport:").pack(side="left", padx=(0, 4))
        sports = get_unique_sports(self.events)
        self.sport_picker = MultiSelectPicker(row1, sports, on_change=self.apply_filters, placeholder="All Sports", width=220)
        self.sport_picker.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row1, text="Zone:").pack(side="left", padx=(0, 4))
        zones = ["All", "LA Area Only"] + get_unique_zones(self.events)
        self.zone_var = ctk.StringVar(value="LA Area Only")
        self.zone_menu = ctk.CTkComboBox(row1, values=zones, variable=self.zone_var, width=180, command=lambda _: self.apply_filters())
        self.zone_menu.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row1, text="Type:").pack(side="left", padx=(0, 4))
        types = ["All"] + get_unique_session_types(self.events)
        self.type_var = ctk.StringVar(value="All")
        self.type_menu = ctk.CTkComboBox(row1, values=types, variable=self.type_var, width=150, command=lambda _: self.apply_filters())
        self.type_menu.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row1, text="Date:").pack(side="left", padx=(0, 4))
        dates_list = get_unique_dates(self.events)
        self._date_strs = [format_date(d) for d in dates_list]
        self._date_lookup = {format_date(d): d for d in dates_list}
        self.date_picker = MultiSelectPicker(row1, self._date_strs, on_change=self.apply_filters, placeholder="All Dates", width=160)
        self.date_picker.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row1, text="Medal:").pack(side="left", padx=(0, 4))
        self.medal_var = ctk.StringVar(value="All")
        self.medal_menu = ctk.CTkComboBox(row1, values=["All", "Medal Events", "Non-Medal Events"],
                                           variable=self.medal_var, width=155, command=lambda _: self.apply_filters())
        self.medal_menu.pack(side="left", padx=(0, 12))

        row2 = ctk.CTkFrame(top, fg_color="transparent")
        row2.pack(fill="x", pady=2)

        ctk.CTkLabel(row2, text="Search:").pack(side="left", padx=(0, 4))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.apply_filters())
        ctk.CTkEntry(row2, textvariable=self.search_var, width=200, placeholder_text="sport, venue, description...").pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row2, text="Max price $:").pack(side="left", padx=(0, 4))
        self.maxprice_var = ctk.StringVar(value="")
        self.maxprice_entry = ctk.CTkEntry(row2, textvariable=self.maxprice_var, width=80, placeholder_text="any")
        self.maxprice_entry.pack(side="left", padx=(0, 12))
        self.maxprice_var.trace_add("write", lambda *_: self.apply_filters())

        self.selected_only_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(row2, text="Show selected only", variable=self.selected_only_var, command=self.apply_filters).pack(side="left", padx=(0, 12))

        self.event_count_label = ctk.CTkLabel(row2, text="0 events")
        self.event_count_label.pack(side="right", padx=6)

        table_frame = ctk.CTkFrame(self.tab_browse)
        table_frame.pack(fill="both", expand=True, padx=6, pady=3)

        cols = ("selected", "sport", "venue", "zone", "date", "time", "type", "description", "cheapest", "session_code")
        # Extended selectmode for multi-select
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="extended")

        self.tree.heading("selected", text="\u2713")
        self.tree.heading("sport", text="Sport")
        self.tree.heading("venue", text="Venue")
        self.tree.heading("zone", text="Zone")
        self.tree.heading("date", text="Date")
        self.tree.heading("time", text="Time")
        self.tree.heading("type", text="Type")
        self.tree.heading("description", text="Description")
        self.tree.heading("cheapest", text="Cheapest")
        self.tree.heading("session_code", text="Code")

        self.tree.column("selected", width=30, anchor="center")
        self.tree.column("sport", width=140)
        self.tree.column("venue", width=170)
        self.tree.column("zone", width=100)
        self.tree.column("date", width=100)
        self.tree.column("time", width=120)
        self.tree.column("type", width=90)
        self.tree.column("description", width=280)
        self.tree.column("cheapest", width=75, anchor="e")
        self.tree.column("session_code", width=70)

        for col in cols:
            self.tree.heading(col, command=lambda c=col: self.sort_tree(c))
        self.sort_col = None
        self.sort_reverse = False

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#2b2b2b", foreground="white",
                         fieldbackground="#2b2b2b", rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#1a1a2e", foreground="white",
                         font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#16213e")])
        style.configure("Treeview", borderwidth=0)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<Double-1>", self.on_event_double_click)
        self.tree.bind("<Return>", self.on_event_double_click)

        detail = ctk.CTkFrame(self.tab_browse)
        detail.pack(fill="x", padx=6, pady=(3, 6))

        self.detail_label = ctk.CTkLabel(detail, text="Select one or more events, then click Add. Ctrl+Click / Shift+Click for multi-select.", font=("Segoe UI", 12))
        self.detail_label.pack(side="left", padx=8, pady=6)

        btn_frame = ctk.CTkFrame(detail, fg_color="transparent")
        btn_frame.pack(side="right")
        ctk.CTkButton(btn_frame, text="Add Selected to Schedule...", command=self.add_selected_events, width=210).pack(side="left", padx=4, pady=6)

        # Save/Load profile buttons
        ctk.CTkButton(btn_frame, text="Save Profile...", command=self.save_profile_dialog, width=120,
                       fg_color="#2563eb", hover_color="#1d4ed8").pack(side="left", padx=4, pady=6)
        ctk.CTkButton(btn_frame, text="Load Profile...", command=self.load_profile_dialog, width=120,
                       fg_color="#7c3aed", hover_color="#6d28d9").pack(side="left", padx=4, pady=6)

    def sort_tree(self, col):
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col = col
            self.sort_reverse = False
        self.populate_tree()

    def apply_filters(self):
        selected_sports = self.sport_picker.get_selected()
        zone = self.zone_var.get()
        stype = self.type_var.get()
        selected_dates = self.date_picker.get_selected()
        search = self.search_var.get().lower().strip()
        selected_only = self.selected_only_var.get()
        medal = self.medal_var.get()

        max_price = None
        try:
            mp = self.maxprice_var.get().strip()
            if mp:
                max_price = float(mp)
        except ValueError:
            pass

        sel_date_set = None
        if selected_dates is not None:
            sel_date_set = {self._date_lookup[ds] for ds in selected_dates if ds in self._date_lookup}

        self.filtered_events = []
        for e in self.events:
            if selected_sports is not None and e["sport"] not in selected_sports:
                continue
            if zone == "LA Area Only" and not e["is_la"]:
                continue
            elif zone not in ("All", "LA Area Only") and e["zone"] != zone:
                continue
            if stype != "All" and e["session_type"] != stype:
                continue
            if medal == "Medal Events" and e["session_type"] not in MEDAL_SESSION_TYPES:
                continue
            if medal == "Non-Medal Events" and e["session_type"] in MEDAL_SESSION_TYPES:
                continue
            if sel_date_set is not None and e["date"] not in sel_date_set:
                continue
            if search:
                haystack = f"{e['sport']} {e['venue']} {e['description']} {e['session_code']} {e['zone']}".lower()
                if search not in haystack:
                    continue
            if max_price is not None:
                cheapest = min(e["prices"].values()) if e["prices"] else None
                if cheapest is None or cheapest > max_price:
                    continue
            if selected_only and e["session_code"] not in self.selections:
                continue
            self.filtered_events.append(e)

        self.populate_tree()

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())

        events = list(self.filtered_events)
        if self.sort_col:
            col_map = {
                "selected": lambda e: e["session_code"] in self.selections,
                "sport": lambda e: e["sport"],
                "venue": lambda e: e["venue"],
                "zone": lambda e: e["zone"],
                "date": lambda e: e["date"] or date(2099, 1, 1),
                "time": lambda e: e["start_time"] or time(23, 59),
                "type": lambda e: e["session_type"],
                "description": lambda e: e["description"],
                "cheapest": lambda e: min(e["prices"].values()) if e["prices"] else 99999,
                "session_code": lambda e: e["session_code"],
            }
            key_fn = col_map.get(self.sort_col, lambda e: "")
            events.sort(key=key_fn, reverse=self.sort_reverse)

        for e in events:
            code = e["session_code"]
            is_sel = "\u2713" if code in self.selections else ""
            cheapest = min(e["prices"].values()) if e["prices"] else None
            time_str = f"{format_time(e['start_time'])} - {format_time(e['end_time'])}"
            self.tree.insert("", "end", iid=code, values=(
                is_sel, e["sport"], e["venue"], e["zone"],
                format_date(e["date"]), time_str, e["session_type"],
                e["description"], format_price(cheapest), code,
            ))

        self.event_count_label.configure(text=f"{len(events)} events")

    def on_event_double_click(self, event=None):
        self.add_selected_events()

    def add_selected_events(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select one or more events from the list first.")
            return

        # Gather events, separate already-selected from new
        new_codes = []
        already_codes = []
        for code in sel:
            if code in self.selections:
                already_codes.append(code)
            else:
                new_codes.append(code)

        # If all selected are already added, offer removal
        if not new_codes and already_codes:
            names = ", ".join(already_codes[:5])
            if len(already_codes) > 5:
                names += f" (+{len(already_codes) - 5} more)"
            if messagebox.askyesno("Remove", f"Remove {len(already_codes)} event(s) from schedule?\n{names}"):
                for c in already_codes:
                    del self.selections[c]
                save_selections(self.selections)
                self.apply_filters()
                self.refresh_schedule()
                self.refresh_tiers()
                self.refresh_shopping()
            return

        if not new_codes:
            return

        # Single event → normal dialog
        if len(new_codes) == 1:
            ev = self.get_event_by_code(new_codes[0])
            if ev:
                self.show_add_dialog(ev)
            return

        # Multiple events → batch dialog
        evs = [self.get_event_by_code(c) for c in new_codes]
        evs = [e for e in evs if e is not None]
        if evs:
            self.show_bulk_add_dialog(evs)

    def get_event_by_code(self, code):
        for e in self.events:
            if e["session_code"] == code:
                return e
        return None

    def show_add_dialog(self, ev):
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Add {ev['sport']} - {ev['session_code']}")
        dialog.transient(self)
        dialog.grab_set()

        scroll = ctk.CTkScrollableFrame(dialog, width=500, height=550)
        scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(scroll, text=f"{ev['sport']}", font=("Segoe UI", 18, "bold")).pack(pady=(10, 2))
        ctk.CTkLabel(scroll, text=f"{ev['venue']} ({ev['zone']})", font=("Segoe UI", 13)).pack()
        ctk.CTkLabel(scroll, text=f"{format_date(ev['date'])}  {format_time(ev['start_time'])} - {format_time(ev['end_time'])}", font=("Segoe UI", 13)).pack()
        ctk.CTkLabel(scroll, text=ev["description"], font=("Segoe UI", 11), wraplength=480).pack(pady=(2, 10))

        conflicts = self.find_conflicts(ev)
        if conflicts:
            conflict_frame = ctk.CTkFrame(scroll, fg_color="#4a1a1a")
            conflict_frame.pack(fill="x", padx=10, pady=5)
            ctk.CTkLabel(conflict_frame, text="Schedule Conflicts:", font=("Segoe UI", 12, "bold"), text_color="#ff6b6b").pack(anchor="w", padx=8, pady=(4, 2))
            for c in conflicts:
                cev = self.get_event_by_code(c)
                ctk.CTkLabel(conflict_frame, text=f"  {cev['sport']} ({c}) {format_time(cev['start_time'])}-{format_time(cev['end_time'])}", text_color="#ff9999", font=("Segoe UI", 11)).pack(anchor="w", padx=8)
            ctk.CTkLabel(conflict_frame, text="", font=("Segoe UI", 4)).pack()

        ctk.CTkLabel(scroll, text="Select ticket category:", font=("Segoe UI", 13, "bold")).pack(pady=(10, 5))

        price_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        price_frame.pack(fill="x", padx=20)

        cat_var = ctk.StringVar()
        first_set = False
        for cat in PRICE_CATS:
            if cat in ev["prices"]:
                price = ev["prices"][cat]
                rb = ctk.CTkRadioButton(price_frame, text=f"{cat}: ${price:,.2f}", variable=cat_var, value=cat)
                rb.pack(anchor="w", padx=10, pady=1)
                if not first_set:
                    cat_var.set(cat)
                    first_set = True

        ctk.CTkLabel(scroll, text="Priority:", font=("Segoe UI", 13, "bold")).pack(pady=(10, 5))
        prio_var = ctk.StringVar(value="want")
        prio_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        prio_frame.pack(fill="x", padx=20)
        ctk.CTkRadioButton(prio_frame, text="Must-have", variable=prio_var, value="must").pack(side="left", padx=10)
        ctk.CTkRadioButton(prio_frame, text="Want", variable=prio_var, value="want").pack(side="left", padx=10)
        ctk.CTkRadioButton(prio_frame, text="If available", variable=prio_var, value="maybe").pack(side="left", padx=10)

        def confirm():
            cat = cat_var.get()
            if not cat:
                messagebox.showwarning("Select Category", "Please select a ticket category.")
                return
            self.selections[ev["session_code"]] = {
                "category": cat,
                "price": ev["prices"][cat],
                "priority": prio_var.get(),
            }
            save_selections(self.selections)
            dialog.destroy()
            self.apply_filters()
            self.refresh_schedule()
            self.refresh_tiers()
            self.refresh_shopping()

        ctk.CTkButton(scroll, text="Add to Schedule", command=confirm, width=200, height=36, font=("Segoe UI", 13)).pack(pady=15)

        dialog.update_idletasks()
        dialog.geometry("540x620")
        dialog.minsize(540, 500)

    def show_bulk_add_dialog(self, evs):
        """Bulk add dialog. Groups events by sport+price structure for batch category selection."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Bulk Add — {len(evs)} Events")
        dialog.transient(self)
        dialog.grab_set()

        scroll = ctk.CTkScrollableFrame(dialog, width=620, height=560)
        scroll.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(scroll, text=f"Adding {len(evs)} events", font=("Segoe UI", 18, "bold")).pack(pady=(10, 4))

        # Group by (sport, price_structure)
        groups = defaultdict(list)
        for ev in evs:
            key = (ev["sport"], price_cats_key(ev["prices"]))
            groups[key].append(ev)

        ctk.CTkLabel(scroll, text=f"{len(groups)} group(s) by sport & ticket structure",
                     font=("Segoe UI", 12), text_color="#888").pack(pady=(0, 8))

        group_vars = {}  # key -> (cat_var, prio_var, events)

        for (sport, pcats), group_evs in sorted(groups.items(), key=lambda x: x[0][0]):
            gframe = ctk.CTkFrame(scroll, fg_color="#1a1a2e", corner_radius=8)
            gframe.pack(fill="x", padx=4, pady=4)

            # Header
            header = ctk.CTkFrame(gframe, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(6, 2))
            ctk.CTkLabel(header, text=f"{sport}", font=("Segoe UI", 14, "bold")).pack(side="left")
            ctk.CTkLabel(header, text=f"  ({len(group_evs)} event{'s' if len(group_evs) > 1 else ''})",
                         font=("Segoe UI", 12), text_color="#888").pack(side="left")

            # Show event list
            for ev in group_evs:
                ctk.CTkLabel(gframe, text=f"    {ev['session_code']}  {format_date(ev['date'])} {format_time(ev['start_time'])}  {ev['description'][:60]}",
                             font=("Segoe UI", 10), text_color="#aaa").pack(anchor="w", padx=14)

            # Category selector (shared for this group)
            cat_frame = ctk.CTkFrame(gframe, fg_color="transparent")
            cat_frame.pack(fill="x", padx=14, pady=(6, 2))
            ctk.CTkLabel(cat_frame, text="Category:", font=("Segoe UI", 12, "bold")).pack(anchor="w")

            cat_var = ctk.StringVar()
            # Use first event's prices as representative
            rep = group_evs[0]
            first_set = False
            for cat in PRICE_CATS:
                if cat in rep["prices"]:
                    price = rep["prices"][cat]
                    rb = ctk.CTkRadioButton(cat_frame, text=f"{cat}: ${price:,.2f}", variable=cat_var, value=cat)
                    rb.pack(anchor="w", padx=10, pady=1)
                    if not first_set:
                        cat_var.set(cat)
                        first_set = True

            # Priority selector
            prio_frame = ctk.CTkFrame(gframe, fg_color="transparent")
            prio_frame.pack(fill="x", padx=14, pady=(4, 8))
            ctk.CTkLabel(prio_frame, text="Priority:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 8))
            prio_var = ctk.StringVar(value="want")
            ctk.CTkRadioButton(prio_frame, text="Must-have", variable=prio_var, value="must").pack(side="left", padx=6)
            ctk.CTkRadioButton(prio_frame, text="Want", variable=prio_var, value="want").pack(side="left", padx=6)
            ctk.CTkRadioButton(prio_frame, text="If available", variable=prio_var, value="maybe").pack(side="left", padx=6)

            group_vars[(sport, pcats)] = (cat_var, prio_var, group_evs)

        def confirm_all():
            added = 0
            for (sport, pcats), (cat_var, prio_var, group_evs) in group_vars.items():
                cat = cat_var.get()
                if not cat:
                    continue
                prio = prio_var.get()
                for ev in group_evs:
                    price = ev["prices"].get(cat)
                    if price is None:
                        # Fallback: pick cheapest available
                        for fallback_cat in reversed(PRICE_CATS):
                            if fallback_cat in ev["prices"]:
                                cat = fallback_cat
                                price = ev["prices"][fallback_cat]
                                break
                    if price is not None:
                        self.selections[ev["session_code"]] = {
                            "category": cat,
                            "price": price,
                            "priority": prio,
                        }
                        added += 1

            save_selections(self.selections)
            dialog.destroy()
            self.apply_filters()
            self.refresh_schedule()
            self.refresh_tiers()
            self.refresh_shopping()
            messagebox.showinfo("Added", f"{added} events added to your schedule.")

        ctk.CTkButton(scroll, text=f"Add All {len(evs)} Events", command=confirm_all,
                       width=250, height=38, font=("Segoe UI", 14, "bold")).pack(pady=15)

        dialog.update_idletasks()
        w = min(700, max(600, dialog.winfo_reqwidth()))
        h = min(750, max(550, dialog.winfo_reqheight()))
        dialog.geometry(f"{w}x{h}")
        dialog.minsize(580, 450)

    def find_conflicts(self, new_event):
        conflicts = []
        for code in self.selections:
            existing = self.get_event_by_code(code)
            if existing and events_overlap(existing, new_event):
                conflicts.append(code)
        return conflicts

    # ── Save / Load Profiles ───────────────────────────────────────────
    def save_profile_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Save Profile")
        dialog.geometry("400x280")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Save Current Selections", font=("Segoe UI", 16, "bold")).pack(pady=(15, 5))
        ctk.CTkLabel(dialog, text=f"{len(self.selections)} events, {len(self.sport_tiers)} sport tiers",
                     font=("Segoe UI", 12), text_color="#888").pack(pady=(0, 10))

        ctk.CTkLabel(dialog, text="Profile name:", font=("Segoe UI", 13)).pack(padx=20, anchor="w")
        name_var = ctk.StringVar()
        ctk.CTkEntry(dialog, textvariable=name_var, width=300, placeholder_text="e.g. Plan A - Swimming Focus").pack(padx=20, pady=4)

        # Show existing profiles
        profiles = list_profiles()
        if profiles:
            ctk.CTkLabel(dialog, text="Existing profiles:", font=("Segoe UI", 11), text_color="#888").pack(padx=20, anchor="w", pady=(8, 2))
            ctk.CTkLabel(dialog, text=", ".join(profiles), font=("Segoe UI", 11), text_color="#666", wraplength=360).pack(padx=20, anchor="w")

        def do_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Name Required", "Enter a profile name.")
                return
            # Sanitize filename
            safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()
            if not safe:
                messagebox.showwarning("Invalid Name", "Name must contain alphanumeric characters.")
                return
            save_profile(safe, self.selections, self.sport_tiers, self.excluded_events)
            dialog.destroy()
            messagebox.showinfo("Saved", f"Profile '{safe}' saved.")

        ctk.CTkButton(dialog, text="Save", command=do_save, width=150, height=36).pack(pady=15)

    def load_profile_dialog(self):
        profiles = list_profiles()
        if not profiles:
            messagebox.showinfo("No Profiles", "No saved profiles found. Save one first.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Load Profile")
        dialog.geometry("450x400")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Load a Saved Profile", font=("Segoe UI", 16, "bold")).pack(pady=(15, 10))

        scroll = ctk.CTkScrollableFrame(dialog, width=400, height=250)
        scroll.pack(fill="both", expand=True, padx=10, pady=5)

        for name in profiles:
            row = ctk.CTkFrame(scroll, fg_color="#1a1a2e", corner_radius=6)
            row.pack(fill="x", padx=4, pady=3)

            ctk.CTkLabel(row, text=name, font=("Segoe UI", 13, "bold")).pack(side="left", padx=10, pady=8)

            def make_delete(n=name):
                def do_del():
                    if messagebox.askyesno("Delete", f"Delete profile '{n}'?"):
                        delete_profile(n)
                        dialog.destroy()
                        self.load_profile_dialog()
                return do_del

            def make_load(n=name):
                def do_load():
                    data = load_profile(n)
                    if data is None:
                        messagebox.showerror("Error", f"Could not load '{n}'.")
                        return
                    self.selections = data["selections"]
                    self.sport_tiers = data["tiers"]
                    self.excluded_events = data["excluded"]
                    save_selections(self.selections)
                    save_tiers(self.sport_tiers)
                    save_excluded(self.excluded_events)
                    dialog.destroy()
                    self.apply_filters()
                    self.refresh_schedule()
                    self.refresh_tiers()
                    self.refresh_shopping()
                    messagebox.showinfo("Loaded", f"Profile '{n}' loaded — {len(self.selections)} events.")
                return do_load

            ctk.CTkButton(row, text="Delete", width=60, height=28, fg_color="#dc2626",
                          hover_color="#ef4444", command=make_delete()).pack(side="right", padx=4, pady=4)
            ctk.CTkButton(row, text="Load", width=60, height=28, command=make_load()).pack(side="right", padx=4, pady=4)

    # ── Schedule Tab ────────────────────────────────────────────────────
    def build_schedule_tab(self):
        top = ctk.CTkFrame(self.tab_schedule)
        top.pack(fill="x", padx=6, pady=6)

        self.budget_var = ctk.StringVar(value="5000")
        ctk.CTkLabel(top, text="Budget: $", font=("Segoe UI", 14)).pack(side="left", padx=(8, 0))
        ctk.CTkEntry(top, textvariable=self.budget_var, width=100).pack(side="left", padx=(0, 12))
        ctk.CTkButton(top, text="Refresh", command=self.refresh_schedule, width=100).pack(side="left", padx=4)

        self.budget_label = ctk.CTkLabel(top, text="", font=("Segoe UI", 14, "bold"))
        self.budget_label.pack(side="right", padx=12)

        self.schedule_scroll = ctk.CTkScrollableFrame(self.tab_schedule)
        self.schedule_scroll.pack(fill="both", expand=True, padx=6, pady=6)

        self.refresh_schedule()

    def refresh_schedule(self):
        for w in self.schedule_scroll.winfo_children():
            w.destroy()

        if not self.selections:
            ctk.CTkLabel(self.schedule_scroll, text="No events selected yet. Browse events and add them to your schedule.",
                         font=("Segoe UI", 14)).pack(pady=40)
            self.budget_label.configure(text="$0.00 / budget")
            return

        by_date = {}
        total = 0
        must_total = 0
        for code, sel in self.selections.items():
            ev = self.get_event_by_code(code)
            if not ev:
                continue
            d = ev["date"]
            if d not in by_date:
                by_date[d] = []
            by_date[d].append((ev, sel))
            total += sel.get("price", 0)
            if sel.get("priority") == "must":
                must_total += sel.get("price", 0)

        budget = 0
        try:
            budget = float(self.budget_var.get())
        except ValueError:
            pass

        color = "#4ade80" if total <= budget else "#f87171"
        self.budget_label.configure(
            text=f"Total: ${total:,.2f}  |  Must-haves: ${must_total:,.2f}  |  Budget: ${budget:,.2f}",
            text_color=color
        )

        for d in sorted(by_date.keys(), key=lambda x: x or date(2099, 1, 1)):
            day_events = by_date[d]
            day_events.sort(key=lambda x: x[0]["start_time"] or time(23, 59))

            day_frame = ctk.CTkFrame(self.schedule_scroll)
            day_frame.pack(fill="x", padx=4, pady=(8, 2))

            day_total = sum(s.get("price", 0) for _, s in day_events)
            ctk.CTkLabel(day_frame, text=f"{format_date(d)}  ({len(day_events)} events, ${day_total:,.2f})",
                         font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=10, pady=(6, 4))

            conflict_pairs = set()
            for i, (e1, _) in enumerate(day_events):
                for j, (e2, _) in enumerate(day_events):
                    if i < j and events_overlap(e1, e2):
                        conflict_pairs.add(e1["session_code"])
                        conflict_pairs.add(e2["session_code"])

            for ev, sel in day_events:
                has_conflict = ev["session_code"] in conflict_pairs
                bg = "#4a1a1a" if has_conflict else "#1a2a1a" if sel["priority"] == "must" else "#1a1a2e"
                row = ctk.CTkFrame(day_frame, fg_color=bg, corner_radius=6)
                row.pack(fill="x", padx=8, pady=2)

                prio_colors = {"must": "#4ade80", "want": "#60a5fa", "maybe": "#a78bfa"}
                prio_label = sel.get("priority", "want").upper()
                time_str = f"{format_time(ev['start_time'])} - {format_time(ev['end_time'])}"

                left_text = f"  [{prio_label}]  {time_str}  |  {ev['sport']}  |  {ev['venue']}"
                right_text = f"{sel['category']}: ${sel['price']:,.2f}"

                ctk.CTkLabel(row, text=left_text, font=("Segoe UI", 12),
                             text_color=prio_colors.get(sel.get("priority"), "white")).pack(side="left", padx=6, pady=4)
                if has_conflict:
                    ctk.CTkLabel(row, text=" CONFLICT", font=("Segoe UI", 11, "bold"),
                                 text_color="#ff6b6b").pack(side="left")
                ctk.CTkLabel(row, text=right_text, font=("Segoe UI", 12)).pack(side="right", padx=6, pady=4)

                def make_remove(c=ev["session_code"]):
                    def remove():
                        if messagebox.askyesno("Remove", f"Remove {c} from schedule?"):
                            del self.selections[c]
                            save_selections(self.selections)
                            self.refresh_schedule()
                            self.refresh_tiers()
                            self.refresh_shopping()
                            self.apply_filters()
                    return remove

                ctk.CTkButton(row, text="X", width=28, height=28, fg_color="#dc2626",
                              hover_color="#ef4444", command=make_remove()).pack(side="right", padx=2, pady=4)

    # ── Sport Tiers Tab ─────────────────────────────────────────────────
    def build_tiers_tab(self):
        top = ctk.CTkFrame(self.tab_tiers)
        top.pack(fill="x", padx=6, pady=6)

        ctk.CTkLabel(top, text="Rank Your Sports by Priority", font=("Segoe UI", 16, "bold")).pack(side="left", padx=8)
        ctk.CTkLabel(top, text="(Tier 1 = highest priority. Sports on the same tier have equal priority.)",
                     font=("Segoe UI", 12), text_color="#888").pack(side="left", padx=12)
        ctk.CTkButton(top, text="Save & Recalculate", command=self.save_tiers_and_recalc, width=180).pack(side="right", padx=8)

        self.tiers_scroll = ctk.CTkScrollableFrame(self.tab_tiers)
        self.tiers_scroll.pack(fill="both", expand=True, padx=6, pady=6)

        self.refresh_tiers()

    def get_selected_sports(self):
        sports = set()
        for code in self.selections:
            ev = self.get_event_by_code(code)
            if ev:
                sports.add(ev["sport"])
        return sorted(sports)

    def refresh_tiers(self):
        for w in self.tiers_scroll.winfo_children():
            w.destroy()

        sports = self.get_selected_sports()
        if not sports:
            ctk.CTkLabel(self.tiers_scroll, text="Select some events first, then come back to rank your sports.",
                         font=("Segoe UI", 14)).pack(pady=40)
            return

        self.sport_tiers = {s: t for s, t in self.sport_tiers.items() if s in sports}

        max_tier = max(self.sport_tiers.values()) if self.sport_tiers else 0
        for s in sports:
            if s not in self.sport_tiers:
                max_tier += 1
                self.sport_tiers[s] = max_tier

        sport_event_count = {}
        for code in self.selections:
            ev = self.get_event_by_code(code)
            if ev:
                sport_event_count[ev["sport"]] = sport_event_count.get(ev["sport"], 0) + 1

        tiers_grouped = {}
        for s, t in self.sport_tiers.items():
            if t not in tiers_grouped:
                tiers_grouped[t] = []
            tiers_grouped[t].append(s)

        self._tier_vars = {}
        num_tiers = max(tiers_grouped.keys()) if tiers_grouped else 1

        for tier_num in sorted(tiers_grouped.keys()):
            tier_sports = sorted(tiers_grouped[tier_num])

            tier_frame = ctk.CTkFrame(self.tiers_scroll, fg_color="#1a1a2e", corner_radius=8)
            tier_frame.pack(fill="x", padx=4, pady=4)

            header = ctk.CTkFrame(tier_frame, fg_color="transparent")
            header.pack(fill="x", padx=8, pady=(6, 2))

            brightness = max(0.3, 1.0 - (tier_num - 1) * 0.12)
            r = int(74 * brightness)
            g = int(222 * brightness)
            b = int(128 * brightness)
            tier_color = f"#{r:02x}{g:02x}{b:02x}"

            ctk.CTkLabel(header, text=f"Tier {tier_num}", font=("Segoe UI", 16, "bold"),
                         text_color=tier_color).pack(side="left")

            for sport in tier_sports:
                sport_row = ctk.CTkFrame(tier_frame, fg_color="#2b2b3b", corner_radius=6)
                sport_row.pack(fill="x", padx=12, pady=2)

                count = sport_event_count.get(sport, 0)
                ctk.CTkLabel(sport_row, text=f"{sport}  ({count} event{'s' if count != 1 else ''})",
                             font=("Segoe UI", 13)).pack(side="left", padx=10, pady=6)

                tier_var = ctk.StringVar(value=str(tier_num))
                self._tier_vars[sport] = tier_var
                tier_options = [str(i) for i in range(1, num_tiers + 2)]
                ctk.CTkLabel(sport_row, text="Tier:", font=("Segoe UI", 11)).pack(side="right", padx=(0, 4))
                ctk.CTkComboBox(sport_row, values=tier_options, variable=tier_var,
                                 width=60, font=("Segoe UI", 11)).pack(side="right", padx=(0, 8), pady=4)

                def make_move_up(s=sport):
                    def move():
                        cur = self.sport_tiers.get(s, 1)
                        if cur > 1:
                            self.sport_tiers[s] = cur - 1
                            self._compact_tiers()
                            save_tiers(self.sport_tiers)
                            self.refresh_tiers()
                    return move

                def make_move_down(s=sport):
                    def move():
                        cur = self.sport_tiers.get(s, 1)
                        self.sport_tiers[s] = cur + 1
                        self._compact_tiers()
                        save_tiers(self.sport_tiers)
                        self.refresh_tiers()
                    return move

                ctk.CTkButton(sport_row, text="\u25bc", width=28, height=28, command=make_move_down(),
                              fg_color="#444", hover_color="#555").pack(side="right", padx=1, pady=4)
                ctk.CTkButton(sport_row, text="\u25b2", width=28, height=28, command=make_move_up(),
                              fg_color="#444", hover_color="#555").pack(side="right", padx=1, pady=4)

            ctk.CTkLabel(tier_frame, text="", font=("Segoe UI", 2)).pack()

    def _compact_tiers(self):
        if not self.sport_tiers:
            return
        used = sorted(set(self.sport_tiers.values()))
        mapping = {old: new for new, old in enumerate(used, 1)}
        self.sport_tiers = {s: mapping[t] for s, t in self.sport_tiers.items()}

    def save_tiers_and_recalc(self):
        for sport, var in self._tier_vars.items():
            try:
                self.sport_tiers[sport] = int(var.get())
            except ValueError:
                pass
        self._compact_tiers()
        save_tiers(self.sport_tiers)
        self.refresh_tiers()
        self.refresh_shopping()

    # ── Shopping List Tab ───────────────────────────────────────────────
    def build_shopping_tab(self):
        top = ctk.CTkFrame(self.tab_shopping)
        top.pack(fill="x", padx=6, pady=6)

        ctk.CTkLabel(top, text="Optimized 6-Event Plan", font=("Segoe UI", 16, "bold")).pack(side="left", padx=8)
        ctk.CTkButton(top, text="Export to CSV", command=self.export_csv, width=140).pack(side="right", padx=8)
        ctk.CTkButton(top, text="Recalculate", command=self.refresh_shopping, width=120).pack(side="right", padx=4)

        info = ctk.CTkFrame(self.tab_shopping, fg_color="transparent")
        info.pack(fill="x", padx=6)
        ctk.CTkLabel(info, text="12 tickets (2 per event)  |  One sport per event  |  3hr gap between events  |  Higher tiers first  |  Days compressed",
                     font=("Segoe UI", 11), text_color="#888").pack(anchor="w", padx=8)

        self.shopping_scroll = ctk.CTkScrollableFrame(self.tab_shopping)
        self.shopping_scroll.pack(fill="both", expand=True, padx=6, pady=6)

        self.refresh_shopping()

    def build_optimized_plan(self):
        """
        Build the best 6-event plan. Two-phase approach:
        Phase 1: Pick the best candidate per sport (tier-priority sorted).
        Phase 2: From those, greedily select 6 that fit, preferring same-day
                 packing (day compression) while respecting the 3hr gap rule.
        """
        prio_order = {"must": 0, "want": 1, "maybe": 2}

        # Build candidate list
        candidates = []
        for code, sel in self.selections.items():
            if code in self.excluded_events:
                continue
            ev = self.get_event_by_code(code)
            if not ev or ev["date"] is None or ev["start_time"] is None:
                continue
            tier = self.sport_tiers.get(ev["sport"], 999)
            is_medal = 0 if ev["session_type"] in MEDAL_SESSION_TYPES else 1
            prio = prio_order.get(sel.get("priority", "want"), 1)
            candidates.append({
                "code": code,
                "event": ev,
                "selection": sel,
                "tier": tier,
                "is_medal": is_medal,
                "prio": prio,
                "sort_key": (tier, is_medal, prio, sel.get("price", 9999)),
            })

        # Sort by tier priority
        candidates.sort(key=lambda c: c["sort_key"])

        # Phase 1: For each sport, pick the best candidate (already sorted, so first wins)
        best_per_sport = {}
        for cand in candidates:
            sport = cand["event"]["sport"]
            if sport not in best_per_sport:
                best_per_sport[sport] = cand

        # Sort sports by tier to establish pick order
        sport_order = sorted(best_per_sport.keys(), key=lambda s: best_per_sport[s]["sort_key"])

        # Phase 2: Greedy selection with day compression
        # We try to pack events onto days that already have picks, as long as 3hr gap holds.
        # Strategy: Process sports in tier order. For each sport, find all non-excluded
        # candidates for that sport. Prefer candidates on days already used by the plan.
        plan = []
        used_sports = set()
        plan_days = set()  # dates already in the plan

        for sport in sport_order:
            if len(plan) >= 6:
                break
            if sport in used_sports:
                continue

            # Get all candidates for this sport, sorted: prefer days already in plan, then by sort_key
            sport_cands = [c for c in candidates if c["event"]["sport"] == sport]

            # Score: bonus for being on an existing plan day
            def day_score(c):
                on_existing_day = 0 if c["event"]["date"] in plan_days else 1
                return (on_existing_day, c["sort_key"])

            sport_cands.sort(key=day_score)

            for cand in sport_cands:
                # Check 3hr gap with all picked events
                ok = True
                for picked in plan:
                    if not has_3hr_gap(cand["event"], picked["event"]):
                        ok = False
                        break
                if ok:
                    plan.append(cand)
                    used_sports.add(sport)
                    plan_days.add(cand["event"]["date"])
                    break

        # Sort final plan by tier first, then date/time within tier
        plan.sort(key=lambda c: (c["tier"], c["event"]["date"], c["event"]["start_time"]))
        return plan

    def refresh_shopping(self):
        for w in self.shopping_scroll.winfo_children():
            w.destroy()

        if not self.selections:
            ctk.CTkLabel(self.shopping_scroll, text="No events selected yet.",
                         font=("Segoe UI", 14)).pack(pady=40)
            return

        if not self.sport_tiers:
            ctk.CTkLabel(self.shopping_scroll, text="Set your sport tiers first in the Sport Tiers tab, then come back.",
                         font=("Segoe UI", 14)).pack(pady=40)
            return

        self.optimized_plan = self.build_optimized_plan()

        if not self.optimized_plan:
            ctk.CTkLabel(self.shopping_scroll, text="No valid plan could be built. Check your selections and excluded events.",
                         font=("Segoe UI", 14)).pack(pady=40)
            return

        # Summary
        total = sum(c["selection"]["price"] * 2 for c in self.optimized_plan)
        unique_days = len(set(c["event"]["date"] for c in self.optimized_plan))

        summary = ctk.CTkFrame(self.shopping_scroll, fg_color="#1a1a2e", corner_radius=8)
        summary.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(summary, text="Your Plan", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(summary, text=f"{len(self.optimized_plan)} events  |  {len(self.optimized_plan) * 2} tickets  |  {unique_days} day(s)  |  Total: ${total:,.2f}",
                     font=("Segoe UI", 14), text_color="#4ade80").pack(anchor="w", padx=20, pady=(0, 4))
        if self.excluded_events:
            ctk.CTkLabel(summary, text=f"{len(self.excluded_events)} event(s) marked unavailable",
                         font=("Segoe UI", 11), text_color="#f87171").pack(anchor="w", padx=20, pady=(0, 6))
        else:
            ctk.CTkLabel(summary, text="", font=("Segoe UI", 2)).pack()

        # Plan items - sorted by tier
        running = 0
        for idx, cand in enumerate(self.optimized_plan, 1):
            ev = cand["event"]
            sel = cand["selection"]
            ticket_cost = sel["price"] * 2
            running += ticket_cost
            tier = cand["tier"]

            brightness = max(0.3, 1.0 - (tier - 1) * 0.12)
            r = int(74 * brightness)
            g = int(222 * brightness)
            b = int(128 * brightness)
            tier_color = f"#{r:02x}{g:02x}{b:02x}"

            medal_str = " (Medal)" if cand["is_medal"] == 0 else ""

            row = ctk.CTkFrame(self.shopping_scroll, fg_color="#1a2a1a" if idx % 2 == 1 else "#1a1a2e", corner_radius=6)
            row.pack(fill="x", padx=4, pady=3)

            top_line = ctk.CTkFrame(row, fg_color="transparent")
            top_line.pack(fill="x", padx=8, pady=(6, 0))

            ctk.CTkLabel(top_line, text=f"#{idx}", font=("Segoe UI", 14, "bold"), width=30).pack(side="left")
            ctk.CTkLabel(top_line, text=f"Tier {tier}", font=("Segoe UI", 12, "bold"),
                         text_color=tier_color, width=55).pack(side="left", padx=4)
            ctk.CTkLabel(top_line, text=f"{ev['sport']}{medal_str}", font=("Segoe UI", 14, "bold")).pack(side="left", padx=4)
            ctk.CTkLabel(top_line, text=f"{sel['category']}: ${sel['price']:,.2f} x2 = ${ticket_cost:,.2f}",
                         font=("Segoe UI", 13, "bold")).pack(side="right", padx=4)

            bot_line = ctk.CTkFrame(row, fg_color="transparent")
            bot_line.pack(fill="x", padx=8, pady=(0, 6))

            ctk.CTkLabel(bot_line, text=f"    {ev['venue']}  |  {format_date(ev['date'])}  {format_time(ev['start_time'])} - {format_time(ev['end_time'])}",
                         font=("Segoe UI", 11), text_color="#aaa").pack(side="left")
            ctk.CTkLabel(bot_line, text=f"Running: ${running:,.2f}", font=("Segoe UI", 11), text_color="#888").pack(side="right", padx=4)

            def make_exclude(c=cand["code"]):
                def exclude():
                    self.excluded_events.add(c)
                    save_excluded(self.excluded_events)
                    self.refresh_shopping()
                return exclude

            ctk.CTkButton(bot_line, text="Unavailable / Too Expensive", width=210, height=26,
                          fg_color="#7f1d1d", hover_color="#991b1b", font=("Segoe UI", 11),
                          command=make_exclude()).pack(side="right", padx=(0, 12))

        # Excluded events section
        if self.excluded_events:
            ctk.CTkLabel(self.shopping_scroll, text="", font=("Segoe UI", 6)).pack()
            excl_frame = ctk.CTkFrame(self.shopping_scroll, fg_color="#2a1a1a", corner_radius=8)
            excl_frame.pack(fill="x", padx=4, pady=4)
            ctk.CTkLabel(excl_frame, text="Excluded Events (marked unavailable/too expensive):",
                         font=("Segoe UI", 13, "bold"), text_color="#f87171").pack(anchor="w", padx=10, pady=(6, 2))

            for code in sorted(self.excluded_events):
                ev = self.get_event_by_code(code)
                if not ev:
                    continue
                erow = ctk.CTkFrame(excl_frame, fg_color="#3a1a1a", corner_radius=4)
                erow.pack(fill="x", padx=12, pady=1)
                ctk.CTkLabel(erow, text=f"{ev['sport']} ({code}) - {format_date(ev['date'])} {format_time(ev['start_time'])}",
                             font=("Segoe UI", 11), text_color="#f99").pack(side="left", padx=8, pady=3)

                def make_restore(c=code):
                    def restore():
                        self.excluded_events.discard(c)
                        save_excluded(self.excluded_events)
                        self.refresh_shopping()
                    return restore

                ctk.CTkButton(erow, text="Restore", width=70, height=24, fg_color="#444",
                              hover_color="#555", font=("Segoe UI", 10),
                              command=make_restore()).pack(side="right", padx=4, pady=3)

            ctk.CTkLabel(excl_frame, text="", font=("Segoe UI", 2)).pack()

    def export_csv(self):
        if not self.optimized_plan:
            messagebox.showinfo("Empty", "No plan to export. Recalculate first.")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".csv",
                                                 filetypes=[("CSV files", "*.csv")],
                                                 initialfile="LA2028_shopping_list.csv")
        if not filepath:
            return

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Order", "Tier", "Sport", "Session Code", "Venue", "Zone",
                             "Date", "Start Time", "End Time", "Description", "Type",
                             "Category", "Price Each", "Price x2"])
            for idx, cand in enumerate(self.optimized_plan, 1):
                ev = cand["event"]
                sel = cand["selection"]
                writer.writerow([
                    idx, cand["tier"], ev["sport"], cand["code"],
                    ev["venue"], ev["zone"],
                    ev["date"].strftime("%Y-%m-%d") if ev["date"] else "TBD",
                    format_time(ev["start_time"]), format_time(ev["end_time"]),
                    ev["description"], ev["session_type"],
                    sel["category"], f"{sel['price']:.2f}", f"{sel['price'] * 2:.2f}",
                ])

        messagebox.showinfo("Exported", f"Shopping list saved to:\n{filepath}")

    # ── Map Tab ─────────────────────────────────────────────────────────
    def build_map_tab(self):
        top = ctk.CTkFrame(self.tab_map)
        top.pack(fill="x", padx=6, pady=6)

        ctk.CTkLabel(top, text="LA 2028 Venue Map", font=("Segoe UI", 16, "bold")).pack(side="left", padx=8)

        self.map_selected_only = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(top, text="Show only my selected venues", variable=self.map_selected_only,
                         command=self.refresh_map).pack(side="right", padx=8)

        self.map_widget = tkintermapview.TkinterMapView(self.tab_map, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True, padx=6, pady=6)
        self.map_widget.set_position(34.0, -118.3)
        self.map_widget.set_zoom(10)

        self.map_markers = []
        self.refresh_map()

    def refresh_map(self):
        for m in self.map_markers:
            m.delete()
        self.map_markers.clear()

        if self.map_selected_only.get():
            venues_to_show = set()
            for code in self.selections:
                ev = self.get_event_by_code(code)
                if ev:
                    venues_to_show.add(ev["venue"])
        else:
            venues_to_show = set(e["venue"] for e in self.events if e["is_la"])

        for venue, coords in VENUE_COORDS.items():
            if venue not in venues_to_show:
                continue

            venue_events = [e for e in self.events if e["venue"] == venue]
            selected_at = [e for e in venue_events if e["session_code"] in self.selections]

            sports = sorted(set(e["sport"] for e in venue_events))
            text = f"{venue}\n{len(venue_events)} events ({', '.join(sports[:3])}{'...' if len(sports) > 3 else ''})"
            if selected_at:
                text += f"\n{len(selected_at)} selected"

            color = "#4ade80" if selected_at else "#60a5fa"
            marker = self.map_widget.set_marker(coords[0], coords[1], text=venue, marker_color_outside=color, marker_color_circle=color)
            self.map_markers.append(marker)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
