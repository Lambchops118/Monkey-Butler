
import os
import sys
import time
import queue
import pygame
import platform
from pathlib import Path
from   dotenv import load_dotenv; load_dotenv()

#import gears2 as gears
from . import butler_vector_art as MBVectorArt
from . import moving_vector_portrait as vec3d
from . import obj_wireframe_loader as objl
from . import screen_effects as fx
from . import windows
from .screen_effects import GpuCRT

font_path = str(Path(__file__).resolve().parent / "VT323-Regular.ttf")

# =============== PYGAME INFO PANEL ===============
color         = (0, 255, 100)
color_offline = (5, 5, 5)
red           = (255, 0, 0)

RESOLUTIONS = {
    "QHD"   : (2560, 1440),
    "UHD"   : (3840, 2160),
    "1080P" : (1920, 1080),
}

scale = 0.75
FORCED_WINDOW_SIZE = RESOLUTIONS["1080P"]

# Debug mode: show the mouse cursor plus a crosshair and label giving its
# position in design units (the values PORTRAIT_BOX, dynamo configs etc. use)
# and in window pixels.
DEBUG_MOUSE = False

# Special effects. Everything is drawn the same way either way; these only
# switch the finishing touches applied to the finished frame. ENABLE_FX is the
# master switch: when False, every effect below is off regardless of its own
# setting, giving a flat, undistorted picture (handy with DEBUG_MOUSE, since
# the cursor then lines up exactly with what is drawn).
ENABLE_FX = True
FX_CRT_SHADER = True  # OpenGL: screen curvature and gamma
FX_BLOOM      = 0.25   # CPU: glow around bright lines and text, 0.0 (off) to 1.0 (full)
FX_GRILLE     = True  # CPU: faint vertical aperture-grille stripes
# These two each control BOTH versions of the effect: the CPU overlay and the
# shader's own pass (when FX_CRT_SHADER is on).
FX_VIGNETTE   = True  # darkened edges and corners
FX_SCANLINES  = True  # horizontal scanlines


def fx_on(flag):
    """True when the master switch and the individual effect are both on."""
    return ENABLE_FX and flag

# Every on-screen coordinate, size and font size in this module is authored in
# this fixed design space. ``Layout`` maps it onto the real window with one
# uniform scale factor (so circles stay round and text keeps its proportions)
# and centres the result, letterboxing when the aspect ratio is not 16:9.
DESIGN_W, DESIGN_H = RESOLUTIONS["QHD"]


class Layout:
    """Maps design-space coordinates onto the actual window."""

    def __init__(self, screen_w, screen_h, design_w=DESIGN_W, design_h=DESIGN_H):
        self.design_w = design_w
        self.design_h = design_h
        self.scale = min(screen_w / design_w, screen_h / design_h)
        self.offset_x = (screen_w - design_w * self.scale) / 2
        self.offset_y = (screen_h - design_h * self.scale) / 2

    def x(self, dx):
        return self.offset_x + dx * self.scale

    def y(self, dy):
        return self.offset_y + dy * self.scale

    def point(self, dx, dy):
        return self.x(dx), self.y(dy)

    def length(self, d):
        return d * self.scale

    def to_design(self, px, py):
        """Inverse of ``point``: window pixels -> design units."""
        return (px - self.offset_x) / self.scale, (py - self.offset_y) / self.scale


def choose_window_size(display_w, display_h):
    forced_w, forced_h = FORCED_WINDOW_SIZE
    window_w = min(forced_w, display_w)
    window_h = min(forced_h, display_h)
    return window_w, window_h

def draw_monkey_butler_head(
    screen, base_x, base_y, scale_x, scale_y, color_, animation_time=0.0
):
    MBVectorArt.draw_monkey_butler_head(
        screen,
        base_x,
        base_y,
        scale_x,
        scale_y,
        color_,
        animation_time=animation_time,
    )

_font_cache = {}

def get_font(size, ui_scale=scale):
    key = max(1, int(size * ui_scale))
    if key not in _font_cache:
         _font_cache[key] = pygame.font.Font(font_path, key)
    return _font_cache[key]


