"""Round-table ASCII renderer: the 'graphic' shell interface.

Seats are placed on an ellipse around a central table; the human always
sits bottom-center. The screen is redrawn after every action (scrolling
frames when output is piped). Input handling is shared with the classic
text interface in cli.py.
"""
import math
import sys
import time
from collections import deque

from .ai import BotAgent
from .cards import card_str, cards_str
from .cli import POSITION_NAMES, describe_action, human_turn
from .engine import Hand
from .evaluator import category_name

W, H = 76, 19                       # canvas size
CX, CY, RX, RY = 37, 9, 29, 7       # seat ellipse
TX, TY, TW, TH = 24, 6, 29, 7       # central table box
SEAT_W, SEAT_H = 13, 5
STREET_SHORT = {0: "PREFLOP", 3: "FLOP", 4: "TURN", 5: "RIVER"}


class Canvas:
    def __init__(self):
        self.grid = [[" "] * W for _ in range(H)]

    def put(self, x, y, text):
        if 0 <= y < H:
            for i, ch in enumerate(text):
                if 0 <= x + i < W:
                    self.grid[y][x + i] = ch

    def put_center(self, x0, width, y, text):
        self.put(x0 + max(0, (width - len(text)) // 2), y, text)

    def box(self, x0, y0, w, h, rounded=False):
        tl, tr, bl, br = ("╭", "╮", "╰", "╯") if rounded else ("┌", "┐", "└", "┘")
        self.put(x0, y0, tl + "─" * (w - 2) + tr)
        self.put(x0, y0 + h - 1, bl + "─" * (w - 2) + br)
        for y in range(y0 + 1, y0 + h - 1):
            self.put(x0, y, "│")
            self.put(x0 + w - 1, y, "│")

    def render(self):
        return "\n".join("".join(row).rstrip() for row in self.grid)


def seat_xy(rel, n):
    # human at bottom; the next player to act sits to the human's left,
    # which is screen-right — so seats advance counterclockwise in angle
    ang = math.pi / 2 - rel * 2 * math.pi / n
    return round(CX + RX * math.cos(ang)), round(CY + RY * math.sin(ang))


def draw(hand, names, human_pos, board_limit=None):
    cv = Canvas()
    shown = hand.board if board_limit is None else hand.board[:board_limit]
    label = STREET_SHORT[len(shown)]

    cv.box(TX, TY, TW, TH, rounded=True)
    cv.put_center(TX + 1, TW - 2, TY + 1, label)
    slots = "".join(
        f"[{card_str(shown[i]) if i < len(shown) else '  '}]" for i in range(5)
    )
    cv.put_center(TX + 1, TW - 2, TY + 3, slots)
    cv.put_center(TX + 1, TW - 2, TY + 4, f"Pot: {hand.pot()}")

    reveal = getattr(hand, "showdown_scores", None) if hand.terminal else None
    for s in range(hand.n):
        x, y = seat_xy((s - human_pos) % hand.n, hand.n)
        x0, y0 = x - SEAT_W // 2, y - SEAT_H // 2
        cv.box(x0, y0, SEAT_W, SEAT_H)
        marker = "►" if (not hand.terminal and hand.to_act == s) else " "
        cv.put(x0 + 1, y0 + 1, (marker + names[s])[: SEAT_W - 2])

        bet = hand.street_contrib[s]
        if hand.folded[s]:
            money = "folded"
        elif hand.allin[s]:
            money = f"ALL-IN {hand.contrib[s]}"
        else:
            money = f"{hand.stacks[s]} bet {bet}" if bet else f"{hand.stacks[s]}"
        cv.put(x0 + 1, y0 + 2, f" {money}"[: SEAT_W - 2])

        if s == human_pos or (reveal and s in reveal):
            cards = cards_str(hand.hole[s])
        elif hand.folded[s]:
            cards = ""
        else:
            cards = "░░ ░░"
        cv.put(x0 + 1, y0 + 3, f" {cards}"[: SEAT_W - 2])
    return cv.render()


def play_hand_tui(hand_no, n, blueprint, rng, human_pos, stacks, names):
    hand = Hand(n, stacks, blueprint.sb, blueprint.bb, rng=rng)
    bot = BotAgent(blueprint, rng)
    log = deque(maxlen=3)
    tty = sys.stdout.isatty()

    def redraw(extra=(), board_limit=None):
        if tty:
            print("\033[2J\033[H", end="")
        else:
            print("\n" + "·" * W)
        print(
            f" Hand #{hand_no}  ·  blinds {blueprint.sb}/{blueprint.bb}  ·  "
            f"you are {POSITION_NAMES[n][human_pos]}  ·  [?] = advice at your turn"
        )
        print(draw(hand, names, human_pos, board_limit))
        for line in log:
            print(f"  » {line}")
        for line in extra:
            print(line)

    redraw()
    while not hand.terminal:
        p = hand.to_act
        tc = hand.to_call(p)
        if p == human_pos:
            token, action = human_turn(hand, human_pos, blueprint, rng)
        else:
            if tty:
                time.sleep(0.7)
            token, action = bot.act(hand)
        desc = describe_action(hand, p, token, action, tc)
        prev_board = len(hand.board)
        hand.apply(action, token)
        log.append(f"{names[p]} {desc}")

        # all-in run-out: reveal the remaining streets one frame at a time
        if (
            hand.terminal and tty
            and len(hand.active_players()) > 1
            and len(hand.board) - prev_board >= 2
        ):
            for limit in (3, 4, 5):
                if limit > prev_board:
                    redraw(board_limit=limit)
                    time.sleep(1.0)
        redraw()

    extra = []
    scores = getattr(hand, "showdown_scores", None)
    if scores:
        extra.append("  Showdown:")
        for p in sorted(scores):
            extra.append(
                f"    {names[p]}: {cards_str(hand.hole[p])}"
                f"  ({category_name(scores[p])})"
            )
    if hand.uncalled:
        p, amount = hand.uncalled
        extra.append(f"  {names[p]} takes back {amount} (uncalled bet)")
    for p, amount in hand.winners_info:
        extra.append(f"  {names[p]} wins {amount}")
    redraw(extra)
    return hand.payoffs
