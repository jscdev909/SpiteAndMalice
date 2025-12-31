from enum import Enum
from typing import Any
import pygame
import socket
import struct
import pickle
from socket_utils import recv_all, HEADER_SIZE

class CardPosition(Enum):
    FACE_DOWN = 0,
    FACE_UP = 1


class Card:
    def __init__(self, name: str, surface_array: Any):
        self.name = name
        self.surface_array = surface_array
        self.position = CardPosition.FACE_DOWN
        self.surface = None
        self.rect = None

        if self.name[0].isdigit():
            if self.name[:2].isdigit():
                self.rank = int(self.name[:2])
            else:
                self.rank = int(self.name[0])
        else:
            if self.name.startswith("ace"):
                self.rank = 1
            elif self.name.startswith("jack"):
                self.rank = 11
            elif self.name.startswith("queen"):
                self.rank = 12
            elif self.name.startswith("king"):
                self.rank = 13

    def generate_rect(self):
        if self.surface is not None:
            self.rect = self.surface.get_rect()

    def generate_surface(self):
        self.surface = pygame.surfarray.make_surface(self.surface_array)


def receive_cards(sock: socket.socket, cards_to_receive: int) -> list[Card]:

    received_cards = []

    for _ in range(0, cards_to_receive, 1):

        # Receive message length
        raw_message_length = recv_all(sock, HEADER_SIZE)
        if not raw_message_length:
            return []
        message_length = struct.unpack("!I", raw_message_length)[0]

        # Receive the actual data payload
        pickled_data = recv_all(sock, message_length)
        if not pickled_data:
            return []

        card_data = pickle.loads(pickled_data)
        card_data.generate_surface()
        card_data.generate_rect()
        received_cards.append(card_data)
        print(f"Received {received_cards[-1].name}")

    return received_cards


def send_cards(sock: socket.socket, cards_to_send: list[Card]) -> None:

    for sent_card in cards_to_send:
        # Can't serialize pygame surfaces and rects
        sent_card.surface = None
        sent_card.rect = None

        pickled_card = pickle.dumps(sent_card)
        message_length = struct.pack('!I', len(pickled_card))
        sock.sendall(message_length + pickled_card)