def platform_time_formats():
    """strftime formats for (time, day, date), e.g. "6:34 PM", "Thursday",
    "September 2, 2026". Windows spells "no leading zero" as %#, others as %-.
    """
    if platform.system() == "Windows":
        return "%#I:%M %p", "%A", "%B %#d, %Y"
    return "%-I:%M %p", "%A", "%B %-d, %Y"


# ---- Clock (time / day / date) ------------------------------------------------
# Design units. CLOCK_TOP_Y is the top of the first line's capitals, and
# CLOCK_GAP the empty space between one line's baseline and the top of the next
# line's capitals, so the lines look evenly spaced whatever their font sizes.
# Horizontally the lines are centred between the portrait frame's right edge
# and the vertical divider left of the dynamos (see clock_center_x); set
# CLOCK_X to a design-unit x to pin them somewhere else instead.
CLOCK_X     = None
CLOCK_TOP_Y = 200  # level with the portrait frame top; was 162
CLOCK_GAP   = 25

_cap_metrics_cache = {}


def _cap_metrics(font):
    """(top, height) in pixels of capital letters/digits within a rendered line."""
    key = id(font)
    if key not in _cap_metrics_cache:
        ink = font.render("H0", True, (255, 255, 255)).get_bounding_rect()
        _cap_metrics_cache[key] = (ink.y, ink.height)
    return _cap_metrics_cache[key]


def draw_text_stack(screen, layout, lines, center_x, top_y, gap, color_):
    """Draw ``(text, size)`` lines centred on ``center_x``, evenly spaced from
    ``top_y`` downward. All arguments other than pixels are design units."""
    px_x = layout.x(center_x)
    cursor = layout.y(top_y)
    for text, size in lines:
        font = get_font(size, layout.scale)
        cap_top, cap_h = _cap_metrics(font)
        surf = font.render(str(text), True, color_)
        # Centre the visible ink, not the glyph box (side bearings differ).
        ink = surf.get_bounding_rect()
        left = px_x - (ink.x + ink.width / 2)
        screen.blit(surf, (round(left), round(cursor - cap_top)))
        cursor += cap_h + layout.length(gap)


def static_drawings(screen, layout, clock_x):
    base_w, base_h = layout.design_w, layout.design_h
    time_format, day_format, date_format = platform_time_formats()
    time_readable = time.strftime(time_format)   # 6:34 PM
    day_readable  = time.strftime(day_format)    # Thursday
    date_readable = time.strftime(date_format)   # September 2, 2026

    def draw_text_centered(text, bx, by, color, size=30):
        surf = get_font(size, layout.scale).render(str(text), True, color)
        rect = surf.get_rect(center=layout.point(bx, by))
        screen.blit(surf, rect)

    # Clock block: lines stacked top to bottom with an equal visible gap.
    clock_lines = [
        (time_readable, 150),
        (day_readable,  125),
        (date_readable,  90),
    ]
    draw_text_stack(screen, layout, clock_lines, clock_x, CLOCK_TOP_Y,
                    CLOCK_GAP, color)

    items = [
        ("Monkey Butler", base_w/8.5,     base_h/14,  90),
        #("Information",   base_w/4,     base_h/14,  50),
        ("Systems Status",base_w/1.25,  base_h/14,  50),
        ("Chopscorp. Ltd. c 1977", base_w-180, base_h-75, 30),
    ]

    for text, x, y, size in items:
        draw_text_centered(text, x, y, color, size)


# ---- Portrait -----------------------------------------------------------------
# The border and the Monkey Butler head are both driven by PORTRAIT_BOX, so
# editing it moves and resizes them together. x/y is the box's top-left corner;
# all values are design units (see Layout).
#
# w and h resize the frame independently. The head always keeps its aspect
# ratio: its size follows the frame's height only, and it is clipped to the
# frame's interior, so a frame narrower than the head eclipses its sides.
#PORTRAIT_BOX = dict(x=1073, y=170, w=415, h=426)
PORTRAIT_BOX = dict(x=75, y=170, w=1000, h=1100)
PORTRAIT_LINE_WIDTH = 8

