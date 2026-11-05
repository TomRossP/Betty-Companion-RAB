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
from difflib import SequenceMatcher

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
    'no_sports': "racing only: no sports bets",
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
        is_sport = s.get('category') == 'sport'
        if allowed.get('no_horses') and s.get('category') != 'greyhound' and not is_sport:
            out.append(f"{s['name']}: horse racing, which the account can't have")
        if allowed.get('uk_ire_only') and not is_sport and not s.get('uk_ire'):
            out.append(f"{s['name']}: not UK / Irish racing")
        if is_sport and (allowed.get('no_sports') or any(means in ('no_greyhounds', 'no_horses') and 'only' in clause.lower()
                                                         for clause, means, _ in allowed['clauses'])):
            out.append(f"{s['name']}: a sports bet, which the account can't have")
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
# A price as the website writes it. Only the request's last selection ends in ')' (user's screenshots, 5 Nov), which is
# how the end of a request too long for its panel is known
PRICE = r"\d+\s*/\s*\d+|\d+\.\d+|evens|evs|sp"
SELECTION = re.compile(r"(?P<meeting>[A-Za-z][A-Za-z'&.\- ]*?)\s+(?P<time>\d{1,2}:\d{2})\s+(?P<number>\d{1,2})\s*\.\s*"
                       rf"(?P<name>[^@]+?)\s*@\s*(?P<price>{PRICE})\s*(?P<end>\))?", re.IGNORECASE)
# A sports selection: 'AGF Aarhus v Braga Goals Over Under Over 2.5 @ 19/20'. Event, market and result with nothing between
# them, always in that order (user, 5 Nov): master_index.split_line tells them apart
SPORT_SELECTION = re.compile(rf"(?P<text>\S.*?)\s*[@©®]\s*(?P<price>{PRICE})\s*(?P<end>\))?", re.IGNORECASE)
EACH_WAY = re.compile(r"\b(?:each\s*way|e\s*/\s*w|ew)\b", re.IGNORECASE)
WIN_WORD = re.compile(r"\bwin\b", re.IGNORECASE)
# Words that only a sports request has (racing requests are "Meeting HH:MM N. Name @ price)")
SPORT_WORDS = re.compile(r"\b(?:v|vs|football|match|correct score|btts|both teams|over|under|goals?|corners?|cards?|"
                         r"handicap|half time|full time|ht|ft|draw|scorer|tennis|golf|darts|snooker|cricket|rugby|"
                         r"nfl|nba|premier|league|cup)\b", re.IGNORECASE)


def parse_request(text: str) -> dict:
    """
    The request as Betty shows it. {'ok', 'reason', 'sport', 'ended', 'bets': [{'stake_pence', 'words', 'each_way',
    'description'}], 'selections': [{'meeting', 'time', 'number', 'name', 'price'}], 'sports': [{'text', 'price'}]}.
    Every bet line covers every selection. 'ended': the request's closing ')' has been read; a long one goes on below
    its panel. Anything left over that isn't a bet line or a racing selection makes it unread (ok False). 'ok' is for a
    whole racing request; a sports one has 'sport', its 'sports', and 'ended'.
    """
    out: dict = {'ok': False, 'reason': '', 'sport': False, 'ended': False, 'bets': [], 'selections': [], 'sports': []}
    lines = [re.sub(r'\s+', ' ', ln).strip() for ln in str(text or '').splitlines()]
    lines = [ln for ln in lines if ln]
    rest = []
    for ln in lines:
        if re.match(r'^(?:RAB request|Email\b|Various Events)', ln, re.IGNORECASE):
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
    last = None
    for m in SELECTION.finditer(joined):
        out['selections'].append({'meeting': m.group('meeting').strip(), 'time': m.group('time'),
                                  'number': int(m.group('number')), 'name': m.group('name').strip(),
                                  'price': m.group('price').strip()})
        left = left.replace(m.group(0), ' ', 1)
        last = m
    left = left.strip()
    if out['selections']:
        out['ended'] = bool(last.group('end'))
    # Sports words count only in text that isn't a racing selection: horses are called 'Over The Moon' and 'Gold Cup'
    if not out['bets']:
        out['reason'] = "no stake and bet type line could be read"
    elif not out['selections']:
        out['sport'] = bool(joined)
        out['reason'] = "no racing selection could be read" + (" (a sports bet?)" if out['sport'] else "")
        blocks = list(SPORT_SELECTION.finditer(joined))
        out['sports'] = [{'text': " ".join(m.group('text').split()), 'price': re.sub(r'\s', '', m.group('price'))}
                         for m in blocks]
        out['ended'] = bool(blocks) and bool(blocks[-1].group('end'))
    elif left:
        out['sport'] = bool(SPORT_WORDS.search(left))
        out['reason'] = f"part of the request isn't a racing selection: '{left}'"
    elif not out['ended']:
        out['reason'] = "the end of the request hasn't been read"
    else:
        out['ok'] = True
    return out


def bet_words(words: str) -> str:
    """A request's bet line as the bet type reader knows it: Betty's own 'Acc On All Selns' is an accumulator."""
    return re.sub(r'\bacc\s*on\s*all\s*sel\w*', 'accumulator', str(words).lower())


def merge_scrolled(lines: list[str], more: list[str]) -> list[str] | None:
    """
    A request read in two scrolls of its panel made one: `more` starts somewhere in `lines`, and its reading of the lines
    both hold is kept, clear of the View Note icon. A line that doesn't agree is allowed once in a longer overlap. None
    when they don't overlap, so nothing is ever silently left out.
    """
    def alike(a: str, b: str) -> bool:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.8
    for k in range(min(len(lines), len(more)), 0, -1):
        agree = sum(alike(a, b) for a, b in zip(lines[-k:], more[:k]))
        if agree >= max(1, k - 1):
            return lines[:-k] + more
    return None


def same_request(a: dict, b: dict) -> bool:
    """Two readings of one request agree (`a` the slip panel in the bet edit, `b` View Wagers): stakes, bet words, and each
    selection's time, number and price; meeting and name by letters, since a wrapped line may split a word. A sports line
    is its text, allowing for a slip, and its price. `a` may not have ended: then what it shows must be how `b` starts."""
    def letters(s: str) -> str:
        return re.sub(r'[^a-z]', '', str(s).lower())
    def same_sport(x: dict, y: dict) -> bool:
        return x['price'] == y['price'] and SequenceMatcher(None, x['text'].lower(), y['text'].lower()).ratio() >= 0.9
    if b['sports'] and not a['bets']:  # scrolled down from View Wagers: its first line may be the end of a selection
        shows = a['sports'][1:]
        return bool(shows) and any(all(same_sport(x, y) for x, y in zip(shows, b['sports'][i:]))
                                   for i in range(len(b['sports']) - len(shows) + 1))
    if not a['bets'] or [(x['stake_pence'], letters(x['words'])) for x in a['bets']] != \
       [(x['stake_pence'], letters(x['words'])) for x in b['bets']]:
        return False
    if b['sports']:
        if not a['sports'] or len(a['sports']) > len(b['sports']) or (a['ended'] and len(a['sports']) != len(b['sports'])):
            return False
        return all(same_sport(x, y) for x, y in zip(a['sports'], b['sports']))
    key = lambda s: (letters(s['meeting']), s['time'], s['number'], letters(s['name']), s['price'].replace(' ', ''))
    seen = [key(s) for s in a['selections']]
    return bool(seen) and seen == [key(s) for s in b['selections']][:len(seen) if not a['ended'] else None]
