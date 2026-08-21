"""Interactive shell game: you vs. blueprint bots."""
import random
import sys
import time

from .abstraction import nearest_raise_token, playable_actions, raising_is_dead
from .ai import BotAgent, spot_strategy
from .cards import cards_str
from .engine import FLOP, RIVER, TURN, Hand
from .equity import hand_equity
from .evaluator import category_name, evaluate

STREET_LABELS = [
    "Preflop",
    "Flop (first 3 community cards)",
    "Turn (4th card)",
    "River (5th and final card)",
]

POSITION_NAMES = {
    3: ["SB", "BB", "BTN"],
    4: ["SB", "BB", "UTG", "BTN"],
    5: ["SB", "BB", "UTG", "CO", "BTN"],
    6: ["SB", "BB", "UTG", "MP", "CO", "BTN"],
}


class QuitSession(Exception):
    pass


def describe_action(hand, p, token, action, to_call_before):
    if action[0] == "f":
        return "folds"
    if action[0] == "c":
        return "checks" if to_call_before == 0 else f"calls {to_call_before}"
    target = min(action[1], hand.street_contrib[p] + hand.stacks[p])
    allin = target == hand.street_contrib[p] + hand.stacks[p]
    verb = "raises to" if hand.current_bet > 0 else "bets"
    return f"{verb} {target}" + (" (ALL-IN)" if allin else "")


def action_label(hand, p, token, action):
    tc = hand.to_call(p)
    if action[0] == "f":
        return "fold"
    if action[0] == "c":
        return "check" if tc == 0 else f"call {tc}"
    target = action[1]
    if target >= hand.street_contrib[p] + hand.stacks[p]:
        return f"all-in ({hand.street_contrib[p] + hand.stacks[p]})"
    size = {"h": "½-pot", "p": "pot"}.get(token, "")
    verb = "raise to" if hand.current_bet > 0 else "bet"
    return f"{verb} {target}" + (f" ({size})" if size else "")


def show_advice(blueprint, hand, hp, rng):
    acts, probs, trained = spot_strategy(blueprint, hand, hp, rng)
    hole = hand.hole[hp]
    print(f"\n  ── GTO advice for {cards_str(hole)} ──")
    if hand.board:
        eq = hand_equity(hole, hand.board, rng, trials=300)
        print(f"  Estimated equity vs one random hand: {eq * 100:.0f}%")
    if raising_is_dead(hand, hp):
        print("  (opponents are all-in — a raise would come straight back)")
    ranked = sorted(zip(acts, probs), key=lambda x: -x[1])
    for (tok, action), pr in ranked:
        bar = "█" * int(round(pr * 20))
        print(f"  {action_label(hand, hp, tok, action):<18} {pr * 100:5.1f}%  {bar}")
    if not trained:
        print("  (spot not reached in training — this is a fallback guess;")
        print("   train more iterations for real coverage)")
    print()


def human_turn(hand, hp, blueprint, rng):
    acts = playable_actions(hand)
    tokens = {tok: (tok, action) for tok, action in acts}
    tc = hand.to_call(hp)
    pot = hand.pot()
    parts = []
    for tok, action in acts:
        parts.append(f"[{tok}] {action_label(hand, hp, tok, action)}")
    can_custom = (
        hand.stacks[hp] > tc
        and any(a[0] == "r" for _, a in acts)
    )
    if can_custom:
        parts.append("[b <amt>] raise to amt")
    parts.append("[?] advice")
    parts.append("[q] quit")

    odds = f", pot odds {tc / (pot + tc) * 100:.0f}%" if tc else ""
    print(f"\n  Your turn. Pot: {pot}. To call: {tc}{odds}. Stack: {hand.stacks[hp]}.")
    if hand.board:
        made = category_name(evaluate(hand.hole[hp] + hand.board))
        print(
            f"  Your hand so far: {made}"
            f"  [{cards_str(hand.hole[hp])}] + [{cards_str(hand.board)}]"
        )
    print("  " + "  ".join(parts))
    while True:
        try:
            raw = input("  > ").strip().lower()
        except EOFError:
            raise QuitSession
        if not raw:
            continue
        if raw == "q":
            raise QuitSession
        if raw == "?":
            show_advice(blueprint, hand, hp, rng)
            continue
        if raw in tokens:
            return tokens[raw]
        if raw.startswith(("b ", "r ")) and can_custom:
            try:
                target = int(raw.split()[1])
            except (ValueError, IndexError):
                print("  usage: b <amount>  (raise TO that many chips this street)")
                continue
            max_to = hand.street_contrib[hp] + hand.stacks[hp]
            min_to = min(hand.current_bet + hand.min_raise, max_to)
            if target >= max_to:
                return tokens["a"] if "a" in tokens else ("a", ("r", max_to))
            if target < min_to:
                print(f"  minimum raise is to {min_to} (all-in excepted)")
                continue
            return nearest_raise_token(hand, target), ("r", target)
        print("  ? = advice, or one of: " + ", ".join(tokens))


