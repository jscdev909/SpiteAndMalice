from collections import deque
from card import Card

class Player:
    def __init__(self, number, name):
        self.number: int = number
        self.name: str = name
        self.payoff_pile: list[Card] = []
        self.discard_piles: list[list[Card]] = [[], [], [], []]
        self.hand: list[Card] = []
        self.draw_count: int = 0
        self.moves_queue: deque = deque()
        self.rematch = None

    def reset(self):
        self.payoff_pile = []
        self.discard_piles = [[], [], [], []]
        self.hand = []
        self.draw_count = 0
        self.moves_queue = deque()
        self.rematch = None