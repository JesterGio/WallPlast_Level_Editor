import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import math

MAP_FILE = "map.wpm"
CANVAS_SIZE = (400, 300)
DEFAULT_SCALE = 20

def load_blocks(filename=MAP_FILE):
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({"blocks": []}, f, ensure_ascii=False)
        return []
    with open(filename, encoding="utf-8") as f:
        data = json.load(f)
        return data.get("blocks", [])

def save_blocks(blocks, filename=MAP_FILE):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({"blocks": blocks}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        messagebox.showerror("Ошибка сохранения", f"Ошибка: {e}")
        return False

def _get(obj, *keys, default=0.0):
    t = obj
    for k in keys:
        t = t.get(k, None)
        if t is None:
            return default
    return t

def project_block_2d(block, view):
    x = _get(block, 'position', 'x')
    y = _get(block, 'position', 'y')
    z = _get(block, 'position', 'z')
    sx = _get(block, 'size', 'x', default=1.0)
    sy = _get(block, 'size', 'y', default=1.0)
    sz = _get(block, 'size', 'z', default=1.0)
    rot = block.get('rotation', {})
    if view == 'top':
        cx, cy = x, z
        sw, sh = sx, sz
        ang = rot.get("y", 0.0)
    elif view == 'front':
        cx, cy = x, y
        sw, sh = sx, sy
        ang = rot.get("z", 0.0)
    elif view == 'right':
        cx, cy = z, y
        sw, sh = sz, sy
        ang = rot.get("x", 0.0)
    else:
        cx, cy, sw, sh, ang = 0, 0, 1, 1, 0
    return (cx, cy, sw, sh, ang)

def to_canvas_coords(cx, cy, sw, sh, cam, canvas_w, canvas_h):
    px = canvas_w // 2 + int((cx - cam['center_x']) * cam['scale'])
    py = canvas_h // 2 - int((cy - cam['center_y']) * cam['scale'])
    sx = int(sw * cam['scale'] / 2)
    sy = int(sh * cam['scale'] / 2)
    return (px - sx, py - sy, px + sx, py + sy)

def draw_axis_handle(canvas, pos, direction, color, scale=1.0, tag="gizmo"):
    x0, y0 = pos
    dx, dy = direction
    x1, y1 = x0 + dx*40*scale, y0 + dy*40*scale
    arr = canvas.create_line(x0, y0, x1, y1, width=5, arrow=tk.LAST, fill=color, tags=tag)
    return arr, (x0, y0, x1, y1)

def draw_arc_handle(canvas, pos, color, active, tag="gizmo_arc", angle=0.0):
    x, y = pos
    r = 50
    start = 30
    extent = 300
    arc = canvas.create_arc(x - r, y - r, x + r, y + r, style=tk.ARC, outline=color,
                            width=6 if active else 4, start=start, extent=extent, tags=tag)
    ang = math.radians(angle)
    dx = math.cos(ang) * r
    dy = -math.sin(ang) * r
    canvas.create_oval(x + dx - 6, y + dy - 6, x + dx + 6, y + dy + 6, fill='black', tags=tag)
    return arc

class MapEditorGUI(tk.Tk):
    def __init__(self, blocks):
        super().__init__()
        self.title("Редактор карты – три проекции + режимы гизмоса")
        self.geometry("1100x420")
        self.minsize(1100, 420)
        self.blocks = blocks
        self.selected = None
        self.last_clicked_index = {view: 0 for view in ["top", "front", "right"]}
        self.views = {}
        self.cameras = {
            "top":   {'scale': DEFAULT_SCALE, 'center_x': 0.0, 'center_y': 0.0},
            "front": {'scale': DEFAULT_SCALE, 'center_x': 0.0, 'center_y': 0.0},
            "right": {'scale': DEFAULT_SCALE, 'center_x': 0.0, 'center_y': 0.0},
        }
        self._panning = {view: False for view in self.cameras}
        self._drag_start = {view: (0, 0) for view in self.cameras}
        self._cam_start = {view: (0.0, 0.0) for view in self.cameras}
        self._gizmo_action = None
        self._gizmo_axis = None
        self.gizmo_mode = tk.StringVar(value="move")
        self.create_menu()
        self.create_widgets()
        self.draw_all()
        self.bind_all('<KeyPress>', self.on_key_press)

    def create_menu(self):
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Сохранить карту", command=self.save_map)
        menu_bar.add_cascade(label="Файл", menu=file_menu)
        self.config(menu=menu_bar)

    def save_map(self):
        if save_blocks(self.blocks, MAP_FILE):
            messagebox.showinfo("Сохранено", "Карта успешно сохранена.")

    def create_widgets(self):
        frame = ttk.Frame(self)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=10, pady=10)
        grid_labels = [("Вид сверху (XZ)", "top"), ("Вид спереди (XY)", "front"), ("Вид справа (ZY)", "right")]
        for col, (label, name) in enumerate(grid_labels):
            inner = ttk.LabelFrame(frame, text=label)
            inner.grid(row=0, column=col, sticky="nsew", padx=5, pady=5)
            canvas = tk.Canvas(inner, bg="white", width=CANVAS_SIZE[0], height=CANVAS_SIZE[1])
            canvas.pack(fill=tk.BOTH, expand=True)
            self.views[name] = canvas
            canvas.bind("<MouseWheel>", lambda e, v=name: self.on_mouse_wheel(e, v))
            canvas.bind("<Button-4>", lambda e, v=name: self.on_mouse_wheel(e, v, delta=120))
            canvas.bind("<Button-5>", lambda e, v=name: self.on_mouse_wheel(e, v, delta=-120))
            canvas.bind("<ButtonPress-3>", lambda e, v=name: self.on_pan_start(e, v))
            canvas.bind("<B3-Motion>", lambda e, v=name: self.on_pan_move(e, v))
            canvas.bind("<ButtonRelease-3>", lambda e, v=name: self.on_pan_end(e, v))
            canvas.bind("<Motion>", lambda e, v=name: self.on_canvas_motion(e, v))
            canvas.bind("<ButtonPress-1>", lambda e, v=name: self.on_canvas_lmb_down(e, v))
            canvas.bind("<B1-Motion>", lambda e, v=name: self.on_canvas_lmb_drag(e, v))
            canvas.bind("<ButtonRelease-1>", lambda e, v=name: self.on_canvas_lmb_up(e, v))
        right_panel = ttk.Frame(self)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, expand=False, padx=(6, 18), pady=15)
        ttk.Label(right_panel, text="Режим инструмента", font=("Arial", 11, "bold")).pack(anchor="w", pady=(2, 10))
        for txt, mode in [("Двигать", "move"), ("Вращать", "rotate"), ("Масштабировать", "scale")]:
            ttk.Radiobutton(right_panel, text=txt, variable=self.gizmo_mode, value=mode, command=self.draw_all).pack(anchor="w", pady=6)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)

    def draw_all(self):
        blocks_sorted = [
            (i, b) for i, b in enumerate(self.blocks)
        ]
        blocks_top_sorted = sorted(
            blocks_sorted,
            key=lambda ib: (
                -abs(_get(ib[1], 'size', 'x', default=1.0)) * abs(_get(ib[1], 'size', 'z', default=1.0))
            )
        )
        self.draw_grid(self.views["top"], "top")
        for idx, block in blocks_top_sorted:
            self.draw_block_on_view(idx, block, self.views["top"], "top")
        for view in ("front", "right"):
            self.draw_grid(self.views[view], view)
            for idx, block in enumerate(self.blocks):
                self.draw_block_on_view(idx, block, self.views[view], view)
        if self.selected is not None:
            idx, view = self.selected
            self.draw_gizmos(idx, view)

    def draw_grid(self, canvas, view):
        canvas.delete("all")
        width, height = CANVAS_SIZE
        cam = self.cameras[view]
        step_px = 50
        step = step_px / cam['scale']
        num_lines = int(max(width, height) / step_px * 1.5)
        for i in range(-num_lines, num_lines+1):
            wx = cam['center_x'] + i * step
            wy = cam['center_y'] + i * step
            x = width//2 + int((wx-cam['center_x']) * cam['scale'])
            canvas.create_line(x, 0, x, height, fill="#e0e0e0")
            y = height//2 - int((wy-cam['center_y']) * cam['scale'])
            canvas.create_line(0, y, width, y, fill="#e0e0e0")

    def draw_block_on_view(self, idx, block, canvas, view):
        cam = self.cameras[view]
        cx, cy, sw, sh, angle = project_block_2d(block, view)
        coords = to_canvas_coords(cx, cy, sw, sh, cam, *CANVAS_SIZE)
        color = block.get('material', 'gray')
        label = block.get('name', '')
        selected = (self.selected is not None and self.selected[0] == idx and self.selected[1] == view)
        outline = "red" if selected else "black"
        width = 4 if selected else 2
        if selected and float(angle):
            angle_rad = math.radians(angle)
            mx = (coords[0] + coords[2]) / 2
            my = (coords[1] + coords[3]) / 2
            w = coords[2] - coords[0]
            h = coords[3] - coords[1]
            corners = [(-w/2,-h/2), (w/2,-h/2), (w/2,h/2), (-w/2,h/2)]
            rot_corners = []
            for dx, dy in corners:
                rx =  dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
                ry =  dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
                rot_corners.extend([mx+rx, my+ry])
            canvas.create_polygon(*rot_corners, fill=color, outline=outline, width=width)
        else:
            canvas.create_rectangle(*coords, fill=color, outline=outline, width=width)
        canvas.create_text((coords[0] + coords[2]) // 2, coords[1] - 10, text=label, fill="black")

    def draw_gizmos(self, idx, view):
        mode = self.gizmo_mode.get()
        block = self.blocks[idx]
        cam = self.cameras[view]
        cx, cy, sw, sh, angle = project_block_2d(block, view)
        px = CANVAS_SIZE[0] // 2 + int((cx - cam['center_x']) * cam['scale'])
        py = CANVAS_SIZE[1] // 2 - int((cy - cam['center_y']) * cam['scale'])
        canvas = self.views[view]
        if mode == "move":
            axis_config = {
                "top":   [("x", (1, 0), "darkred"), ("z", (0, -1), "blue")],
                "front": [("x", (1, 0), "darkred"), ("y", (0, -1), "purple")],
                "right": [("z", (1, 0), "blue"),    ("y", (0, -1), "purple")],
            }[view]
        elif mode == "scale":
            axis_config = {
                "top":   [("x", (1, 0), "purple"), ("z", (0, -1), "purple")],
                "front": [("x", (1, 0), "purple"), ("y", (0, -1), "purple")],
                "right": [("z", (1, 0), "purple"), ("y", (0, -1), "purple")],
            }[view]
        elif mode == "rotate":
            arc_color = "purple"
            draw_arc_handle(canvas, (px, py), arc_color, self._gizmo_axis == "rot", tag="gizmo_arc", angle=angle)
            return
        for axis, direction, color in axis_config:
            handle_color = color if self._gizmo_axis != axis else "orange"
            draw_axis_handle(canvas, (px, py), direction, handle_color, scale=1.0, tag=f"gizmo_{axis}")

    def find_gizmo_axis_under_cursor(self, event, view):
        mode = self.gizmo_mode.get()
        if self.selected is None or self.selected[1] != view:
            return None
        idx, _ = self.selected
        block = self.blocks[idx]
        cam = self.cameras[view]
        cx, cy, sw, sh, angle = project_block_2d(block, view)
        px = CANVAS_SIZE[0] // 2 + int((cx - cam['center_x']) * cam['scale'])
        py = CANVAS_SIZE[1] // 2 - int((cy - cam['center_y']) * cam['scale'])
        mx, my = event.x, event.y
        if mode == "rotate":
            dx, dy = mx - px, my - py
            dist = math.hypot(dx, dy)
            if 42 < dist < 62:
                return "rot"
            return None
        axis_config = {
            "top":   [("x", (1, 0)), ("z", (0, -1))],
            "front": [("x", (1, 0)), ("y", (0, -1))],
            "right": [("z", (1, 0)), ("y", (0, -1))],
        }[view]
        for axis, dir2d in axis_config:
            hx, hy = px + dir2d[0] * 40, py + dir2d[1] * 40
            dist = (abs((mx-hx)*dir2d[1] - (my-hy)*dir2d[0])) / (math.hypot(*dir2d) + 1e-2)
            along = ((mx-px)*dir2d[0] + (my-py)*dir2d[1]) / (math.hypot(*dir2d)+1e-2)
            if dist < 10 and 0 < along < 40:
                return axis
        return None

    def on_canvas_motion(self, event, view):
        axis = self.find_gizmo_axis_under_cursor(event, view)
        prev_axis = self._gizmo_axis
        self._gizmo_axis = axis
        if prev_axis != axis:
            self.draw_all()

    def on_canvas_lmb_down(self, event, view):
        mode = self.gizmo_mode.get()
        axis = self.find_gizmo_axis_under_cursor(event, view)
        if self.selected and axis is not None:
            self._gizmo_action = (mode, self.selected[0], view, axis, event.x, event.y)
        else:
            self.on_canvas_click(event, view)

    def on_canvas_lmb_drag(self, event, view):
        if not self._gizmo_action:
            return
        mode, idx, v, axis, x0, y0 = self._gizmo_action
        block = self.blocks[idx]
        cam = self.cameras[view]
        dx_canvas = event.x - x0
        dy_canvas = event.y - y0
        if mode == "move":
            axis_map = {
                "top": {"x": ("x", dx_canvas), "z": ("z", -dy_canvas)},
                "front": {"x": ("x", dx_canvas), "y": ("y", -dy_canvas)},
                "right": {"z": ("z", dx_canvas), "y": ("y", -dy_canvas)},
            }[view]
            coord, d = axis_map[axis]
            d_world = d / cam['scale']
            pos = block.setdefault("position", {})
            prev = pos.get(coord, 0.0)
            pos[coord] = prev + d_world
            self._gizmo_action = (mode, idx, view, axis, event.x, event.y)
        elif mode == "scale":
            axis_map = {
                "top": {"x": ("x", dx_canvas), "z": ("z", -dy_canvas)},
                "front": {"x": ("x", dx_canvas), "y": ("y", -dy_canvas)},
                "right": {"z": ("z", dx_canvas), "y": ("y", -dy_canvas)},
            }[view]
            coord, d = axis_map[axis]
            d_world = d / cam['scale']
            size = block.setdefault("size", {})
            prev = size.get(coord, 1.0)
            size[coord] = max(0.1, prev + d_world)
            self._gizmo_action = (mode, idx, view, axis, event.x, event.y)
        elif mode == "rotate":
            px = CANVAS_SIZE[0] // 2 + int((_get(block, 'position', view[0]) - cam['center_x']) * cam['scale'])
            py = CANVAS_SIZE[1] // 2 - int((_get(block, 'position', view[-1]) - cam['center_y']) * cam['scale'])
            ang1 = math.atan2(-(y0 - py), x0 - px)
            ang2 = math.atan2(-(event.y - py), event.x - px)
            d_angle = math.degrees(ang2 - ang1)
            rot = block.setdefault("rotation", {})
            if view == "top":
                prev = rot.get("y", 0.0)
                rot["y"] = (prev + d_angle) % 360
            elif view == "front":
                prev = rot.get("z", 0.0)
                rot["z"] = (prev + d_angle) % 360
            elif view == "right":
                prev = rot.get("x", 0.0)
                rot["x"] = (prev + d_angle) % 360
            self._gizmo_action = (mode, idx, view, axis, event.x, event.y)
        self.draw_all()

    def on_canvas_lmb_up(self, event, view):
        self._gizmo_action = None

    def on_canvas_click(self, event, view):
        cam = self.cameras[view]
        x_click, y_click = event.x, event.y
        candidates = []
        for idx, block in enumerate(self.blocks):
            cx, cy, sw, sh, _ = project_block_2d(block, view)
            coords = to_canvas_coords(cx, cy, sw, sh, cam, *CANVAS_SIZE)
            x0, y0, x1, y1 = coords
            if x0 <= x_click <= x1 and y0 <= y_click <= y1:
                candidates.append(idx)
        if not candidates:
            self.selected = None
            self.last_clicked_index[view] = 0
            self.draw_all()
            return
        last_idx = self.selected[0] if self.selected and self.selected[1] == view and self.selected[0] in candidates else None
        if last_idx is not None:
            try:
                pos = candidates.index(last_idx)
                pos = (pos + 1) % len(candidates)
            except ValueError:
                pos = 0
        else:
            pos = 0
        self.selected = (candidates[pos], view)
        self.last_clicked_index[view] = pos
        self.draw_all()

    def on_key_press(self, event):
        if self._gizmo_action:
            return
        if self.selected is None:
            return
        idx, view = self.selected
        block = self.blocks[idx]
        move_amount = 0.2
        axis1, axis2 = {
            "top":   ("x", "z"),
            "front": ("x", "y"),
            "right": ("z", "y"),
        }[view]
        mode = self.gizmo_mode.get()
        if mode == "move":
            if event.keysym == 'Left':
                block.setdefault("position", {})
                block["position"][axis1] = block["position"].get(axis1, 0.0) - move_amount
            elif event.keysym == 'Right':
                block.setdefault("position", {})
                block["position"][axis1] = block["position"].get(axis1, 0.0) + move_amount
            elif event.keysym == 'Up':
                block.setdefault("position", {})
                block["position"][axis2] = block["position"].get(axis2, 0.0) + move_amount
            elif event.keysym == 'Down':
                block.setdefault("position", {})
                block["position"][axis2] = block["position"].get(axis2, 0.0) - move_amount
            else:
                return
            self.draw_all()
        elif mode == "scale":
            if event.keysym == 'Left':
                block.setdefault("size", {})
                block["size"][axis1] = max(0.1, block["size"].get(axis1, 1.0) - move_amount)
            elif event.keysym == 'Right':
                block.setdefault("size", {})
                block["size"][axis1] = max(0.1, block["size"].get(axis1, 1.0) + move_amount)
            elif event.keysym == 'Up':
                block.setdefault("size", {})
                block["size"][axis2] = max(0.1, block["size"].get(axis2, 1.0) + move_amount)
            elif event.keysym == 'Down':
                block.setdefault("size", {})
                block["size"][axis2] = max(0.1, block["size"].get(axis2, 1.0) - move_amount)
            else:
                return
            self.draw_all()

    def on_mouse_wheel(self, event, view, delta=None):
        cam = self.cameras[view]
        dd = event.delta if delta is None else delta
        if dd > 0:
            cam['scale'] *= 1.1
        else:
            cam['scale'] /= 1.1
        cam['scale'] = max(2.0, min(300, cam['scale']))
        self.draw_all()

    def on_pan_start(self, event, view):
        self._panning[view] = True
        self._drag_start[view] = (event.x, event.y)
        cam = self.cameras[view]
        self._cam_start[view] = (cam['center_x'], cam['center_y'])

    def on_pan_move(self, event, view):
        if not self._panning[view]:
            return
        dx = event.x - self._drag_start[view][0]
        dy = event.y - self._drag_start[view][1]
        cam = self.cameras[view]
        sx, sy = self._cam_start[view]
        cam['center_x'] = sx - dx / cam['scale']
        cam['center_y'] = sy + dy / cam['scale']
        self.draw_all()

    def on_pan_end(self, event, view):
        self._panning[view] = False

if __name__ == "__main__":
    blocks = load_blocks(MAP_FILE)
    app = MapEditorGUI(blocks)
    app.mainloop()
