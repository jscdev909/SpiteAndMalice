import socket
import threading
import re
import random
import tomllib
import os
import sys
from collections import deque
from card import CardPosition, send_cards, deal, create_deck
from socket_utils import receive_message, send_message
from path_utils import get_path
from pathlib import Path

VERSION = "0.20"
HOST = "0.0.0.0"

connection_count = 0
current_turn = 0
current_turn_lock = threading.Lock()
connection_count_lock = threading.Lock()
card_lock = threading.Lock()
deck = []
payoff_pile1 = []
payoff_pile2 = []
build_piles = [[], [], [], []]
player1_discard_piles = [[], [], [], []]
player2_discard_piles = [[], [], [], []]
draw_pile = []
player1_name = ""
player1_hand = []
player1_draw_count = 0
player1_moves_queue = deque()
player1_rematch = None
player2_name = ""
player2_hand = []
player2_draw_count = 0
player2_moves_queue = deque()
player2_rematch = None
rematch_setup_complete = False
rematch_setup_lock = threading.Lock()

class ServerError(Exception):
    pass

def handle_client(client_socket: socket.socket, client_address: tuple[str, int]) -> None:
    global connection_count, current_turn, deck, payoff_pile1, payoff_pile2, draw_pile
    global player1_hand, player2_hand, player1_draw_count, player2_draw_count
    global player1_name, player2_name, player1_rematch, player2_rematch, rematch_setup_complete
    global build_piles, player1_discard_piles, player2_discard_piles

    player_number = 0

    print(f"[+] Accepted connection from {client_address[0]}:{client_address[1]}", flush=True)

    try:
        while True:
            request = receive_message(client_socket)
            if not request:
                print("[*] Client disconnected!", flush=True)
                break

            elif "Player ready!" in request:
                connection_count_lock.acquire()
                if connection_count == 2:
                    send_message(client_socket, "Game lobby is full")
                    connection_count_lock.release()
                else:
                    connection_count += 1
                    player_number = connection_count
                    connection_count_lock.release()

                    player_name_match = re.search(r"Name: (.*)", request)
                    if player_name_match:
                        if player_number == 1:
                            player1_name = player_name_match.group(1)
                            print(f"[*] Player {player_number} ({player1_name}) has joined the game", flush=True)
                            send_message(client_socket,f"You are player {player_number}")
                        elif player_number == 2:
                            player2_name = player_name_match.group(1)
                            print(f"[*] Player {player_number} ({player2_name}) has joined the game", flush=True)
                            send_message(client_socket,f"You are player {player_number}")
                        else:
                            raise ServerError("Player number cannot be 0!")
                    else:
                        raise ServerError("Received an invalid player name")

            # Note: This request should only be sent by the player 1 client
            elif request == "Has player 2 joined?":
                connection_count_lock.acquire()
                if connection_count == 2:
                    connection_count_lock.release()
                    send_message(client_socket, "Player 2 has joined")
                else:
                    connection_count_lock.release()
                    send_message(client_socket, "Waiting for player 2")

            elif "What is player" in request and "name" in request:
                target_player = 0
                pattern = r"player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError("Could not parse target player ID from client data")

                if target_player == 1:
                    send_message(client_socket, player1_name)
                elif target_player == 2:
                    send_message(client_socket, player2_name)
                else:
                    raise ServerError(f"Invalid player ID ({target_player}) specified in client data")

            elif "Player" in request and "did not want a re-match" in request:
                target_player = 0
                pattern = r"Player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError(
                        "Could not parse target player ID from client data")

                if target_player == 1:
                    player1_rematch = False
                elif target_player == 2:
                    player2_rematch = False

            elif "Player" in request and "wants a re-match" in request:
                target_player = 0
                pattern = r"Player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError(
                        "Could not parse target player ID from client data")

                if target_player == 1:
                    player1_rematch = True
                elif target_player == 2:
                    player2_rematch = True

            elif "Does player" in request and "also want a re-match?" in request:
                target_player = 0
                pattern = r"player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError(
                        "Could not parse target player ID from client data")

                if target_player == 1:
                    if player1_rematch is True:
                        send_message(client_socket, "Yes")
                    elif player1_rematch is False:
                        send_message(client_socket, "No")
                    else:
                        send_message(client_socket, "Undecided")
                elif target_player == 2:
                    if player2_rematch is True:
                        send_message(client_socket, "Yes")
                    elif player2_rematch is False:
                        send_message(client_socket, "No")
                    else:
                        send_message(client_socket, "Undecided")

            elif request == "Set up a new game":
                rematch_setup_lock.acquire()
                if not rematch_setup_complete:
                    print("[*] New game requested, resetting game parameters...", flush=True)
                    card_lock.acquire()
                    deck = []
                    payoff_pile1 = []
                    payoff_pile2 = []
                    build_piles = [[], [], [], []]
                    player1_discard_piles = [[], [], [], []]
                    player2_discard_piles = [[], [], [], []]
                    draw_pile = []
                    player1_hand = []
                    player2_hand = []
                    card_lock.release()
                    player1_moves_queue.clear()
                    player2_moves_queue.clear()
                    player1_draw_count = 0
                    player2_draw_count = 0
                    current_turn_lock.acquire()
                    current_turn = 0
                    current_turn_lock.release()
                    rematch_setup_complete = True
                else:
                    player1_rematch = None
                    player2_rematch = None
                    rematch_setup_complete = False
                rematch_setup_lock.release()

            elif request == "Draw pile needs to be reshuffled":

                card_lock.acquire()

                draw_pile_needs_to_be_reshuffled = False
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

                # DEBUG
                print("DEBUG783838")
                print(cards_to_shuffle)

                if draw_pile_needs_to_be_reshuffled:
                    # DEBUG
                    print("DEBUG82929")
                    print(len(draw_pile))
                    draw_pile += cards_to_shuffle
                    print(len(draw_pile))
                    random.shuffle(draw_pile)

                card_lock.release()

            elif request == "Create new deck and payoff piles":
                card_lock.acquire()

                if not deck and not payoff_pile1 and not payoff_pile2 and not draw_pile:
                    # Got the lock, create the deck, payoff piles and draw pile
                    print(f"[*] Creating the deck (player {player_number} thread)...", flush=True)
                    deck = create_deck(get_path("assets/card_faces"))
                    print(f"[*] Creating the payoff piles and draw pile (player {player_number} thread)...", flush=True)
                    payoff_pile1, payoff_pile2, draw_pile = deal(deck)
                else:
                    print(f"[*] Status update from player {player_number} thread: other thread already created decks and piles", flush=True)

                card_lock.release()

            elif request == "Is the other player still connected?":
                connection_count_lock.acquire()
                if connection_count == 1:
                    send_message(client_socket, "No")
                elif connection_count == 2:
                    send_message(client_socket, "Yes")
                connection_count_lock.release()

            elif "How many cards are in player" in request and "hand" in request:
                target_player = 0
                pattern = r"player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError(
                        "Could not parse target player ID from client data")
                card_lock.acquire()
                if target_player == 1:
                    send_message(client_socket, str(len(player1_hand)))
                elif target_player == 2:
                    send_message(client_socket, str(len(player2_hand)))
                card_lock.release()

            elif "How many cards are left in player" in request and "payoff pile?" in request:
                target_player = 0
                pattern = r"player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError(
                        "Could not parse target player ID from client data")

                card_lock.acquire()

                if target_player == 1:
                    send_message(client_socket, str(len(payoff_pile1)))
                elif target_player == 2:
                    send_message(client_socket, str(len(payoff_pile2)))

                card_lock.release()

            elif "Send the top card of player" in request and "payoff pile" in request:
                target_player = 0
                pattern = r"player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError(
                        "Could not parse target player ID from client data")

                card_lock.acquire()
                if target_player == 1:
                    send_cards(client_socket, [payoff_pile1[-1]])
                elif target_player == 2:
                    send_cards(client_socket, [payoff_pile2[-1]])
                card_lock.release()

            elif request == "Has the game result been determined?":
                card_lock.acquire()
                if not payoff_pile1 or not payoff_pile2 or not draw_pile:
                    send_message(client_socket, "Yes")
                else:
                    send_message(client_socket, "No")
                card_lock.release()

            elif request == "Who won the game?":
                card_lock.acquire()
                if not payoff_pile1:
                    send_message(client_socket, "Player 1")
                elif not payoff_pile2:
                    send_message(client_socket, "Player 2")
                elif not draw_pile and len(payoff_pile1) < len(payoff_pile2):
                    send_message(client_socket, "Player 1")
                elif not draw_pile and len(payoff_pile1) > len(payoff_pile2):
                    send_message(client_socket, "Player 2")
                elif not draw_pile and len(payoff_pile1) == len(payoff_pile2):
                    send_message(client_socket, "Stalemate")
                card_lock.release()

            elif request == "How many cards are left in the draw pile?":

                card_lock.acquire()
                send_message(client_socket, str(len(draw_pile)))
                card_lock.release()

            elif "What was" in request and "last move" in request:
                target_player = 0
                pattern = r"player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).isdigit():
                    target_player = int(first_match.group(1))
                else:
                    raise ServerError("Invalid player ID specified in request")

                if target_player == 1:
                    if player1_moves_queue:
                        print("in here 1 - server")
                        last_move = player1_moves_queue.popleft()
                        send_message(client_socket, last_move[0])
                        if last_move[1] is not None:
                            send_cards(client_socket, [last_move[1]])
                    else:
                        send_message(client_socket, "Nothing")
                elif target_player == 2:
                    if player2_moves_queue:
                        print("in here 2 - server")
                        last_move = player2_moves_queue.popleft()
                        send_message(client_socket, last_move[0])
                        if last_move[1] is not None:
                            send_cards(client_socket, [last_move[1]])
                    else:
                        send_message(client_socket, "Nothing")
                else:
                    # Should never get here but raise an exception just in case
                    raise ServerError("Invalid player ID specified in request")

            elif request == "Whose turn is it?":
                current_turn_lock.acquire()
                if current_turn == 0:
                    if payoff_pile1[-1].rank > payoff_pile2[-1].rank:
                        current_turn = 1
                    elif payoff_pile1[-1].rank < payoff_pile2[-1].rank:
                        current_turn = 2
                    elif payoff_pile1[-1].rank == payoff_pile2[-1].rank:
                        current_turn = random.randint(1, 2)
                    print(f"Setting current turn to {current_turn}", flush=True)
                send_message(client_socket, f"Player {current_turn}")
                # DEBUG
                print(f"It is currently player {current_turn}'s turn", flush=True)
                current_turn_lock.release()

            elif "ended their turn" in request:
                current_turn_lock.acquire()
                if current_turn == 1:
                    player1_draw_count = 0
                    current_turn = 2
                elif current_turn == 2:
                    player2_draw_count = 0
                    current_turn = 1
                current_turn_lock.release()

            elif "Player" in request and "draws 5 cards" in request:
                target_player = 0
                pattern = r"Player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError("Invalid player ID specified in draw request")
                card_lock.acquire()
                if target_player == 1:
                    for _ in range(0, 5, 1):
                        player1_hand.append(draw_pile.pop())
                    print("DEBUG--------------", flush=True)
                    print("Player 1's hand is:", flush=True)
                    print([dbg_card.name for dbg_card in player1_hand], flush=True)
                    send_cards(client_socket, player1_hand)
                elif target_player == 2:
                    for _ in range(0, 5, 1):
                        player2_hand.append(draw_pile.pop())
                    print("DEBUG--------------", flush=True)
                    print("Player 2's hand is:", flush=True)
                    print([dbg_card.name for dbg_card in player2_hand], flush=True)
                    send_cards(client_socket, player2_hand)

                card_lock.release()

                if target_player == 1:
                    player1_draw_count += 5
                elif target_player == 2:
                    player2_draw_count += 5

            elif "moved" in request and "from their" in request:
                last_card_moved_from_hand = None
                target_player = 0
                pattern = r"Player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError("Invalid player ID specified in move request")
                card_name = ""
                pattern = r"moved\b(.*)\bfrom"
                first_match = re.search(pattern, request)
                if first_match:
                    card_name = first_match.group(1).strip()
                else:
                    raise ServerError("Invalid card name specified in move request")
                moving_from = ""
                pattern = r"their\b(.*)\bto"
                first_match = re.search(pattern, request)
                if first_match:
                    moving_from = first_match.group(1).strip()
                else:
                    raise ServerError("Invalid 'moving from' location specified in move request")
                moving_to = ""
                pattern = r"to\b(.*)$"
                first_match = re.search(pattern, request)
                if first_match:
                    moving_to = first_match.group(1).strip()
                else:
                    raise ServerError("Invalid 'moving to' location specified in move request")

                if target_player == 1:
                    if moving_from == "hand":
                        if moving_to == "discard pile 0":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 1 hand:")
                            for card in player1_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player1_hand if card.name == card_name][0]
                            player1_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            player1_discard_piles[0].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "discard pile 1":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 1 hand:")
                            for card in player1_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player1_hand if card.name == card_name][0]
                            player1_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            player1_discard_piles[1].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "discard pile 2":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 1 hand:")
                            for card in player1_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player1_hand if card.name == card_name][0]
                            player1_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            player1_discard_piles[2].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "discard pile 3":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 1 hand:")
                            for card in player1_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player1_hand if card.name == card_name][0]
                            player1_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            player1_discard_piles[3].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "build pile 0":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 1 hand:")
                            for card in player1_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player1_hand if card.name == card_name][0]
                            player1_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            build_piles[0].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 1 hand:")
                            for card in player1_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player1_hand if card.name == card_name][0]
                            player1_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            build_piles[1].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 1 hand:")
                            for card in player1_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player1_hand if card.name == card_name][0]
                            player1_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            build_piles[2].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 1 hand:")
                            for card in player1_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player1_hand if card.name == card_name][0]
                            player1_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            build_piles[3].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        else:
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    elif moving_from == "discard pile 0":
                        card_lock.acquire()
                        card_to_move = player1_discard_piles[0][-1]
                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on discard pile 0 did not match card name in move request")
                        player1_discard_piles[0].pop()
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    elif moving_from == "discard pile 1":
                        card_lock.acquire()
                        card_to_move = player1_discard_piles[1][-1]
                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on discard pile 1 did not match card name in move request")
                        player1_discard_piles[1].pop()
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    elif moving_from == "discard pile 2":
                        card_lock.acquire()
                        card_to_move = player1_discard_piles[2][-1]
                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on discard pile 2 did not match card name in move request")
                        player1_discard_piles[2].pop()
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    elif moving_from == "discard pile 3":
                        card_lock.acquire()
                        card_to_move = player1_discard_piles[3][-1]
                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on discard pile 3 did not match card name in move request")
                        player1_discard_piles[3].pop()
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")

                    elif moving_from == "payoff pile":
                        card_lock.acquire()
                        card_to_move = payoff_pile1[-1]
                        print("in here 7", flush=True)
                        print("DEBUG---------------------------", flush=True)
                        print(card_to_move.name, flush=True)
                        print(card_name, flush=True)
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on payoff pile did not match card name in move request")
                        payoff_pile1.pop()

                        if payoff_pile1:
                            # Flip over next card
                            payoff_pile1[-1].position = CardPosition.FACE_UP

                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    else:
                        raise ServerError("Invalid 'moving from' location specified in move request")

                    if moving_from == "hand":
                        player1_moves_queue.append((f"Player 1 moved {card_name} from {moving_from} to {moving_to}", last_card_moved_from_hand))
                        print(f"Player 1 moved {card_name} from {moving_from} to {moving_to}", flush=True)
                    else:
                        player1_moves_queue.append((f"Player 1 moved {card_name} from {moving_from} to {moving_to}", None))
                        print(f"Player 1 moved {card_name} from {moving_from} to {moving_to}", flush=True)

                elif target_player == 2:
                    if moving_from == "hand":
                        if moving_to == "discard pile 0":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 2 hand:")
                            for card in player2_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player2_hand if card.name == card_name][0]
                            player2_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            player2_discard_piles[0].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "discard pile 1":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 2 hand:")
                            for card in player2_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player2_hand if card.name == card_name][0]
                            player2_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            player2_discard_piles[1].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "discard pile 2":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 2 hand:")
                            for card in player2_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player2_hand if card.name == card_name][0]
                            player2_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            player2_discard_piles[2].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "discard pile 3":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 2 hand:")
                            for card in player2_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player2_hand if card.name == card_name][0]
                            player2_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            player2_discard_piles[3].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "build pile 0":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 2 hand:")
                            for card in player2_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player2_hand if card.name == card_name][0]
                            player2_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            build_piles[0].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 2 hand:")
                            for card in player2_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player2_hand if card.name == card_name][0]
                            player2_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            build_piles[1].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 2 hand:")
                            for card in player2_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player2_hand if card.name == card_name][0]
                            player2_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            build_piles[2].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            card_lock.acquire()
                            print("DEBUG---------------------")
                            print("Cards in player 2 hand:")
                            for card in player2_hand:
                                print(card.name)
                            print(f"Card name being searched for: {card_name}")
                            # if multiple items in list take first one
                            card_to_move = [card for card in player2_hand if card.name == card_name][0]
                            player2_hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP
                            build_piles[3].append(card_to_move)
                            last_card_moved_from_hand = card_to_move
                            card_lock.release()
                        else:
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    elif moving_from == "discard pile 0":
                        card_lock.acquire()
                        card_to_move = player2_discard_piles[0][-1]
                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on discard pile 0 did not match card name in move request")
                        player2_discard_piles[0].pop()
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    elif moving_from == "discard pile 1":
                        card_lock.acquire()
                        card_to_move = player2_discard_piles[1][-1]
                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on discard pile 1 did not match card name in move request")
                        player2_discard_piles[1].pop()
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    elif moving_from == "discard pile 2":
                        card_lock.acquire()
                        card_to_move = player2_discard_piles[2][-1]
                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on discard pile 2 did not match card name in move request")
                        player2_discard_piles[2].pop()
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    elif moving_from == "discard pile 3":
                        card_lock.acquire()
                        card_to_move = player2_discard_piles[3][-1]
                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on discard pile 3 did not match card name in move request")
                        player2_discard_piles[3].pop()
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")

                    elif moving_from == "payoff pile":
                        card_lock.acquire()
                        card_to_move = payoff_pile2[-1]
                        if card_to_move.name != card_name:
                            print("in here 6", flush=True)
                            print("DEBUG---------------------------", flush=True)
                            print(card_to_move.name, flush=True)
                            print(card_name, flush=True)
                            raise ServerError("Name of top card on payoff pile did not match card name in move request")
                        payoff_pile2.pop()
                        if payoff_pile2:
                            # Flip over next card
                            payoff_pile2[-1].position = CardPosition.FACE_UP
                        if moving_to == "build pile 0":
                            build_piles[0].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 1":
                            build_piles[1].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 2":
                            build_piles[2].append(card_to_move)
                            card_lock.release()
                        elif moving_to == "build pile 3":
                            build_piles[3].append(card_to_move)
                            card_lock.release()
                        else:
                            card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    else:
                        raise ServerError("Invalid 'moving from' location specified in move request")

                    if moving_from == "hand":
                        player2_moves_queue.append((f"Player 2 moved {card_name} from {moving_from} to {moving_to}", last_card_moved_from_hand))
                        print(f"Player 2 moved {card_name} from {moving_from} to {moving_to}", flush=True)
                    else:
                        player2_moves_queue.append((f"Player 2 moved {card_name} from {moving_from} to {moving_to}", None))
                        print(f"Player 2 moved {card_name} from {moving_from} to {moving_to}", flush=True)


            else:
                print(f"[*] Client {client_address[0]}:{client_address[1]} sent incorrect data", flush=True)
                raise ServerError("Incorrect data received from client")

    except ServerError as se:
        print(f"[*] Error handling client {client_address[0]}:{client_address[1]}: {se}", flush=True)
    except ConnectionResetError:
        print(f"[*] Connection reset by client (client disconnected)", flush=True)
    except BrokenPipeError:
        print(f"[*] Client disconnected in the middle of an operation", flush=True)
    finally:
        client_socket.close()
        connection_count_lock.acquire()
        connection_count -= 1
        if connection_count == 0:
            card_lock.acquire()
            deck = []
            payoff_pile1 = []
            payoff_pile2 = []
            draw_pile = []
            player1_hand = []
            player2_hand = []
            build_piles = [[], [], [], []]
            player1_discard_piles = [[], [], [], []]
            player2_discard_piles = [[], [], [], []]
            card_lock.release()
            player1_name = ""
            player2_name = ""
            player1_moves_queue.clear()
            player2_moves_queue.clear()
            player1_draw_count = 0
            player2_draw_count = 0
            player1_rematch = None
            player2_rematch = None
        connection_count_lock.release()
        current_turn_lock.acquire()
        current_turn = 0
        current_turn_lock.release()
        print(f"[-] Connection with {client_address[0]}:{client_address[1]} closed.", flush=True)

