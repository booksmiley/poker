"""Card representation and helpers.

A card is an int 0..51: rank = card >> 2 (0 = deuce .. 12 = ace),
suit = card & 3.
"""
import random

RANK_CHARS = "23456789TJQKA"
SUIT_CHARS = "cdhs"
SUIT_SYMBOLS = "♣♦♥♠"  # clubs, diamonds, hearts, spades


def rank_of(card):
    return card >> 2


def suit_of(card):
    return card & 3


def make_card(rank, suit):
    return (rank << 2) | suit


def card_str(card, pretty=True):
    r = RANK_CHARS[rank_of(card)]
    s = SUIT_SYMBOLS[suit_of(card)] if pretty else SUIT_CHARS[suit_of(card)]
    return r + s


def cards_str(cards, pretty=True):
    return " ".join(card_str(c, pretty) for c in cards)


def parse_card(text):
    text = text.strip()
    r = RANK_CHARS.index(text[0].upper())
    s = SUIT_CHARS.index(text[1].lower())
    return make_card(r, s)


def new_deck(rng=None):
    deck = list(range(52))
    (rng or random).shuffle(deck)
    return deck


def preflop_class(hole):
    """Canonical 169-class label for two hole cards, e.g. 'AKs', 'T9o', 'QQ'."""
    a, b = hole
    ra, rb = rank_of(a), rank_of(b)
    if ra < rb:
        ra, rb = rb, ra
    hi, lo = RANK_CHARS[ra], RANK_CHARS[rb]
    if ra == rb:
        return hi + lo
    suited = "s" if suit_of(a) == suit_of(b) else "o"
    return hi + lo + suited
