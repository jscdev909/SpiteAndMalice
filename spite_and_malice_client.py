import re
import socket
import threading
import tomllib
import os
import sys
import pygame
from card import Card, CardPosition, receive_cards, send_cards
from socket_utils import send_message, receive_message
from path_utils import get_path
from enum import Enum
from pathlib import Path
from input_box import InputBox

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
    PAYOFF_PILE1_RECEIVE_ERROR = 3,
    PAYOFF_PILE2_RECEIVE_ERROR = 4,
    DRAW_PILE_RECEIVE_ERROR = 5,
    OTHER_PLAYER_DISCONNECTED = 6

class ShuffleStatus(Enum):
    UNSET = 0
    IN_PROGRESS = 1,
    COMPLETE = 2,
    ERROR = 3

class ShuffleErrorStatus(Enum):
    UNSET = 0,
    INCORRECT_DRAW_PILE_LENGTH = 1,
    EMPTY_DRAW_PILE = 2


class ClientError(Exception):
    pass

DARK_GREEN = (0, 100, 0)
WHITE = (255, 255, 255)

WINDOW_WIDTH = 925
WINDOW_HEIGHT = 950

FPS = 60

host = ""
port = 0

player_number = 0
player_name = ""
opponent_player = 0
payoff_pile1 = []
payoff_pile2 = []
draw_pile = []

initial_setup_status = SetupStatus.UNSET
initial_setup_error_status = SetupErrorStatus.UNSET

reshuffle_draw_pile_status = ShuffleStatus.UNSET
reshuffle_draw_pile_error_status = ShuffleErrorStatus.UNSET


def initial_setup(server_socket: socket.socket):

    global player_number, player_name, opponent_player, initial_setup_status, initial_setup_error_status
    global payoff_pile1, payoff_pile2, draw_pile, host, port

    # Connect to the server
    initial_setup_status = SetupStatus.CONNECTING_TO_SERVER
    server_socket.settimeout(10)

    try:
        server_socket.connect((host, port))
    except OSError:
        initial_setup_status = SetupStatus.ERROR
        initial_setup_error_status = SetupErrorStatus.COULD_NOT_CONNECT_TO_SERVER
        return

    # Receive player number
    send_message(server_socket, f"Player ready! Name: {player_name}")
    print("Sent player ready message to server")  # DEBUG
    data = receive_message(server_socket)
    print(data)

    if "You are player" in data and data[-1].isdigit():
        player_number = int(data[-1])
        print(f"Player number: {player_number}")
        initial_setup_status = SetupStatus.PLAYER_ASSIGNED
    elif "Game lobby is full":
        initial_setup_status = SetupStatus.ERROR
        initial_setup_error_status = SetupErrorStatus.GAME_LOBBY_FULL
        return

    if player_number == 1:
        opponent_player = 2
    elif player_number == 2:
        opponent_player = 1

    if player_number == 1:

        # Receive other player status message
        send_message(server_socket, "Has player 2 joined?")
        data = receive_message(server_socket)

        if data == "Waiting for player 2":
            initial_setup_status = SetupStatus.WAITING_FOR_OTHER_PLAYER

            # Wait for player 2
            while True:
                send_message(server_socket, "Has player 2 joined?")
                data = receive_message(server_socket)
                if data == "Player 2 has joined":
                    break
                else:
                    pygame.time.wait(2000)


    initial_setup_status = SetupStatus.RECEIVING_CARD_DATA
    send_message(server_socket, "Awaiting card data")
    print("Sent awaiting card data message to server")  # DEBUG

    # Receive payoff pile 1
    print("Receiving payoff pile 1")
    data = receive_message(server_socket)

    if data == "Sending payoff pile 1":
        payoff_pile1 = receive_cards(server_socket, 20)
        if not payoff_pile1:
            initial_setup_status = SetupStatus.ERROR
            initial_setup_error_status = SetupErrorStatus.PAYOFF_PILE1_RECEIVE_ERROR
            return
        print("Payoff pile 1 received on client:")
        for payoff_pile_card in payoff_pile1:
            print(f"{payoff_pile_card.name}:{payoff_pile_card.order}")

    # Receive payoff pile 2
    print("Receiving payoff pile 2")
    data = receive_message(server_socket)

    if data == "Sending payoff pile 2":
        payoff_pile2 = receive_cards(server_socket, 20)
        if not payoff_pile2:
            initial_setup_status = SetupStatus.ERROR
            initial_setup_error_status = SetupErrorStatus.PAYOFF_PILE2_RECEIVE_ERROR
            return
        print("Payoff pile 2 received on client:")
        for payoff_pile_card in payoff_pile2:
            print(f"{payoff_pile_card.name}:{payoff_pile_card.order}")

    # Receive draw pile
    print("Receiving draw pile")
    data = receive_message(server_socket)

    if data == "Sending draw pile":
        draw_pile = receive_cards(server_socket, 168)
        if not draw_pile:
            initial_setup_status = SetupStatus.ERROR
            initial_setup_error_status = SetupErrorStatus.DRAW_PILE_RECEIVE_ERROR
            return
        print("Draw pile received on client:")
        for draw_pile_card in draw_pile:
            print(f"{draw_pile_card.name}:{draw_pile_card.order}")

    initial_setup_status = SetupStatus.OTHER_PLAYER_STATUS_CHECK
    send_message(server_socket, "Is the other player still connected?")
    data = receive_message(server_socket)

    if data == "No":
        initial_setup_status = SetupStatus.ERROR
        initial_setup_error_status = SetupErrorStatus.OTHER_PLAYER_DISCONNECTED
        return

    while True:
        send_message(server_socket,"Have both players received the decks and piles?")
        data = receive_message(server_socket)
        if data == "Yes":
            break
        elif data == "No":
            pygame.time.wait(2000)

    initial_setup_status = SetupStatus.COMPLETE
    return


def reshuffle_draw_pile(server_socket: socket.socket, cards_to_shuffle: list[Card]):

    global draw_pile, player_number, reshuffle_draw_pile_status, reshuffle_draw_pile_error_status

    reshuffle_draw_pile_status = ShuffleStatus.IN_PROGRESS

    # Send request to server first
    send_message(server_socket, "Draw pile needs to be reshuffled")

    # Then send new draw pile length
    send_message(server_socket, str(len(draw_pile) + len(cards_to_shuffle)))

    # DEBUG
    print(
        f"New draw pile length sent to server from client {player_number}: {str(len(draw_pile) + len(cards_to_shuffle))}")

    response = receive_message(server_socket)
    if response == "Ready to receive new draw pile cards":
        print(f"Sending new draw pile cards - player {player_number}")  # DEBUG
        send_message(server_socket, str(len(cards_to_shuffle)))
        send_cards(server_socket, cards_to_shuffle)

    print(f"Requesting the new draw pile - player {player_number}")  # DEBUG
    send_message(server_socket, "Please send the draw pile")
    draw_pile_length = receive_message(server_socket)
    print(f"Draw pile length from server: {draw_pile_length}")  # DEBUG

    if draw_pile_length and draw_pile_length.strip().isdigit():
        draw_pile_length = int(draw_pile_length.strip())
    else:
        reshuffle_draw_pile_status = ShuffleStatus.ERROR
        reshuffle_draw_pile_error_status = ShuffleErrorStatus.INCORRECT_DRAW_PILE_LENGTH
        return

    draw_pile = receive_cards(server_socket, draw_pile_length)

    if not draw_pile:
        reshuffle_draw_pile_status = ShuffleStatus.ERROR
        reshuffle_draw_pile_error_status = ShuffleErrorStatus.EMPTY_DRAW_PILE
        return

    print(f"Listing new draw pile cards received for client {player_number}")

    # DEBUG
    for draw_pile_card in draw_pile:
        print(f"{draw_pile_card.name}: {draw_pile_card.order}")

    shuffle_sound_effect = pygame.mixer.Sound(
        get_path("assets/shuffle_cards.wav"))
    shuffle_sound_effect.play()

    reshuffle_draw_pile_status = ShuffleStatus.COMPLETE

    return


