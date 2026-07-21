import asyncio
import time
import os
import sys
import flet as ft
import random
import steam_backend as backend

APP_TITLE = "LarpSense NFA"

# ============================================================
#  Color Palette (Cosmic Larpsense UI)
# ============================================================
BG = "#07090a"
NEBULA_PURPLE = "#1a2340"
PANEL = "#111511"
CARD_BG = "#111511"
INPUT_BG = "#0e120e"
BORDER = "#1f271f"
TXT = "#e6ede6"
TITLE_TXT = "#e9fce9"
TXT2 = "#7d887d"
GREEN = "#8bff3d"
AMBER = "#f5a623"
RED_ERR = "#ff5c5c"
BTN_BG = "#161d16"

# Cooldown/NFA specific colors
SUCCESS = GREEN
DANGER = RED_ERR
WARNING = AMBER
TEXT_MAIN = TXT
TEXT_MUTED = TXT2
TEXT_LABEL = TXT2
PRIME_GOLD = AMBER

_STARFIELD_SEED = 20240721

STAT_FIELDS = [
    ("csgoRank", "CS Level", ft.Icons.STAR_ROUNDED),
    ("medals", "Medals", ft.Icons.MILITARY_TECH_ROUNDED),
    ("inventoryValue", "Inventory", ft.Icons.DIAMOND_OUTLINED),
    ("earnedServiceMedal", "Service Medal", ft.Icons.WORKSPACE_PREMIUM_OUTLINED),
    ("hasRareItem", "Rare Items", ft.Icons.AUTO_AWESOME_OUTLINED),
]

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

LOGO_PATH = get_resource_path(os.path.join("assets", "Logo.png"))

# ============================================================
#  Data Parsing Helpers (NFA Logic)
# ============================================================
def parse_account_string(raw: str) -> tuple[str, str, dict]:
    raw = (raw or "").strip()
    username = ""
    token = ""
    stats: dict = {}

    if "----" in raw:
        parts = raw.split("----")
        if parts[0].startswith("ey"):
            token = parts[0]
            stats_parts = parts[1:]
        else:
            username = parts[0]
            token = parts[1]
            stats_parts = parts[2:]
        for part in stats_parts:
            if ":" in part:
                key, value = part.split(":", 1)
                stats[key] = value
    elif ":" in raw and not raw.startswith("ey"):
        username, token = raw.split(":", 1)
    else:
        token = raw

    return username, token, stats

def extract_token(raw: str) -> str:
    _, token, _ = parse_account_string(raw)
    return token

def format_stat_value(key: str, value: str) -> str:
    if not value: return "—"
    if key == "inventoryValue":
        try: return f"${float(value):.1f}" if "." in value else f"${value}"
        except ValueError: return f"${value}"
    if key == "rating":
        try: return f"{int(value):,}".replace(",", " ")
        except ValueError: return value
    if key == "earnedServiceMedal":
        return "Earned" if value.lower() in ("yes", "true", "1") else value
    return value

def stat_color(key: str, value: str) -> str:
    if key == "vacStatus" and value.lower() == "clean": return SUCCESS
    if key == "earnedServiceMedal" and value.lower() in ("yes", "true", "1"): return SUCCESS
    return TEXT_MAIN

def count_header_stats(accounts: list) -> tuple[int, int, int]:
    total = len(accounts)
    prime = sum(1 for a in accounts if a.get("stats", {}).get("primeStatus", "").lower() in ("yes", "true", "1"))
    on_cooldown = sum(1 for a in accounts if backend.cooldown_status(a)[0] and not backend.cooldown_status(a)[1])
    return total, prime, on_cooldown

def cooldown_display(acc: dict) -> tuple[str, str]:
    label, expired = backend.cooldown_status(acc)
    token_cd = acc.get("stats", {}).get("cooldown", "").lower()
    if label:
        if expired: return "Cooldown expired", SUCCESS
        return label, WARNING
    if token_cd in ("true", "1", "yes"): return "On cooldown", WARNING
    return "No cooldown", TEXT_MUTED

