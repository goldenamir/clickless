"""macOS virtual keycode helpers for Clickless."""

MAC_KEY_NAMES = {
    'A': 0,
    'S': 1,
    'D': 2,
    'F': 3,
    'H': 4,
    'G': 5,
    'Z': 6,
    'X': 7,
    'C': 8,
    'V': 9,
    'B': 11,
    'Q': 12,
    'W': 13,
    'E': 14,
    'R': 15,
    'Y': 16,
    'T': 17,
    '1': 18,
    '2': 19,
    '3': 20,
    '4': 21,
    '6': 22,
    '5': 23,
    '=': 24,
    '9': 25,
    '7': 26,
    '-': 27,
    '8': 28,
    '0': 29,
    ']': 30,
    'O': 31,
    'U': 32,
    '[': 33,
    'I': 34,
    'P': 35,
    'L': 37,
    'J': 38,
    "'": 39,
    'K': 40,
    ';': 41,
    '\\': 42,
    ',': 43,
    '/': 44,
    'N': 45,
    'M': 46,
    '.': 47,
    'TAB': 48,
    'SPACE': 49,
    '`': 50,
    'BACKSPACE': 51,
    'ESCAPE': 53,
    'CMDLEFT': 55,
    'COMMANDLEFT': 55,
    'METALEFT': 55,
    'SHIFTRIGHT': 60,
    'SHIFTLEFT': 56,
    'CAPSLOCK': 57,
    'ALTLEFT': 58,
    'OPTIONLEFT': 58,
    'CONTROLLEFT': 59,
    'CTRLLEFT': 59,
    'ALTRIGHT': 61,
    'OPTIONRIGHT': 61,
    'CONTROLRIGHT': 62,
    'CTRLRIGHT': 62,
    'FUNCTION': 63,
    'FN': 63,
    'GLOBE': 63,
    'CMDRIGHT': 54,
    'COMMANDRIGHT': 54,
    'METARIGHT': 54,
    'LEFT': 123,
    'RIGHT': 124,
    'DOWN': 125,
    'UP': 126,
}

ALIASES = {
    'SHIFT': MAC_KEY_NAMES['SHIFTLEFT'],
    'SHIFT_L': MAC_KEY_NAMES['SHIFTLEFT'],
    'SHIFT_R': MAC_KEY_NAMES['SHIFTRIGHT'],
    'CTRL': MAC_KEY_NAMES['CONTROLLEFT'],
    'CONTROL': MAC_KEY_NAMES['CONTROLLEFT'],
    'CTRL_L': MAC_KEY_NAMES['CONTROLLEFT'],
    'CTRL_R': MAC_KEY_NAMES['CONTROLRIGHT'],
    'ALT': MAC_KEY_NAMES['ALTLEFT'],
    'OPTION': MAC_KEY_NAMES['OPTIONLEFT'],
    'ALT_L': MAC_KEY_NAMES['ALTLEFT'],
    'ALT_R': MAC_KEY_NAMES['ALTRIGHT'],
    'CMD': MAC_KEY_NAMES['COMMANDLEFT'],
    'COMMAND': MAC_KEY_NAMES['COMMANDLEFT'],
    'META': MAC_KEY_NAMES['COMMANDLEFT'],
    'WIN': MAC_KEY_NAMES['COMMANDLEFT'],
    'SEMICOLON': MAC_KEY_NAMES[';'],
    'COMMA': MAC_KEY_NAMES[','],
    'DOT': MAC_KEY_NAMES['.'],
    'PERIOD': MAC_KEY_NAMES['.'],
    'SLASH': MAC_KEY_NAMES['/'],
    'ESC': MAC_KEY_NAMES['ESCAPE'],
    'BACK_SPACE': MAC_KEY_NAMES['BACKSPACE'],
}
MAC_KEY_NAMES.update(ALIASES)

MAC_CODE_NAMES = {}
for name, code in MAC_KEY_NAMES.items():
    if code not in MAC_CODE_NAMES or len(name) < len(MAC_CODE_NAMES[code]):
        MAC_CODE_NAMES[code] = name

LEFT_SHIFT = MAC_KEY_NAMES['SHIFTLEFT']
RIGHT_SHIFT = MAC_KEY_NAMES['SHIFTRIGHT']
LEFT_CTRL = MAC_KEY_NAMES['CONTROLLEFT']
RIGHT_CTRL = MAC_KEY_NAMES['CONTROLRIGHT']
LEFT_ALT = MAC_KEY_NAMES['ALTLEFT']
RIGHT_ALT = MAC_KEY_NAMES['ALTRIGHT']
FUNCTION = MAC_KEY_NAMES['FUNCTION']
SPACE = MAC_KEY_NAMES['SPACE']
ESCAPE = MAC_KEY_NAMES['ESCAPE']
BACKSPACE = MAC_KEY_NAMES['BACKSPACE']
TAB = MAC_KEY_NAMES['TAB']


def parse_hotkey_str(s):
    if not s or not str(s).strip():
        return None
    value = str(s).strip()
    is_tap = False
    is_hold = False
    is_double_tap = False
    parts = value.split()
    if len(parts) >= 2:
        if parts[-1].lower() == 'tap':
            is_tap = True
            value = ' '.join(parts[:-1])
        elif parts[-1].lower() == 'hold':
            is_hold = True
            value = ' '.join(parts[:-1])
        elif len(parts) >= 3 and parts[-1].lower() == 'tap' and parts[-2].lower() == 'double':
            is_double_tap = True
            value = ' '.join(parts[:-2])

    keys = [k.strip() for k in value.split('+') if k.strip()]
    if not keys:
        return None

    main_key = keys[-1].upper()
    modifiers = set()
    for modifier in keys[:-1]:
        code = MAC_KEY_NAMES.get(modifier.upper())
        if code is not None:
            modifiers.add(code)

    key_code = MAC_KEY_NAMES.get(main_key)
    return {
        'code': key_code,
        'modifiers': modifiers,
        'is_tap': is_tap,
        'is_hold': is_hold,
        'is_double_tap': is_double_tap,
    }


def code_to_grid_key(code):
    name = MAC_CODE_NAMES.get(code, '')
    if len(name) == 1:
        return name
    return {
        'SEMICOLON': ';',
        'COMMA': ',',
        'DOT': '.',
        'PERIOD': '.',
        'SLASH': '/',
    }.get(name)