def run_game(server_socket: socket.socket, display_surface: pygame.Surface) -> bool:

    global payoff_pile1, payoff_pile2, draw_pile, player_number, opponent_player
    global reshuffle_draw_pile_status, reshuffle_draw_pile_error_status

    socket_closed = False

    last_turn = 0
    current_turn = 0

    current_hand = []
    draggable_cards = []
    draggable_cards_set = False
    draw_pile_needs_to_be_reshuffled = False

    opponent_draw_count = 0
    opponents_hand_size = 0

    clock = pygame.time.Clock()

    first_turn = True

    discard_piles1 = [[], [], [], []]
    discard_piles1_rects = [None, None, None, None]

    discard_piles2 = [[], [], [], []]
    discard_piles2_rects = [None, None, None, None]

    build_piles = [[], [], [], []]
    build_piles_rects = [None, None, None, None]

    card_back = pygame.image.load(
        get_path("assets/card_back_red.png")).convert_alpha()
    card_back = pygame.transform.scale(card_back, (100, 150))
    card_back_rect = card_back.get_rect()

    font = pygame.font.SysFont("Arial", 30)
    game_result_font = pygame.font.SysFont("Arial", 60)

    currently_dragging_card = False
    card_being_dragged = None

    game_result_determined = False

    original_dragging_x = 0
    original_dragging_y = 0


    running = True

    while running:

        clock.tick(FPS)

        if reshuffle_draw_pile_status == ShuffleStatus.UNSET:
            send_message(server_socket, "Is the other player still connected?")
            data = receive_message(server_socket)
            if data == "No":
                raise ClientError("Other player disconnected!")

            if current_turn == 0:
                send_message(server_socket, "Whose turn is it?")
                data = receive_message(server_socket)

                if data:
                    if data[-1].isdigit() and int(data[-1]) != current_turn:
                        draggable_cards_set = False
                else:
                    raise ClientError("Could not receive current turn number from server")

                if data == "Player 1":
                    current_turn = 1
                elif data == "Player 2":
                    current_turn = 2

        if reshuffle_draw_pile_status == ShuffleStatus.COMPLETE and reshuffle_draw_pile_error_status == ShuffleErrorStatus.UNSET:
            reshuffle_draw_pile_status = ShuffleStatus.UNSET
            draggable_cards_set = False
        elif reshuffle_draw_pile_status == ShuffleStatus.ERROR:
            if reshuffle_draw_pile_error_status == ShuffleErrorStatus.INCORRECT_DRAW_PILE_LENGTH:
                raise ClientError("Incorrect draw pile length received from server")
            elif reshuffle_draw_pile_error_status == ShuffleErrorStatus.EMPTY_DRAW_PILE:
                raise ClientError("Empty draw pile received from server")

        if current_turn == player_number:
            opponent_draw_count = 0
            if not draggable_cards_set and reshuffle_draw_pile_status == ShuffleStatus.UNSET:
                draggable_cards = []
                draggable_cards += current_hand
                if player_number == 1:
                    if discard_piles1[0] and discard_piles1[0][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles1[0][-1])
                    if discard_piles1[1] and discard_piles1[1][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles1[1][-1])
                    if discard_piles1[2] and discard_piles1[2][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles1[2][-1])
                    if discard_piles1[3] and discard_piles1[3][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles1[3][-1])
                    if payoff_pile1:
                        if payoff_pile1[-1] not in draggable_cards:
                            draggable_cards.append(payoff_pile1[-1])
                elif player_number == 2:
                    if discard_piles2[0] and discard_piles2[0][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles2[0][-1])
                    if discard_piles2[1] and discard_piles2[1][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles2[1][-1])
                    if discard_piles2[2] and discard_piles2[2][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles2[2][-1])
                    if discard_piles2[3] and discard_piles2[3][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles2[3][-1])
                    if payoff_pile2:
                        if payoff_pile2[-1] not in draggable_cards:
                            draggable_cards.append(payoff_pile2[-1])
                draggable_cards_set = True

                print("DEBUG------------------")
                print(f"Player {player_number}'s draggable cards this turn:")
                print([dbg_card.name for dbg_card in draggable_cards])

            elif reshuffle_draw_pile_status == ShuffleStatus.IN_PROGRESS:
                draggable_cards = []

        else:

            if not draggable_cards_set:
                draggable_cards = []
                draggable_cards_set = True

            if reshuffle_draw_pile_status == ShuffleStatus.UNSET:
                send_message(server_socket, f"How many cards has player {opponent_player} drawn this turn?")
                data = receive_message(server_socket)

                if data.isdigit():

                    #print(f"DEBUG: Opponent has drawn {int(data)} cards this turn")
                    if int(data) != opponent_draw_count:
                        for _ in range(opponent_draw_count, int(data), 1):
                            # Cards disappear into the void (intentional)
                            draw_pile.pop()
                        opponent_draw_count = int(data)
                else:
                    raise ClientError("Received invalid number of opponent draws from server")

                send_message(server_socket, f"What was player {opponent_player}'s last move?")
                data = receive_message(server_socket)
                if data != "Nothing":
                    card_name = ""
                    pattern = r"moved\b(.*)\bfrom"
                    first_match = re.search(pattern, data)
                    if first_match:
                        card_name = first_match.group(1).strip()
                    else:
                        raise ClientError("Could not parse card name from server message")
                    moved_from = ""
                    pattern = r"from\b(.*)\bto"
                    first_match = re.search(pattern, data)
                    if first_match:
                        moved_from = first_match.group(1).strip()
                    else:
                        raise ClientError("Could not parse 'moved from' location from server message")
                    moved_to = ""
                    pattern = r"to\b(.*)$"
                    first_match = re.search(pattern, data)
                    if first_match:
                        moved_to = first_match.group(1).strip()
                    else:
                        raise ClientError("Could not parse 'moved to' location from server message")

                    if moved_from == "hand":

                        # Receive a card from the server
                        received_card = receive_cards(server_socket, 1)[0]

                        if moved_to == "discard pile 0":
                            if opponent_player == 1:
                                discard_piles1[0].append(received_card)
                            elif opponent_player == 2:
                                discard_piles2[0].append(received_card)
                            last_turn = current_turn
                            current_turn = 0
                        elif moved_to == "discard pile 1":
                            if opponent_player == 1:
                                discard_piles1[1].append(received_card)
                            elif opponent_player == 2:
                                discard_piles2[1].append(received_card)
                            last_turn = current_turn
                            current_turn = 0
                        elif moved_to == "discard pile 2":
                            if opponent_player == 1:
                                discard_piles1[2].append(received_card)
                            elif opponent_player == 2:
                                discard_piles2[2].append(received_card)
                            last_turn = current_turn
                            current_turn = 0
                        elif moved_to == "discard pile 3":
                            if opponent_player == 1:
                                discard_piles1[3].append(received_card)
                            elif opponent_player == 2:
                                discard_piles2[3].append(received_card)
                            last_turn = current_turn
                            current_turn = 0
                        elif moved_to == "build pile 0":
                            build_piles[0].append(received_card)
                        elif moved_to == "build pile 1":
                            build_piles[1].append(received_card)
                        elif moved_to == "build pile 2":
                            build_piles[2].append(received_card)
                        elif moved_to == "build pile 3":
                            build_piles[3].append(received_card)

                    elif moved_from == "payoff pile":
                        if moved_to == "build pile 0":
                            if opponent_player == 1:
                                if payoff_pile1[-1].name == card_name:
                                    build_piles[0].append(payoff_pile1.pop())
                                    # Flip over next card
                                    if payoff_pile1:
                                        payoff_pile1[-1].position = CardPosition.FACE_UP
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if payoff_pile2[-1].name == card_name:
                                    build_piles[0].append(payoff_pile2.pop())
                                    # Flip over next card
                                    if payoff_pile2:
                                        payoff_pile2[-1].position = CardPosition.FACE_UP
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 1":
                            if opponent_player == 1:
                                if payoff_pile1[-1].name == card_name:
                                    build_piles[1].append(payoff_pile1.pop())
                                    # Flip over next card
                                    if payoff_pile1:
                                        payoff_pile1[-1].position = CardPosition.FACE_UP
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if payoff_pile2[-1].name == card_name:
                                    build_piles[1].append(payoff_pile2.pop())
                                    # Flip over next card
                                    if payoff_pile2:
                                        payoff_pile2[-1].position = CardPosition.FACE_UP
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 2":
                            if opponent_player == 1:
                                if payoff_pile1[-1].name == card_name:
                                    build_piles[2].append(payoff_pile1.pop())
                                    # Flip over next card
                                    if payoff_pile1:
                                        payoff_pile1[-1].position = CardPosition.FACE_UP
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if payoff_pile2[-1].name == card_name:
                                    build_piles[2].append(payoff_pile2.pop())
                                    # Flip over next card
                                    if payoff_pile2:
                                        payoff_pile2[-1].position = CardPosition.FACE_UP
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 3":
                            if opponent_player == 1:
                                if payoff_pile1[-1].name == card_name:
                                    build_piles[3].append(payoff_pile1.pop())
                                    # Flip over next card
                                    if payoff_pile1:
                                        payoff_pile1[-1].position = CardPosition.FACE_UP
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if payoff_pile2[-1].name == card_name:
                                    build_piles[3].append(payoff_pile2.pop())
                                    # Flip over next card
                                    if payoff_pile2:
                                        payoff_pile2[-1].position = CardPosition.FACE_UP
                                else:
                                    raise ClientError("Issue syncing cards with the server")

                    elif moved_from == "discard pile 0":
                        if moved_to == "build pile 0":
                            if opponent_player == 1:
                                if card_name == discard_piles1[0][-1].name:
                                    build_piles[0].append(discard_piles1[0].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[0][-1].name:
                                    build_piles[0].append(discard_piles2[0].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 1":
                            if opponent_player == 1:
                                if card_name == discard_piles1[0][-1].name:
                                    build_piles[1].append(discard_piles1[0].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[0][-1].name:
                                    build_piles[1].append(discard_piles2[0].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 2":
                            if opponent_player == 1:
                                if card_name == discard_piles1[0][-1].name:
                                    build_piles[2].append(discard_piles1[0].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[0][-1].name:
                                    build_piles[2].append(discard_piles2[0].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 3":
                            if opponent_player == 1:
                                if card_name == discard_piles1[0][-1].name:
                                    build_piles[3].append(discard_piles1[0].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[0][-1].name:
                                    build_piles[3].append(discard_piles2[0].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")

                    elif moved_from == "discard pile 1":
                        if moved_to == "build pile 0":
                            if opponent_player == 1:
                                if card_name == discard_piles1[1][-1].name:
                                    build_piles[0].append(discard_piles1[1].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[1][-1].name:
                                    build_piles[0].append(discard_piles2[1].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 1":
                            if opponent_player == 1:
                                if card_name == discard_piles1[1][-1].name:
                                    build_piles[1].append(discard_piles1[1].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[1][-1].name:
                                    build_piles[1].append(discard_piles2[1].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 2":
                            if opponent_player == 1:
                                if card_name == discard_piles1[1][-1].name:
                                    build_piles[2].append(discard_piles1[1].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[1][-1].name:
                                    build_piles[2].append(discard_piles2[1].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 3":
                            if opponent_player == 1:
                                if card_name == discard_piles1[1][-1].name:
                                    build_piles[3].append(discard_piles1[1].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[1][-1].name:
                                    build_piles[3].append(discard_piles2[1].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")

                    elif moved_from == "discard pile 2":
                        if moved_to == "build pile 0":
                            if opponent_player == 1:
                                if card_name == discard_piles1[2][-1].name:
                                    build_piles[0].append(discard_piles1[2].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[2][-1].name:
                                    build_piles[0].append(discard_piles2[2].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 1":
                            if opponent_player == 1:
                                if card_name == discard_piles1[2][-1].name:
                                    build_piles[1].append(discard_piles1[2].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[2][-1].name:
                                    build_piles[1].append(discard_piles2[2].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 2":
                            if opponent_player == 1:
                                if card_name == discard_piles1[2][-1].name:
                                    build_piles[2].append(discard_piles1[2].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[2][-1].name:
                                    build_piles[2].append(discard_piles2[2].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 3":
                            if opponent_player == 1:
                                if card_name == discard_piles1[2][-1].name:
                                    build_piles[3].append(discard_piles1[2].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[2][-1].name:
                                    build_piles[3].append(discard_piles2[2].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")

                    elif moved_from == "discard pile 3":
                        if moved_to == "build pile 0":
                            if opponent_player == 1:
                                if card_name == discard_piles1[3][-1].name:
                                    build_piles[0].append(discard_piles1[3].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[3][-1].name:
                                    build_piles[0].append(discard_piles2[3].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 1":
                            if opponent_player == 1:
                                if card_name == discard_piles1[3][-1].name:
                                    build_piles[1].append(discard_piles1[3].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[3][-1].name:
                                    build_piles[1].append(discard_piles2[3].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 2":
                            if opponent_player == 1:
                                if card_name == discard_piles1[3][-1].name:
                                    build_piles[2].append(discard_piles1[3].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[3][-1].name:
                                    build_piles[2].append(discard_piles2[3].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 3":
                            if opponent_player == 1:
                                if card_name == discard_piles1[3][-1].name:
                                    build_piles[3].append(discard_piles1[3].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                if card_name == discard_piles2[3][-1].name:
                                    build_piles[3].append(discard_piles2[3].pop())
                                else:
                                    raise ClientError("Issue syncing cards with the server")


        cards_to_shuffle = []
        if len(build_piles[0]) == 12:
            cards_to_shuffle += build_piles[0]
            build_piles[0] = []
            draw_pile_needs_to_be_reshuffled = True
        if len(build_piles[1]) == 12:
            cards_to_shuffle += build_piles[1]
            build_piles[1] = []
            draw_pile_needs_to_be_reshuffled = True
        if len(build_piles[2]) == 12:
            cards_to_shuffle += build_piles[2]
            build_piles[2] = []
            draw_pile_needs_to_be_reshuffled = True
        if len(build_piles[3]) == 12:
            cards_to_shuffle += build_piles[3]
            build_piles[3] = []
            draw_pile_needs_to_be_reshuffled = True

        if draw_pile_needs_to_be_reshuffled:

            shuffle_deck_thread = threading.Thread(target=reshuffle_draw_pile, args=(server_socket, cards_to_shuffle))
            shuffle_deck_thread.start()
            draw_pile_needs_to_be_reshuffled = False


        if not current_hand and current_turn == player_number and reshuffle_draw_pile_status == ShuffleStatus.UNSET:
            send_message(server_socket, f"Player {player_number} draws 5 cards")
            for _ in range(0, 5, 1):
                current_hand.append(draw_pile.pop())
            draw_cards_sound_effect = pygame.mixer.Sound(get_path("assets/dealing_cards.wav"))
            draw_cards_sound_effect.play()
            draggable_cards_set = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    if currently_dragging_card:
                        if card_being_dragged.rect.colliderect(build_piles_rects[0]):
                            if ((build_piles[0] and card_being_dragged.rank == build_piles[0][-1].rank + 1) or
                                ((not build_piles[0] and card_being_dragged.rank == 1) or card_being_dragged.rank == 13) or
                                    card_being_dragged.rank == len(build_piles[0]) + 1):

                                card_being_dragged.rect.x = build_piles_rects[0].x
                                card_being_dragged.rect.y = build_piles_rects[0].y
                                draggable_cards.remove(card_being_dragged)

                                if player_number == 1:
                                    if card_being_dragged in current_hand:
                                        current_hand.remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to build pile 0")
                                        card_being_dragged.position = CardPosition.FACE_UP
                                    elif card_being_dragged in discard_piles1[0]:
                                        discard_piles1[0].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 0 to build pile 0")
                                    elif card_being_dragged in discard_piles1[1]:
                                        discard_piles1[1].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 1 to build pile 0")
                                    elif card_being_dragged in discard_piles1[2]:
                                        discard_piles1[2].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 2 to build pile 0")
                                    elif card_being_dragged in discard_piles1[3]:
                                        discard_piles1[3].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 3 to build pile 0")
                                    elif card_being_dragged in payoff_pile1:
                                        payoff_pile1.remove(card_being_dragged)
                                        # Flip over next card
                                        if payoff_pile1:
                                            payoff_pile1[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 0")

                                elif player_number == 2:
                                    if card_being_dragged in current_hand:
                                        current_hand.remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to build pile 0")
                                        card_being_dragged.position = CardPosition.FACE_UP
                                    elif card_being_dragged in discard_piles2[0]:
                                        discard_piles2[0].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 0 to build pile 0")
                                    elif card_being_dragged in discard_piles2[1]:
                                        discard_piles2[1].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 1 to build pile 0")
                                    elif card_being_dragged in discard_piles2[2]:
                                        discard_piles2[2].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 2 to build pile 0")
                                    elif card_being_dragged in discard_piles2[3]:
                                        discard_piles2[3].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 3 to build pile 0")
                                    elif card_being_dragged in payoff_pile2:
                                        payoff_pile2.remove(card_being_dragged)
                                        # Flip over next card
                                        if payoff_pile2:
                                            payoff_pile2[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 0")

                                build_piles[0].append(card_being_dragged)

                                currently_dragging_card = False
                                card_being_dragged = None

                                draggable_cards_set = False

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(build_piles_rects[1]):
                            if ((build_piles[1] and card_being_dragged.rank == build_piles[1][-1].rank + 1) or
                                ((not build_piles[1] and card_being_dragged.rank == 1) or card_being_dragged.rank == 13) or
                                    card_being_dragged.rank == len(build_piles[1]) + 1):

                                card_being_dragged.rect.x = build_piles_rects[1].x
                                card_being_dragged.rect.y = build_piles_rects[1].y
                                draggable_cards.remove(card_being_dragged)

                                if player_number == 1:
                                    if card_being_dragged in current_hand:
                                        current_hand.remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to build pile 1")
                                        card_being_dragged.position = CardPosition.FACE_UP
                                    elif card_being_dragged in discard_piles1[0]:
                                        discard_piles1[0].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 0 to build pile 1")
                                    elif card_being_dragged in discard_piles1[1]:
                                        discard_piles1[1].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 1 to build pile 1")
                                    elif card_being_dragged in discard_piles1[2]:
                                        discard_piles1[2].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 2 to build pile 1")
                                    elif card_being_dragged in discard_piles1[3]:
                                        discard_piles1[3].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 3 to build pile 1")
                                    elif card_being_dragged in payoff_pile1:
                                        payoff_pile1.remove(card_being_dragged)
                                        # Flip over next card
                                        if payoff_pile1:
                                            payoff_pile1[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 1")

                                elif player_number == 2:
                                    if card_being_dragged in current_hand:
                                        current_hand.remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to build pile 1")
                                        card_being_dragged.position = CardPosition.FACE_UP
                                    elif card_being_dragged in discard_piles2[0]:
                                        discard_piles2[0].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 0 to build pile 1")
                                    elif card_being_dragged in discard_piles2[1]:
                                        discard_piles2[1].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 1 to build pile 1")
                                    elif card_being_dragged in discard_piles2[2]:
                                        discard_piles2[2].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 2 to build pile 1")
                                    elif card_being_dragged in discard_piles2[3]:
                                        discard_piles2[3].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 3 to build pile 1")
                                    elif card_being_dragged in payoff_pile2:
                                        payoff_pile2.remove(card_being_dragged)
                                        # Flip over next card
                                        if payoff_pile2:
                                            payoff_pile2[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 1")

                                build_piles[1].append(card_being_dragged)

                                currently_dragging_card = False
                                card_being_dragged = None

                                draggable_cards_set = False

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None


                        elif card_being_dragged.rect.colliderect(build_piles_rects[2]):
                            if ((build_piles[2] and card_being_dragged.rank == build_piles[2][-1].rank + 1) or
                                ((not build_piles[2] and card_being_dragged.rank == 1) or card_being_dragged.rank == 13) or
                                    card_being_dragged.rank == len(build_piles[2]) + 1):

                                card_being_dragged.rect.x = build_piles_rects[2].x
                                card_being_dragged.rect.y = build_piles_rects[2].y
                                draggable_cards.remove(card_being_dragged)

                                if player_number == 1:
                                    if card_being_dragged in current_hand:
                                        current_hand.remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to build pile 2")
                                        card_being_dragged.position = CardPosition.FACE_UP
                                    elif card_being_dragged in discard_piles1[0]:
                                        discard_piles1[0].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 0 to build pile 2")
                                    elif card_being_dragged in discard_piles1[1]:
                                        discard_piles1[1].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 1 to build pile 2")
                                    elif card_being_dragged in discard_piles1[2]:
                                        discard_piles1[2].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 2 to build pile 2")
                                    elif card_being_dragged in discard_piles1[3]:
                                        discard_piles1[3].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 3 to build pile 2")
                                    elif card_being_dragged in payoff_pile1:
                                        payoff_pile1.remove(card_being_dragged)
                                        # Flip over next card
                                        if payoff_pile1:
                                            payoff_pile1[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 2")
                                elif player_number == 2:
                                    if card_being_dragged in current_hand:
                                        current_hand.remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to build pile 2")
                                        card_being_dragged.position = CardPosition.FACE_UP
                                    elif card_being_dragged in discard_piles2[0]:
                                        discard_piles2[0].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 0 to build pile 2")
                                    elif card_being_dragged in discard_piles2[1]:
                                        discard_piles2[1].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 1 to build pile 2")
                                    elif card_being_dragged in discard_piles2[2]:
                                        discard_piles2[2].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 2 to build pile 2")
                                    elif card_being_dragged in discard_piles2[3]:
                                        discard_piles2[3].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 3 to build pile 2")
                                    elif card_being_dragged in payoff_pile2:
                                        payoff_pile2.remove(card_being_dragged)
                                        # Flip over next card
                                        if payoff_pile2:
                                            payoff_pile2[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 2")

                                build_piles[2].append(card_being_dragged)

                                currently_dragging_card = False
                                card_being_dragged = None

                                draggable_cards_set = False

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(build_piles_rects[3]):
                            if ((build_piles[3] and card_being_dragged.rank == build_piles[3][-1].rank + 1) or
                                ((not build_piles[3] and card_being_dragged.rank == 1) or card_being_dragged.rank == 13) or
                                    card_being_dragged.rank == len(build_piles[3]) + 1):

                                card_being_dragged.rect.x = build_piles_rects[3].x
                                card_being_dragged.rect.y = build_piles_rects[3].y
                                draggable_cards.remove(card_being_dragged)

                                if player_number == 1:
                                    if card_being_dragged in current_hand:
                                        current_hand.remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to build pile 3")
                                        card_being_dragged.position = CardPosition.FACE_UP
                                    elif card_being_dragged in discard_piles1[0]:
                                        discard_piles1[0].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 0 to build pile 3")
                                    elif card_being_dragged in discard_piles1[1]:
                                        discard_piles1[1].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 1 to build pile 3")
                                    elif card_being_dragged in discard_piles1[2]:
                                        discard_piles1[2].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 2 to build pile 3")
                                    elif card_being_dragged in discard_piles1[3]:
                                        discard_piles1[3].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 3 to build pile 3")
                                    elif card_being_dragged in payoff_pile1:
                                        payoff_pile1.remove(card_being_dragged)
                                        # Flip over next card
                                        if payoff_pile1:
                                            payoff_pile1[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 3")
                                elif player_number == 2:
                                    if card_being_dragged in current_hand:
                                        current_hand.remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to build pile 3")
                                        card_being_dragged.position = CardPosition.FACE_UP
                                    elif card_being_dragged in discard_piles2[0]:
                                        discard_piles2[0].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 0 to build pile 3")
                                    elif card_being_dragged in discard_piles2[1]:
                                        discard_piles2[1].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 1 to build pile 3")
                                    elif card_being_dragged in discard_piles2[2]:
                                        discard_piles2[2].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 2 to build pile 3")
                                    elif card_being_dragged in discard_piles2[3]:
                                        discard_piles2[3].remove(card_being_dragged)
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their discard pile 3 to build pile 3")
                                    elif card_being_dragged in payoff_pile2:
                                        payoff_pile2.remove(card_being_dragged)
                                        # Flip over next card
                                        if payoff_pile2:
                                            payoff_pile2[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 3")

                                build_piles[3].append(card_being_dragged)

                                currently_dragging_card = False
                                card_being_dragged = None

                                draggable_cards_set = False

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(discard_piles1_rects[0]):
                            if player_number == 1:
                                if card_being_dragged in current_hand:
                                    card_being_dragged.x = discard_piles1_rects[0].x
                                    card_being_dragged.y = discard_piles1_rects[0].y
                                    draggable_cards.remove(card_being_dragged)
                                    current_hand.remove(card_being_dragged)
                                    send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to discard pile 0")
                                    card_being_dragged.position = CardPosition.FACE_UP
                                    discard_piles1[0].append(card_being_dragged)
                                    currently_dragging_card = False
                                    card_being_dragged = None
                                    send_message(server_socket, f"Player {player_number} ended their turn")
                                    last_turn = current_turn
                                    current_turn = 0

                                else:
                                    card_being_dragged.rect.x = original_dragging_x
                                    card_being_dragged.rect.y = original_dragging_y
                                    currently_dragging_card = False
                                    card_being_dragged = None

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(discard_piles1_rects[1]):
                            if player_number == 1:
                                if card_being_dragged in current_hand:
                                    card_being_dragged.x = discard_piles1_rects[1].x
                                    card_being_dragged.y = discard_piles1_rects[1].y
                                    draggable_cards.remove(card_being_dragged)
                                    current_hand.remove(card_being_dragged)
                                    send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to discard pile 1")
                                    card_being_dragged.position = CardPosition.FACE_UP
                                    discard_piles1[1].append(card_being_dragged)
                                    currently_dragging_card = False
                                    card_being_dragged = None
                                    send_message(server_socket, f"Player {player_number} ended their turn")
                                    last_turn = current_turn
                                    current_turn = 0

                                else:
                                    card_being_dragged.rect.x = original_dragging_x
                                    card_being_dragged.rect.y = original_dragging_y
                                    currently_dragging_card = False
                                    card_being_dragged = None

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(discard_piles1_rects[2]):
                            if player_number == 1:
                                if card_being_dragged in current_hand:
                                    card_being_dragged.x = discard_piles1_rects[2].x
                                    card_being_dragged.y = discard_piles1_rects[2].y
                                    draggable_cards.remove(card_being_dragged)
                                    current_hand.remove(card_being_dragged)
                                    send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to discard pile 2")
                                    card_being_dragged.position = CardPosition.FACE_UP
                                    discard_piles1[2].append(card_being_dragged)
                                    currently_dragging_card = False
                                    card_being_dragged = None
                                    send_message(server_socket, f"Player {player_number} ended their turn")
                                    last_turn = current_turn
                                    current_turn = 0

                                else:
                                    card_being_dragged.rect.x = original_dragging_x
                                    card_being_dragged.rect.y = original_dragging_y
                                    currently_dragging_card = False
                                    card_being_dragged = None

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(discard_piles1_rects[3]):
                            if player_number == 1:
                                if card_being_dragged in current_hand:
                                    card_being_dragged.x = discard_piles1_rects[3].x
                                    card_being_dragged.y = discard_piles1_rects[3].y
                                    draggable_cards.remove(card_being_dragged)
                                    current_hand.remove(card_being_dragged)
                                    send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to discard pile 3")
                                    card_being_dragged.position = CardPosition.FACE_UP
                                    discard_piles1[3].append(card_being_dragged)
                                    currently_dragging_card = False
                                    card_being_dragged = None
                                    send_message(server_socket, f"Player {player_number} ended their turn")
                                    last_turn = current_turn
                                    current_turn = 0

                                else:
                                    card_being_dragged.rect.x = original_dragging_x
                                    card_being_dragged.rect.y = original_dragging_y
                                    currently_dragging_card = False
                                    card_being_dragged = None

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(discard_piles2_rects[0]):
                            if player_number == 2:
                                if card_being_dragged in current_hand:
                                    card_being_dragged.x = discard_piles2_rects[0].x
                                    card_being_dragged.y = discard_piles2_rects[0].y
                                    draggable_cards.remove(card_being_dragged)
                                    current_hand.remove(card_being_dragged)
                                    send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to discard pile 0")
                                    card_being_dragged.position = CardPosition.FACE_UP
                                    discard_piles2[0].append(card_being_dragged)
                                    currently_dragging_card = False
                                    card_being_dragged = None
                                    send_message(server_socket, f"Player {player_number} ended their turn")
                                    last_turn = current_turn
                                    current_turn = 0

                                else:
                                    card_being_dragged.rect.x = original_dragging_x
                                    card_being_dragged.rect.y = original_dragging_y
                                    currently_dragging_card = False
                                    card_being_dragged = None

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None


                        elif card_being_dragged.rect.colliderect(discard_piles2_rects[1]):
                            if player_number == 2:
                                if card_being_dragged in current_hand:
                                    card_being_dragged.x = discard_piles2_rects[1].x
                                    card_being_dragged.y = discard_piles2_rects[1].y
                                    draggable_cards.remove(card_being_dragged)
                                    current_hand.remove(card_being_dragged)
                                    send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to discard pile 1")
                                    card_being_dragged.position = CardPosition.FACE_UP
                                    discard_piles2[1].append(card_being_dragged)
                                    currently_dragging_card = False
                                    card_being_dragged = None
                                    send_message(server_socket, f"Player {player_number} ended their turn")
                                    last_turn = current_turn
                                    current_turn = 0


                                else:
                                    card_being_dragged.rect.x = original_dragging_x
                                    card_being_dragged.rect.y = original_dragging_y
                                    currently_dragging_card = False
                                    card_being_dragged = None

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(discard_piles2_rects[2]):
                            if player_number == 2:
                                if card_being_dragged in current_hand:
                                    card_being_dragged.x = discard_piles2_rects[2].x
                                    card_being_dragged.y = discard_piles2_rects[2].y
                                    draggable_cards.remove(card_being_dragged)
                                    current_hand.remove(card_being_dragged)
                                    send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to discard pile 2")
                                    card_being_dragged.position = CardPosition.FACE_UP
                                    discard_piles2[2].append(card_being_dragged)
                                    currently_dragging_card = False
                                    card_being_dragged = None
                                    send_message(server_socket, f"Player {player_number} ended their turn")
                                    last_turn = current_turn
                                    current_turn = 0

                                else:
                                    card_being_dragged.rect.x = original_dragging_x
                                    card_being_dragged.rect.y = original_dragging_y
                                    currently_dragging_card = False
                                    card_being_dragged = None

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        elif card_being_dragged.rect.colliderect(discard_piles2_rects[3]):
                            if player_number == 2:
                                if card_being_dragged in current_hand:
                                    card_being_dragged.x = discard_piles2_rects[3].x
                                    card_being_dragged.y = discard_piles2_rects[3].y
                                    draggable_cards.remove(card_being_dragged)
                                    current_hand.remove(card_being_dragged)
                                    send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their hand to discard pile 3")
                                    card_being_dragged.position = CardPosition.FACE_UP
                                    discard_piles2[3].append(card_being_dragged)
                                    currently_dragging_card = False
                                    card_being_dragged = None
                                    send_message(server_socket, f"Player {player_number} ended their turn")
                                    last_turn = current_turn
                                    current_turn = 0

                                else:
                                    card_being_dragged.rect.x = original_dragging_x
                                    card_being_dragged.rect.y = original_dragging_y
                                    currently_dragging_card = False
                                    card_being_dragged = None

                            else:
                                card_being_dragged.rect.x = original_dragging_x
                                card_being_dragged.rect.y = original_dragging_y
                                currently_dragging_card = False
                                card_being_dragged = None

                        else:
                            card_being_dragged.rect.x = original_dragging_x
                            card_being_dragged.rect.y = original_dragging_y
                            currently_dragging_card = False
                            card_being_dragged = None

        if pygame.mouse.get_pressed()[0]:

            mouse_x, mouse_y = pygame.mouse.get_pos()
            for card in draggable_cards:
                if card.rect.collidepoint(mouse_x, mouse_y) and not currently_dragging_card:
                    print("in here 10 - client")
                    original_dragging_x = card.rect.x
                    original_dragging_y = card.rect.y
                    card.rect.centerx = mouse_x
                    card.rect.centery = mouse_y
                    currently_dragging_card = True
                    card_being_dragged = card

            if currently_dragging_card:
                card_being_dragged.rect.centerx = mouse_x
                card_being_dragged.rect.centery = mouse_y

        display_surface.fill(DARK_GREEN)
        for i in range(0, len(current_hand), 1):
            if current_hand[i] != card_being_dragged:
                current_hand[i].rect.bottom = WINDOW_HEIGHT
                current_hand[i].rect.left = 190 + i * 110
                display_surface.blit(current_hand[i].surface, current_hand[i].rect)

        if player_number == 1:
            for stock_card in payoff_pile1:
                if stock_card != card_being_dragged:
                    if stock_card.position == CardPosition.FACE_UP:
                        stock_card.rect.left = 25
                        stock_card.rect.bottom = WINDOW_HEIGHT
                        display_surface.blit(stock_card.surface, stock_card.rect)
                    else:
                        card_back_rect.left = 25
                        card_back_rect.bottom = WINDOW_HEIGHT
                        display_surface.blit(card_back, card_back_rect)
        elif player_number == 2:
            for stock_card in payoff_pile2:
                if stock_card != card_being_dragged:
                    if stock_card.position == CardPosition.FACE_UP:
                        stock_card.rect.left = 25
                        stock_card.rect.bottom = WINDOW_HEIGHT
                        display_surface.blit(stock_card.surface, stock_card.rect)
                    else:
                        card_back_rect.left = 25
                        card_back_rect.bottom = WINDOW_HEIGHT
                        display_surface.blit(card_back, card_back_rect)

        if player_number == 1:
            for x in range(0, len(discard_piles1_rects), 1):
                if discard_piles1[x]:
                    for card in discard_piles1[x]:
                        if card != card_being_dragged:
                            if card.position == CardPosition.FACE_UP:
                                card.rect.x = 225 + (x * 125)
                                card.rect.y = 625
                                display_surface.blit(card.surface, card.rect)
                            else:
                                card_back_rect.x = 225 + (x * 125)
                                card_back_rect.y = 625
                                display_surface.blit(card_back, card_back_rect)
                else:
                    discard_piles1_rects[x] = pygame.draw.rect(display_surface, WHITE, (225 + (x * 125), 625, 100, 150), 2)
        elif player_number == 2:
            for x in range(0, len(discard_piles2_rects), 1):
                if discard_piles2[x]:
                    for card in discard_piles2[x]:
                        if card != card_being_dragged:
                            if card.position == CardPosition.FACE_UP:
                                card.rect.x = 225 + (x * 125)
                                card.rect.y = 625
                                display_surface.blit(card.surface, card.rect)
                            else:
                                card_back_rect.x = 225 + (x * 125)
                                card_back_rect.y = 625
                                display_surface.blit(card_back, card_back_rect)
                else:
                    discard_piles2_rects[x] = pygame.draw.rect(display_surface, WHITE,(225 + (x * 125), 625, 100, 150), 2)

        if player_number == 1:
            for y in range(0, len(build_piles_rects), 1):
                if build_piles[y]:
                    for card in build_piles[y]:
                        if card.position == CardPosition.FACE_UP:
                            card.rect.x = 225 + (y * 125)
                            card.rect.y = 400
                            display_surface.blit(card.surface, card.rect)
                        else:
                            card_back_rect.x = 225 + (y * 125)
                            card_back_rect.y = 400
                            display_surface.blit(card_back, card_back_rect)
                else:
                    build_piles_rects[y] = pygame.draw.rect(display_surface, WHITE, (225 + (y * 125), 400, 100, 150), 2)
        elif player_number == 2:
            for y in range(0, len(build_piles_rects), 1):
                if build_piles[y]:
                    for card in build_piles[y]:
                        if card.position == CardPosition.FACE_UP:
                            card.rect.x = WINDOW_WIDTH - 325 - (y * 125)
                            card.rect.y = 400
                            display_surface.blit(card.surface, card.rect)
                        else:
                            card_back_rect.x = WINDOW_WIDTH - 325 - (y * 125)
                            card_back_rect.y = 400
                            display_surface.blit(card_back, card_back_rect)
                else:
                    build_piles_rects[y] = pygame.draw.rect(display_surface, WHITE, (WINDOW_WIDTH - 325 - (y * 125), 400, 100, 150), 2)


        if player_number == 1:
            for z in range(0, len(discard_piles2_rects), 1):
                if discard_piles2[z]:
                    for card in discard_piles2[z]:
                        if card.position == CardPosition.FACE_UP:
                            card.rect.x = WINDOW_WIDTH - 325 - (z * 125)
                            card.rect.y = 175
                            display_surface.blit(card.surface, card.rect)
                        else:
                            card_back_rect.x = WINDOW_WIDTH - 325 - (z * 125)
                            card_back_rect.y = 175
                            display_surface.blit(card_back, card_back_rect)
                else:
                    discard_piles2_rects[z] = pygame.draw.rect(display_surface, WHITE,(WINDOW_WIDTH - 325 - (z * 125), 175, 100, 150), 2)
        elif player_number == 2:
            for z in range(0, len(discard_piles1_rects), 1):
                if discard_piles1[z]:
                    for card in discard_piles1[z]:
                        if card.position == CardPosition.FACE_UP:
                            card.rect.x = WINDOW_WIDTH - 325 - (z * 125)
                            card.rect.y = 175
                            display_surface.blit(card.surface, card.rect)
                        else:
                            card_back_rect.x = WINDOW_WIDTH - 325 - (z * 125)
                            card_back_rect.y = 175
                            display_surface.blit(card_back, card_back_rect)
                else:
                    discard_piles1_rects[z] = pygame.draw.rect(display_surface, WHITE, (WINDOW_WIDTH - 325 - (z * 125), 175, 100, 150), 2)


        if player_number == 1:
            for stock_card in payoff_pile2:
                if stock_card.position == CardPosition.FACE_UP:
                    stock_card.rect.right = WINDOW_WIDTH - 25
                    stock_card.rect.top = 0
                    display_surface.blit(stock_card.surface, stock_card.rect)
                else:
                    card_back_rect.right = WINDOW_WIDTH - 25
                    card_back_rect.top = 0
                    display_surface.blit(card_back, card_back_rect)
        if player_number == 2:
            for stock_card in payoff_pile1:
                if stock_card.position == CardPosition.FACE_UP:
                    stock_card.rect.right = WINDOW_WIDTH - 25
                    stock_card.rect.top = 0
                    display_surface.blit(stock_card.surface, stock_card.rect)
                else:
                    card_back_rect.right = WINDOW_WIDTH - 25
                    card_back_rect.top = 0
                    display_surface.blit(card_back, card_back_rect)

        if reshuffle_draw_pile_status == ShuffleStatus.UNSET:
            send_message(server_socket, f"How many cards are in player {opponent_player}'s hand?")
            data = receive_message(server_socket)
            if data.isdigit():
                opponents_hand_size = int(data)
            else:
                raise ClientError("Received an invalid number of cards in opponents hand")

        for i in range(0, opponents_hand_size, 1):
            card_back_rect.x = 190 + i * 110
            card_back_rect.y = 0
            display_surface.blit(card_back, card_back_rect)

        player_number1_text = font.render("Player 1", True, WHITE, DARK_GREEN)
        player_number1_rect = player_number1_text.get_rect()
        player_number2_text = font.render("Player 2", True, WHITE, DARK_GREEN)
        player_number2_rect = player_number2_text.get_rect()
        if player_number == 1:
            player_number1_rect.centerx = WINDOW_WIDTH - 100
            player_number1_rect.centery = WINDOW_HEIGHT - 100
            player_number2_rect.centerx = 100
            player_number2_rect.centery = 100
        elif player_number == 2:
            player_number1_rect.centerx = 100
            player_number1_rect.centery = 100
            player_number2_rect.centerx = WINDOW_WIDTH - 100
            player_number2_rect.centery = WINDOW_HEIGHT - 100

        display_surface.blit(player_number1_text, player_number1_rect)
        display_surface.blit(player_number2_text, player_number2_rect)

        if current_turn != 0:
            current_turn_text = font.render(f"Current turn:\n   Player {current_turn}", True, WHITE, DARK_GREEN)
            current_turn_rect = current_turn_text.get_rect()
            current_turn_rect.right = WINDOW_WIDTH - 25
            current_turn_rect.y = WINDOW_HEIGHT // 2
            display_surface.blit(current_turn_text, current_turn_rect)
        else:
            current_turn_text = font.render(f"Current turn:\n   Player {last_turn}", True, WHITE, DARK_GREEN)
            current_turn_rect = current_turn_text.get_rect()
            current_turn_rect.right = WINDOW_WIDTH - 25
            current_turn_rect.y = WINDOW_HEIGHT // 2
            display_surface.blit(current_turn_text, current_turn_rect)

        build_pile_value1_text = font.render(str(len(build_piles[0])), True, WHITE, DARK_GREEN)
        build_pile_value1_rect = build_pile_value1_text.get_rect()
        build_pile_value2_text = font.render(str(len(build_piles[1])), True, WHITE, DARK_GREEN)
        build_pile_value2_rect = build_pile_value2_text.get_rect()
        build_pile_value3_text = font.render(str(len(build_piles[2])), True, WHITE, DARK_GREEN)
        build_pile_value3_rect = build_pile_value3_text.get_rect()
        build_pile_value4_text = font.render(str(len(build_piles[3])), True, WHITE, DARK_GREEN)
        build_pile_value4_rect = build_pile_value4_text.get_rect()

        if player_number == 1:
            build_pile_value1_rect.x = 260
            build_pile_value1_rect.y = 550
            build_pile_value2_rect.x = 385
            build_pile_value2_rect.y = 550
            build_pile_value3_rect.x = 510
            build_pile_value3_rect.y = 550
            build_pile_value4_rect.x = 635
            build_pile_value4_rect.y = 550
        elif player_number == 2:
            build_pile_value1_rect.x = 635
            build_pile_value1_rect.y = 550
            build_pile_value2_rect.x = 510
            build_pile_value2_rect.y = 550
            build_pile_value3_rect.x = 385
            build_pile_value3_rect.y = 550
            build_pile_value4_rect.x = 260
            build_pile_value4_rect.y = 550

        display_surface.blit(build_pile_value1_text, build_pile_value1_rect)
        display_surface.blit(build_pile_value2_text, build_pile_value2_rect)
        display_surface.blit(build_pile_value3_text, build_pile_value3_rect)
        display_surface.blit(build_pile_value4_text, build_pile_value4_rect)

        payoff_pile1_remaining_cards_text = font.render(str(len(payoff_pile1)), True, WHITE, DARK_GREEN)
        payoff_pile1_remaining_cards_rect = payoff_pile1_remaining_cards_text.get_rect()
        payoff_pile2_remaining_cards_text = font.render(str(len(payoff_pile2)), True, WHITE, DARK_GREEN)
        payoff_pile2_remaining_cards_rect = payoff_pile2_remaining_cards_text.get_rect()

        if player_number == 1:
            payoff_pile1_remaining_cards_rect.x = 55
            payoff_pile1_remaining_cards_rect.y = 760
            payoff_pile2_remaining_cards_rect.x = WINDOW_WIDTH - 95
            payoff_pile2_remaining_cards_rect.y = 155
        elif player_number == 2:
            payoff_pile1_remaining_cards_rect.x = WINDOW_WIDTH - 95
            payoff_pile1_remaining_cards_rect.y = 155
            payoff_pile2_remaining_cards_rect.x = 55
            payoff_pile2_remaining_cards_rect.y = 760

        display_surface.blit(payoff_pile1_remaining_cards_text, payoff_pile1_remaining_cards_rect)
        display_surface.blit(payoff_pile2_remaining_cards_text, payoff_pile2_remaining_cards_rect)

        draw_pile_remaining_cards_text = font.render(f"Remaining\ndraw pile\ncards: {str(len(draw_pile))}", True, WHITE, DARK_GREEN)
        draw_pile_remaining_cards_rect = draw_pile_remaining_cards_text.get_rect()
        draw_pile_remaining_cards_rect.x = 25
        draw_pile_remaining_cards_rect.y = WINDOW_HEIGHT // 2
        display_surface.blit(draw_pile_remaining_cards_text, draw_pile_remaining_cards_rect)

        if reshuffle_draw_pile_status != ShuffleStatus.UNSET:
            if reshuffle_draw_pile_status == ShuffleStatus.IN_PROGRESS:
                reshuffling_text = font.render("Reshuffling draw pile, please wait...", True, WHITE, DARK_GREEN)
                reshuffling_rect = reshuffling_text.get_rect()
                reshuffling_rect.centerx = WINDOW_WIDTH // 2
                reshuffling_rect.centery = WINDOW_HEIGHT // 2
                display_surface.blit(reshuffling_text, reshuffling_rect)

        # Win / lose / stalemate conditions
        if ((not payoff_pile1 and player_number == 1) or (not payoff_pile2 and player_number == 2) or
            (not draw_pile and len(payoff_pile1) < len(payoff_pile2) and player_number == 1) or
            (not draw_pile and len(payoff_pile1) > len(payoff_pile2) and player_number == 2)):
            draggable_cards = []
            win_text = game_result_font.render("YOU WIN!", True, WHITE, DARK_GREEN)
            win_rect = win_text.get_rect()
            win_rect.centerx = WINDOW_WIDTH // 2
            win_rect.centery = WINDOW_HEIGHT // 2
            display_surface.blit(win_text, win_rect)
            game_result_determined = True
        elif ((not payoff_pile1 and player_number == 2) or (not payoff_pile2 and player_number == 1) or
            (not draw_pile and len(payoff_pile1) > len(payoff_pile2) and player_number == 1) or
            (not draw_pile and len(payoff_pile1) < len (payoff_pile2) and player_number == 2)):
            draggable_cards = []
            lose_text = game_result_font.render("Sorry, you lose!", True, WHITE, DARK_GREEN)
            lose_rect = lose_text.get_rect()
            lose_rect.centerx = WINDOW_WIDTH // 2
            lose_rect.centery = WINDOW_HEIGHT // 2
            display_surface.blit(lose_text, lose_rect)
            game_result_determined = True
        elif not draw_pile and len(payoff_pile1) == len(payoff_pile2):
            draggable_cards = []
            stalemate_text = game_result_font.render("STALEMATE!", True, WHITE, DARK_GREEN)
            stalemate_rect = stalemate_text.get_rect()
            stalemate_rect.x = WINDOW_WIDTH // 2
            stalemate_rect.y = WINDOW_HEIGHT // 2
            display_surface.blit(stalemate_text, stalemate_rect)
            game_result_determined = True

        if currently_dragging_card:
            display_surface.blit(card_being_dragged.surface, card_being_dragged.rect)

        pygame.display.update()

        if first_turn:
            # Let the shuffle sound effect play
            shuffle_sound_effect = pygame.mixer.Sound(get_path("assets/shuffle_cards.wav"))
            shuffle_sound_effect.play()
            pygame.time.wait(1000)
            first_turn = False

        if game_result_determined:
            server_socket.close()
            socket_closed = True
            paused = True
            while paused:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        paused = False
            break

    return socket_closed


def main():

    global player_number, player_name, host, port

    pygame.init()

    display_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Spite and Malice")

    getting_user_input = True
    user_quit_game = False
    check_user_input = False
    verified_name = False
    verified_server_ip = False
    verified_server_port = False
    write_config_file = True

    server_ip_pattern = r"^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$"

    # Check for existing config file
    unknown_os = False
    if os.name == "nt":
        config_file_path = Path("C:/ProgramData") / "jscdev909" / "spite_and_malice_client" / "config.toml"
    elif os.name == "posix":
        config_file_path = Path(os.getenv("HOME")) / ".config" / "spite_and_malice_client" / "config.toml"
    else:
        unknown_os = True
        config_file_path = Path()

    name_input_box = InputBox(425, 300, 300, 50)
    server_ip_input_box = InputBox(425, 400, 300, 50)
    server_port_input_box = InputBox(425, 500, 150, 50)

    if config_file_path.exists():
        print(config_file_path) # DEBUG
        with open(config_file_path, "rb") as config_file:
            data = tomllib.load(config_file)
        if ("name" in data and data["name"] and "server_ip" in data and
            re.search(server_ip_pattern, data["server_ip"]) is not None and
            "server_port" in data and 32768 < data["server_port"] < 65535):
            name_input_box.text = data["name"]
            server_ip_input_box.text = data["server_ip"]
            server_port_input_box.text = data["server_port"]
            write_config_file = False

    active_button_inner_color = (0, 75, 0)
    active_button_outer_color = (0, 75, 0)
    inactive_button_inner_color = DARK_GREEN
    inactive_button_outer_color = (0, 75, 0)
    current_inner_button_color = inactive_button_inner_color
    current_outer_button_color = inactive_button_outer_color
    outer_button_rect = pygame.Rect(363, 586, 125, 75)

    input_error_message = ""

    while getting_user_input:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                getting_user_input = False
                user_quit_game = True
            name_input_box.handle_event(event)
            server_ip_input_box.handle_event(event)
            server_port_input_box.handle_event(event)

            mouse_x, mouse_y = pygame.mouse.get_pos()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if outer_button_rect.collidepoint(mouse_x, mouse_y):
                        check_user_input = True

            if outer_button_rect.collidepoint(mouse_x, mouse_y):
                current_inner_button_color = active_button_inner_color
                current_outer_button_color =  active_button_outer_color
            else:
                current_inner_button_color = inactive_button_inner_color
                current_outer_button_color = inactive_button_outer_color

        # Check user input
        if check_user_input:
            if not name_input_box.text:
                input_error_message = "Please enter a name"
            elif not server_ip_input_box.text:
                input_error_message = "Please enter a server IP"
            elif not server_port_input_box.text:
                input_error_message = "Please enter a server port"
            elif name_input_box.text and server_ip_input_box.text and server_port_input_box.text:
                print(name_input_box.text)
                verified_name = True

                if server_ip_input_box.text:

                    ip_match = re.search(server_ip_pattern, server_ip_input_box.text)

                    if ip_match:
                        print(ip_match.group())
                        verified_server_ip = True
                    else:
                        input_error_message = "Please enter a valid IP address"

                if server_port_input_box.text and verified_server_ip:
                    if server_port_input_box.text.isdigit():
                        if 32768 <= int(server_port_input_box.text) <= 65535:
                            print(server_port_input_box.text)
                            verified_server_port = True
                        else:
                            input_error_message = "Please enter a valid port number\n             (32768-65535)"

                if verified_name and verified_server_ip and verified_server_port:
                    if write_config_file and not unknown_os:
                        config_file_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(config_file_path, "w") as config_file:
                            config_file.write(f"name = {name_input_box.text}\n")
                            config_file.write(f"server_ip = {server_ip_input_box.text}\n")
                            config_file.write(f"server_port = {server_port_input_box.text}\n")
                    host = server_ip_input_box.text
                    port = int(server_port_input_box.text)
                    getting_user_input = False
                else:
                    verified_name = False
                    verified_server_ip = False
                    verified_server_port = False

            check_user_input = False

        display_surface.fill(DARK_GREEN)
        name_input_box.draw(display_surface)
        server_ip_input_box.draw(display_surface)
        server_port_input_box.draw(display_surface)

        name_label_surface = pygame.font.SysFont("Arial", 32).render("Player Name:", True, WHITE)
        name_label_rect = name_label_surface.get_rect()
        name_label_rect.x = 210
        name_label_rect.y = 305
        display_surface.blit(name_label_surface, name_label_rect)

        host_label_surface = pygame.font.SysFont("Arial", 32).render("Server IP:", True, WHITE)
        host_label_rect = name_label_surface.get_rect()
        host_label_rect.x = 260
        host_label_rect.y = 405
        display_surface.blit(host_label_surface, host_label_rect)

        port_label_surface = pygame.font.SysFont("Arial", 32).render("Server Port:", True, WHITE)
        port_label_rect = name_label_surface.get_rect()
        port_label_rect.x = 230
        port_label_rect.y = 505
        display_surface.blit(port_label_surface, port_label_rect)

        pygame.draw.rect(display_surface, current_outer_button_color, outer_button_rect)
        inner_button_rect = pygame.draw.rect(display_surface, current_inner_button_color, (375, 600, 100, 50))
        ok_label_surface = pygame.font.SysFont("Arial", 32).render("OK", True, WHITE)
        ok_label_rect = ok_label_surface.get_rect()
        ok_label_rect.x = inner_button_rect.x + 25
        ok_label_rect.y = inner_button_rect.y + 8
        display_surface.blit(ok_label_surface, ok_label_rect)

        if input_error_message:
            input_error_surface = pygame.font.SysFont("Arial", 32).render(input_error_message, True, WHITE)
            input_error_rect = input_error_surface.get_rect()
            input_error_rect.x = 250
            input_error_rect.y = 200
            display_surface.blit(input_error_surface, input_error_rect)

        pygame.display.update()

    if not user_quit_game:
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            initial_setup_thread = threading.Thread(target=initial_setup, args=(server_socket,))
            initial_setup_thread.start()

            performing_setup = True

            status_font = pygame.font.SysFont("Arial", 32)

            while performing_setup:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        performing_setup = False
                        user_quit_game = True

                display_surface.fill(DARK_GREEN)

                status_text = None
                if initial_setup_status == SetupStatus.CONNECTING_TO_SERVER:
                    status_text = status_font.render("Connecting to server...", True, WHITE, DARK_GREEN)
                elif initial_setup_status == SetupStatus.PLAYER_ASSIGNED:
                    status_text = status_font.render(f"You are player {player_number}", True, WHITE, DARK_GREEN)
                elif initial_setup_status == SetupStatus.WAITING_FOR_OTHER_PLAYER:
                    status_text = status_font.render("Waiting for other player to join...", True, WHITE, DARK_GREEN)
                elif initial_setup_status == SetupStatus.RECEIVING_CARD_DATA:
                    status_text = status_font.render("Receiving card data from server...", True, WHITE, DARK_GREEN)
                elif initial_setup_status == SetupStatus.OTHER_PLAYER_STATUS_CHECK:
                    status_text = status_font.render("Checking status of other player...", True, WHITE, DARK_GREEN)
                elif initial_setup_status == SetupStatus.COMPLETE:
                    status_text = status_font.render("Initial setup complete! Loading game...", True, WHITE, DARK_GREEN)

                if status_text is not None:
                    status_text_rect = status_text.get_rect()
                    status_text_rect.centerx = WINDOW_WIDTH // 2
                    status_text_rect.centery = WINDOW_HEIGHT // 2
                    display_surface.blit(status_text, status_text_rect)

                pygame.display.update()

                if ((initial_setup_error_status != SetupErrorStatus.UNSET) or
                    (initial_setup_status == SetupStatus.COMPLETE and
                     initial_setup_error_status == SetupErrorStatus.UNSET)):
                    performing_setup = False

            if (initial_setup_status == SetupStatus.COMPLETE and
                initial_setup_error_status == SetupErrorStatus.UNSET and not user_quit_game):
                socket_closed = run_game(server_socket, display_surface)
                if not socket_closed:
                    server_socket.close()
            else:
                if initial_setup_error_status == SetupErrorStatus.COULD_NOT_CONNECT_TO_SERVER:
                    raise ClientError(f"Could not connect to server {host}:{port}")
                elif initial_setup_error_status == SetupErrorStatus.GAME_LOBBY_FULL:
                    raise ClientError("Game lobby full!")
                elif initial_setup_error_status == SetupErrorStatus.PAYOFF_PILE1_RECEIVE_ERROR:
                    raise ClientError("Error receiving payoff pile 1 from server")
                elif initial_setup_error_status == SetupErrorStatus.PAYOFF_PILE2_RECEIVE_ERROR:
                    raise ClientError("Error receiving payoff pile 2 from server")
                elif initial_setup_error_status == SetupErrorStatus.DRAW_PILE_RECEIVE_ERROR:
                    raise ClientError("Error receiving draw pile from server")
                elif initial_setup_error_status == SetupErrorStatus.OTHER_PLAYER_DISCONNECTED:
                    raise ClientError("Other player disconnected!")



        except TimeoutError:
            display_surface.fill(DARK_GREEN)
            error_message = "An operation with the server timed out\n(other player may have disconnected or the server might be down)"
            error_font = pygame.font.SysFont("Arial", 32)
            error_text = error_font.render(error_message, True, WHITE, DARK_GREEN)
            error_text_rect = error_text.get_rect()
            error_text_rect.centerx = WINDOW_WIDTH//2
            error_text_rect.centery = WINDOW_HEIGHT//2
            paused = True
            while paused:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        paused = False
                display_surface.fill(DARK_GREEN)
                display_surface.blit(error_text, error_text_rect)
                pygame.display.update()
        except ConnectionRefusedError:
            display_surface.fill(DARK_GREEN)
            error_message = "Server actively refused the client connection.\n       Please check the server and restart."
            error_font = pygame.font.SysFont("Arial", 32)
            error_text = error_font.render(error_message, True, WHITE, DARK_GREEN)
            error_text_rect = error_text.get_rect()
            error_text_rect.centerx = WINDOW_WIDTH//2
            error_text_rect.centery = WINDOW_HEIGHT//2
            paused = True
            while paused:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        paused = False
                display_surface.fill(DARK_GREEN)
                display_surface.blit(error_text, error_text_rect)
                pygame.display.update()
        except ClientError as ce:
            display_surface.fill(DARK_GREEN)
            error_message = ""
            if "]" in str(ce):
                error_message = "There was an issue communicating with the server.\nPlease restart the program and try again."
            elif str(ce) == "timed out":
                error_message = "Connection to the server timed out (30 seconds)"
            else:
                error_message = str(ce)
            error_font = pygame.font.SysFont("Arial", 32)
            error_text = error_font.render(error_message, True, WHITE, DARK_GREEN)
            error_text_rect = error_text.get_rect()
            error_text_rect.centerx = WINDOW_WIDTH//2
            error_text_rect.centery = WINDOW_HEIGHT//2
            paused = True
            while paused:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        paused = False
                display_surface.fill(DARK_GREEN)
                display_surface.blit(error_text, error_text_rect)
                pygame.display.update()

        pygame.quit()

if __name__ == "__main__":
    if sys.version_info >= (3, 11):
        main()
    else:
        print("This script requires at least Python 3.11")