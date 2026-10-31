"""
Request A Bet (RAB): wagers sent from the website, shown pink in Betty's unedited list. Betty shows the request in
typed text, so it is read here without the slip reader:

    RAB request received: 31-10-2026 9:08:47
    Email:
    £3.00 Singles
    The Gardens 09:11 6. Nuts Then Bolts  @ 85/40)

and the customer's account notes ("NO BOG - £100 max stake") are read against it with the shorthand dictionary in
rab_notes_dictionary.json (re-read when the file is edited). A note the dictionary doesn't cover means the request
is skipped: an account restriction is never guessed.

No screen, no keys: betty_companion.py reads the screen and calls these.
"""
import json
import os
import re

NOTES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rab_notes_dictionary.json")

# What a dictionary rule can mean. 'max_stake' and 'max_odds' take the amount / odds the pattern captured.
MEANINGS = {
    'refuse_all': "no request a bet accepted on this account",
    'no_bog': "no best odds guaranteed (the bet goes on without 'g')",
    'max_stake': "the wager's total stake can't be more than this",
    'no_each_way': "win only: no each way",
    'sp_only': "starting price only: no price taken",
    'no_greyhounds': "no greyhound bets",
    'no_horses': "no horse racing bets",
    'singles_only': "singles only: no multiples or full covers",
    'no_forecasts': "no forecasts or tricasts",
    'uk_ire_only': "UK and Irish racing only",
    'max_odds': "no selection at a price longer than this",
    'ignore': "not a restriction (information only)",
}
AMOUNT = r"£?\s*(\d+(?:\.\d{1,2})?)\s*(k|p)?"
ODDS = r"(\d+\s*[/-]\s*\d+|\d+(?:\.\d+)?|evens|evs)"

_cache: dict = {'mtime': None, 'rules': []}


class NotesDictionaryError(Exception):
    """rab_notes_dictionary.json is missing or unreadable: no RAB is done (its notes can't be checked)."""


