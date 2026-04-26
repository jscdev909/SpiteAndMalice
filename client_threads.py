import threading
import socket
import pygame
from enum import Enum
from card import receive_cards
from socket_utils import send_message, receive_message

WHITE = (255, 255, 255)

class SetupStatus(Enum):
    UNSET = 0,
    CONNECTING_TO_SERVER = 1,
    PLAYER_ASSIGNED = 2,
    WAITING_FOR_OTHER_PLAYER = 3,
    RECEIVING_CARD_DATA = 4,
    OTHER_PLAYER_STATUS_CHECK = 5,
    COMPLETE = 6,
    ERROR = 7


class SetupErrorStatus(Enum):
    UNSET = 0,
    COULD_NOT_CONNECT_TO_SERVER = 1,
    GAME_LOBBY_FULL = 2,
    RECEIVED_EMPTY_OPPONENT_NAME = 3,
    CARD_DATA_RECEIVE_ERROR = 4,
    OTHER_PLAYER_DISCONNECTED = 5


class RematchStatus(Enum):
    UNSET = 0,
    IN_PROGRESS = 1,
    RECEIVING_CARD_DATA = 2,
    COMPLETE = 3,
    ERROR = 4


class RematchErrorStatus(Enum):
    UNSET = 0,
    ERROR_RECEIVING_CARD_DATA = 1


class NetworkHandlerStatus(Enum):
    UNSET = 0,
    RUNNING = 1,
    ERROR = 2,
    EXITED = 3


class NetworkHandlerErrorStatus(Enum):
    UNSET = 0,
    OTHER_PLAYER_DISCONNECTED = 1
    INVALID_PAYOFF_PILE1_LENGTH = 2,
    INVALID_PAYOFF_PILE2_LENGTH = 3,
    INVALID_DRAW_PILE_LENGTH = 4,
    INVALID_OPPONENT_HAND_LENGTH = 5,
    INVALID_GAME_RESULT_RESPONSE = 6,
    INVALID_GAME_WINNER = 7


class InitialSetupThread(threading.Thread):
    def __init__(self, server_socket: socket.socket, host: str, port: int, player_name: str):
        threading.Thread.__init__(self)
        self.server_socket = server_socket
        self.host = host
        self.port = port
        self.player_name = player_name
        self.player_number = 0
        self.opponent_player_name = ""
        self.opponent_player = 0
        self.payoff_pile1_top_card = None
        self.payoff_pile2_top_card = None
        self.status = SetupStatus.UNSET
        self.error = SetupErrorStatus.UNSET

    def run(self):
        # Connect to the server
        self.status = SetupStatus.CONNECTING_TO_SERVER
        self.server_socket.settimeout(30)

        try:
            self.server_socket.connect((self.host, self.port))
        except OSError:
            self.status = SetupStatus.ERROR
            self.error = SetupErrorStatus.COULD_NOT_CONNECT_TO_SERVER
            return

        # Receive player number
        send_message(self.server_socket, f"Player ready! Name: {self.player_name}")
        data = receive_message(self.server_socket)

        if "You are player" in data and data[-1].isdigit():
            self.player_number = int(data[-1])
            self.status = SetupStatus.PLAYER_ASSIGNED
        elif "Game lobby is full":
            self.status = SetupStatus.ERROR
            self.error = SetupErrorStatus.GAME_LOBBY_FULL
            return

        if self.player_number == 1:
            self.opponent_player = 2
        elif self.player_number == 2:
            self.opponent_player = 1

        if self.player_number == 1:
            # Receive other player status message
            send_message(self.server_socket, "Has player 2 joined?")
            data = receive_message(self.server_socket)

            if data == "Waiting for player 2":
                self.status = SetupStatus.WAITING_FOR_OTHER_PLAYER

                # Wait for player 2
                while True:
                    send_message(self.server_socket, "Has player 2 joined?")
                    data = receive_message(self.server_socket)
                    if data == "Player 2 has joined":
                        break
                    else:
                        pygame.time.wait(2000)

        send_message(self.server_socket,
                     f"What is player {self.opponent_player}'s name?")
        self.opponent_player_name = receive_message(self.server_socket)

        if not self.opponent_player_name:
            self.status = SetupStatus.ERROR
            self.error = SetupErrorStatus.RECEIVED_EMPTY_OPPONENT_NAME
            return

        self.status = SetupStatus.RECEIVING_CARD_DATA

        send_message(self.server_socket, "Create new deck and payoff piles")

        send_message(self.server_socket,
                     f"Send the top card of player {self.player_number}'s payoff pile")

        data = receive_cards(self.server_socket, 1)

        if not data:
            self.status = SetupStatus.ERROR
            self.error = SetupErrorStatus.CARD_DATA_RECEIVE_ERROR
            return

        if self.player_number == 1:
            self.payoff_pile1_top_card = data[0]
        elif self.player_number == 2:
            self.payoff_pile2_top_card = data[0]

        send_message(self.server_socket,
                     f"Send the top card of player {self.opponent_player}'s payoff pile")

        data = receive_cards(self.server_socket, 1)

        if not data:
            self.status = SetupStatus.ERROR
            self.error = SetupErrorStatus.CARD_DATA_RECEIVE_ERROR
            return

        if self.opponent_player == 1:
            self.payoff_pile1_top_card = data[0]
        elif self.opponent_player == 2:
            self.payoff_pile2_top_card = data[0]

        self.status = SetupStatus.OTHER_PLAYER_STATUS_CHECK
        send_message(self.server_socket, "Is the other player still connected?")
        data = receive_message(self.server_socket)

        if data == "No":
            self.status = SetupStatus.ERROR
            self.error = SetupErrorStatus.OTHER_PLAYER_DISCONNECTED
            return

        self.status = SetupStatus.COMPLETE


