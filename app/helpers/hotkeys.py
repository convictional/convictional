from markupsafe import Markup


def format_kbd_hint(kbd: str) -> Markup:
    """
    Format keyboard shortcut for display in tooltips.

    Handles three types of shortcuts:
    - Single keys: "e" -> <kbd>e</kbd>
    - Sequential keys: "g i" -> <kbd>g</kbd><kbd>i</kbd>
    - Modifier combos: "Meta+k" -> <kbd>⌘K</kbd>

    Args:
        kbd: Keyboard shortcut string

    Returns:
        Markup object containing formatted HTML kbd elements
    """
    kbd_class = "kbd kbd-xs bg-base-400 border-base-500 text-base-900"
    if " " in kbd and "+" not in kbd:
        keys = kbd.split(" ")
        kbd_elements = [f'<kbd class="{kbd_class}">{_format_key_display(key)}</kbd>' for key in keys]
        return Markup("".join(kbd_elements))
    elif "+" in kbd:
        formatted = _format_modifier_combo(kbd)
        return Markup(f'<kbd class="{kbd_class}">{formatted}</kbd>')
    else:
        return Markup(f'<kbd class="{kbd_class}">{_format_key_display(kbd)}</kbd>')


def _format_modifier_combo(kbd: str) -> str:
    """Convert modifier+key combinations to symbolic format."""
    parts = kbd.split("+")
    output = []
    for part in parts:
        match part:
            case "Meta":
                output.append("⌘")
            case "Ctrl":
                output.append("^")
            case "Shift":
                output.append("⇧")
            case "Alt":
                output.append("⌥")
            case _:
                output.append(_format_key_display(part))
    return " ".join(output)


def _format_key_display(key: str) -> str:
    """Convert special key names to symbols."""
    special_keys = {
        "ArrowUp": "↑",
        "ArrowDown": "↓",
        "ArrowLeft": "←",
        "ArrowRight": "→",
        "Enter": "↵",
        "Escape": "Esc",
        "Space": "␣",
    }
    return special_keys.get(key, key)