def run_server(valid_port: int) -> None:

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:

        server.bind((HOST, valid_port))
        server.listen(2)
        server.settimeout(1)
        print(f"[*] Listening on {HOST}:{valid_port}", flush=True)

        while True:
            try:
                client_socket, addr = server.accept()
                client_handler = threading.Thread(target=handle_client, args=(client_socket, addr))
                client_handler.start()
            except socket.timeout:
                pass
    except KeyboardInterrupt:
        print("\n[*] KeyboardInterrupt received. Server shutting down...", flush=True)
    except OSError as ose:
        if "Address already in use" in str(ose):
            print(f"[*] Error binding to address {HOST}:{valid_port}: Address already in use", flush=True)
        elif "Permission denied" in str(ose):
            # Should never reach here due to prior error checking
            print(f"[*] Error binding to valid_port {valid_port}: Did you specify a privileged port?", flush=True)
        elif "Invalid argument" in str(ose):
            # Should never reach here due to prior error checking
            print(f"[*] Error binding to port {valid_port}: Invalid port number specified", flush=True)
    finally:
        server.close()

def main():

    unknown_os = False
    if os.name == "nt":
        config_file_path = Path("C:/ProgramData") / "jscdev909" / "spite_and_malice_server" / "config.toml"
    elif os.name == "posix":
        config_file_path = Path(os.getenv("HOME")) / ".config" / "spite_and_malice_server" / "config.toml"
    else:
        unknown_os = True
        config_file_path = Path()

    port = 0

    try:
        if config_file_path.exists():
            print(f"Using config file found at {config_file_path}", flush=True)
            with open(config_file_path, "rb") as config_file:
                data = tomllib.load(config_file)
            if "port" in data and 32768 <= data["port"] <= 65535:
                port = data["port"]
            else:
                print("Config file contains incorrect port number, rewriting config file with new input")
                receiving_input = True
                while receiving_input:
                    user_input = input("Please enter a port number (32768-65535) for the server to listen to: ")
                    if user_input.isdigit() and 32768 <= int(user_input) <= 65535:
                        port = int(user_input)
                        receiving_input = False

                with open(config_file_path, "w") as config_file:
                    config_file.write(f"port = {port}\n")

                print(f"Re-wrote config file to {str(config_file_path)}",
                      flush=True)
        else:
            receiving_input = True
            while receiving_input:
                user_input = input("Please enter a port number (32768-65535) for the server to listen to: ")
                if user_input.isdigit():
                    if 32768 <= int(user_input) <= 65535:
                        port = int(user_input)
                        receiving_input = False

            if not unknown_os:
                config_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_file_path, "w") as config_file:
                    config_file.write(f"port = {port}\n")

                print(f"Wrote new config file to {str(config_file_path)}", flush=True)

        run_server(port)

    except KeyboardInterrupt:
        print("\nExiting...", flush=True)


if __name__ == "__main__":
    if sys.version_info >= (3, 11):
        print(f"Spite and Malice Server - Version {VERSION}", flush=True)
        main()
    else:
        print("This script requires at least Python 3.11", flush=True)