class RematchSetupThread(threading.Thread):
    def __init__(self, server_socket: socket.socket, player_number: int, opponent_player: int):
        threading.Thread.__init__(self)
        self.server_socket = server_socket
        self.player_number = player_number
        self.opponent_player = opponent_player
        self.payoff_pile1_top_card = None
        self.payoff_pile2_top_card = None
        self.status = RematchStatus.UNSET
        self.error = RematchErrorStatus.UNSET

    def run(self):
        self.status = RematchStatus.IN_PROGRESS

        send_message(self.server_socket, "Set up a new game")
        send_message(self.server_socket, "Create new deck and payoff piles")

        self.status = RematchStatus.RECEIVING_CARD_DATA

        send_message(self.server_socket, f"Send the top card of player {self.player_number}'s payoff pile")

        data = receive_cards(self.server_socket, 1)

        if not data:
            self.status = SetupStatus.ERROR
            self.error = RematchErrorStatus.ERROR_RECEIVING_CARD_DATA
            return

        if self.player_number == 1:
            self.payoff_pile1_top_card = data[0]
        elif self.player_number == 2:
            self.payoff_pile2_top_card = data[0]

        send_message(self.server_socket, f"Send the top card of player {self.opponent_player}'s payoff pile")

        data = receive_cards(self.server_socket, 1)

        if not data:
            self.status = SetupStatus.ERROR
            self.error = RematchErrorStatus.ERROR_RECEIVING_CARD_DATA
            return

        if self.opponent_player == 1:
            self.payoff_pile1_top_card = data[0]
        elif self.opponent_player == 2:
            self.payoff_pile2_top_card = data[0]

        self.status = RematchStatus.COMPLETE


