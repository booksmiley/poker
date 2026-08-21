"""Fast-ish pure-Python hand evaluator for 5, 6 or 7 cards.

evaluate(cards) returns an int score; higher is better. The score packs
(category, tiebreak ranks) into one integer so scores compare directly.

Categories: 8 straight flush, 7 quads, 6 full house, 5 flush, 4 straight,
3 trips, 2 two pair, 1 pair, 0 high card.
"""

CATEGORY_NAMES = [
    "High Card", "Pair", "Two Pair", "Three of a Kind", "Straight",
    "Flush", "Full House", "Four of a Kind", "Straight Flush",
]


def _straight_high(rank_mask):
    """Highest straight top-rank in a rank bitmask, or -1. Handles the wheel."""
    for high in range(12, 3, -1):
        if (rank_mask >> (high - 4)) & 0b11111 == 0b11111:
            return high
    # wheel: A-2-3-4-5
    if rank_mask & 0b1000000001111 == 0b1000000001111:
        return 3
    return -1


def _pack(cat, t1=0, t2=0, t3=0, t4=0, t5=0):
    return (cat << 20) | (t1 << 16) | (t2 << 12) | (t3 << 8) | (t4 << 4) | t5


def evaluate(cards):
    """Score the best 5-card hand contained in 5-7 cards (ints 0..51)."""
    rank_count = [0] * 13
    suit_count = [0] * 4
    for c in cards:
        rank_count[c >> 2] += 1
        suit_count[c & 3] += 1

    # With <=7 cards a flush precludes quads and full houses, so check it first.
    for s in range(4):
        if suit_count[s] >= 5:
            fmask = 0
            for c in cards:
                if c & 3 == s:
                    fmask |= 1 << (c >> 2)
            sh = _straight_high(fmask)
            if sh >= 0:
                return _pack(8, sh)
            tops = []
            for r in range(12, -1, -1):
                if fmask >> r & 1:
                    tops.append(r)
                    if len(tops) == 5:
                        break
            return _pack(5, *tops)

    quads = trips = -1
    pairs = []
    for r in range(12, -1, -1):
        n = rank_count[r]
        if n == 4:
            quads = r
        elif n == 3:
            if trips < 0:
                trips = r
            else:
                pairs.append(r)  # second trips plays as a pair
        elif n == 2:
            pairs.append(r)

    if quads >= 0:
        kicker = max(r for r in range(13) if rank_count[r] and r != quads)
        return _pack(7, quads, kicker)
    if trips >= 0 and pairs:
        return _pack(6, trips, pairs[0])

    rank_mask = 0
    for r in range(13):
        if rank_count[r]:
            rank_mask |= 1 << r
    sh = _straight_high(rank_mask)
    if sh >= 0:
        return _pack(4, sh)

    if trips >= 0:
        kickers = [r for r in range(12, -1, -1) if rank_count[r] and r != trips][:2]
        return _pack(3, trips, *kickers)
    if len(pairs) >= 2:
        hi, lo = pairs[0], pairs[1]
        kicker = max(r for r in range(13) if rank_count[r] and r != hi and r != lo)
        return _pack(2, hi, lo, kicker)
    if len(pairs) == 1:
        p = pairs[0]
        kickers = [r for r in range(12, -1, -1) if rank_count[r] and r != p][:3]
        return _pack(1, p, *kickers)

    tops = [r for r in range(12, -1, -1) if rank_count[r]][:5]
    return _pack(0, *tops)


def category_name(score):
    return CATEGORY_NAMES[score >> 20]
