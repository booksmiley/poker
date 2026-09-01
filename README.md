# Poker GTO Simulator

Play No-Limit Texas Hold'em in the shell against approximate game-theory-optimal
bots, with on-demand "what would GTO do here?" advice for your own seat.
Pure Python, no dependencies.

## Quick start

```bash
python3 play.py --players 4
```

The repo ships a distilled 4-player blueprint (`blueprints/bp_4p.gto`),
so this works straight after cloning. For other table sizes (or stronger
bots), train your own:

```bash
python3 train.py --players 5 --iters 50000    # full .pkl, resumable
python3 distill.py --players 5                # small .gto for git
```

If no blueprint exists, `play.py` quick-trains a weak starter one
automatically. At any decision, type `?` to see the blueprint's action mix
for your exact spot before you act.

By default you get the **round-table view**, redrawn after every action —
you sit bottom-center, seats show each player's stack, current bet, and
status, with the community cards and pot in the middle:

```
                               ┌───────────┐
                               │ SB        │
                               │ 199 bet 1 │
                               │ ░░ ░░     │
      ┌───────────┐            └───────────┘           ┌───────────┐
      │ CO        │                                    │ BB        │
      │ 200       │     ╭───────────────────────────╮  │ 198 bet 2 │
      │ ░░ ░░     │     │          PREFLOP          │  │ ░░ ░░     │
      └───────────┘     │                           │  └───────────┘
                        │   [  ][  ][  ][  ][  ]    │
                        │          Pot: 3           │  ┌───────────┐
                        ╰───────────────────────────╯  │►UTG       │
                                                       │ 200       │
                               ┌───────────┐           │ ░░ ░░     │
                               │ You(BTN)  │           └───────────┘
                               │ 200       │
                               │ A♠ K♦     │
                               └───────────┘
```

`►` marks whose turn it is; play proceeds clockwise; opponents' cards stay
hidden (`░░ ░░`) until showdown. Prefer the original scrolling log?
`python3 play.py --ui text`.

```
Your turn. Pot: 10. To call: 5, pot odds 33%. Stack: 198.
[f] fold  [c] call 5  [h] raise to 15 (½-pot)  [p] raise to 22 (pot)  [a] all-in (200)  [b <amt>]  [?]  [q]
> ?
  ── GTO advice for A♠ K♦ ──
  raise to 22 (pot)    64.2%  █████████████
  call 5               28.1%  ██████
  all-in (200)          6.5%  █
  fold                  1.2%
```

## Game setup

- 3-6 players (you pick with `--players`; one seat is you, the rest are bots)
- Blinds 1/2, everyone buys in for 200 chips (100bb); **stacks carry over
  from hand to hand** like a real cash game, and anyone who busts
  automatically rebuys for another 200 (the session tracks your net)
- `--reset-stacks` restores the trainer-style mode where every stack
  resets to 200 each hand — the exact situation the bots trained on
- Your position rotates every hand (the button moves after each hand)
- Bets are integer chips; the menu offers the trained sizes (½-pot, pot,
  all-in) but `b <amount>` lets you raise to any legal amount

## Play with friends (phones + bots)

```bash
python3 serve.py --players 4
```

Your Mac hosts the table; phones are just browsers — no app, no internet.
The server loads the small distilled `bp_4p.gto` (ships with the repo) in
a few seconds, so a fresh clone can host a table immediately.

### At home (same Wi-Fi)

1. On the Mac: `python3 serve.py --players 4`. It prints an address like
   `http://192.168.1.7:8080`.
2. First launch, macOS asks *"Do you want Python to accept incoming
   network connections?"* — **Allow**. (Clicked Deny once? System
   Settings → Network → Firewall → Options, allow Python.)
3. On each phone (same Wi-Fi as the Mac): open that exact address in the
   browser, including the `:8080`.