# How much of the frame's height the head fills (0..1). 245/426 matches the
# original head size in the original 415x426 frame.
PORTRAIT_FILL = 245 / 426

# Once-a-second bob, in art units, so it scales with the head.
PORTRAIT_BOB = 40.0 / 3.0

# Bounding box of the head art in butler_vector_art's own units (y points up).
_ART_X0, _ART_X1 = 290, 675
_ART_Y0, _ART_Y1 = 190, 435
_ART_CX = (_ART_X0 + _ART_X1) / 2
_ART_CY = (_ART_Y0 + _ART_Y1) / 2


def portrait_art_scale(box=PORTRAIT_BOX, fill=PORTRAIT_FILL):
    """Design units per art unit so the head fills ``fill`` of the box height."""
    return fill * box["h"] / (_ART_Y1 - _ART_Y0)


def portrait_clip_rect(layout, box=PORTRAIT_BOX, line_width=PORTRAIT_LINE_WIDTH):
    """Pixel rect inside the frame's border, rounded the same way as Widget."""
    lw = max(1, int(line_width * layout.scale))
    outer = pygame.Rect(int(layout.x(box["x"])), int(layout.y(box["y"])),
                        int(layout.length(box["w"])), int(layout.length(box["h"])))
    return outer.inflate(-2 * lw, -2 * lw)


