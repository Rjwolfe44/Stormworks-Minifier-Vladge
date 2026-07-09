"""
VladgeMinifier - Sprite to Lua Converter
Converts images into Stormworks screen API drawing code.
"""

from __future__ import annotations
import os
from pathlib import Path
from tkinter import filedialog
from PIL import Image

import customtkinter as ctk
from src.gui import theme as T

class SpriteConverterWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("🎨 Sprite to Lua Converter")
        self.geometry("900x600")
        self.minsize(850, 400)
        self.configure(fg_color=T.BG_DARK)
        self.transient(parent)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self._image_path = None
        self._lua_code = ""
        
        self._build_ui()
        
    def _build_ui(self):
        # Top Bar (Rows 0 and 1)
        top_bar = ctk.CTkFrame(self, fg_color=T.BG_MID, corner_radius=0)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)  # Spacer column
        
        # --- Row 0 Controls ---
        ctk.CTkButton(
            top_bar,
            text="📁 Select Image",
            command=self._select_image,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_DIM,
            text_color=T.BG_DARK,
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, padx=20, pady=(12, 6))
        
        # Empty spacer column to push controls to the right
        ctk.CTkFrame(top_bar, fg_color="transparent", height=1).grid(row=0, column=1)
        
        self._colors_mode = ctk.CTkComboBox(
            top_bar,
            values=["Colors: Unlimited", "Colors: 64", "Colors: 32", "Colors: 16"],
            state="readonly",
            width=130,
            command=lambda _: self.after(10, self._reconvert_if_loaded)
        )
        self._colors_mode.set("Colors: 32")
        self._colors_mode.grid(row=0, column=2, padx=10, pady=(12, 6))
        
        self._dither_mode = ctk.CTkComboBox(
            top_bar,
            values=["Dither: None", "Dither: Yes"],
            state="readonly",
            width=110,
            command=lambda _: self.after(10, self._reconvert_if_loaded)
        )
        self._dither_mode.set("Dither: None")
        self._dither_mode.grid(row=0, column=3, padx=10, pady=(12, 6))
        
        self._smooth_mode = ctk.CTkComboBox(
            top_bar,
            values=["Denoise: None", "Denoise: Light", "Denoise: Heavy"],
            state="readonly",
            width=130,
            command=lambda _: self.after(10, self._reconvert_if_loaded)
        )
        self._smooth_mode.set("Denoise: None")
        self._smooth_mode.grid(row=0, column=4, padx=(10, 20), pady=(12, 6))
        
        # --- Row 1 Controls ---
        self._monitor_mode = ctk.CTkComboBox(
            top_bar,
            values=["Monitor: 1x1 (32px)", "Monitor: 2x2 (64px)", "Monitor: 3x3 (96px)", "Monitor: 5x5 (160px)", "Monitor: 9x9 (288px)"],
            state="readonly",
            width=150,
            command=lambda _: self.after(10, self._reconvert_if_loaded)
        )
        self._monitor_mode.set("Monitor: 9x9 (288px)")
        self._monitor_mode.grid(row=1, column=1, padx=(10, 0), pady=(6, 12))
        
        self._upscale_mode = ctk.CTkComboBox(
            top_bar,
            values=["Aspect Ratio", "Stretch", "None (1:1)"],
            state="readonly",
            width=120,
            command=lambda _: self.after(10, self._reconvert_if_loaded)
        )
        self._upscale_mode.set("Aspect Ratio")
        self._upscale_mode.grid(row=1, column=2, padx=10, pady=(6, 12))
        
        self._scripts_mode = ctk.CTkComboBox(
            top_bar,
            values=["Scripts: 1", "Scripts: 2", "Scripts: 3", "Scripts: Auto"],
            width=110,
            command=lambda _: self.after(10, self._reconvert_if_loaded)
        )
        self._scripts_mode.bind("<Return>", lambda _: self.after(10, self._reconvert_if_loaded))
        self._scripts_mode.bind("<FocusOut>", lambda _: self.after(10, self._reconvert_if_loaded))
        self._scripts_mode.set("Scripts: 1")
        self._scripts_mode.grid(row=1, column=3, padx=10, pady=(6, 12))
        
        # Group the checkboxes into a single frame for the last column
        checkbox_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        checkbox_frame.grid(row=1, column=4, padx=(10, 20), pady=(6, 12), sticky="e")
        
        self._props_mode_var = ctk.BooleanVar(value=False)
        self._props_mode_chk = ctk.CTkCheckBox(
            checkbox_frame,
            text="📌 Props",
            variable=self._props_mode_var,
            command=self._on_props_toggle,
            font=T.FONT_BODY,
            width=70
        )
        self._props_mode_chk.pack(side="left")
        
        # Set Window Icon using parent
        try:
            self.after(200, lambda: self.iconbitmap(self.master.iconbitmap()))
        except Exception:
            pass
        
        # Bottom Bar (Actions)
        action_bar = ctk.CTkFrame(self, fg_color=T.BG_MID, corner_radius=0, height=50)
        action_bar.grid(row=2, column=0, sticky="ew")
        
        self._lua_scripts = []
        self._script_labels = []
        self._script_idx = 0
        
        ctk.CTkButton(
            action_bar,
            text="📋 Copy Code",
            command=self._copy_code,
            fg_color=T.BG_PANEL,
            hover_color=T.BG_HOVER,
            border_width=1,
            border_color=T.BORDER,
            text_color=T.TEXT_PRIMARY
        ).pack(side="right", padx=20, pady=10)
        
        # Pagination
        self._page_frame = ctk.CTkFrame(action_bar, fg_color="transparent")
        self._page_frame.pack(side="right", padx=(0, 10), pady=10)
        
        self._prev_btn = ctk.CTkButton(
            self._page_frame, text="<", width=30, command=self._prev_script, state="disabled"
        )
        self._prev_btn.pack(side="left", padx=5)
        
        self._page_lbl = ctk.CTkLabel(self._page_frame, text="Script 1 of 1", font=T.FONT_BODY)
        self._page_lbl.pack(side="left", padx=5)
        
        self._next_btn = ctk.CTkButton(
            self._page_frame, text=">", width=30, command=self._next_script, state="disabled"
        )
        self._next_btn.pack(side="left", padx=5)
        
        self._status_lbl = ctk.CTkLabel(
            action_bar,
            text="No image selected",
            font=T.FONT_BODY,
            text_color=T.TEXT_SECONDARY
        )
        self._status_lbl.pack(side="left", padx=20, pady=10)
        
        # Main Area
        main_area = ctk.CTkFrame(self, fg_color="transparent")
        main_area.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        main_area.grid_columnconfigure(0, weight=1)
        main_area.grid_rowconfigure(0, weight=1)
        
        self._code_box = ctk.CTkTextbox(
            main_area,
            fg_color=T.BG_PANEL,
            text_color=T.TEXT_PRIMARY,
            font=T.FONT_MONO,
            border_width=1,
            border_color=T.BORDER,
            wrap="none"
        )
        self._code_box.grid(row=0, column=0, sticky="nsew")
        
    def _reconvert_if_loaded(self):
        if self._image_path:
            self._status_lbl.configure(text=f"Re-processing: {os.path.basename(self._image_path)}...", text_color=T.TEXT_PRIMARY)
            
            import threading
            threading.Thread(target=self._run_conversion_thread, daemon=True).start()

    def _run_conversion_thread(self):
        try:
            self._convert_to_lua()
        except Exception as e:
            self.after(0, lambda e=e: self._status_lbl.configure(text=f"❌ Error: {e}", text_color=T.RED))
            
    def _apply_results(self, scripts, labels, status_text, status_color):
        self._lua_scripts = scripts
        self._script_labels = labels
        self._script_idx = 0
        self._update_script_view()
        self._status_lbl.configure(text=status_text, text_color=status_color)

    def _on_props_toggle(self):
        if self._props_mode_var.get():
            self._scripts_mode.configure(values=["Props: 2", "Props: 5", "Props: 10", "Props: 20", "Props: Auto"])
            self._scripts_mode.set("Props: Auto")
        else:
            self._scripts_mode.configure(values=["Scripts: 1", "Scripts: 2", "Scripts: 3", "Scripts: Auto"])
            self._scripts_mode.set("Scripts: 1")
        self._reconvert_if_loaded()

    def _select_image(self):
        path = filedialog.askopenfilename(
            title="Open Sprite Image",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp"), ("All files", "*.*")]
        )
        if not path:
            return
            
        self._image_path = path
        self._status_lbl.configure(text=f"Processing: {os.path.basename(path)}...", text_color=T.TEXT_PRIMARY)
        
        import threading
        threading.Thread(target=self._run_conversion_thread, daemon=True).start()
            
    def _get_segments_by_color(self, img: Image.Image) -> tuple[tuple[int,int], dict]:
        """Shared helper: scan image into run-length segments grouped by color."""
        w, h = img.size
        pixels = img.load()
        segments_by_color = {}
        for y in range(h):
            x = 0
            while x < w:
                r, g, b, a = pixels[x, y]
                if a < 128:
                    x += 1
                    continue
                color = (r, g, b)
                start_x = x
                while x < w:
                    nr, ng, nb, na = pixels[x, y]
                    if na >= 128 and (nr, ng, nb) == color:
                        x += 1
                    else:
                        break
                width = x - start_x
                if color not in segments_by_color:
                    segments_by_color[color] = []
                segments_by_color[color].append((start_x, y, width, 1))
        return (w, h), segments_by_color

    def _generate_lua_chunks(self, img: Image.Image) -> tuple[list[str], list[str]]:
        """Performance mode: decode hex once at load time in global scope.
        Every script is self-contained with its own _d table and onDraw.
        Multiple scripts draw their own rectangle slices onto the same screen."""
        (w, h), segments_by_color = self._get_segments_by_color(img)
        
        mode = self._upscale_mode.get()
        
        # Build the onDraw body based on scale mode
        if mode == "Aspect Ratio":
            ondraw_lines = [
                "function onDraw()",
                "    local W,H=_s.getWidth(),_s.getHeight()",
                f"    local S=math.min(W/{w},H/{h})",
                f"    local ox=((W-{w}*S)/2)//1",
                f"    local oy=((H-{h}*S)/2)//1",
                "    for _,v in ipairs(_d) do",
                "        _s.setColor(v[1],v[2],v[3])",
                "        _s.drawRectF(ox+v[4]*S,oy+v[5]*S,v[6]*S,v[7]*S)",
                "    end",
                "end"
            ]
        elif mode == "Stretch":
            ondraw_lines = [
                "function onDraw()",
                "    local W,H=_s.getWidth(),_s.getHeight()",
                f"    local SX,SY=W/{w},H/{h}",
                "    for _,v in ipairs(_d) do",
                "        _s.setColor(v[1],v[2],v[3])",
                "        _s.drawRectF(v[4]*SX,v[5]*SY,v[6]*SX,v[7]*SY)",
                "    end",
                "end"
            ]
        else:  # None (1:1)
            ondraw_lines = [
                "function onDraw()",
                "    local W,H=_s.getWidth(),_s.getHeight()",
                f"    local ox=((W-{w})/2)//1",
                f"    local oy=((H-{h})/2)//1",
                "    for _,v in ipairs(_d) do",
                "        _s.setColor(v[1],v[2],v[3])",
                "        _s.drawRectF(ox+v[4],oy+v[5],v[6],v[7])",
                "    end",
                "end"
            ]
        
        # Each script is fully self-contained:
        # global scope: _d table + _s ref + _p decode helper + _p() calls + onDraw
        boilerplate = [
            "local _d={}",
            "local _s=screen",
            "local function _p(r,g,b,h)",
            "    for i=1,#h,8 do",
            "        _d[#_d+1]={r,g,b,tonumber(h:sub(i,i+1),16),tonumber(h:sub(i+2,i+3),16),tonumber(h:sub(i+4,i+5),16),tonumber(h:sub(i+6,i+7),16)}",
            "    end",
            "end",
        ] + ondraw_lines  # onDraw is part of every script
        
        calls = []
        for color, segments in segments_by_color.items():
            r, g, b = color
            CHUNK_SIZE = 300
            for i in range(0, len(segments), CHUNK_SIZE):
                chunk = segments[i:i+CHUNK_SIZE]
                hex_parts = []
                for sx, sy, sw, sh in chunk:
                    hex_parts.append(f"{min(255,max(0,sx)):02X}{min(255,max(0,sy)):02X}{min(255,max(0,sw)):02X}{min(255,max(0,sh)):02X}")
                packed_hex = "".join(hex_parts)
                calls.append(f'_p({r},{g},{b},"{packed_hex}")')
        
        # Clear any stale sentinel
        self._perf_draw_body = []
        return boilerplate, calls

    def _generate_property_output(self, img: Image.Image) -> tuple[str, list[tuple[str, str]]]:
        """Property mode: data lives in Stormworks property text fields.
        Returns (lua_script, [(prop_name, hex_value), ...]).
        The Lua script is tiny; each property holds up to 4096 chars of hex data.
        Every script+property set is self-contained."""
        from src.core.minifier import minify
        
        (w, h), segments_by_color = self._get_segments_by_color(img)
        mode = self._upscale_mode.get()
        
        # Build onDraw based on scale mode
        if mode == "Aspect Ratio":
            ondraw = [
                "function onDraw()",
                "    local W,H=_s.getWidth(),_s.getHeight()",
                f"    local S=math.min(W/{w},H/{h})",
                f"    local ox=((W-{w}*S)/2)//1",
                f"    local oy=((H-{h}*S)/2)//1",
                "    for _,v in ipairs(_d) do",
                "        _s.setColor(v[1],v[2],v[3])",
                "        _s.drawRectF(ox+v[4]*S,oy+v[5]*S,v[6]*S,v[7]*S)",
                "    end",
                "end"
            ]
        elif mode == "Stretch":
            ondraw = [
                "function onDraw()",
                "    local W,H=_s.getWidth(),_s.getHeight()",
                f"    local SX,SY=W/{w},H/{h}",
                "    for _,v in ipairs(_d) do",
                "        _s.setColor(v[1],v[2],v[3])",
                "        _s.drawRectF(v[4]*SX,v[5]*SY,v[6]*SX,v[7]*SY)",
                "    end",
                "end"
            ]
        else:
            ondraw = [
                "function onDraw()",
                "    local W,H=_s.getWidth(),_s.getHeight()",
                f"    local ox=((W-{w})/2)//1",
                f"    local oy=((H-{h})/2)//1",
                "    for _,v in ipairs(_d) do",
                "        _s.setColor(v[1],v[2],v[3])",
                "        _s.drawRectF(ox+v[4],oy+v[5],v[6],v[7])",
                "    end",
                "end"
            ]
        
        # Pack all segments into 14-char-aligned property chunks (max 4096 chars each)
        # RRGGBBXXYYWWHH = 14 hex chars per rectangle — all colours in one flat stream
        CHARS_PER_RECT = 14
        CHUNK_SIZE = (4096 // CHARS_PER_RECT) * CHARS_PER_RECT  # 4088 — perfectly aligned
        
        all_segments = []
        for color, segments in segments_by_color.items():
            r, g, b = color
            for sx, sy, sw, sh in segments:
                all_segments.append(
                    f"{min(255,max(0,r)):02X}{min(255,max(0,g)):02X}{min(255,max(0,b)):02X}"
                    f"{min(255,max(0,sx)):02X}{min(255,max(0,sy)):02X}"
                    f"{min(255,max(0,sw)):02X}{min(255,max(0,sh)):02X}"
                )
        
        full_hex = "".join(all_segments)
        properties = []
        for i in range(0, len(full_hex), CHUNK_SIZE):
            chunk = full_hex[i:i + CHUNK_SIZE]  # guaranteed 14-aligned, no data lost
            if chunk:
                properties.append((f"p{len(properties)+1}", chunk))
        
        # Lua decoder — reads 14 chars at a time: r,g,b,x,y,w,h
        # Guard against nil (unfilled properties return nil in Stormworks)
        lua_lines = [
            "local _d={}",
            "local _s=screen",
            "local function _p(s)",
            "    if not s then return end",
            "    for i=1,#s,14 do",
            "        _d[#_d+1]={tonumber(s:sub(i,i+1),16),tonumber(s:sub(i+2,i+3),16),tonumber(s:sub(i+4,i+5),16),tonumber(s:sub(i+6,i+7),16),tonumber(s:sub(i+8,i+9),16),tonumber(s:sub(i+10,i+11),16),tonumber(s:sub(i+12,i+13),16)}",
            "    end",
            "end",
        ]
        for name, _ in properties:
            lua_lines.append(f'_p(property.getText("{name}"))')
        lua_lines.extend(ondraw)
        
        raw_lua = "\n".join(lua_lines)
        minified_lua, _ = minify(raw_lua, level=4, obfuscate=False)
        
        return minified_lua, properties

    def _apply_quantization(self, image: Image.Image) -> Image.Image:
        from PIL import ImageFilter
        
        mode = self._colors_mode.get()
        smooth = self._smooth_mode.get()
        dither_setting = self._dither_mode.get()
        
        # Apply Denoise BEFORE quantization to cluster pixels heavily!
        if "Light" in smooth:
            image = image.filter(ImageFilter.MedianFilter(size=3))
        elif "Heavy" in smooth:
            image = image.filter(ImageFilter.MedianFilter(size=5))
            
        if "Unlimited" in mode:
            return image
        
        max_c = 64
        if "32" in mode: max_c = 32
        elif "16" in mode: max_c = 16
        
        dither_mode = Image.FLOYDSTEINBERG if "Yes" in dither_setting else Image.NONE
        
        alpha = image.getchannel('A') if 'A' in image.getbands() else None
        q_img = image.convert('RGB').quantize(colors=max_c, dither=dither_mode)
        q_img = q_img.convert('RGBA')
        if alpha:
            q_img.putalpha(alpha)
        return q_img

    def _pack_calls_into_scripts(self, boilerplate: list[str], calls: list[str], max_scripts: int = 0) -> list[str]:
        from src.core.minifier import minify
        
        scripts = []
        current_calls = []
        
        # The boilerplate already includes onDraw — no trailing "end" needed
        base_code = "\n".join(boilerplate)
        minified_base, _ = minify(base_code, level=4, obfuscate=False)
        base_size = len(minified_base)
        current_est_size = base_size
        
        def flush_current():
            if not current_calls:
                return
            script_src = "\n".join(boilerplate) + "\n" + "\n".join(current_calls)
            minified, _ = minify(script_src, level=4, obfuscate=False)
            scripts.append(minified)
        
        for call in calls:
            call_bare = len(call.replace(" ", ""))
            
            # Use a tight threshold to trigger real minify checks
            if current_est_size + call_bare > 7500:
                test_calls = current_calls + [call]
                test_src = "\n".join(boilerplate) + "\n" + "\n".join(test_calls)
                minified_test, _ = minify(test_src, level=4, obfuscate=False)
                
                if len(minified_test) > 8192:
                    flush_current()
                    if max_scripts > 0 and len(scripts) >= max_scripts:
                        return scripts
                    current_calls = [call]
                    current_est_size = base_size + call_bare
                else:
                    current_calls.append(call)
                    current_est_size = len(minified_test)
                continue
                    
            current_calls.append(call)
            current_est_size += call_bare
            
        flush_current()
        return scripts

    def _convert_to_lua(self):
        import re
        img = Image.open(self._image_path).convert("RGBA")
        
        limit_mode_str = self._scripts_mode.get()
        if "Auto" in limit_mode_str:
            max_limit = 0
        else:
            match = re.search(r'\d+', limit_mode_str)
            if match:
                max_limit = int(match.group())
            else:
                max_limit = 0
                
        monitor_str = self._monitor_mode.get()
        target_res = 288
        match = re.search(r'\((\d+)px\)', monitor_str)
        if match:
            target_res = int(match.group(1))
            
        w, h = img.size
        new_w, new_h = w, h
        max_scale = 1.0
        if new_w > target_res or new_h > target_res:
            max_scale = min(target_res / new_w, target_res / new_h)
            new_w, new_h = int(new_w * max_scale), int(new_h * max_scale)
            
        proc_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS) if (new_w, new_h) != (w, h) else img.copy()
        proc_img = self._apply_quantization(proc_img)
        
        # --- Property Mode ---
        if self._props_mode_var.get():
            self.after(0, lambda: self._status_lbl.configure(text="Processing: Generating property data...", text_color=T.TEXT_PRIMARY))
            lua_script, prop_pairs = self._generate_property_output(proc_img)
            
            if max_limit == 0 or len(prop_pairs) <= max_limit:
                pages = [lua_script] + [hex_val for _, hex_val in prop_pairs]
                labels = ["Lua Script"] + [f"Property: {name}" for name, _ in prop_pairs]
                
                self.after(0, lambda: self._apply_results(
                    pages, labels, 
                    f"✅ {len(prop_pairs)} properties — paste each into Stormworks property panel", 
                    T.GREEN
                ))
                return
            
            # Binary search to fit into max properties
            best_script = None
            best_pairs = None
            min_script = lua_script
            min_pairs = prop_pairs
            low = 0.01
            high = max_scale
            
            self.after(0, lambda: self._status_lbl.configure(text=f"Processing: Binary Search to fit in {max_limit} properties...", text_color=T.AMBER))
            
            for attempt in range(8):
                mid = (low + high) / 2.0
                new_w, new_h = max(1, int(w * mid)), max(1, int(h * mid))
                current_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                current_img = self._apply_quantization(current_img)
                
                t_script, t_pairs = self._generate_property_output(current_img)
                # Track the smallest result we've seen regardless
                if min_pairs is None or len(t_pairs) < len(min_pairs):
                    min_script = t_script
                    min_pairs = t_pairs
                if len(t_pairs) <= max_limit:
                    best_script = t_script
                    best_pairs = t_pairs
                    low = mid
                else:
                    high = mid
            
            # If nothing fit, use the smallest result we found
            if best_pairs is None:
                best_script = min_script
                best_pairs = min_pairs
                status_text = f"⚠️ Couldn't fit in {max_limit} — best: {len(best_pairs)} properties"
                status_color = T.AMBER
            else:
                status_text = f"✅ Fit in {len(best_pairs)} properties"
                status_color = T.GREEN
            
            pages = [best_script] + [hex_val for _, hex_val in best_pairs]
            labels = ["Lua Script"] + [f"Property: {name}" for name, _ in best_pairs]
            
            self.after(0, lambda: self._apply_results(pages, labels, status_text, status_color))
            return
        
        # --- Normal / Perf Mode ---
        boilerplate, calls = self._generate_lua_chunks(proc_img)
        scripts = self._pack_calls_into_scripts(boilerplate, calls, max_scripts=0)
        
        if max_limit == 0 or len(scripts) <= max_limit:
            labels = [f"Script {i+1}" for i in range(len(scripts))]
            self.after(0, lambda: self._apply_results(
                scripts, labels,
                f"✅ Converted! Split into {len(scripts)} scripts",
                T.GREEN
            ))
            return
            
        best_scripts = None
        low = 0.01
        high = max_scale
        
        self.after(0, lambda: self._status_lbl.configure(text=f"Processing: Binary Search to fit in {max_limit} scripts...", text_color=T.AMBER))
        
        for attempt in range(8):
            mid = (low + high) / 2.0
            
            new_w, new_h = max(1, int(w * mid)), max(1, int(h * mid))
            current_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            current_img = self._apply_quantization(current_img)
            
            boilerplate, calls = self._generate_lua_chunks(current_img)
            scripts = self._pack_calls_into_scripts(boilerplate, calls, max_scripts=max_limit + 1)
            
            if len(scripts) <= max_limit:
                best_scripts = scripts
                low = mid
            else:
                high = mid
                
        if best_scripts is None:
            best_scripts = scripts
            
        labels = [f"Script {i+1}" for i in range(len(best_scripts))]
        self.after(0, lambda: self._apply_results(
            best_scripts, labels,
            f"✅ Converted! Fit in {len(best_scripts)} scripts",
            T.GREEN
        ))

    def _prev_script(self):
        if self._script_idx > 0:
            self._script_idx -= 1
            self._update_script_view()
            
    def _next_script(self):
        if self._script_idx < len(self._lua_scripts) - 1:
            self._script_idx += 1
            self._update_script_view()
            
    def _update_script_view(self):
        if not self._lua_scripts:
            self._code_box.delete("1.0", "end")
            self._page_lbl.configure(text="Page 1 of 1")
            self._prev_btn.configure(state="disabled")
            self._next_btn.configure(state="disabled")
            return
            
        self._code_box.delete("1.0", "end")
        self._code_box.insert("end", self._lua_scripts[self._script_idx])
        
        total = len(self._lua_scripts)
        label = self._script_labels[self._script_idx] if self._script_labels else f"Page {self._script_idx + 1}"
        self._page_lbl.configure(text=f"{label}  ({self._script_idx + 1}/{total})")
        self._prev_btn.configure(state="normal" if self._script_idx > 0 else "disabled")
        self._next_btn.configure(state="normal" if self._script_idx < total - 1 else "disabled")

    def _copy_code(self):
        if not self._lua_scripts or self._script_idx >= len(self._lua_scripts):
            return
        code = self._lua_scripts[self._script_idx]
        label = self._script_labels[self._script_idx] if self._script_labels else f"Page {self._script_idx + 1}"
        try:
            import pyperclip
            pyperclip.copy(code)
        except ImportError:
            self.clipboard_clear()
            self.clipboard_append(code)
        self._status_lbl.configure(text=f"✅ Copied '{label}' to clipboard!", text_color=T.GREEN)
