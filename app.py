"""Tkinter interface for the Beam Designer desktop app."""
from __future__ import annotations

import csv
import json
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages

from beam_calculations import MATERIALS, calculate_beam

BG = "#f3f6fa"
BLUE = "#1769aa"


class BeamDesigner:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Beam Designer")
        self.root.geometry("1200x820")
        self.root.minsize(900, 650)
        self.root.configure(bg=BG)
        self.loads = [{"type": "uniform", "magnitude": 1.0, "start": 0.0, "end": 20.0}]
        self._build_menu()
        self._build_ui()
        self.update_view()

    def _build_menu(self):
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Save", command=self.save_beam, accelerator="Ctrl+S")
        file_menu.add_command(label="Open", command=self.open_beam, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Export CSV", command=self.export_csv)
        file_menu.add_command(label="Calculation sheet PDF", command=self.export_pdf)
        menu.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menu)
        self.root.bind("<Control-s>", lambda _e: self.save_beam())
        self.root.bind("<Control-o>", lambda _e: self.open_beam())

    def _build_ui(self):
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        panel = tk.Frame(self.root, bg="white", padx=14, pady=12, width=310)
        panel.grid(row=0, column=0, sticky="nsw", padx=(12, 6), pady=12)
        panel.grid_propagate(False)
        view = tk.Frame(self.root, bg=BG)
        view.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        view.rowconfigure(0, weight=1)
        view.columnconfigure(0, weight=1)

        tk.Label(panel, text="BEAM DESIGNER", bg="white", fg="#16324f", font=("Arial", 16, "bold")).pack(anchor="w", pady=(0, 12))
        self.support_var = tk.StringVar(value="Simply supported")
        self._combo(panel, "Support type", self.support_var, ["Simply supported", "Cantilever"])
        self.span_var = tk.DoubleVar(value=20.0)
        tk.Label(panel, text="Span (ft)", bg="white", fg="#425466").pack(anchor="w")
        span_row = tk.Frame(panel, bg="white")
        span_row.pack(fill="x", pady=(3, 2))
        self.span_scale = tk.Scale(span_row, from_=4, to=40, orient="horizontal", variable=self.span_var,
                                   command=lambda _v: self.update_view(), showvalue=False, bg="white", highlightthickness=0)
        self.span_scale.pack(side="left", fill="x", expand=True)
        self.span_entry = ttk.Spinbox(span_row, from_=4, to=40, increment=1, textvariable=self.span_var, width=6, command=self.update_view)
        self.span_entry.pack(side="right", padx=(4, 0))
        self.span_entry.bind("<Return>", lambda _e: self.update_view())
        self.material_var = tk.StringVar(value="Steel")
        self._combo(panel, "Material", self.material_var, list(MATERIALS))
        self.section_var = tk.StringVar(value="W12x26")
        self.section_box = self._combo(panel, "Section", self.section_var, list(MATERIALS["Steel"]["sections"]))
        self.limit_var = tk.StringVar(value="360")
        self._combo(panel, "Deflection limit L/n", self.limit_var, ["240", "360"])

        tk.Label(panel, text="Loads", bg="white", fg="#16324f", font=("Arial", 11, "bold")).pack(anchor="w", pady=(12, 4))
        self.load_list = tk.Listbox(panel, height=7, activestyle="none", relief="solid", bd=1, font=("Arial", 9))
        self.load_list.pack(fill="x")
        self.load_list.bind("<Double-Button-1>", lambda _e: self.edit_load())
        btnrow = tk.Frame(panel, bg="white")
        btnrow.pack(fill="x", pady=5)
        ttk.Button(btnrow, text="Add point", command=self.add_point).pack(side="left", expand=True, fill="x", padx=(0, 3))
        ttk.Button(btnrow, text="Add uniform", command=self.add_uniform).pack(side="left", expand=True, fill="x", padx=(3, 0))
        ttk.Button(panel, text="Edit selected", command=self.edit_load).pack(fill="x", pady=2)
        ttk.Button(panel, text="Remove selected", command=self.remove_load).pack(fill="x", pady=2)

        self.status_title = tk.Label(panel, text="DESIGN CHECKS", bg="white", fg="#16324f", font=("Arial", 11, "bold"))
        self.status_title.pack(anchor="w", pady=(14, 5))
        self.bending_text = tk.StringVar()
        self.deflection_text = tk.StringVar()
        self.suggestion_text = tk.StringVar()
        self.bending_label = tk.Label(panel, textvariable=self.bending_text, justify="left", anchor="w", bg="#edf7f0", padx=8, pady=7, wraplength=270)
        self.bending_label.pack(fill="x", pady=3)
        self.deflection_label = tk.Label(panel, textvariable=self.deflection_text, justify="left", anchor="w", bg="#edf7f0", padx=8, pady=7, wraplength=270)
        self.deflection_label.pack(fill="x", pady=3)
        self.bending_bar = tk.Canvas(panel, height=8, bg="white", highlightthickness=0)
        self.bending_bar.pack(fill="x", pady=(0, 3))
        self.deflection_bar = tk.Canvas(panel, height=8, bg="white", highlightthickness=0)
        self.deflection_bar.pack(fill="x", pady=(0, 3))
        self.bending_label.bind("<Enter>", lambda _e: self._tip("Bending stress = |Mmax| × 12 / Sx. Passes when it is at or below Fb."))
        self.deflection_label.bind("<Enter>", lambda _e: self._tip("Maximum absolute deflection is compared with span in inches divided by the selected limit."))
        self.suggestion_label = tk.Label(panel, textvariable=self.suggestion_text, bg="white", fg="#425466", justify="left", wraplength=270)
        self.suggestion_label.pack(anchor="w", pady=(6, 3))
        self.use_button = ttk.Button(panel, text="Use suggested section", command=self.use_suggestion)
        self.use_button.pack(fill="x", pady=(0, 10))
        ttk.Button(panel, text="Export results to CSV", command=self.export_csv).pack(fill="x", pady=2)
        ttk.Button(panel, text="Save calculation sheet PDF", command=self.export_pdf).pack(fill="x", pady=2)
        self.note = tk.Label(panel, text="Self-weight is ignored. Loads are downward positive.", bg="white", fg="#667788", wraplength=270, justify="left", font=("Arial", 8))
        self.note.pack(anchor="w", side="bottom", pady=(10, 0))

        self.figure = Figure(figsize=(8, 7), dpi=100, facecolor="white")
        self.axes = [self.figure.add_subplot(4, 1, i + 1) for i in range(4)]
        self.figure.subplots_adjust(hspace=0.58, left=0.1, right=0.97, top=0.97, bottom=0.07)
        self.canvas = FigureCanvasTkAgg(self.figure, master=view)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.canvas.mpl_connect("button_press_event", self.start_load_drag)
        self.canvas.mpl_connect("button_release_event", self.stop_load_drag)
        self._add_trace_lines()
        self.material_var.trace_add("write", self._material_changed)
        for var in (self.support_var, self.section_var, self.limit_var):
            var.trace_add("write", lambda *_args: self.update_view())

    def _combo(self, parent, label, variable, values, display=None):
        tk.Label(parent, text=label, bg="white", fg="#425466").pack(anchor="w", pady=(5, 1))
        box = ttk.Combobox(parent, textvariable=variable, values=[display(v) for v in values] if display else values, state="readonly")
        box.pack(fill="x")
        if display:
            box.bind("<<ComboboxSelected>>", lambda _e: variable.set(box.get().replace("L/", "")))
        return box

    def _material_changed(self, *_):
        values = list(MATERIALS[self.material_var.get()]["sections"])
        self.section_box.configure(values=values)
        self.section_var.set("W12x26" if "W12x26" in values else values[0])
        self.update_view()

    def _tip(self, text):
        self.note.configure(text=text)

    def _add_trace_lines(self):
        self.trace_lines = [ax.axvline(0, color="#7b8794", lw=0.8, ls="--", visible=False) for ax in self.axes[1:]]

    def _selected_load(self):
        selection = self.load_list.curselection()
        return selection[0] if selection else None

    def _refresh_load_list(self):
        self.load_list.delete(0, tk.END)
        for q in self.loads:
            if q["type"] == "point":
                text = f"Point: {q['magnitude']:g} k at {q['position']:g} ft"
            else:
                text = f"Uniform: {q['magnitude']:g} k/ft, {q['start']:g}–{q['end']:g} ft"
            self.load_list.insert(tk.END, text)

    def add_point(self):
        L = float(self.span_var.get())
        self.loads.append({"type": "point", "magnitude": 5.0, "position": L if self.support_var.get() == "Cantilever" else L / 2})
        self._refresh_load_list(); self.update_view()

    def add_uniform(self):
        self.loads.append({"type": "uniform", "magnitude": 0.5, "start": 0.0, "end": float(self.span_var.get())})
        self._refresh_load_list(); self.update_view()

    def edit_load(self):
        i = self._selected_load()
        if i is None:
            return
        old = self.loads[i]
        fields = [("magnitude", "Magnitude"), ("position", "Position (ft)")] if old["type"] == "point" else [("magnitude", "Magnitude (k/ft)"), ("start", "Start (ft)"), ("end", "End (ft)")]
        updated = dict(old)
        for key, label in fields:
            val = simpledialog.askfloat("Edit load", f"{label}:", initialvalue=old[key], minvalue=0 if key == "magnitude" else None, parent=self.root)
            if val is None: return
            updated[key] = val
        self.loads[i] = updated
        self._refresh_load_list(); self.load_list.selection_set(i); self.update_view()

    def remove_load(self):
        i = self._selected_load()
        if i is not None:
            self.loads.pop(i); self._refresh_load_list(); self.update_view()

    def _inputs(self):
        return dict(support=self.support_var.get(), span=float(self.span_var.get()), material=self.material_var.get(),
                    section=self.section_var.get(), limit=int(self.limit_var.get()), loads=[dict(x) for x in self.loads])

    def update_view(self):
        try:
            span = float(self.span_var.get())
            span = float(np.clip(span, 4.0, 40.0))
            if abs(float(self.span_var.get()) - span) > 1e-9:
                self.span_var.set(span)
            inp = self._inputs()
            if not hasattr(self, "axes"):
                return
            result = calculate_beam(**inp)
        except (ValueError, TypeError, tk.TclError, KeyError):
            return
        self.result = result
        self._refresh_load_list()
        self._draw(result, inp)
        bpass = result["bending_pass"]
        dpass = result["deflection_pass"]
        self.bending_text.set(f"BENDING  {'PASS' if bpass else 'FAIL'}\n{result['stress']:.3f} ksi / {result['allow_stress']:.3f} ksi allowable")
        self.deflection_text.set(f"DEFLECTION  {'PASS' if dpass else 'FAIL'}\n{result['max_deflection']:.3f} in / {result['allow_deflection']:.3f} in allowable")
        for label, bar, ratio in ((self.bending_label, self.bending_bar, result['stress'] / result['allow_stress']), (self.deflection_label, self.deflection_bar, result['max_deflection'] / result['allow_deflection'])):
            label.configure(bg=("#e8f5ec" if ratio < .7 else "#fff4dd" if ratio <= 1 else "#fde9e7"))
            bar.delete("all")
            bar.update_idletasks()
            width = max(1, bar.winfo_width())
            bar.create_rectangle(0, 0, width, 8, fill="#e6ebf0", outline="")
            bar.create_rectangle(0, 0, width * min(ratio, 1), 8, fill=("#3b9b68" if ratio < .7 else "#e0a42e" if ratio <= 1 else "#c83e3e"), outline="")
        if result["lightest"]:
            self.suggestion_text.set(f"Lightest passing section: {result['lightest']['section']}")
            self.use_button.state(["!disabled"])
        else:
            self.suggestion_text.set("No section in this material table passes both checks.")
            self.use_button.state(["disabled"])

    def _draw(self, r, inp):
        for ax in self.axes:
            ax.clear()
        L = inp["span"]
        beam = self.axes[0]
        beam.set_xlim(-L * .04, L * 1.04); beam.set_ylim(-1.2, 2.5); beam.axis("off")
        beam.plot([0, L], [0, 0], color="#263746", lw=4, solid_capstyle="round")
        if inp["support"] == "Simply supported":
            beam.scatter([0, L], [-.25, -.25], marker="^", s=140, color="#1769aa", zorder=4)
            beam.text(L/2, 1.95, "Simply supported beam", ha="center", color="#425466")
        else:
            beam.plot([0, 0], [-.55, .55], color="#1769aa", lw=5)
            beam.text(L/2, 1.95, "Cantilever beam", ha="center", color="#425466")
        for q in r["loads"]:
            if q["type"] == "point":
                x, mag = q["position"], q["magnitude"]
                beam.annotate("", xy=(x, .1), xytext=(x, 1.2), arrowprops=dict(arrowstyle="-|>", color="#c2413b", lw=1.7))
                beam.text(x, 1.28, f"{mag:g} k", ha="center", color="#a3332d", fontsize=8)
            else:
                a, b, mag = q["start"], q["end"], q["magnitude"]
                n = max(2, min(24, int((b-a) / max(L/20, .1)) + 1))
                for x in np.linspace(a, b, n):
                    beam.annotate("", xy=(x, .08), xytext=(x, .72), arrowprops=dict(arrowstyle="-|>", color="#c2413b", lw=1))
                beam.plot([a, b], [.75, .75], color="#c2413b", lw=1)
                beam.text((a+b)/2, .82, f"{mag:g} k/ft", ha="center", color="#a3332d", fontsize=8)
        left_label = f"{r['left_reaction']:.2f} k ↑"
        if inp["support"] == "Cantilever":
            left_label += f"\n{r['fixed_moment']:.2f} kip-ft fixed moment"
        beam.text(0, -.72, left_label, ha="center", color=BLUE, fontsize=8)
        if inp["support"] == "Simply supported": beam.text(L, -.72, f"{r['right_reaction']:.2f} k ↑", ha="center", color=BLUE, fontsize=8)
        specs = [(r["V"], "Shear V (kips)", "#2878b5", "kips"), (r["M"], "Moment M (kip-ft)", "#4a9b72", "kip-ft"), (r["deflection"], "Deflection (in)", "#9a69ad", "in")]
        for ax, (yy, title, color, unit) in zip(self.axes[1:], specs):
            ax.axhline(0, color="#778899", lw=.7)
            ax.fill_between(r["x"], yy, 0, color=color, alpha=.18)
            ax.plot(r["x"], yy, color=color, lw=1.8)
            ax.set_xlim(0, L); ax.set_ylabel(title, fontsize=8); ax.grid(True, alpha=.2)
            ax.tick_params(labelsize=7)
            idx = int(np.argmax(np.abs(yy)))
            ax.annotate(f"{yy[idx]:.3g} {unit} at {r['x'][idx]:.2f} ft", (r["x"][idx], yy[idx]), xytext=(4, 5), textcoords="offset points", fontsize=7)
        self.canvas.draw_idle()

    def on_hover(self, event):
        if getattr(self, "dragging_load", None) is not None and event.inaxes is self.axes[0] and event.xdata is not None:
            i = self.dragging_load
            position = round(float(np.clip(event.xdata, 0, self.span_var.get())) * 4) / 4
            self.loads[i]["position"] = position
            self._refresh_load_list()
            self.load_list.selection_set(i)
            self.update_view()
            return
        if event.inaxes not in self.axes[1:] or not hasattr(self, "result") or event.xdata is None:
            for line in self.trace_lines: line.set_visible(False)
            self.canvas.draw_idle(); return
        x = float(np.clip(event.xdata, 0, self.result["x"][-1]))
        for line in self.trace_lines:
            line.set_xdata([x, x]); line.set_visible(True)
        idx = int(np.argmin(np.abs(self.result["x"] - x)))
        self.note.configure(text=f"At {self.result['x'][idx]:.2f} ft: V = {self.result['V'][idx]:.3f} k, M = {self.result['M'][idx]:.3f} kip-ft, deflection = {self.result['deflection'][idx]:.3f} in")
        self.canvas.draw_idle()

    def start_load_drag(self, event):
        self.dragging_load = None
        if event.inaxes is not self.axes[0] or event.xdata is None:
            return
        point_loads = [(i, q) for i, q in enumerate(self.loads) if q["type"] == "point"]
        if point_loads:
            i, q = min(point_loads, key=lambda pair: abs(pair[1]["position"] - event.xdata))
            if abs(q["position"] - event.xdata) <= max(self.span_var.get() * .035, .25):
                self.dragging_load = i

    def stop_load_drag(self, _event):
        self.dragging_load = None

    def use_suggestion(self):
        if getattr(self, "result", {}).get("lightest"):
            self.section_var.set(self.result["lightest"]["section"])

    def save_beam(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Beam design", "*.json")], parent=self.root)
        if not path: return
        with open(path, "w", encoding="utf-8") as f: json.dump(self._inputs(), f, indent=2)

    def open_beam(self):
        path = filedialog.askopenfilename(filetypes=[("Beam design", "*.json")], parent=self.root)
        if not path: return
        try:
            with open(path, encoding="utf-8") as f: data = json.load(f)
            self.support_var.set(data["support"]); self.span_var.set(data["span"])
            self.material_var.set(data["material"]); self.section_var.set(data["section"])
            self.limit_var.set(str(data["limit"])); self.loads = data["loads"]
            self._refresh_load_list(); self.update_view()
        except (OSError, ValueError, KeyError, TypeError) as e:
            messagebox.showerror("Could not open beam", str(e), parent=self.root)

    def export_csv(self):
        if not hasattr(self, "result"): return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], parent=self.root)
        if not path: return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f); writer.writerow(["x (ft)", "V (kips)", "M (kip-ft)", "deflection (in)"])
            writer.writerows(zip(self.result["x"], self.result["V"], self.result["M"], self.result["deflection"]))

    def export_pdf(self):
        if not hasattr(self, "result"): return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], parent=self.root)
        if not path: return
        inp, r = self._inputs(), self.result
        fig = Figure(figsize=(8.27, 11.69), facecolor="white")
        fig.text(.08, .96, "Beam Designer — Calculation Sheet", fontsize=16, weight="bold")
        lines = [f"Support: {inp['support']}    Span: {inp['span']:g} ft    Material: {inp['material']}    Section: {inp['section']}    Deflection limit: L/{inp['limit']}",
                 "Loads: " + ("; ".join(f"{q['magnitude']:g} k at {q['position']:g} ft" if q['type']=='point' else f"{q['magnitude']:g} k/ft from {q['start']:g} to {q['end']:g} ft" for q in inp['loads']) or "None"),
                 f"Reactions: left {r['left_reaction']:.3f} k, right {r['right_reaction']:.3f} k" + (f", fixed moment {r['fixed_moment']:.3f} kip-ft" if inp['support']=='Cantilever' else ""),
                 f"Bending: {r['stress']:.3f} / {r['allow_stress']:.3f} ksi — {'PASS' if r['bending_pass'] else 'FAIL'}     Deflection: {r['max_deflection']:.3f} / {r['allow_deflection']:.3f} in — {'PASS' if r['deflection_pass'] else 'FAIL'}",
                 f"Maximum moment: {r['max_moment']:.3f} kip-ft at {r['max_moment_x']:.3f} ft     Suggested section: {r['lightest']['section'] if r['lightest'] else 'none'}"]
        for j, line in enumerate(lines): fig.text(.08, .92 - j*.027, line, fontsize=8.6)
        positions = [(0.14, .55, .78, .20), (0.14, .36, .78, .13), (0.14, .20, .78, .13), (0.14, .04, .78, .13)]
        arrays = [(None, "Beam and loads"), (r['V'], "Shear V (kips)"), (r['M'], "Moment M (kip-ft)"), (r['deflection'], "Deflection (in)")]
        for pos, (arr, title) in zip(positions, arrays):
            ax = fig.add_axes(pos); ax.set_title(title, fontsize=9); ax.grid(True, alpha=.2)
            if arr is None:
                ax.plot([0, inp['span']], [0, 0], color="#263746", lw=3); ax.set_xlim(0, inp['span']); ax.set_yticks([])
                for q in r['loads']:
                    if q['type'] == 'point': ax.annotate("", xy=(q['position'], 0), xytext=(q['position'], 1), arrowprops=dict(arrowstyle="-|>", color="#c2413b"))
                    else:
                        for x in np.linspace(q['start'], q['end'], 12): ax.annotate("", xy=(x, 0), xytext=(x, .5), arrowprops=dict(arrowstyle="-|>", color="#c2413b"))
            else:
                ax.plot(r['x'], arr, lw=1.5); ax.fill_between(r['x'], arr, 0, alpha=.15); ax.set_xlim(0, inp['span'])
        with PdfPages(path) as pdf: pdf.savefig(fig, bbox_inches="tight")


def main():
    root = tk.Tk()
    BeamDesigner(root)
    root.mainloop()


if __name__ == "__main__":
    main()