def reveal_showdown(hand, names):
    scores = getattr(hand, "showdown_scores", None)
    if not scores:
        return
    print("  Showdown:")
    for p in sorted(scores):
        print(
            f"    {names[p]:>4}: {cards_str(hand.hole[p])}"
            f"  ({category_name(scores[p])})"
        )


def play_hand(hand_no, n, blueprint, rng, human_pos, stacks, names):
    hand = Hand(n, stacks, blueprint.sb, blueprint.bb, rng=rng)
    bot = BotAgent(blueprint, rng)

    print(f"\n{'=' * 58}")
    print(
        f"Hand #{hand_no}  |  blinds {blueprint.sb}/{blueprint.bb}  |  "
        f"you are {POSITION_NAMES[n][human_pos]} with {stacks[human_pos]} chips"
    )
    print(f"Your cards: {cards_str(hand.hole[human_pos])}")
    print(f"{names[0]} posts {hand.contrib[0]}, {names[1]} posts {hand.contrib[1]}")

    last_street = 0
    while not hand.terminal:
        if hand.street != last_street:
            last_street = hand.street
            print(
                f"\n--- {STREET_LABELS[hand.street]}: "
                f"{cards_str(hand.board)}   (pot {hand.pot()}) ---"
            )
        p = hand.to_act
        tc = hand.to_call(p)
        if p == human_pos:
            token, action = human_turn(hand, human_pos, blueprint, rng)
        else:
            token, action = bot.act(hand)
        desc = describe_action(hand, p, token, action, tc)
        hand.apply(action, token)
        print(f"  {names[p]}: {desc}")

    print()
    if len(hand.active_players()) > 1 and last_street < RIVER:
        # all-in before the river: reveal the run-out street by street
        print("  All bets are in — dealing out the board:")
        for street, upto in ((FLOP, 3), (TURN, 4), (RIVER, 5)):
            if street > last_street:
                print(f"    {STREET_LABELS[street]}: {cards_str(hand.board[:upto])}")
                if sys.stdin.isatty():
                    time.sleep(0.9)
        print()
    elif len(hand.board) > 0:
        print(f"  Final board: {cards_str(hand.board)}")
    reveal_showdown(hand, names)
    if hand.uncalled:
        p, amount = hand.uncalled
        print(f"  {names[p]} takes back {amount} (uncalled bet)")
    for p, amount in hand.winners_info:
        print(f"  {names[p]} wins {amount}")
    return hand.payoffs


def run_session(blueprint, seed=None, max_hands=None, ui="table", persistent=True):
    """Play hands until quit. Player 0 is the human; chips carry over
    between hands (unless persistent=False), and busted players rebuy."""
    if ui == "table":
        from .tui import play_hand_tui as hand_fn
    else:
        hand_fn = play_hand
    n = blueprint.n_players
    buyin = blueprint.stack
    rng = random.Random(seed)
    chips = [buyin] * n     # indexed by persistent player, 0 = you
    total = 0               # your net winnings across the session
    hands = 0
    print(
        f"\nLoaded blueprint: {n} players, trained {blueprint.iters_done:,} "
        f"iterations, {len(blueprint.table):,} infosets."
    )
    print("Type ? at any decision to see the blueprint's strategy for your spot.")
    try:
        while max_hands is None or hands < max_hands:
            if not persistent:
                chips = [buyin] * n
            # the button moves each hand: player i's seat drops by one
            seat_of = [(n - 1 - i - hands) % n for i in range(n)]
            player_at = [0] * n
            for i, s in enumerate(seat_of):
                player_at[s] = i
            human_pos = seat_of[0]
            stacks = [chips[player_at[s]] for s in range(n)]
            names = [
                f"You({POSITION_NAMES[n][s]})" if player_at[s] == 0
                else f"Bot{player_at[s]}·{POSITION_NAMES[n][s]}"
                for s in range(n)
            ]
            payoffs = hand_fn(hands + 1, n, blueprint, rng, human_pos, stacks, names)
            for s in range(n):
                chips[player_at[s]] += payoffs[s]
            net = payoffs[human_pos]
            total += net
            hands += 1
            print(f"  Hand result for you: {net:+} chips.")
            print(
                "  Stacks: You " + str(chips[0]) + "  ·  "
                + "  ·  ".join(f"Bot{i} {chips[i]}" for i in range(1, n))
                + f"     (session: {total:+} chips over {hands} hand(s))"
            )
            if persistent:
                for i in range(1, n):
                    if chips[i] <= 0:
                        chips[i] += buyin
                        print(f"  Bot{i} is busted and rebuys for {buyin}.")
            if max_hands is None or hands < max_hands:
                if persistent and chips[0] <= 0:
                    prompt = f"\nYou're busted! [Enter] rebuy {buyin}, q quits: "
                else:
                    prompt = "\n[Enter] next hand, q quits: "
                try:
                    if input(prompt).strip().lower() == "q":
                        break
                except EOFError:
                    break
                if persistent and chips[0] <= 0:
                    chips[0] += buyin
                    print(f"  You rebuy for {buyin}.")
    except QuitSession:
        pass
    print(
        f"\nSession over: {total:+} chips in {hands} hand(s). "
        f"({total / blueprint.bb:+.1f} big blinds)"
    )
