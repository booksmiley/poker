"""
用 CFR（反事实遗憾最小化）求解 Kuhn Poker 的 GTO 策略

Kuhn Poker 是德扑的极简版本：
  - 牌堆只有 3 张：J(0) < Q(1) < K(2)
  - 每人先下 1 个底注，各发 1 张牌
  - 只有一轮下注，动作只有 p(pass/过牌或弃牌) 和 b(bet/下注1或跟注)

这个游戏小到可以精确求解，正好用来看清 GTO 求解器的内部机制。
真实德扑用的是同一套算法，只是加了抽象化和采样。
"""

import random
from collections import defaultdict

ACTIONS = ['p', 'b']          # pass / bet
N_ACTIONS = 2


class Node:
    """一个信息集(information set)：玩家在此刻能看到的所有信息。
    比如 '2pb' = 我拿 K，对手过牌，我下注，现在轮到对手 —— 不，
    准确说是 '我的牌 + 至今的动作序列'，因为玩家看不到对手的牌。"""

    def __init__(self, key):
        self.key = key
        self.regret_sum = [0.0] * N_ACTIONS   # 累积遗憾值
        self.strategy_sum = [0.0] * N_ACTIONS # 累积策略（用来算平均策略）

    def get_strategy(self, realization_weight):
        """遗憾匹配：按"正遗憾"的比例分配动作概率。
        某个动作的遗憾 = 早知道就一直选它能多赚多少。"""
        strategy = [max(r, 0) for r in self.regret_sum]
        total = sum(strategy)
        if total > 0:
            strategy = [s / total for s in strategy]
        else:
            strategy = [1.0 / N_ACTIONS] * N_ACTIONS  # 没有正遗憾就均匀混合

        for a in range(N_ACTIONS):
            self.strategy_sum[a] += realization_weight * strategy[a]
        return strategy

    def get_average_strategy(self):
        """收敛到纳什均衡的是【平均策略】，不是当前策略。这一点很关键。"""
        total = sum(self.strategy_sum)
        if total > 0:
            return [s / total for s in self.strategy_sum]
        return [1.0 / N_ACTIONS] * N_ACTIONS


node_map = {}


def cfr(cards, history, p0, p1):
    """递归遍历博弈树。
    p0, p1 = 两名玩家走到当前节点的概率（不含自然发牌）
    返回：当前行动方的期望收益
    """
    plays = len(history)
    player = plays % 2
    opponent = 1 - player

    # ---------- 终止节点：直接结算 ----------
    if plays > 1:
        terminal_pass = history[-1] == 'p'
        double_bet = history[-2:] == 'bb'
        is_player_higher = cards[player] > cards[opponent]

        if terminal_pass:
            if history == 'pp':
                return 1 if is_player_higher else -1      # 双过牌摊牌，赌注 1
            else:
                return 1                                   # 对手弃牌，赢底注
        elif double_bet:
            return 2 if is_player_higher else -2           # 摊牌，赌注 2

    # ---------- 决策节点 ----------
    info_set = str(cards[player]) + history
    if info_set not in node_map:
        node_map[info_set] = Node(info_set)
    node = node_map[info_set]

    strategy = node.get_strategy(p0 if player == 0 else p1)
    util = [0.0] * N_ACTIONS
    node_util = 0.0

    for a in range(N_ACTIONS):
        next_history = history + ACTIONS[a]
        # 注意符号取反：递归返回的是对手视角的收益
        if player == 0:
            util[a] = -cfr(cards, next_history, p0 * strategy[a], p1)
        else:
            util[a] = -cfr(cards, next_history, p0, p1 * strategy[a])
        node_util += strategy[a] * util[a]

    # ---------- 累积遗憾 ----------
    # 权重是【对手】走到这里的概率 —— 这就是"反事实"的含义：
    # 我自己的概率不算，因为我在问"如果我一定来到这里会怎样"
    for a in range(N_ACTIONS):
        regret = util[a] - node_util
        node.regret_sum[a] += (p1 if player == 0 else p0) * regret

    return node_util


def train(iterations):
    cards = [0, 1, 2]
    util = 0.0
    for _ in range(iterations):
        random.shuffle(cards)
        util += cfr(cards, '', 1.0, 1.0)
    return util / iterations


if __name__ == '__main__':
    random.seed(42)
    ITER = 300_000
    value = train(ITER)

    print(f"迭代次数: {ITER:,}")
    print(f"先手玩家的期望收益: {value:+.4f}  (理论值 -1/18 = -0.0556)\n")

    names = {'0': 'J', '1': 'Q', '2': 'K'}
    print(f"{'信息集':<12} {'含义':<28} {'过牌/弃牌':>10} {'下注/跟注':>10}")
    print("-" * 64)

    desc = {
        '': '首次行动',
        'p': '对手过牌后',
        'b': '面对下注',
        'pb': '过牌后面对下注',
    }
    for key in sorted(node_map.keys(), key=lambda k: (len(k), k)):
        card, hist = key[0], key[1:]
        node = node_map[key]
        avg = node.get_average_strategy()
        label = f"拿 {names[card]}，{desc[hist]}"
        print(f"{key:<12} {label:<24} {avg[0]:>10.3f} {avg[1]:>10.3f}")

    # 验证已知的均衡性质
    alpha = node_map['0'].get_average_strategy()[1]      # 拿 J 首行动诈唬频率
    print(f"\n验证（Kuhn Poker 的均衡有闭式解，可以逐项对照）：")
    print(f"  先手拿 J 的诈唬频率 α    = {alpha:.3f}   理论 α ∈ [0, 1/3]")
    print(f"  先手拿 K 的下注频率      = {node_map['2'].get_average_strategy()[1]:.3f}"
          f"   理论 3α = {3*alpha:.3f}")
    print(f"  先手拿 Q 被下注后跟注    = {node_map['1pb'].get_average_strategy()[1]:.3f}"
          f"   理论 α + 1/3 = {alpha + 1/3:.3f}")
    print(f"  后手拿 J 在对手过牌后诈唬 = {node_map['0p'].get_average_strategy()[1]:.3f}"
          f"   理论 1/3 = 0.333")
    print(f"  后手拿 Q 面对下注的跟注率 = {node_map['1b'].get_average_strategy()[1]:.3f}"
          f"   理论 1/3 = 0.333")