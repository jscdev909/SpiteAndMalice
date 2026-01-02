import socket
import threading
import pygame
import time
import re
import random
from collections import deque
from card import CardPosition, send_cards, receive_cards, deal, create_deck
from socket_utils import receive_message, send_message
from path_utils import get_path

HOST = '0.0.0.0'
PORT = 43210

connection_count = 0
current_turn = 0
players_with_decks = 0
players_with_decks_lock = threading.Lock()
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
player1_hand = []
player1_draw_count = 0
player1_draw_count_lock = threading.Lock()
player2_hand = []
player2_draw_count = 0
player2_draw_count_lock = threading.Lock()
player1_moves_queue = deque()
player1_moves_queue_lock = threading.Lock()
player2_moves_queue = deque()
player2_moves_queue_lock = threading.Lock()

class ServerError(Exception):
    pass

def handle_client(client_socket: socket.socket, client_address: tuple[str, int]) -> None:
    global connection_count, current_turn, deck, payoff_pile1, payoff_pile2, draw_pile
    global player1_hand, player2_hand, players_with_decks, player1_draw_count, player2_draw_count
    player_number = 0

    print(f"[+] Accepted connection from {client_address[0]}:{client_address[1]}", flush=True)

    try:
        while True:
            request = receive_message(client_socket)
            if not request:
                print("[*] Client disconnected!", flush=True)
                break
            elif request == "Player ready!":
                connection_count_lock.acquire()
                if connection_count == 2:
                    send_message(client_socket, "Game lobby is full")
                    connection_count_lock.release()
                else:
                    connection_count += 1
                    player_number = connection_count
                    connection_count_lock.release()
                    send_message(client_socket, f"You are player {player_number}")
                    print(f"[*] Player {player_number} has joined the game", flush=True)

            # Note: This request should only be sent by the player 1 client
            elif request == "Has player 2 joined?":
                connection_count_lock.acquire()
                if connection_count == 2:
                    connection_count_lock.release()
                    send_message(client_socket, "Player 2 has joined")
                else:
                    connection_count_lock.release()
                    send_message(client_socket, "Waiting for player 2")

            elif request == "Draw pile needs to be reshuffled":

                # Receive length of new draw pile from client
                draw_pile_length = receive_message(client_socket)

                card_lock.acquire()

                # If length of new draw pile is equal to what we already have
                # the other thread already added cards and reshuffled the draw pile
                if int(draw_pile_length) == len(draw_pile):
                    send_message(client_socket, "Already taken care of")
                else:
                    send_message(client_socket, "Ready to receive new draw pile cards")

                    # First receive number of new cards added to the draw pile
                    additional_cards_length = receive_message(client_socket)
                    if additional_cards_length and additional_cards_length.strip().isdigit():
                        additional_cards_length = int(additional_cards_length.strip())
                    else:
                        raise ServerError("Received an invalid number of new draw pile cards from the client")

                    # Then receive the actual cards to add to the draw pile
                    additional_cards = receive_cards(client_socket, additional_cards_length)
                    if not additional_cards:
                        raise ServerError("Could not receive additional draw pile cards from client")

                    draw_pile += additional_cards
                    random.shuffle(draw_pile)

                    # DEBUG
                    print("Listing card names for new draw pile on server", flush=True)
                    for index, draw_pile_card in enumerate(list(draw_pile)):
                        draw_pile_card.order = index
                        print(f"{draw_pile_card.name}: {draw_pile_card.order}", flush=True)

                card_lock.release()


            elif request == "Please send the draw pile":

                card_lock.acquire()

                # Send number of cards in the new draw pile first
                send_message(client_socket, str(len(draw_pile)))

                # Then send the actual cards to the client
                send_cards(client_socket, draw_pile)

                card_lock.release()


            elif request == "Awaiting card data":
                print(f"[*] Player {player_number} is awaiting card data", flush=True)
                card_lock.acquire()

                if not deck and not payoff_pile1 and not payoff_pile2 and not draw_pile:
                    # Got the lock, create the deck, payoff piles and draw pile
                    print(f"[*] Creating the deck (player {player_number} thread)...", flush=True)
                    deck = create_deck(get_path("assets/card_faces"))
                    print(f"[*] Creating the payoff piles and draw pile (player {player_number} thread)...", flush=True)
                    payoff_pile1, payoff_pile2, draw_pile = deal(deck)
                else:
                    print(f"[*] Status update from player {player_number} thread: other thread already created decks and piles", flush=True)
                    time.sleep(5)

                send_message(client_socket, "Sending payoff pile 1")
                print(f"[*] Length of payoff pile 1: {len(payoff_pile1)}",
                      flush=True)
                print("Payoff pile 1 on server side:", flush=True)
                for card in payoff_pile1:
                    print(f"{card.name}: {card.order}", flush=True)
                send_cards(client_socket, payoff_pile1)

                send_message(client_socket, "Sending payoff pile 2")
                print(f"[*] Length of payoff pile 2: {len(payoff_pile2)}",
                      flush=True)
                print("Payoff pile 2 on server side:", flush=True)
                for card in payoff_pile2:
                    print(f"{card.name}: {card.order}", flush=True)
                send_cards(client_socket, payoff_pile2)

                send_message(client_socket, "Sending draw pile")
                print(f"[*] Length of draw pile: {len(draw_pile)}",
                      flush=True)
                print("Draw pile on server side:", flush=True)
                for card in draw_pile:
                    print(f"{card.name}: {card.order}", flush=True)
                send_cards(client_socket, draw_pile)

                card_lock.release()

                players_with_decks_lock.acquire()
                players_with_decks += 1
                players_with_decks_lock.release()

            elif request == "Is the other player still connected?":
                connection_count_lock.acquire()
                if connection_count == 1:
                    send_message(client_socket, "No")
                elif connection_count == 2:
                    send_message(client_socket, "Yes")
                connection_count_lock.release()

            elif request == "Have both players received the decks and piles?":
                lock = players_with_decks_lock.acquire(timeout=2)
                if lock:
                    if players_with_decks == 2:
                        response = "Yes"
                    else:
                        response = "No"
                    players_with_decks_lock.release()
                else:
                    response = "No"
                send_message(client_socket, response)

            elif "How many cards" in request and "hand" in request:
                target_player = 0
                for char in request:
                    if char.isdigit():
                        target_player = int(char)
                        break
                card_lock.acquire()
                if target_player == 1:
                    send_message(client_socket, str(len(player1_hand)))
                elif target_player == 2:
                    send_message(client_socket, str(len(player2_hand)))
                card_lock.release()

            elif "How many cards has player" in request and "drawn this turn?" in request:
                target_player = 0
                pattern = r"player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).strip().isdigit():
                    target_player = int(first_match.group(1).strip())
                else:
                    raise ServerError("Invalid player ID specified in client data")

                if target_player == 1:
                    player1_draw_count_lock.acquire()
                    send_message(client_socket, str(player1_draw_count))
                    player1_draw_count_lock.release()
                elif target_player == 2:
                    player2_draw_count_lock.acquire()
                    send_message(client_socket, str(player2_draw_count))
                    player2_draw_count_lock.release()


            elif "What was" in request and "last move" in request:
                target_player = 0
                pattern = r"player (\d)"
                first_match = re.search(pattern, request)
                if first_match and first_match.group(1).isdigit():
                    target_player = int(first_match.group(1))
                else:
                    raise ServerError("Invalid player ID specified in request")

                if target_player == 1:
                    player1_moves_queue_lock.acquire()
                    if player1_moves_queue:
                        print("in here 1 - server")
                        last_move = player1_moves_queue.popleft()
                        send_message(client_socket, last_move[0])
                        if last_move[1] is not None:
                            send_cards(client_socket, [last_move[1]])
                    else:
                        send_message(client_socket, "Nothing")
                    player1_moves_queue_lock.release()
                elif target_player == 2:
                    player2_moves_queue_lock.acquire()
                    if player2_moves_queue:
                        print("in here 2 - server")
                        last_move = player2_moves_queue.popleft()
                        send_message(client_socket, last_move[0])
                        if last_move[1] is not None:
                            send_cards(client_socket, [last_move[1]])
                    else:
                        send_message(client_socket, "Nothing")
                    player2_moves_queue_lock.release()
                else:
                    # Should never get here but raise an exception just in case
                    raise ServerError("Invalid player ID specified in request")

            elif request == "Whose turn is it?":
                current_turn_lock.acquire()
                if current_turn == 0:
                    current_turn = random.randint(1, 2)
                    print(f"Setting current turn to {current_turn}", flush=True)
                send_message(client_socket, f"Player {current_turn}")
                current_turn_lock.release()

            elif "ended their turn" in request:
                current_turn_lock.acquire()
                if current_turn == 1:
                    player1_draw_count_lock.acquire()
                    player1_draw_count = 0
                    player1_draw_count_lock.release()
                    current_turn = 2
                elif current_turn == 2:
                    player2_draw_count_lock.acquire()
                    player2_draw_count = 0
                    player2_draw_count_lock.release()
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
                elif target_player == 2:
                    for _ in range(0, 5, 1):
                        player2_hand.append(draw_pile.pop())
                    print("DEBUG--------------", flush=True)
                    print("Player 2's hand is:", flush=True)
                    print([dbg_card.name for dbg_card in player2_hand], flush=True)
                card_lock.release()

                if target_player == 1:
                    player1_draw_count_lock.acquire()
                    player1_draw_count += 5
                    player1_draw_count_lock.release()
                elif target_player == 2:
                    player2_draw_count_lock.acquire()
                    player2_draw_count += 5
                    player2_draw_count_lock.release()

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

                    player1_moves_queue_lock.acquire()
                    if moving_from == "hand":
                        player1_moves_queue.append((f"Player 1 moved {card_name} from {moving_from} to {moving_to}", last_card_moved_from_hand))
                        print(f"Player 1 moved {card_name} from {moving_from} to {moving_to}", flush=True)
                    else:
                        player1_moves_queue.append((f"Player 1 moved {card_name} from {moving_from} to {moving_to}", None))
                        print(f"Player 1 moved {card_name} from {moving_from} to {moving_to}", flush=True)
                    player1_moves_queue_lock.release()

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

                    player2_moves_queue_lock.acquire()
                    if moving_from == "hand":
                        player2_moves_queue.append((f"Player 2 moved {card_name} from {moving_from} to {moving_to}", last_card_moved_from_hand))
                        print(f"Player 2 moved {card_name} from {moving_from} to {moving_to}", flush=True)
                    else:
                        player2_moves_queue.append((f"Player 2 moved {card_name} from {moving_from} to {moving_to}", None))
                        print(f"Player 2 moved {card_name} from {moving_from} to {moving_to}", flush=True)
                    player2_moves_queue_lock.release()


            else:
                print(f"[*] Client {client_address[0]}:{client_address[1]} sent incorrect data", flush=True)
                raise ServerError("Incorrect data received from client")

    except ServerError as se:
        print(f"[*] Error handling client {client_address[0]}:{client_address[1]}: {se}", flush=True)
    except ConnectionResetError:
        print(f"[*] Existing connection forcibly closed by client", flush=True)
    except BrokenPipeError:
        print(f"[*] Client disconnected in the middle of an operation", flush=True)
    finally:
        client_socket.close()
        connection_count_lock.acquire()
        players_with_decks_lock.acquire()
        connection_count -= 1
        players_with_decks -= 1
        if connection_count == 0:
            card_lock.acquire()
            deck = []
            payoff_pile1 = []
            payoff_pile2 = []
            draw_pile = []
            player1_hand = []
            player2_hand = []
            card_lock.release()
            players_with_decks = 0
            player1_moves_queue_lock.acquire()
            player2_moves_queue_lock.acquire()
            player1_moves_queue.clear()
            player2_moves_queue.clear()
            player2_moves_queue_lock.release()
            player1_moves_queue_lock.release()
            player1_draw_count_lock.acquire()
            player2_draw_count_lock.acquire()
            player1_draw_count = 0
            player2_draw_count = 0
            player2_draw_count_lock.release()
            player1_draw_count_lock.release()
        players_with_decks_lock.release()
        connection_count_lock.release()
        current_turn_lock.acquire()
        current_turn = 0
        current_turn_lock.release()
        print(f"[-] Connection with {client_address[0]}:{client_address[1]} closed.", flush=True)

def run_server() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.bind((HOST, PORT))
    server.listen(2)
    server.settimeout(0.5)
    print(f"[*] Listening on {HOST}:{PORT}", flush=True)

    try:
        while True:
            try:
                client_socket, addr = server.accept()
                client_handler = threading.Thread(target=handle_client, args=(client_socket, addr))
                client_handler.start()
            except socket.timeout:
                pass
    except KeyboardInterrupt:
        print("[*] KeyboardInterrupt received. Server shutting down...", flush=True)
    finally:
        server.close()


if __name__ == "__main__":
    pygame.init()
    run_server()
    pygame.quit()