def resolve_display_name(acc: dict) -> str:
    persona = acc.get("persona") or acc.get("_persona_cache")
    if persona: return persona
    steam_id = acc.get("steamId") or acc.get("steam_id") or ""
    if steam_id:
        fetched = backend.get_steam_persona(steam_id)
        if fetched:
            acc["_persona_cache"] = fetched
            return fetched
    return acc.get("username", "Unknown")

# ============================================================
#  UI Shadows and Cosmic Background
# ============================================================
def _lift_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(blur_radius=16, spread_radius=0, color=ft.Colors.with_opacity(0.35, "#000000"), offset=ft.Offset(0, 4))

def _glow_shadow(blur: float = 28, spread: float = 1, opacity: float = 0.22, color: str = GREEN) -> ft.BoxShadow:
    return ft.BoxShadow(blur_radius=blur, spread_radius=spread, color=ft.Colors.with_opacity(opacity, color), offset=ft.Offset(0, 0))

def _panel_shadows() -> list[ft.BoxShadow]:
    return [_lift_shadow(), _glow_shadow()]

def _build_background() -> ft.Stack:
    rng = random.Random(_STARFIELD_SEED)
    layers: list[ft.Control] = [ft.Container(bgcolor=BG, expand=True)]
    nebulas = [(ft.Alignment.BOTTOM_RIGHT, GREEN, 0.08), (ft.Alignment.TOP_LEFT, NEBULA_PURPLE, 0.10), (ft.Alignment.TOP_RIGHT, NEBULA_PURPLE, 0.06)]
    for center, color, opacity in nebulas:
        layers.append(ft.Container(expand=True, gradient=ft.RadialGradient(colors=[ft.Colors.with_opacity(opacity, color), ft.Colors.TRANSPARENT], center=center, radius=1.3)))
    for _ in range(55):
        size = rng.choice([1, 1, 1, 2])
        opacity = round(rng.uniform(0.15, 0.5), 2)
        color = GREEN if rng.random() < 0.25 else "#ffffff"
        x, y = rng.uniform(-0.97, 0.97), rng.uniform(-0.97, 0.97)
        dot = ft.Container(width=size, height=size, border_radius=size, bgcolor=ft.Colors.with_opacity(opacity, color))
        layers.append(ft.Container(content=dot, alignment=ft.Alignment(x, y), expand=True))
    comets = [(ft.Alignment(-0.55, -0.75), -0.5, 150), (ft.Alignment(0.6, 0.35), -0.4, 110)]
    for center, angle, length in comets:
        streak = ft.Container(width=length, height=2, border_radius=2, rotate=angle, gradient=ft.LinearGradient(colors=[ft.Colors.TRANSPARENT, ft.Colors.with_opacity(0.15, GREEN)], begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT))
        layers.append(ft.Container(content=streak, alignment=center, expand=True))
    return ft.Stack(layers, expand=True)

def _stat_box(icon: str, label: str, value: str, value_color: str) -> ft.Container:
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=13, color=TXT2),
                ft.Column(
                    [
                        ft.Text(label.upper(), size=9, color=TXT2, weight=ft.FontWeight.W_600),
                        ft.Text(value, size=11, color=value_color, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ],
                    spacing=0, tight=True,
                ),
            ],
            spacing=6, tight=True,
        ),
        bgcolor=INPUT_BG,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        expand=True
    )

def build_stats_grid(stats: dict) -> ft.Control | None:
    tiles = []
    for key, label, icon in STAT_FIELDS:
        value = stats.get(key, "")
        if not value or value in ("0", "false", "False", "no", "No"):
            continue
        tiles.append(_stat_box(icon, label, format_stat_value(key, value), stat_color(key, value)))
    
    if not tiles: return None
    rows = []
    for i in range(0, len(tiles), 2):
        pair = tiles[i : i + 2]
        if len(pair) == 1:
            rows.append(ft.Row([pair[0], ft.Container(expand=True)], spacing=8))
        else:
            rows.append(ft.Row(pair, spacing=8))
    return ft.Column(rows, spacing=8, tight=True)

