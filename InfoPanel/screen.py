
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
    if platform.system() == "Windows":
        return "%A %#I:%M %p", "%B %#d, %Y"
    return "%A %-I:%M %p", "%B %-d, %Y"


def static_drawings(screen, layout):
    base_w, base_h = layout.design_w, layout.design_h
    time_format, date_format = platform_time_formats()
    time_readable = time.strftime(time_format)
    date_readable = time.strftime(date_format)

    def draw_text_centered(text, bx, by, color, size=30):
        surf = get_font(size, layout.scale).render(str(text), True, color)
        rect = surf.get_rect(center=layout.point(bx, by))
        screen.blit(surf, rect)

    items = [
        #(time_readable,   base_w/2,     base_h/2.3, 75),
        #(date_readable,   base_w/2,     base_h/2.1, 75),
        ("Monkey Butler", base_w/2,     base_h/14,  80),
        #("Information",   base_w/4,     base_h/14,  50),
        ("Systems Status",base_w/1.25,  base_h/14,  50),
        ("Chopscorp. Ltd. c 1977", base_w-180, base_h-75, 30),
    ]

    for text, x, y, size in items:
        draw_text_centered(text, x, y, color, size)


# ---- Portrait box -----------------------------------------------------------
# Edit PORTRAIT_BOX to move or resize the box; the Monkey Butler head follows
# it, stays centred inside it and scales with it. Values are design units.
PORTRAIT_BOX = dict(x=1073, y=170, w=415, h=426)
PORTRAIT_LINE_WIDTH = 8

# How much of the box the head may fill (0..1), measured on whichever of the
# box's width or height is the tighter fit. 385/415 is the original size.
PORTRAIT_FILL = 385 / 415

# Once-a-second bob, in design units at the original head size.
PORTRAIT_BOB = 40.0 / 3.0

# Bounding box of the head art in butler_vector_art's own units (y points up).
_ART_X0, _ART_X1 = 290, 675
_ART_Y0, _ART_Y1 = 190, 435
_ART_CX = (_ART_X0 + _ART_X1) / 2
_ART_CY = (_ART_Y0 + _ART_Y1) / 2


def portrait_art_scale(box=None, fill=None):
    """Design units per art unit so the head fits ``fill`` of ``box``."""
    box = PORTRAIT_BOX if box is None else box
    fill = PORTRAIT_FILL if fill is None else fill
    return fill * min(box["w"] / (_ART_X1 - _ART_X0),
                      box["h"] / (_ART_Y1 - _ART_Y0))


def draw_portrait(surface, layout, color_, animation_time, *, bob=0.0,
                  box=None, fill=None):
    """Draw the head centred in ``box``, shifted up by ``bob`` (art units).

    ``butler_vector_art`` places art point (ax, ay) at pixel
    ``(dx + ax*s - 200, height - (dy + ay*s - 145))``. Solve for dx/dy so the
    art's centre lands on the box centre at any resolution.
    """
    box = PORTRAIT_BOX if box is None else box
    s = layout.scale * portrait_art_scale(box, fill)
    cx, cy = layout.point(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    dx = cx - _ART_CX * s + 200
    dy = surface.get_height() + 145 - cy - (_ART_CY + bob) * s
    draw_monkey_butler_head(surface, dx, dy, s, s, color_, animation_time)


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
    try:
        crt = GpuCRT(window_size=(screen_width, screen_height),
               kx=0.18, ky=0.16, curv=0.3,
               scan=0.18, vign=0.45, gamma=2.0,
               extra_flags=window_flags)
        print("GPU CRT effect enabled.")
    except Exception as exc:
        print(f"GPU CRT unavailable, falling back to standard Pygame rendering: {exc}")
        screen = pygame.display.set_mode((screen_width, screen_height), window_flags)

    pygame.display.set_caption("Monkey Butler")
    pygame.mouse.set_visible(False)

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
        dict(id="mqtt", x=1700, y=250, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "MQTT Broker", subtext="[status]"),
        dict(id="panels",x=1700, y=475, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Home Automation MCP", subtext="[status]"),
        dict(id="waterer",x=1700, y=700, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Auto Waterer", subtext="[status]"),
        dict(id="discord",x=1700, y=925,  base_deg=45,  surface=framebuffer, scale=scale, color=color, supertext= "Discord Frontend", subtext=""),
        dict(id="engassist",x=1700, y=1150, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Engineering Assist", subtext="")
    ]
    
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
        static_drawings(framebuffer, layout)
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
        fx.add_bloom(post, strength=1, down=0.45)
        #post = fx.apply_persistence(last_frame, post, alpha=80)
        post.blit(grille_surf,   (0, 0))
        post.blit(vignette_surf, (0, 0))
        post.blit(scanlines_surf,(0, 0))

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