4. Enter a name → *Sit down* → anyone taps *Deal the first hand*. Seats
   without a human are GTO bots. On your turn: action buttons with
   amounts, pot odds, a countdown, a raise-to box for custom sizes, and a
   private `GTO ?` advice button per player. All cards are revealed at
   hand end. The next hand starts as soon as every human taps *Ready for
   next hand*. Once the first player is ready, a 30-second countdown
   guarantees the game continues even if somebody does not respond.
   Any seated human can use *Stop & reset table* to abort the current
   hand, restore the starting stacks, and return everyone to the lobby.
5. A phone that locks mid-hand is auto-checked/folded after
   `--turn-timeout` seconds (default 45) so the table never stalls;
   reopening the page rejoins the same seat (the browser remembers your
   session). Two minutes fully absent and a bot takes the seat over.

### On a plane (no internet anywhere)

Wi-Fi radios are allowed in airplane mode, and the game only needs the
phones to reach the Mac. Do a dry run at home first.

1. Create the Mac's own network: System Settings → **General → Sharing →
   Internet Sharing** (the ⓘ). *Share your connection from:* an unused
   port such as **Thunderbolt Bridge**; *To devices using:* **Wi-Fi**.
   Under *Wi-Fi Options…* set a network name and WPA2 password. Toggle
   Internet Sharing on. (A pocket travel router works too.)
2. Phones: airplane mode on, re-enable Wi-Fi, join that network. Ignore
   the "No Internet Connection" warning — none is needed.
3. Mac: `caffeinate -dims python3 serve.py --players 4` (the caffeinate
   keeps the Mac from sleeping mid-session), lid open. Phones open the
   printed address — the IP differs per network, so always use what it
   prints.

### Host it on Render (play away from your laptop)