# ============================================================
#  Main Application
# ============================================================
async def main(page: ft.Page):
    page.title = APP_TITLE
    page.window.icon = LOGO_PATH
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 0
    page.scroll = None
    page.theme = ft.Theme(font_family="Segoe UI")
    
    page.window.width = 1200
    page.window.height = 820
    page.window.min_width = 800
    page.window.min_height = 600
    await page.window.center()

    loop = asyncio.get_running_loop()
    accounts = await loop.run_in_executor(None, backend.load_accounts)

    cooldown_text_refs: list[tuple[ft.Text, dict]] = []

    count_text = ft.Text("0", size=26, weight=ft.FontWeight.BOLD, color=TXT)
    stat_prime = ft.Text("0", size=26, weight=ft.FontWeight.BOLD, color=TXT)
    stat_cooldown = ft.Text("0", size=26, weight=ft.FontWeight.BOLD, color=TXT)

    cards_view = ft.Row(wrap=True, spacing=14, run_spacing=14, vertical_alignment=ft.CrossAxisAlignment.START)

    def set_status(message: str, color: str):
        status_text.value = message
        status_text.color = color
        page.update()
        def clearer():
            time.sleep(4)
            if status_text.value == message:
                status_text.value = ""
                page.update()
        page.run_thread(clearer)

    def update_header_stats():
        total, prime, cooldown = count_header_stats(accounts)
        count_text.value = str(total)
        stat_prime.value = str(prime)
        stat_cooldown.value = str(cooldown)

    def update_cooldown_labels(save_expired: bool = False) -> bool:
        changed = False
        expired_accounts = []
        for text_ctrl, acc in cooldown_text_refs:
            label, color = cooldown_display(acc)
            if text_ctrl.value != label or text_ctrl.color != color:
                text_ctrl.value = label
                text_ctrl.color = color
                changed = True
            cd_label, expired = backend.cooldown_status(acc)
            if expired and acc.get("note"):
                expired_accounts.append(acc)
        if save_expired and expired_accounts:
            for acc in expired_accounts:
                acc["note"] = ""
                acc["note_set_at"] = 0
            backend.save_accounts(accounts)
            changed = True
        old_cd = stat_cooldown.value
        update_header_stats()
        if stat_cooldown.value != old_cd:
            changed = True
        return changed

    async def cooldown_ticker():
        while True:
            await asyncio.sleep(1)
            if cooldown_text_refs:
                if update_cooldown_labels(save_expired=True):
                    page.update()

    input_field = ft.TextField(
        hint_text="Paste your Steam JWT token or full account string...",
        bgcolor=INPUT_BG,
        border_color=BORDER,
        border_radius=10,
        border_width=1,
        focused_border_color=GREEN,
        focused_border_width=2,
        color=TXT,
        hint_style=ft.TextStyle(color=TXT2),
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=12),
        height=46,
        expand=True,
    )
    input_glow_wrap = ft.Container(content=input_field, border_radius=10, expand=True, shadow=[ft.BoxShadow(blur_radius=0, spread_radius=0, color=ft.Colors.TRANSPARENT)])

    def _input_focus(e):
        input_glow_wrap.shadow = [_glow_shadow(blur=18, spread=1, opacity=0.35)]
        page.update()

    def _input_blur(e):
        input_glow_wrap.shadow = [ft.BoxShadow(blur_radius=0, spread_radius=0, color=ft.Colors.TRANSPARENT)]
        page.update()

    input_field.on_focus = _input_focus
    input_field.on_blur = _input_blur

    status_text = ft.Text("", size=12, color=TXT2)

    def do_add_account(e=None):
        raw = (input_field.value or "").strip()
        if not raw:
            set_status("Paste a token before adding an account.", RED_ERR)
            return

        username, token, stats = parse_account_string(raw)
        set_status("Verifying token...", TXT2)
        
        def worker():
            try:
                result = backend.check_token(token)
                if not result["steam_id"]:
                    set_status(f"Could not add account: {result['detail'] or result['status']}", RED_ERR)
                    return

                steam_id = result["steam_id"]
                persona = result.get("persona") or ""
                nonlocal username
                if not username:
                    username = steam_id

                existing = next((a for a in accounts if (a.get("steamId") or a.get("steam_id")) == steam_id), None)
                entry = {
                    "username": username,
                    "steamId": steam_id,
                    "token": token,
                    "persona": persona,
                    "note": existing.get("note", "") if existing else "",
                    "note_set_at": existing.get("note_set_at", 0) if existing else 0,
                    "stats": stats,
                }

                if existing: existing.update(entry)
                else: accounts.append(entry)

                backend.save_accounts(accounts)
                input_field.value = ""
                render_cards()
                set_status(f"Account '{persona or username}' saved.", GREEN)
            except Exception as e:
                import traceback
                traceback.print_exc()
                set_status(f"Crash during adding: {e}", RED_ERR)

        page.run_thread(worker)

    def do_check_token(e):
        token = extract_token(input_field.value or "")
        set_status("Verifying token...", TXT2)
        def worker():
            e.control.disabled = True
            e.control.update()
            try:
                result = backend.check_token(token)
                set_status(f"{result['status']}  -  {result['detail']}", SUCCESS if result["valid"] else DANGER)
            except Exception as ex:
                set_status(f"Crash during verification: {ex}", RED_ERR)
            time.sleep(1.5)
            e.control.disabled = False
            e.control.update()
        page.run_thread(worker)


    def build_account_card(index: int, acc: dict) -> ft.Container:
        display_name = resolve_display_name(acc)
        steam_id = acc.get("steamId") or acc.get("steam_id") or ""
        token = acc.get("token", "")
        stats = acc.get("stats", {})

        avatar_url = acc.get("_avatar_cache")
        if avatar_url is None and steam_id:
            avatar_url = backend.get_steam_avatar_url(steam_id) or ""
            acc["_avatar_cache"] = avatar_url

        avatar_inner = (
            ft.CircleAvatar(foreground_image_src=avatar_url, radius=30)
            if avatar_url else
            ft.CircleAvatar(content=ft.Text(display_name[:1].upper(), size=20, weight=ft.FontWeight.BOLD, color=GREEN), bgcolor=INPUT_BG, radius=30)
        )

        payload_ok = backend.parse_jwt(token) is not None
        
        avatar_stack = ft.Stack(
            [
                ft.Container(
                    content=avatar_inner,
                    width=56, height=56, border_radius=28,
                    border=ft.Border.all(2, ft.Colors.with_opacity(0.55, GREEN if payload_ok else RED_ERR)),
                    shadow=[ft.BoxShadow(blur_radius=0, spread_radius=0, color=ft.Colors.TRANSPARENT)],
                    alignment=ft.Alignment.CENTER,
                    animate=ft.Animation(150),
                ),
                ft.Container(
                    width=13, height=13, border_radius=7,
                    bgcolor=GREEN if payload_ok else RED_ERR,
                    border=ft.Border.all(2, CARD_BG),
                    right=0, bottom=0,
                ),
            ],
            width=56, height=56,
        )

        cd_label, cd_color = cooldown_display(acc)
        cooldown_text = ft.Text(cd_label, size=10, color=cd_color, weight=ft.FontWeight.W_600)
        cooldown_text_refs.append((cooldown_text, acc))

        is_prime = stats.get("primeStatus", "").lower() in ("yes", "true", "1")

        def on_login(e, acc=acc):
            try:
                backend.do_login(acc.get("username", ""), acc.get("token", ""))
                set_status(f"Signed in as '{resolve_display_name(acc)}'. Launching Steam...", GREEN)
            except Exception as ex:
                set_status(f"Login failed: {ex}", RED_ERR)

        def on_remove(e, acc=acc):
            try:
                sid = acc.get("steamId") or acc.get("steam_id") or ""
                if sid:
                    backend.add_to_blocklist(sid)
                accounts.remove(acc)
                backend.save_accounts(accounts)
                render_cards()
                set_status(f"Account '{resolve_display_name(acc)}' removed.", GREEN)
            except Exception as ex:
                set_status(f"Error removing account: {ex}", RED_ERR)

        def open_cooldown_dialog(e, acc=acc):
            def on_select(note_value):
                acc["note"] = note_value
                acc["note_set_at"] = time.time() if note_value else 0
                backend.save_accounts(accounts)
                render_cards()
                name = resolve_display_name(acc)
                set_status(f"Cooldown set for '{name}'." if note_value else f"Cooldown cleared for '{name}'.", GREEN)
                cd_dialog.open = False
                page.update()

            cd_dialog = ft.AlertDialog(
                modal=True,
                bgcolor=CARD_BG,
                shape=ft.RoundedRectangleBorder(radius=12),
                title=ft.Text("Set Cooldown", size=16, weight=ft.FontWeight.BOLD, color=TXT),
                content=ft.Column(
                    [
                        ft.ElevatedButton(content=ft.Text("Clear cooldown", color=TXT), width=220, style=ft.ButtonStyle(bgcolor=INPUT_BG, shape=ft.RoundedRectangleBorder(radius=8)), on_click=lambda e: on_select(""))
                    ] + [
                        ft.ElevatedButton(content=ft.Text(opt, color=TXT), width=220, style=ft.ButtonStyle(bgcolor=INPUT_BG, shape=ft.RoundedRectangleBorder(radius=8)), on_click=lambda e, opt=opt: on_select(opt)) 
                        for opt in backend.NOTE_OPTIONS
                    ],
                    spacing=8, tight=True,
                ),
                actions=[ft.OutlinedButton("Cancel", on_click=lambda e: (setattr(cd_dialog, 'open', False), page.update()), style=ft.ButtonStyle(color=RED_ERR, side=ft.BorderSide(1, RED_ERR)))],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.overlay.append(cd_dialog)
            cd_dialog.open = True
            page.update()

        def set_login_hover(is_hover):
            login_glow.shadow = [_glow_shadow(blur=15, spread=1, opacity=0.45)] if is_hover else [ft.BoxShadow(blur_radius=0, spread_radius=0, color=ft.Colors.TRANSPARENT)]
            login_glow.offset = ft.Offset(0, -0.05) if is_hover else ft.Offset(0, 0)
            login_glow.update()

        login_button_inner = ft.ElevatedButton("Log In", icon=ft.Icons.LOGIN, bgcolor=GREEN, color="#0a0d0a", on_click=on_login, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)))
        login_glow = ft.Container(
            content=login_button_inner,
            border_radius=8,
            shadow=[ft.BoxShadow(blur_radius=0, spread_radius=0, color=ft.Colors.TRANSPARENT)],
            offset=ft.Offset(0, 0),
            animate=ft.Animation(150),
            animate_offset=ft.Animation(150),
        )
        login_button = ft.GestureDetector(
            content=login_glow,
            on_enter=lambda e: set_login_hover(True),
            on_exit=lambda e: set_login_hover(False),
            expand=True,
        )


        def on_verify(e, acc=acc):
            set_status("Verifying token...", TXT2)
            def worker():
                e.control.disabled = True
                e.control.update()
                try:
                    result = backend.check_token(acc.get("token", ""))
                    set_status(f"{result['status']}  -  {result['detail']}", SUCCESS if result["valid"] else DANGER)
                except Exception as ex:
                    set_status(f"Crash during verification: {ex}", RED_ERR)
                time.sleep(1.5)
                e.control.disabled = False
                e.control.update()
            page.run_thread(worker)

        actions_row = ft.Row(
            [
                login_button,
                ft.IconButton(icon=ft.Icons.SECURITY_UPDATE_GOOD_OUTLINED, icon_color=TXT2, icon_size=17, tooltip="Verify Token", on_click=on_verify),
                ft.IconButton(icon=ft.Icons.SCHEDULE_ROUNDED, icon_color=TXT2, icon_size=17, tooltip="Set cooldown", on_click=open_cooldown_dialog),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=RED_ERR, icon_size=17, tooltip="Remove", on_click=on_remove),
            ],
            spacing=2,
        )

        stats_grid = build_stats_grid(stats) or ft.Container()
        stats_container = ft.Container(content=stats_grid, visible=False)

        def toggle_stats(e):
            stats_container.visible = not stats_container.visible
            e.control.icon = ft.Icons.KEYBOARD_ARROW_UP if stats_container.visible else ft.Icons.KEYBOARD_ARROW_DOWN
            card_content.update()

        stats_toggle_btn = ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_DOWN, icon_color=TXT2, icon_size=17, tooltip="Toggle details", on_click=toggle_stats)

        card_content = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            avatar_stack,
                            ft.Column(
                                [
                                    ft.Text(display_name, size=15, weight=ft.FontWeight.BOLD, color=TXT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Text(steam_id, size=11, color=TXT2, font_family="Consolas", selectable=True),
                                    ft.Row(
                                        [
                                            ft.Icon(ft.Icons.SCHEDULE_ROUNDED if cd_color == WARNING else ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED, size=12, color=cd_color),
                                            cooldown_text,
                                        ],
                                        spacing=3, tight=True
                                    )
                                ],
                                spacing=2, expand=True,
                            ),
                            stats_toggle_btn,
                        ],
                        spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    stats_container,
                    actions_row,
                ],
                spacing=12,
            ),
            width=340,
            bgcolor=CARD_BG,
            border=ft.Border.all(1, BORDER),
            border_radius=14,
            padding=16,
            shadow=[_lift_shadow()],
            animate=ft.Animation(150),
        )
        def set_card_hover(is_hover, c=card_content, av_container=avatar_stack.controls[0]):
            try:
                c.border = ft.Border.all(1, ft.Colors.with_opacity(0.7, GREEN)) if is_hover else ft.Border.all(1, BORDER)
                c.shadow = [_glow_shadow(blur=20, spread=2, opacity=0.25, color=GREEN)] if is_hover else [_lift_shadow()]
                av_container.shadow = [_glow_shadow(blur=15, spread=1, opacity=0.4, color=GREEN if payload_ok else RED_ERR)] if is_hover else [ft.BoxShadow(blur_radius=0, spread_radius=0, color=ft.Colors.TRANSPARENT)]
                c.update()
                av_container.update()
            except Exception as ex:
                with open("debug_hover.txt", "a") as f: f.write(f"Hover error: {ex}\n")

        card_gesture = ft.GestureDetector(
            content=card_content,
            on_enter=lambda e: set_card_hover(True),
            on_exit=lambda e: set_card_hover(False),
        )
                
        card_stack_children = [card_gesture]
        if is_prime:
            prime_badge = ft.Container(
                content=ft.Row([ft.Icon(ft.Icons.STAR_ROUNDED, size=12, color="#000000"), ft.Text("PRIME", size=10, weight=ft.FontWeight.BOLD, color="#000000")], spacing=2, tight=True),
                bgcolor=PRIME_GOLD,
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border_radius=ft.BorderRadius(top_left=0, top_right=14, bottom_left=8, bottom_right=0),
                top=0, right=0,
                shadow=ft.BoxShadow(blur_radius=8, spread_radius=0, color=ft.Colors.with_opacity(0.4, "#000000"), offset=ft.Offset(2, 2))
            )
            card_stack_children.append(prime_badge)

        return ft.Container(content=ft.Stack(card_stack_children), width=340, border_radius=14)

    def render_cards():
        cooldown_text_refs.clear()
        cards_view.controls.clear()
        if not accounts:
            cards_view.controls.append(ft.Text("No profiles yet — paste a Steam JWT token or account string above.", size=12, color=TXT2))
        else:
            for i, acc in enumerate(accounts):
                cards_view.controls.append(build_account_card(i, acc))
        update_header_stats()
        page.update()

    input_field.on_submit = do_add_account
    
    def set_add_hover(is_hover):
        add_glow.shadow = [_glow_shadow(blur=15, spread=1, opacity=0.45)] if is_hover else [ft.BoxShadow(blur_radius=0, spread_radius=0, color=ft.Colors.TRANSPARENT)]
        add_glow.offset = ft.Offset(0, -0.05) if is_hover else ft.Offset(0, 0)
        add_glow.update()

    add_button_inner = ft.ElevatedButton("Add", bgcolor=GREEN, color="#0a0d0a", on_click=do_add_account, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)))
    add_glow = ft.Container(
        content=add_button_inner, 
        shadow=[ft.BoxShadow(blur_radius=0, spread_radius=0, color=ft.Colors.TRANSPARENT)],
        offset=ft.Offset(0, 0),
        animate=ft.Animation(150), 
        animate_offset=ft.Animation(150)
    )
    add_btn_container = ft.GestureDetector(
        content=add_glow,
        on_enter=lambda e: set_add_hover(True),
        on_exit=lambda e: set_add_hover(False),
    )
    verify_button = ft.OutlinedButton("Verify", icon=ft.Icons.VERIFIED_USER_OUTLINED, on_click=do_check_token, style=ft.ButtonStyle(color=TXT, side=ft.BorderSide(1, BORDER)))

    logo = ft.Container(
        content=ft.Image(src=LOGO_PATH, width=52, height=52, fit=ft.BoxFit.COVER, border_radius=26),
        width=52, height=52, border_radius=26,
        shadow=ft.BoxShadow(blur_radius=15, spread_radius=1, color=ft.Colors.with_opacity(0.15, GREEN)),
    )

    def header_stat_block(label: str, value_control: ft.Text) -> ft.Column:
        return ft.Column([value_control, ft.Text(label, size=10, color=TXT2, weight=ft.FontWeight.W_600)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=1, tight=True)

    header = ft.Container(
        content=ft.Row(
            [
                logo,
                ft.Column(
                    [
                        ft.Text(APP_TITLE, size=22, weight=ft.FontWeight.BOLD, color=TITLE_TXT),
                        ft.Text("Steam Account Manager", size=12, color=TXT2),
                    ],
                    spacing=0,
                ),
                ft.Container(expand=True),
                ft.Row(
                    [
                        header_stat_block("ACCOUNTS", count_text),
                        ft.Container(width=28),
                        header_stat_block("PRIME", stat_prime),
                        ft.Container(width=28),
                        header_stat_block("ON COOLDOWN", stat_cooldown),
                    ],
                ),
            ],
            spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=22, vertical=20),
    )

    input_row = ft.Container(
        content=ft.Row([input_glow_wrap, verify_button, add_btn_container], spacing=10),
        padding=ft.Padding.symmetric(horizontal=22, vertical=16),
        bgcolor=PANEL, border=ft.Border.all(1, BORDER), shadow=None,
    )

    status_row = ft.Container(content=status_text, padding=ft.Padding.only(left=22, top=10, bottom=10))

    cards_scroll = ft.Column([ft.Container(content=cards_view, padding=22)], expand=True, scroll=ft.ScrollMode.AUTO)

    foreground = ft.Column([header, input_row, status_row, cards_scroll], spacing=0, expand=True)

    discord_btn = ft.Container(
        content=ft.IconButton(
            content=ft.Image(src="discord.png", width=24, height=24),
            on_click=lambda _: page.launch_url("https://discord.gg/larpsense"),
            tooltip="Join our Discord Server",
        ),
        bottom=15,
        right=20,
    )

    root = ft.Stack([_build_background(), foreground, discord_btn], expand=True)

    page.add(root)
    render_cards()
    
    page.run_task(cooldown_ticker)

if __name__ == "__main__":
    ft.app(target=main, assets_dir=get_resource_path("assets"))