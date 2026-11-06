import colorsys
import re
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageOps, ImageTk


class ThemeColorPicker(ctk.CTkToplevel):
    def __init__(self, parent, label, color, preview, finish):
        super().__init__(parent)
        self.withdraw()
        self.title(f"Edit {label} color")
        self.transient(parent)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", self._cancel)
        self.preview = preview
        self.finish = finish
        self.preview_job = None
        self.updating_hex = False
        self.hex_value = tk.StringVar(master=self, value=color.upper())
        self.hue, self.saturation, self.value = self._to_hsv(color)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=18)
        ctk.CTkLabel(body, text=f"{label} color", font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(body, text="Changes preview live in Pizza Tools.").pack(anchor="w", pady=(2, 12))

        self.field = self._create_canvas(body, 150, self._select_field, self._nudge_field)
        self.field.pack(fill="x")
        self.hue_bar = self._create_canvas(body, 20, self._select_hue, self._nudge_hue)
        self.hue_bar.pack(fill="x", pady=(12, 14))
        self.field.bind("<Configure>", self._draw_field)
        self.hue_bar.bind("<Configure>", self._draw_hue_bar)

        inputs = ctk.CTkFrame(body, fg_color="transparent")
        inputs.pack(fill="x")
        ctk.CTkLabel(inputs, text="Hex").pack(side="left", padx=(0, 10))
        self.entry = ctk.CTkEntry(inputs, textvariable=self.hex_value, width=112, height=32)
        self.entry.pack(side="left")
        self.entry.bind("<Return>", self._save)
        self.swatch = ctk.CTkFrame(inputs, width=32, height=32, corner_radius=7, fg_color=color,
                                  border_width=1, border_color="#758195")
        self.swatch.pack(side="right")

        self.error = ctk.CTkLabel(body, text="", text_color="#FF9999", anchor="w", height=23)
        self.error.pack(fill="x")
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill="x", pady=(4, 0))
        self.save_button = ctk.CTkButton(actions, text="Save color", width=112, command=self._save)
        self.save_button.pack(side="right")
        ctk.CTkButton(actions, text="Cancel", width=88, fg_color="transparent", border_width=1,
                      command=self._cancel).pack(side="right", padx=(0, 8))
        self.hex_value.trace_add("write", self._on_hex_change)

        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        left = parent.winfo_rootx()
        right = left + parent.winfo_width()
        x = right + 12
        if x + width > self.winfo_screenwidth():
            x = left - width - 12
        if x < 0:
            x = max(0, left + (parent.winfo_width() - width) // 2)
        y = max(0, min(parent.winfo_rooty() + 40, self.winfo_screenheight() - height - 48))
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.wait_visibility()
        self.grab_set()
        self.entry.focus_set()

    def _create_canvas(self, parent, height, select, nudge):
        canvas = tk.Canvas(parent, width=round(parent._apply_widget_scaling(280)),
                           height=round(parent._apply_widget_scaling(height)),
                           borderwidth=0, highlightthickness=1, highlightbackground="#566174",
                           highlightcolor="#91B9FF", takefocus=True, cursor="crosshair")
        canvas.bind("<Button-1>", lambda event: (canvas.focus_set(), select(event)))
        canvas.bind("<B1-Motion>", select)
        for key in ("Left", "Right", "Up", "Down"):
            canvas.bind(f"<{key}>", nudge)
        return canvas

    @staticmethod
    def _to_hsv(color):
        return colorsys.rgb_to_hsv(*(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)))

    @staticmethod
    def _clamp(value):
        return min(1.0, max(0.0, value))

    @staticmethod
    def _dimensions(canvas):
        return max(1, canvas.winfo_width() - 2), max(1, canvas.winfo_height() - 2)

    def _draw_field(self, event=None):
        width, height = self._dimensions(self.field)
        saturation = Image.linear_gradient("L").transpose(Image.Transpose.ROTATE_90).resize((width, height))
        brightness = ImageOps.invert(Image.linear_gradient("L")).resize((width, height))
        pure_hue = tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(self.hue, 1, 1))
        colors = ImageOps.colorize(saturation, (255, 255, 255), pure_hue)
        image = Image.composite(colors, Image.new("RGB", (width, height)), brightness)
        self._field_image = ImageTk.PhotoImage(image, master=self.field)
        self.field.delete("all")
        self.field.create_image(1, 1, image=self._field_image, anchor="nw")
        self._draw_markers()

    def _draw_hue_bar(self, event=None):
        width, height = self._dimensions(self.hue_bar)
        strip = Image.frombytes("HSV", (256, 1), bytes(channel for hue in range(256) for channel in (hue, 255, 255)))
        self._hue_image = ImageTk.PhotoImage(strip.convert("RGB").resize((width, height)), master=self.hue_bar)
        self.hue_bar.delete("all")
        self.hue_bar.create_image(1, 1, image=self._hue_image, anchor="nw")
        self._draw_markers()

    def _draw_markers(self):
        self.field.delete("marker")
        self.hue_bar.delete("marker")
        width, height = self._dimensions(self.field)
        x = 1 + self.saturation * (width - 1)
        y = 1 + (1 - self.value) * (height - 1)
        for radius, color in ((6, "#151515"), (5, "#FFFFFF")):
            self.field.create_oval(x - radius, y - radius, x + radius, y + radius,
                                   outline=color, width=2, tags="marker")
        width, height = self._dimensions(self.hue_bar)
        x = 1 + self.hue * (width - 1)
        self.hue_bar.create_rectangle(x - 3, 1, x + 3, height, outline="#151515", width=2, tags="marker")
        self.hue_bar.create_rectangle(x - 2, 2, x + 2, height - 1, outline="#FFFFFF", tags="marker")

    def _select_field(self, event):
        width, height = self._dimensions(self.field)
        self.saturation = self._clamp((event.x - 1) / max(1, width - 1))
        self.value = 1 - self._clamp((event.y - 1) / max(1, height - 1))
        self._on_palette_change()

    def _select_hue(self, event):
        width, _ = self._dimensions(self.hue_bar)
        self.hue = self._clamp((event.x - 1) / max(1, width - 1))
        self._on_palette_change(hue_changed=True)

    def _nudge_field(self, event):
        step = 0.02
        if event.keysym in ("Left", "Right"):
            self.saturation = self._clamp(self.saturation + (step if event.keysym == "Right" else -step))
        else:
            self.value = self._clamp(self.value + (step if event.keysym == "Up" else -step))
        self._on_palette_change()
        return "break"

    def _nudge_hue(self, event):
        self.hue = (self.hue + (1 if event.keysym in ("Right", "Up") else -1) / 180) % 1
        self._on_palette_change(hue_changed=True)
        return "break"

    def _on_palette_change(self, hue_changed=False):
        rgb = colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)
        color = "#" + "".join(f"{round(channel * 255):02X}" for channel in rgb)
        self.updating_hex = True
        self.hex_value.set(color)
        self.updating_hex = False
        self._update_color(color, hue_changed)

    def _on_hex_change(self, *_):
        if self.updating_hex:
            return
        value = self.hex_value.get().strip()
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
            if self.preview_job is not None:
                self.after_cancel(self.preview_job)
                self.preview_job = None
            self.error.configure(text="Enter six hex digits, for example #2563EB.")
            self.save_button.configure(state="disabled")
            return
        color = "#" + value.lstrip("#").upper()
        hue, self.saturation, self.value = self._to_hsv(color)
        hue_changed = self.saturation > 0 and hue != self.hue
        if hue_changed:
            self.hue = hue
        self._update_color(color, hue_changed)

    def _update_color(self, color, hue_changed):
        self.color = color
        self.error.configure(text="")
        self.save_button.configure(state="normal")
        self.swatch.configure(fg_color=color)
        if hue_changed:
            self._draw_field()
        else:
            self._draw_markers()
        if self.preview_job is None:
            self.preview_job = self.after(32, self._preview)

    def _preview(self):
        self.preview_job = None
        self.preview(self.color)

    def _save(self, event=None):
        value = self.hex_value.get().strip()
        if re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
            self._close("#" + value.lstrip("#").upper())

    def _cancel(self, event=None):
        self._close(None)

    def _close(self, color):
        if self.preview_job is not None:
            self.after_cancel(self.preview_job)
        self.destroy()
        self.finish(color)