def notes_rules() -> list[tuple[re.Pattern, str, str]]:
    """The dictionary's rules as (compiled pattern, meaning, example), read again when the file changes."""
    try:
        mtime = os.path.getmtime(NOTES_FILE)
    except OSError as e:
        raise NotesDictionaryError(f"the RAB notes dictionary is missing ({NOTES_FILE})") from e
    if mtime == _cache['mtime']:
        return _cache['rules']
    try:
        with open(NOTES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        rules = []
        for rule in data['rules']:
            if rule['means'] not in MEANINGS:
                raise ValueError(f"unknown meaning '{rule['means']}' (one of: {', '.join(MEANINGS)})")
            pattern = rule['match'].replace('{amount}', AMOUNT).replace('{odds}', ODDS)
            rules.append((re.compile(rf"(?:{pattern})", re.IGNORECASE), rule['means'], rule.get('example', '')))
    except (OSError, ValueError, KeyError, TypeError, re.error) as e:
        raise NotesDictionaryError(f"the RAB notes dictionary can't be read: {e}") from e
    _cache.update(mtime=mtime, rules=rules)
    return rules


def amount_pence(number: str, suffix: str | None = None) -> int:
    """'100' -> 10000, '1.50' -> 150, '50' with 'p' -> 50, '1' with 'k' -> 100000."""
    suffix = (suffix or '').lower()
    if suffix == 'p':
        return round(float(number))
    return round(float(number) * (100000 if suffix == 'k' else 100))


def decimal_odds(price: str) -> float | None:
    """'85/40' or '85-40' -> 3.125, '5.00' -> 5.0, 'Evs' -> 2.0; None for SP or anything unread."""
    p = str(price or '').strip().lower()
    if p in ('evs', 'evens', 'ev', 'e'):
        return 2.0
    m = re.fullmatch(r'(\d+)\s*[/-]\s*(\d+)', p)
    if m and int(m.group(2)):
        return 1 + int(m.group(1)) / int(m.group(2))
    m = re.fullmatch(r'\d+(?:\.\d+)?', p)
    if m and float(p) > 1:
        return float(p)
    return None


def _clauses(notes: str) -> list[str]:
    """A note split where staff separate restrictions: ' - ', ',', ';', ' / ', '|', a full stop, a new line. 'NO E/W'
    and '£1.50' stay whole."""
    text = notes.replace('–', '-').replace('—', '-')
    parts = re.split(r'\s+-\s+|\s*[,;|\n]\s*|\s+/\s+|\.(?=\s|$)', text)
    return [c for c in (re.sub(r'\s+', ' ', p).strip(" -:*'\"") for p in parts) if c]


def read_notes(notes: str) -> dict:
    """
    What an account's notes allow. {'clauses': [(clause, meaning, value)], 'unknown': [clauses no rule covers],
    'no_bog', 'max_stake_pence', 'max_odds', and a True for every other meaning found}. An empty note allows anything.
    """
    out: dict = {'clauses': [], 'unknown': [], 'no_bog': False, 'max_stake_pence': None, 'max_odds': None}
    rules = notes_rules()
    for clause in _clauses(notes or ''):
        for pattern, means, _ in rules:
            m = pattern.fullmatch(clause)
            if not m:
                continue
            value = None
            groups = [g for g in m.groups() if g is not None]
            if means == 'max_stake':
                nums = [g for g in groups if re.fullmatch(r'\d+(?:\.\d+)?', g)]
                suffix = next((g for g in groups if g.lower() in ('k', 'p')), None)
                if not nums:
                    continue
                value = amount_pence(nums[0], suffix)
                old = out['max_stake_pence']
                out['max_stake_pence'] = value if old is None else min(old, value)
            elif means == 'max_odds':
                odds = next((decimal_odds(g) for g in groups if decimal_odds(g)), None)
                if odds is None:
                    continue
                value = odds
                out['max_odds'] = odds if out['max_odds'] is None else min(out['max_odds'], odds)
            elif means != 'ignore':
                out[means] = True
            out['clauses'].append((clause, means, value))
            break
        else:
            out['unknown'].append(clause)
    return out


def describe_notes(allowed: dict) -> str:
    """One line for the console: what each clause was taken to mean."""
    parts = []
    for clause, means, value in allowed['clauses']:
        if means == 'max_stake':
            parts.append(f"'{clause}' = max stake £{value / 100:.2f}")
        elif means == 'max_odds':
            parts.append(f"'{clause}' = max odds {value:.2f} (decimal)")
        else:
            parts.append(f"'{clause}' = {MEANINGS[means]}")
    parts += [f"'{c}' = NOT UNDERSTOOD" for c in allowed['unknown']]
    return "; ".join(parts) or "no notes"


def notes_breaches(allowed: dict, total_pence: int, bets: list[dict], selections: list[dict]) -> list[str]:
    """
    Every way the request breaks the account's notes ([] = allowed). `bets`: {'bet_type' (canonical), 'each_way'};
    `selections`: {'name', 'category' (domestic / international / greyhound / virtual), 'uk_ire' (bool),
    'price' (as requested; SP or empty for none)}. 'no_bog' is never a breach: the bet goes on without the guarantee.
    """
    out = [f"the notes say '{c}', which the RAB dictionary doesn't cover" for c in allowed['unknown']]
    if allowed.get('refuse_all'):
        out.append("the notes refuse request a bet on this account")
    cap = allowed.get('max_stake_pence')
    if cap is not None and total_pence > cap:
        out.append(f"£{total_pence / 100:.2f} staked, over the £{cap / 100:.2f} max stake")
    if allowed.get('no_each_way') and any(b.get('each_way') for b in bets):
        out.append("each way, but the account is win only")
    if allowed.get('singles_only') and any(b.get('bet_type') != 'single' for b in bets):
        out.append("a multiple, but the account is singles only")
    if allowed.get('no_forecasts') and any(re.search(r'forecast|tricast', str(b.get('bet_type'))) for b in bets):
        out.append("a forecast / tricast, which the account can't have")
    for s in selections:
        took_price = decimal_odds(s.get('price')) is not None
        if allowed.get('sp_only') and took_price:
            out.append(f"{s['name']}: a price ({s['price']}) taken, but the account is SP only")
        if allowed.get('no_greyhounds') and s.get('category') == 'greyhound':
            out.append(f"{s['name']}: a greyhound, which the account can't have")
        if allowed.get('no_horses') and s.get('category') != 'greyhound':
            out.append(f"{s['name']}: horse racing, which the account can't have")
        if allowed.get('uk_ire_only') and not s.get('uk_ire'):
            out.append(f"{s['name']}: not UK / Irish racing")
        cap_odds = allowed.get('max_odds')
        if cap_odds is not None:
            odds = decimal_odds(s.get('price'))
            if odds is None:
                out.append(f"{s['name']}: SP, so its odds can't be held to the max odds")
            elif odds > cap_odds + 1e-6:
                out.append(f"{s['name']}: {s['price']} is longer than the max odds")
    return out


# --- The request text ---
BET_LINE = re.compile(r"^\W{0,2}[£Eef]?\s*(\d+\.\d{2})\s+([A-Za-z].*)$")
SELECTION = re.compile(r"(?P<meeting>[A-Za-z][A-Za-z'&.\- ]*?)\s+(?P<time>\d{1,2}:\d{2})\s+(?P<number>\d{1,2})\s*\.\s*"
                       r"(?P<name>[^@]+?)\s*@\s*(?P<price>[^)@]+?)\s*\)")
EACH_WAY = re.compile(r"\b(?:each\s*way|e\s*/\s*w|ew)\b", re.IGNORECASE)
WIN_WORD = re.compile(r"\bwin\b", re.IGNORECASE)
# Words that only a sports request has (racing requests are "Meeting HH:MM N. Name @ price)")
SPORT_WORDS = re.compile(r"\b(?:v|vs|football|match|correct score|btts|both teams|over|under|goals?|corners?|cards?|"
                         r"handicap|half time|full time|ht|ft|draw|scorer|tennis|golf|darts|snooker|cricket|rugby|"
                         r"nfl|nba|premier|league|cup)\b", re.IGNORECASE)


def parse_request(text: str) -> dict:
    """
    The request as Betty shows it. {'ok', 'reason', 'sport', 'bets': [{'stake_pence', 'words', 'each_way',
    'description'}], 'selections': [{'meeting', 'time', 'number', 'name', 'price'}]}. Every bet line covers every
    selection. Anything left over that isn't a bet line or a racing selection makes it unread (ok False): a sports
    request, or a format not seen yet.
    """
    out: dict = {'ok': False, 'reason': '', 'sport': False, 'bets': [], 'selections': []}
    lines = [re.sub(r'\s+', ' ', ln).strip() for ln in str(text or '').splitlines()]
    lines = [ln for ln in lines if ln]
    rest = []
    for ln in lines:
        if re.match(r'^(?:RAB request|Email\b)', ln, re.IGNORECASE):
            continue
        m = BET_LINE.match(ln)
        if m and not out['selections'] and not rest and not SELECTION.search(ln):
            words = m.group(2).strip()
            out['bets'].append({'stake_pence': amount_pence(m.group(1)), 'words': words,
                                'each_way': bool(EACH_WAY.search(words)) and not WIN_WORD.search(words),
                                'description': ln})
            continue
        rest.append(ln)
    joined = " ".join(rest)  # a selection Betty wrapped onto two lines is one again
    left = joined
    for m in SELECTION.finditer(joined):
        out['selections'].append({'meeting': m.group('meeting').strip(), 'time': m.group('time'),
                                  'number': int(m.group('number')), 'name': m.group('name').strip(),
                                  'price': m.group('price').strip()})
        left = left.replace(m.group(0), ' ', 1)
    left = left.strip()
    # Sports words count only in text that isn't a racing selection: horses are called 'Over The Moon' and 'Gold Cup'
    if not out['bets']:
        out['reason'] = "no stake and bet type line could be read"
    elif not out['selections']:
        out['sport'] = bool(joined)
        out['reason'] = "no racing selection could be read" + (" (a sports bet?)" if out['sport'] else "")
    elif left:
        out['sport'] = bool(SPORT_WORDS.search(left))
        out['reason'] = f"part of the request isn't a racing selection: '{left}'"
    else:
        out['ok'] = True
    return out


def same_request(a: dict, b: dict) -> bool:
    """Two readings of one request agree (View Wagers and the slip panel in the bet edit): stakes, bet words, and each
    selection's time, number and price; meeting and name by letters, since a wrapped line may split a word."""
    def letters(s: str) -> str:
        return re.sub(r'[^a-z]', '', str(s).lower())
    if [(x['stake_pence'], letters(x['words'])) for x in a['bets']] != \
       [(x['stake_pence'], letters(x['words'])) for x in b['bets']]:
        return False
    key = lambda s: (letters(s['meeting']), s['time'], s['number'], letters(s['name']), s['price'].replace(' ', ''))
    return [key(s) for s in a['selections']] == [key(s) for s in b['selections']]