class NetworkHandler(threading.Thread):
    def __init__(self, server_socket: socket.socket,
                 player_number: int,
                 opponent_player: int,
                 network_traffic_lock: threading.Lock,
                 game_over: threading.Event):

        threading.Thread.__init__(self)
        self.server_socket = server_socket
        self.player_number = player_number
        self.opponent_player = opponent_player
        self.network_traffic_lock = network_traffic_lock
        self.payoff_pile1_remaining_cards = 0
        self.payoff_pile2_remaining_cards = 0
        self.draw_pile_remaining_cards = 0
        self.opponents_hand_size = 0
        self.game_result_text = None
        self.game_over = game_over
        self.status = NetworkHandlerStatus.UNSET
        self.error = NetworkHandlerErrorStatus.UNSET

    def run(self):

        self.status = NetworkHandlerStatus.RUNNING

        network_timer = 20

        while not self.game_over.is_set():

            if network_timer == 0:

                self.network_traffic_lock.acquire()
                send_message(self.server_socket,"Is the other player still connected?")
                data = receive_message(self.server_socket)
                self.network_traffic_lock.release()

                if data == "No":
                    self.status = NetworkHandlerStatus.ERROR
                    self.error = NetworkHandlerErrorStatus.OTHER_PLAYER_DISCONNECTED

                self.network_traffic_lock.acquire()
                send_message(self.server_socket,"How many cards are left in player 1's payoff pile?")
                data = receive_message(self.server_socket)
                self.network_traffic_lock.release()

                if not data.isdigit():
                    self.status = NetworkHandlerStatus.ERROR
                    self.error = NetworkHandlerErrorStatus.INVALID_PAYOFF_PILE1_LENGTH

                self.payoff_pile1_remaining_cards = int(data)

                self.network_traffic_lock.acquire()
                send_message(self.server_socket,"How many cards are left in player 2's payoff pile?")
                data = receive_message(self.server_socket)
                self.network_traffic_lock.release()

                if not data.isdigit():
                    self.status = NetworkHandlerStatus.ERROR
                    self.error = NetworkHandlerErrorStatus.INVALID_PAYOFF_PILE2_LENGTH

                self.payoff_pile2_remaining_cards = int(data)

                self.network_traffic_lock.acquire()
                send_message(self.server_socket,"How many cards are left in the draw pile?")
                data = receive_message(self.server_socket)
                self.network_traffic_lock.release()

                if data.isdigit():
                    self.draw_pile_remaining_cards = int(data)
                else:
                    self.status = NetworkHandlerStatus.ERROR
                    self.error = NetworkHandlerErrorStatus.INVALID_DRAW_PILE_LENGTH

                self.network_traffic_lock.acquire()
                send_message(self.server_socket,f"How many cards are in player {self.opponent_player}'s hand?")
                data = receive_message(self.server_socket)
                self.network_traffic_lock.release()

                if data.isdigit():
                    self.opponents_hand_size = int(data)
                else:
                    self.status = NetworkHandlerStatus.ERROR
                    self.error = NetworkHandlerErrorStatus.INVALID_OPPONENT_HAND_LENGTH

                self.network_traffic_lock.acquire()
                send_message(self.server_socket,"Is the game over?")
                data = receive_message(self.server_socket)
                self.network_traffic_lock.release()

                if data == "Yes":
                    self.network_traffic_lock.acquire()
                    send_message(self.server_socket, "Who won the game?")
                    data = receive_message(self.server_socket)
                    self.network_traffic_lock.release()

                    # Win / lose / stalemate conditions
                    if self.player_number == 1 and data == "Player 1" or self.player_number == 2 and data == "Player 2":
                        self.game_result_text = pygame.font.SysFont("Arial",60).render("YOU WIN!", True, WHITE)
                    elif self.player_number == 2 and data == "Player 1" or self.player_number == 1 and data == "Player 2":
                        self.game_result_text = pygame.font.SysFont("Arial",60).render("Sorry, you lose!", True, WHITE)
                    elif data == "Stalemate":
                        self.game_result_text = pygame.font.SysFont("Arial",60).render("STALEMATE!", True, WHITE)
                    else:
                        self.status = NetworkHandlerStatus.ERROR
                        self.error = NetworkHandlerErrorStatus.INVALID_GAME_WINNER

                elif data != "No":
                    self.status = NetworkHandlerStatus.ERROR
                    self.error = NetworkHandlerErrorStatus.INVALID_GAME_RESULT_RESPONSE

            if network_timer == 0:
                network_timer = 20
            else:
                network_timer -= 1

        self.status = NetworkHandlerStatus.EXITED