The repo deploys to [Render](https://render.com)'s free tier as-is:

1. On Render: **New → Blueprint**, connect this GitHub repo — `render.yaml`
   configures everything (free plan, Python, start command using the slim
   blueprint).
2. Set the `TABLE_PASSWORD` environment variable when prompted — the
   URL is public internet, so the password keeps strangers out of your
   game. Players enter it once when joining.
3. Open `https://<your-app>.onrender.com` on any phone, anywhere.

Free-tier realities:

- **No per-hand cost.** Render bills instance hours (750 free/month —
  a whole month of uptime) and bandwidth (100GB; a full evening of play
  uses a few MB). Play as many hands as you like.
- **512MB RAM** is why the deploy uses `bp_4p_slim.gto`: the top 1.2M
  infosets by training weight (95% of all strategy mass, every preflop
  spot included) loading to ~310MB, vs 1.8GB for the full distilled
  table. Rarely-reached spots fall back to a passive default.
- **Sleep after 15 idle minutes**: the first visit after a break takes
  ~a minute to wake, and the table (chips, seats) resets — it lives in
  memory. During play, the phones' polling keeps it awake.

To serve the slim blueprint locally instead (or test before deploying):
`python3 serve.py --players 4 --blueprint blueprints/bp_4p_slim.gto`.
Regenerate it after more training with
`python3 distill.py --players 4 --max-entries 1200000 --out blueprints/bp_4p_slim.gto`.

### If a phone can't load the page

Almost always one of: the phone is on a different network (turn cellular
data off so it can't route around); the `:8080` was dropped from the URL;
the firewall prompt was denied; or the Mac's IP changed after switching
networks (restart `serve.py`, use the newly printed address).

## Glossary (all the abbreviations the interface uses)

### Money and chips

| Term | Meaning |
|---|---|
| **Blinds 1/2** | Forced bets that two players must post before seeing any cards, to create something worth fighting for. The *small blind* posts 1 chip, the *big blind* posts 2. Everyone else may fold for free. |
| **bb** | Big blinds, used as a unit of money ("200 chips = 100bb"). Poker results are measured in blinds so they're comparable across stake sizes. |
| **Stack** | The chips you have in front of you — the most you can lose (or win from any one opponent) in a single hand. Everyone starts with 200 chips (100bb) and stacks carry over between hands; a busted player rebuys for another 200. |
| **Pot** | All the chips bet so far in the current hand. The winner takes it. |
| **To call** | How much you must pay to stay in the hand and match the current bet. |
| **Pot odds** | The price of calling: `to call / (pot + to call)`. If it costs 5 to win a 15 pot, pot odds are 25% — so calling is profitable if you win more than 25% of the time. |
| **bb/100** | Big blinds won per 100 hands, the standard win-rate measure. Wildly noisy over a few hands; meaningful over thousands. |

### Positions (seats)

Seats are named by where they sit relative to the dealer. Position matters
because acting *later* in a betting round means acting with more
information, so late seats can profitably play more hands.

| Term | Meaning |
|---|---|
| **BTN** | *Button* — the (nominal) dealer seat. Acts **last** after the flop: the best seat at the table. |
| **SB** | *Small blind* — first seat left of the button; posts the small forced bet. Acts first after the flop: the worst seat. |
| **BB** | *Big blind* — second seat left of the button; posts the big forced bet. Preflop it acts last and may raise even after everyone just calls ("the option"). |
| **UTG** | *Under the gun* — first seat to act before the flop (left of the BB). Must play the tightest range since everyone else still waits behind. |
| **MP** | *Middle position* — between UTG and the CO (6-player tables). |
| **CO** | *Cutoff* — the seat just before the button. Second-best position. |

In this simulator your position rotates every hand so you experience all
of them.

### Actions

| Term | Meaning |
|---|---|
| **Fold** | Give up the hand. You lose whatever you already put in, nothing more. |
| **Check** | Bet nothing and pass the action on. Only possible when nobody has bet yet this round (to call = 0). |
| **Call** | Match the current bet and stay in. |
| **Raise to X** | Increase the bet; X is your *total* for this street, not the increment. |
| **½-pot / pot** | Raise sizes measured against the pot. Bigger bets pressure opponents but risk more. |
| **All-in** | Bet your entire stack. You can't be forced out afterwards; if others keep betting past your stack, side pots form that you can't win. |
| **Limp** | Just call the big blind preflop instead of raising (generally a weak, passive play). |

### Cards and streets

| Term | Meaning |
|---|---|
| **Preflop / Flop / Turn / River** | The four betting rounds ("streets"): after your 2 private cards, after the first 3 community cards, after the 4th, after the 5th. |
| **Board** | The face-up community cards everyone shares. |
| **Hole cards** | Your 2 private cards. |
| **Showdown** | If two or more players survive the river betting, hands are revealed and the best 5-card hand (from your 2 + the 5 board cards) wins. |
| **AKs / AKo / T9s ...** | Shorthand for starting hands: the two card ranks plus `s` = *suited* (same suit) or `o` = *offsuit*. `T` is ten. Pairs are just `AA`, `77`. Suited hands are a bit stronger (flush potential). |
| **Equity** | Your chance of winning the pot if the remaining cards were dealt out with no more betting. The `?` advice shows an estimate vs one random hand. |
| **GTO** | *Game-theory optimal* — a strategy that can't be exploited even by an opponent who knows it exactly. See the caveats below for what that means with 3+ players. |

## Optional speedup

```bash
pip3 install phevaluator
```

If present, the equity rollouts use phevaluator's C hand evaluator (~5x
faster raw, ~1.3x faster training; verified to rank hands identically to
ours). Without it everything still runs on the pure-Python evaluator in
`pokersim/evaluator.py`, which remains the readable reference
implementation either way.

## Tools

```bash
python3 tests/run_tests.py                        # test suite
python3 train.py --players 4 --iters 50000 --resume   # keep improving a blueprint
python3 inspect_strategy.py --chart ""            # 13x13 preflop chart, first to act
python3 inspect_strategy.py --key "AKs|p"         # strategy facing a pot-size open
```

Training checkpoints every `--save-every` iterations, so Ctrl-C is safe and
`--resume` continues where it left off. Blueprints live in `blueprints/`
and are specific to a player count, in two formats:

- `bp_{n}p.pkl` — full trainer state (regrets + strategy). Hundreds of MB;
  supports `--resume`; git-ignored.
- `bp_{n}p.gto` — distilled play blueprint from `distill.py`: regrets
  dropped, near-unvisited infosets pruned (99.9% of strategy weight kept),
  probabilities quantized to 1 byte, gzipped. ~10x smaller (well under
  GitHub's 100MB limit), loads ~9x faster, plays identically (worst
  quantization error <1%). Cannot resume training. If it ever outgrows
  the size cap it is auto-split into `.partNN` files that the game
  recombines transparently.

`play.py` and `serve.py` prefer the distilled `.gto` when it exists
(seconds to load); pass `--blueprint blueprints/bp_4p.pkl` to play against
the full checkpoint instead. Refresh the `.gto` after more training with
`python3 distill.py --players 4`.

## How the "GTO" works (and its limits)

The bots follow a **blueprint strategy** computed with external-sampling
Monte-Carlo CFR (counterfactual regret minimization) — the same family of
techniques behind Libratus/Pluribus, shrunk to pure-Python scale. To make
that tractable, the game is abstracted:

- **Card abstraction** — preflop hands use their canonical 169 classes
  (`AKs`, `T9o`, ...); postflop hands collapse to an equity bucket
  (Monte-Carlo estimated equity vs one random hand, board rolled out,
  quantized into 10 bins). Two different hands with similar equity share a
  strategy.
- **Action abstraction** — raises come in three sizes (½-pot, pot,
  all-in), with sized raises capped at 4 per street. Off-tree bets you
  make with `b <amt>` are mapped to the nearest trained size for the bots'
  bookkeeping.
- **Sampling** — each CFR iteration deals one hand per traversing player
  and explores all of that player's options while sampling everyone
  else's.

Honest caveats:

- CFR is only *guaranteed* to converge to Nash equilibrium in two-player
  zero-sum games. For 3+ players it produces a strong approximate
  equilibrium in practice (this is exactly what Pluribus did), which is
  what "GTO" means at a multiway table for any solver.
- The abstraction is coarse: 10 equity buckets can't distinguish a flush
  draw from a middling made hand of equal equity. Expect solid but not
  superhuman play; more training iterations and more buckets
  (`pokersim/equity.py: N_BUCKETS`, `TRIALS`) improve it at the cost of
  speed.
- Advice for a spot the training never visited falls back to a passive
  default and says so.
- The blueprint was trained with everyone 200 chips deep. With carry-over
  stacks, hands that start far from 200 are played with the same strategy
  (raise sizes still adapt to the real pot and stacks, but the mix was
  tuned for 100bb) — another approximation. Use `--reset-stacks` for
  strategy purity, or accept the drift as part of the game.
- Rules simplification: an all-in raise below the minimum raise still
  reopens the betting.

## Code map

```
pokersim/
  cards.py        card encoding, 169 preflop classes
  evaluator.py    5-7 card hand evaluator (packed-int scores)
  equity.py       Monte-Carlo equity + bucketing (the card abstraction)
  engine.py       NLHE hand state machine: betting, all-ins, side pots
  abstraction.py  action abstraction + infoset keys
  cfr.py          external-sampling MCCFR trainer
  strategy.py     blueprint save/load/lookup
  ai.py           bot agent sampling from the blueprint
  cli.py          interactive shell game (text mode + shared input handling)
  tui.py          round-table view (default UI)
  webtable.py     server-side table for browser multiplayer
train.py          train/resume blueprints
play.py           play a solo session in the terminal
serve.py          host a browser table for phones (web/index.html is the page)
inspect_strategy.py   look inside a blueprint
tests/run_tests.py    self-contained test suite
```

`kuhn.py` is an older standalone Kuhn-poker experiment, unrelated to this
package.