def draw_portrait(surface, layout, color_, animation_time, *, bob=0.0,
                  box=PORTRAIT_BOX, fill=PORTRAIT_FILL):
    """Draw the head centred in ``box``, raised by ``bob`` art units.

    ``butler_vector_art`` places art point (ax, ay) at pixel
    ``(dx + ax*s - 200, height - (dy + ay*s - 145))``. Solve for dx/dy so the
    art's centre lands on the box centre at any resolution and box size.
    Drawing is clipped to the frame's interior.
    """
    s = layout.scale * portrait_art_scale(box, fill)
    cx, cy = layout.point(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    dx = cx - _ART_CX * s + 200
    dy = surface.get_height() + 145 - cy - (_ART_CY + bob) * s
    previous_clip = surface.get_clip()
    surface.set_clip(portrait_clip_rect(layout, box).clip(previous_clip))
    try:
        draw_monkey_butler_head(surface, dx, dy, s, s, color_, animation_time)
    finally:
        surface.set_clip(previous_clip)


def draw_mouse_debug(surface, layout, color_=(255, 255, 255)):
    """Crosshair at the mouse plus its design-unit and pixel coordinates."""
    mx, my = pygame.mouse.get_pos()
    dx, dy = layout.to_design(mx, my)
    w, h = surface.get_size()
    pygame.draw.line(surface, color_, (mx, 0), (mx, h), 1)
    pygame.draw.line(surface, color_, (0, my), (w, my), 1)

    font = get_font(40, layout.scale)
    label = font.render(f"design ({dx:.0f}, {dy:.0f})  px ({mx}, {my})", True, color_)
    rect = label.get_rect(topleft=(mx + 12, my + 12))
    # Flip to the other side of the cursor near the right/bottom edges.
    if rect.right > w:
        rect.right = mx - 12
    if rect.bottom > h:
        rect.bottom = my - 12
    pygame.draw.rect(surface, (0, 0, 0), rect.inflate(8, 4))
    surface.blit(label, rect)


# ---- Boundary lines -----------------------------------------------------------
# Design units. HEADER_RULE_Y is the horizontal line under the titles, midway
# between the bottom of "Monkey Butler"'s descenders (~144) and the portrait
# frame top (170); it runs
# from the portrait frame's left edge to the same margin on the right.
# The vertical divider sits DIVIDER_GAP left of the leftmost dynamo's teeth and
# runs from the header rule to the bottom of the portrait frame.
HEADER_RULE_Y   = 0
RULE_LINE_WIDTH = 5
DIVIDER_GAP     = 25


def dynamo_left_edge(dynamo_configs):
    """Design x of the leftmost pixel of the leftmost dynamo."""
    return min(cfg["x"] for cfg in dynamo_configs) - windows.Dynamo.left_extent()


def divider_x(dynamo_configs):
    """Design x of the vertical divider's centre line."""
    return dynamo_left_edge(dynamo_configs) - DIVIDER_GAP - RULE_LINE_WIDTH / 2


def clock_center_x(dynamo_configs, box=PORTRAIT_BOX):
    """Design x midway between the portrait frame's right edge and the
    vertical divider's left edge."""
    frame_right = box["x"] + box["w"]
    divider_left = divider_x(dynamo_configs) - RULE_LINE_WIDTH / 2
    return (frame_right + divider_left) / 2


def draw_boundaries(screen, layout, divider_center_x, box=PORTRAIT_BOX):
    """Header rule under the titles and the divider left of the dynamos."""
    lw = max(1, round(layout.length(RULE_LINE_WIDTH)))
    left, right = box["x"], layout.design_w - box["x"]
    pygame.draw.line(screen, color, layout.point(left, HEADER_RULE_Y), layout.point(right, HEADER_RULE_Y), lw)
    pygame.draw.line(screen, color, layout.point(divider_center_x, HEADER_RULE_Y), layout.point(divider_center_x, box["y"]+200 + box["h"]), lw)

    pygame.draw.line(screen, color, (0, 96), (1005, 96), lw)
    pygame.draw.line(screen, color, (0, 711), (1005, 711), lw)

def run_info_panel_gui(cmd_queue, scale=None): #The main Pygame loop. Polls 'cmd_queue' for new commands to display.
    # ``scale`` is accepted for compatibility but ignored: the UI scale is now
    # derived from the window size (see Layout).
    print("Starting Pygame GUI for Info Panel...")

    pygame.init()
    info = pygame.display.Info()

    display_w, display_h = info.current_w, info.current_h
    screen_width, screen_height = choose_window_size(display_w, display_h)
    # Opt-in fullscreen (BUTLER_DISPLAY_FULLSCREEN=1) at the native resolution.
    fullscreen = os.getenv("BUTLER_DISPLAY_FULLSCREEN", "0").strip().lower() in ("1", "true", "yes", "on")
    window_flags = pygame.FULLSCREEN if fullscreen else 0
    if fullscreen:
        screen_width, screen_height = display_w, display_h

    #w = screen_width
    #h = screen_height

    print("Detected screen resolution:", display_w, display_h)
    print("Forcing window size:", screen_width, screen_height)
    if (screen_width, screen_height) != FORCED_WINDOW_SIZE:
        print("Adjusted window size to fit the current display.")

    layout = Layout(screen_width, screen_height)
    scale = layout.scale
    print(f"Design resolution {DESIGN_W}x{DESIGN_H}, UI scale {scale:.3f}")

    mob_angle = 0

    screen = None
    crt = None
    if fx_on(FX_CRT_SHADER):
        try:
            crt = GpuCRT(window_size=(screen_width, screen_height),
                   kx=0.18, ky=0.16, curv=0.3,
                   scan=0.18 if fx_on(FX_SCANLINES) else 0.0,
                   vign=0.45 if fx_on(FX_VIGNETTE) else 0.0,
                   gamma=2.0,
                   extra_flags=window_flags)
            print("GPU CRT effect enabled.")
        except Exception as exc:
            print(f"GPU CRT unavailable, falling back to standard Pygame rendering: {exc}")
    else:
        print("GPU CRT shader disabled (ENABLE_FX / FX_CRT_SHADER).")
    if crt is None:
        screen = pygame.display.set_mode((screen_width, screen_height), window_flags)

    pygame.display.set_caption("Monkey Butler")
    pygame.mouse.set_visible(DEBUG_MOUSE)

    clock        = pygame.time.Clock()
    running      = True
    circle_time  = 0
    angle        = 0

    # We'll keep track of the "last voice command" and "last GPT response"
    # so we can display them in the GUI.
    last_command  = "\"butler, water the monstera\""
    last_response = "of course, sir. i have activated the pump for the pot with the monstera."
    remote_sleep_state = {"asleep": False, "display_level": 1.0}
    portrait_started_at = time.monotonic()


    #========================================================================================
    # Off-screen render target
    framebuffer = pygame.Surface((screen_width, screen_height)).convert()
    framebuffer_alpha = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA).convert_alpha()

    # Cached overlays (rebuild these if resolution changes)
    scanlines_surf = fx.build_scanlines(screen_width, screen_height, spacing=5, alpha=200)
    grille_surf    = fx.build_aperture_grille(screen_width, screen_height, pitch=3, alpha=18)
    vignette_surf  = fx.build_vignette(screen_width, screen_height, margin=24, edge_alpha=70, corner_radius=28)

    # Persistence buffer (previous post-processed frame)
    #last_frame = None
    #========================================================================================

    #Code for 3d wireframe panel
    panel_rect = (int(layout.x(1360)), int(layout.y(400)),
                  int(layout.length(453)), int(layout.length(347))) # x, y, w, h
    renderer   = vec3d.WireframeRenderer(panel_rect, fov=55, near=0.1, far=50) 
    mesh       = vec3d.cube_mesh(size=0.7) # Create a cube mesh
    angle      = 180.0 # Rotation angle for animation

    # Add a new dict with settings to add new dynamos to the screen.
    dynamo_system_status = {
        "mqtt": 1,
        "panels": 1,
        "waterer": 1,
        "discord": 0,
        "engassist": 1,
    }


    dynamo_configs = [
        dict(id="mqtt", x=1900, y=250, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "MQTT Broker", subtext="[status]"),
        dict(id="panels",x=1900, y=475, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Home Automation MCP", subtext="[status]"),
        dict(id="waterer",x=1900, y=700, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Auto Waterer", subtext="[status]"),
        dict(id="discord",x=1900, y=925,  base_deg=45,  surface=framebuffer, scale=scale, color=color, supertext= "Discord Frontend", subtext=""),
        dict(id="engassist",x=1900, y=1150, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Engineering Assist", subtext="")
    ]
    
    clock_x = CLOCK_X if CLOCK_X is not None else clock_center_x(dynamo_configs)
    divider_center_x = divider_x(dynamo_configs)

    # This takes the dynamo configs and creates the actual Dynamo objects.
    dynamos = [
        windows.Dynamo(
            windows.WidgetConfig(
                surface=framebuffer,
                x=cfg["x"],
                y=cfg["y"],
                obj_width=0,
                obj_height=0,
                scale=scale,
                color=(255, 0, 0),
                text="test text",
                line_width=5,
                font_size=(60),
                offset_x=layout.offset_x,
                offset_y=layout.offset_y,
            ),
            cfg["supertext"],
            cfg["subtext"],
            dynamo_system_status[cfg["id"]],
            cfg["base_deg"],
        )
        for cfg in dynamo_configs
    ]

    # Add new widget configs here to add new widgets to the screen.

    widget_statuses = {
        "btc_price": None,
        "eth_price": None,
        "sol_price": None,
        "temp"     : None,
        "feelslike": None,
        "humidity" : None,
        "wind"     : None,
        "wind_dir" : None,
        "weather"  : None,
        "uptime"     : None
    }

    widget_configs = [
        #Basic Information Box
        #dict(x=145, y=170, obj_width=850, obj_height=500, surface=framebuffer, scale=scale, color=color,
        #     text=
        #     "BTC: ${btc_price}  ETH: ${eth_price} SOL: ${sol_price} \n" \
        #     "\n" \
        #     "Temperature: {temp}°F   Feels Like: {feelslike}°F\n" \
        #     "Humidity: {humidity}% \n" \
        #     "Wind: {wind}mph  {wind_direction}\n Weather: {weather}\n" \
        #     "\nUptime: {uptime} days | Net Worth: $101,749",
        #     fontsize = 55),
        
        #Voice Input Box
        #dict(x=60, y=735, obj_width=1500, obj_height=150, surface=framebuffer, scale=scale, color=color,
        #     id="voice_cmd", 
        #     text="\"Butler, water the Monstera...\"", 
        #     fontsize = 60),

        #Voice Response Box
        #dict(x=60, y=900, obj_width=1500, obj_height=450, surface=framebuffer, scale=scale, color=color, 
        #     id="voice_resp",
        #     text="Of course sir, the Monstera has been watered.", 
        #     fontsize = 60),
        
        #Portrait Box
        dict(x=PORTRAIT_BOX["x"], y=PORTRAIT_BOX["y"],
             obj_width=PORTRAIT_BOX["w"], obj_height=PORTRAIT_BOX["h"],
             surface=framebuffer, scale=scale, color=color, text="", fontsize=0,
             line_width=PORTRAIT_LINE_WIDTH),
    ]

    # This takes the widget configs and creates the actual Widget objects.
    widgets = [
        windows.Widget(
            windows.WidgetConfig(
                surface=framebuffer,
                x=cfg["x"],
                y=cfg["y"],
                obj_width=cfg["obj_width"],
                obj_height=cfg["obj_height"],
                scale=scale,
                color=cfg["color"],
                text=cfg["text"],
                line_width=cfg.get("line_width", 5),
                font_size=cfg["fontsize"],
                offset_x=layout.offset_x,
                offset_y=layout.offset_y,
            )
        )
        for cfg in widget_configs
    ]


    #character = objl.load_obj_wire( "prototypes/3d-vector-art/butlerv3.obj", keep_edges="feature", # try "boundary" or "all"
    #                                   feature_angle_deg=50.00, # larger -> fewer, sharper edges kept
    #                                     target_radius=0.8 )

    while running: # [][]][][][][][][][][][][][][][][][][]MAIN LOOP[][][][][][][][][][][][][][][][][]
        # --- EVENT HANDLING ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # --- POLL THE QUEUE ---
        # Collect all commands currently in the queue
        while True:
            try:
                msg = cmd_queue.get_nowait()
            except queue.Empty:
                break
            else:
                if msg[0] == "VOICE_CMD":
                    # msg structure: ("VOICE_CMD", recognized_command, gpt_response_text)
                    last_command  = msg[1]
                    last_response = msg[2]
                elif msg[0] == "STATUS":
                    # msg structure: ("STATUS", {"key": value, ...})
                    if isinstance(msg[1], dict):
                        widget_statuses.update(msg[1])
                elif msg[0] == "DISPLAY_STATE" and isinstance(msg[1], dict):
                    snapshot = msg[1]
                    if not snapshot.get("connected", True):
                        last_command = "Display disconnected from Butler"
                        last_response = str(snapshot.get("error", "Connection unavailable"))
                        continue
                    last_command = str(snapshot.get("last_command", last_command))
                    last_response = str(snapshot.get("last_response", last_response))
                    statuses = snapshot.get("statuses")
                    if isinstance(statuses, dict):
                        widget_statuses.update(statuses)
                    sleep = snapshot.get("sleep")
                    if isinstance(sleep, dict):
                        remote_sleep_state = sleep

        # --- RENDER THE FRAME --- 
        framebuffer.fill((0, 1, 0)) 
        static_drawings(framebuffer, layout, clock_x)
        draw_boundaries(framebuffer, layout, divider_center_x)
        second = int(time.strftime("%S"))
        # Bob evenly above/below centre so the head stays centred on average.
        bob = PORTRAIT_BOB / 2 if second % 2 == 0 else -PORTRAIT_BOB / 2

        # Update Dynamo Statuses Here.
        dynamo_system_status["mqtt"]         = 1 #if (second >= 0) else 0  #placeholder code to simulate status changes. replace with actual
        dynamo_system_status["panels"]       = 0 #if (second >= 10) else 0
        dynamo_system_status["waterer"]      = 0 #if (second >= 20) else 0
        dynamo_system_status["discord"]      = 1 #if (second >= 30) else 0
        dynamo_system_status["engassist"]    = 0 #if (second >= 40) else 0

        draw_portrait(
            framebuffer,
            layout,
            color,
            time.monotonic() - portrait_started_at,
            bob=bob,
        )

        #draw_text_topleft(f"Last command:  {last_command}",  75, 740, color, 36, target=framebuffer)
        #draw_text_topleft(f"Last response: {last_response}", 75, 900, color, 36, target=framebuffer)

        # Draw Widgets to the screen
        for d, cfg in zip(dynamos, dynamo_configs):
            d.system_status = dynamo_system_status[cfg["id"]]
            d.subtext = "online" if d.system_status == 1 else "offline"
            if d.system_status == 1:
                d.degrees = (d.degrees + 4) % 360
            d.draw_dynamo()

        for w, cfg in zip(widgets, widget_configs):
                w.drawCenteredRect()
                if cfg.get("id") == "voice_cmd":
                    w.createTextArea(last_command)
                elif cfg.get("id") == "voice_resp":
                    w.createTextArea(last_response)
                else:
                    safe = {k: ("--" if v is None else v) for k, v in widget_statuses.items()}
                    safe["wind_direction"] = safe.get("wind_dir", "--")
                    w.createTextArea(cfg["text"].format(**safe))


        #renderer.draw(
        #    framebuffer,
        #    character,
        #    model_pos     = (0.0, -0.1, 3.2),
        #    model_rot     = (0, mob_angle*0.9, 0),
        #    model_scale   = 3.5,
        #    camera_pos    = (0, 0, 0),
        #    camera_target = (0, 0, 1),
        #    zsort         = True
        #)
        # def draw_mouse_coordinates(surface):
        #     x, y = pygame.mouse.get_pos()
        #     text = font_scaled.render(f"({x}, {y})", True, (255, 255, 255))
        #     surface.blit(text, (10, 10))  # Display in top-left corner
        # draw_mouse_coordinates(framebuffer)

        # === POST FX on a copy (so we can reuse framebuffer if needed) ===
        post = framebuffer#.copy()
        #last_frame = post
        bloom = min(max(float(FX_BLOOM), 0.0), 1.0) if ENABLE_FX else 0.0
        if bloom > 0.0:
            fx.add_bloom(post, strength=bloom, down=0.45)
        #post = fx.apply_persistence(last_frame, post, alpha=80)
        if fx_on(FX_GRILLE):
            post.blit(grille_surf,   (0, 0))
        if fx_on(FX_VIGNETTE):
            post.blit(vignette_surf, (0, 0))
        if fx_on(FX_SCANLINES):
            post.blit(scanlines_surf,(0, 0))

        # Drawn after the post FX so bloom and scanlines don't smear the text.
        if DEBUG_MOUSE:
            draw_mouse_debug(post, layout)

        # Sleep mode: darken the finished frame to a few percent of its
        # brightness. Every layer -- text, dynamos, CRT masks -- dims together,
        # because this is the last thing that touches the picture. The panel
        # stays lit but night-dark: an asleep panel is visibly different from a
        # dead one.
        #
        # Where it happens depends on the path. On the GPU path the shader owns
        # it (see GpuCRT.set_dim): its 1/gamma pass would otherwise take a 1%
        # multiply back up to 10% on the glass, and the 8-bit multiply would
        # crush the mid-tones on the way in. The plain-pygame fallback has no
        # such pass, so a single BLEND_MULT fill is both correct and cheaper
        # than a re-render there.
        asleep = bool(remote_sleep_state.get("asleep", False))
        display_level = float(remote_sleep_state.get("display_level", 1.0))

        if crt is not None:
            crt.set_dim(display_level)
            crt.draw_surface(post)
        else:
            if display_level < 1.0:
                level = int(round(255 * display_level))
                post.fill((level, level, level), special_flags=pygame.BLEND_MULT)
            screen.blit(post, (0, 0))
            pygame.display.flip()
        #last_frame = post

        # Nothing on a sleeping panel animates fast enough to need 60 fps, and
        # the GPU shares this box with the local model.
        clock.tick(15 if asleep else 60)
        circle_time += 1
        mob_angle += 0.01

    pygame.quit()
    return
