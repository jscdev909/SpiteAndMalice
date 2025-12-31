import socket
import threading
import pygame
import os
import time
import pickle
import struct
import re
import random
from collections import deque
from card import Card, CardPosition, send_cards, receive_cards


HOST = '127.0.0.1'
PORT = 65432

connection_count = 0
current_turn = 0
players_with_decks = 0
players_with_decks_lock = threading.Lock()
current_turn_lock = threading.Lock()
connection_count_lock = threading.Lock()
card_lock = threading.Lock()
deck = []
stock_pile1 = []
stock_pile2 = []
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

def create_deck(directory: str) -> list[Card]:
    cards = []
    for _ in range(0, 2, 1):
        for filename in os.listdir(directory):
            image_surface = pygame.image.load(os.path.join(directory, filename))
            image_surface = pygame.transform.scale(image_surface, (100, 150))
            cards.append(Card(os.path.splitext(filename)[0], pygame.surfarray.array3d(image_surface)))

    random.shuffle(cards)
    return cards


def deal(all_cards: list[Card]) -> tuple[list[Card], list[Card], list[Card]]:
    pile1 = []
    pile2 = []

    for index in range(0, 20, 1):
        if index == 19:
            dealt_card = all_cards.pop()
            dealt_card.position = CardPosition.FACE_UP
            pile1.append(dealt_card)
            dealt_card = all_cards.pop()
            dealt_card.position = CardPosition.FACE_UP
            pile2.append(dealt_card)
        else:
            pile1.append(all_cards.pop())
            pile2.append(all_cards.pop())

    remaining_cards = all_cards

    # DEBUG
    print("stock pile 1 contents in order:", flush=True)
    for card in pile1:
        print(card.name, flush=True)
    print(flush=True)
    print("stock pile 2 contents in order:", flush=True)
    for card in pile2:
        print(card.name, flush=True)
    print(flush=True)
    print("draw pile contents in order:", flush=True)
    for card in remaining_cards:
        print(card.name, flush=True)

    return pile1, pile2, remaining_cards

def handle_client(client_socket: socket.socket, client_address: tuple[str, int]) -> None:
    global connection_count, current_turn, deck, stock_pile1, stock_pile2, draw_pile
    global player1_hand, player2_hand, players_with_decks, player1_draw_count, player2_draw_count
    player_number = 0

    print(f"[+] Accepted connection from {client_address[0]}:{client_address[1]}", flush=True)

    try:
        while True:
            request = client_socket.recv(1024).decode()
            if not request:
                print("[*] Client disconnected!", flush=True)
                break
            elif request == "Player ready!":
                connection_count_lock.acquire()
                connection_count += 1
                player_number = connection_count
                connection_count_lock.release()
                response = f"You are player {player_number}"
                print(f"[*] Player {player_number} has joined the game", flush=True)
                client_socket.sendall(response.encode())

            # Note: This request should only be sent by the player 1 client
            elif request == "Has player 2 joined?":
                connection_count_lock.acquire()
                if connection_count == 2:
                    connection_count_lock.release()
                    response = "Player 2 has joined"
                    client_socket.sendall(response.encode())
                else:
                    connection_count_lock.release()
                    response = "Waiting for player 2"
                    client_socket.sendall(response.encode())

            # elif request == "Draw pile needs to be reshuffled":
            #
            #
            #
            #
            #
            # elif request == "Is draw pile done being reshuffled?":
            #
            # elif request == "Download draw pile":



            elif request == "Awaiting card data":
                print(f"[*] Player {player_number} is awaiting card data", flush=True)
                card_lock.acquire()

                if not deck and not stock_pile1 and not stock_pile2 and not draw_pile:
                    # Got the lock, create the deck, stock piles and draw pile
                    print(f"[*] Creating the deck (player {player_number} thread)...", flush=True)
                    deck = create_deck("assets/card_faces")
                    print(f"[*] Creating the stock piles and draw pile (player {player_number} thread)...", flush=True)
                    stock_pile1, stock_pile2, draw_pile = deal(deck)
                else:
                    print(f"[*] Status update from player {player_number} thread: other thread already created decks and piles", flush=True)
                    time.sleep(5)

                response = "Sending stock pile 1"
                message_length = struct.pack('!I', len(response))
                client_socket.sendall(message_length + response.encode())
                print(f"[*] Length of stock pile 1: {len(stock_pile1)}",
                      flush=True)
                send_cards(client_socket, stock_pile1)
                response = "Sending stock pile 2"
                message_length = struct.pack('!I', len(response))
                client_socket.sendall(message_length + response.encode())
                print(f"[*] Length of stock pile 2: {len(stock_pile2)}",
                      flush=True)
                send_cards(client_socket, stock_pile2)
                response = "Sending draw pile"
                message_length = struct.pack('!I', len(response))
                client_socket.sendall(message_length + response.encode())
                print(f"[*] Length of draw pile: {len(draw_pile)}",
                      flush=True)
                send_cards(client_socket, draw_pile)

                card_lock.release()

                players_with_decks_lock.acquire()
                players_with_decks += 1
                players_with_decks_lock.release()

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
                client_socket.sendall(response.encode())

            elif "How many cards" in request and "hand" in request:
                target_player = 0
                for char in request:
                    if char.isdigit():
                        target_player = int(char)
                        break
                card_lock.acquire()
                if target_player == 1:
                    client_socket.sendall(str(len(player1_hand)).encode())
                elif target_player == 2:
                    client_socket.sendall(str(len(player2_hand)).encode())
                card_lock.release()

            elif "other player still connected" in request:
                connection_count_lock.acquire()
                response = ""
                if connection_count == 1:
                    response = "No"
                elif connection_count == 2:
                    response = "Yes"
                connection_count_lock.release()
                client_socket.sendall(response.encode())

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
                    client_socket.sendall(str(player1_draw_count).encode())
                    player1_draw_count_lock.release()
                elif target_player == 2:
                    player2_draw_count_lock.acquire()
                    client_socket.sendall(str(player2_draw_count).encode())
                    player2_draw_count_lock.release()

            # elif "Did player" in request and "draw 5 cards this turn?" in request:
            #     target_player = 0
            #     pattern = r"player (\d)"
            #     first_match = re.search(pattern, request)
            #     if first_match and first_match.group(1).strip().isdigit():
            #         target_player = int(first_match.group(1).strip())
            #     else:
            #         raise ServerError("Invalid player ID specified in client data")
            #
            #     response = ""
            #     card_lock.acquire()
            #     if target_player == 1:
            #         if len(player1_hand) == 5:
            #             response = "Yes"
            #         else:
            #             response = "No"
            #     if target_player == 2:
            #         if len(player2_hand) == 5:
            #             response = "Yes"
            #         else:
            #             response = "No"
            #     card_lock.release()
            #     client_socket.sendall(response.encode())



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
                        client_socket.sendall(last_move[0].encode())
                        if last_move[1] is not None:
                            pickled_object = pickle.dumps(last_move[1])
                            message_length = struct.pack('>I', len(pickled_object))
                            client_socket.sendall(message_length + pickled_object)
                    else:
                        client_socket.sendall("Nothing".encode())
                    player1_moves_queue_lock.release()
                elif target_player == 2:
                    player2_moves_queue_lock.acquire()
                    if player2_moves_queue:
                        print("in here 2 - server")
                        last_move = player2_moves_queue.popleft()
                        client_socket.sendall(last_move[0].encode())
                        if last_move[1] is not None:
                            pickled_object = pickle.dumps(last_move[1])
                            message_length = struct.pack('>I', len(pickled_object))
                            client_socket.sendall(message_length + pickled_object)
                    else:
                        client_socket.sendall("Nothing".encode())
                    player2_moves_queue_lock.release()
                else:
                    # Should never get here but raise an exception just in case
                    raise ServerError("Invalid player ID specified in request")

            elif request == "Whose turn is it?":
                current_turn_lock.acquire()
                if current_turn == 0:
                    current_turn = random.randint(1, 2)
                    print(f"Setting current turn to {current_turn}", flush=True)
                client_socket.sendall(f"Player {current_turn}".encode())
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

                    elif moving_from == "stock pile":
                        card_lock.acquire()
                        card_to_move = stock_pile1[-1]
                        print("in here 7", flush=True)
                        print("DEBUG---------------------------", flush=True)
                        print(card_to_move.name, flush=True)
                        print(card_name, flush=True)
                        if card_to_move.name != card_name:
                            raise ServerError("Name of top card on stock pile did not match card name in move request")
                        stock_pile1.pop()
                        # Flip over next card
                        stock_pile1[-1].position = CardPosition.FACE_UP
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

                    elif moving_from == "stock pile":
                        card_lock.acquire()
                        card_to_move = stock_pile2[-1]
                        if card_to_move.name != card_name:
                            print("in here 6", flush=True)
                            print("DEBUG---------------------------", flush=True)
                            print(card_to_move.name, flush=True)
                            print(card_name, flush=True)
                            raise ServerError("Name of top card on stock pile did not match card name in move request")
                        stock_pile2.pop()
                        # Flip over next card
                        stock_pile2[-1].position = CardPosition.FACE_UP
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
        print(f"[-] Error handling client {client_address[0]}:{client_address[1]}: {se}", flush=True)
    finally:
        client_socket.close()
        connection_count_lock.acquire()
        players_with_decks_lock.acquire()
        connection_count -= 1
        players_with_decks -= 1
        if connection_count == 0:
            card_lock.acquire()
            deck = []
            stock_pile1 = []
            stock_pile2 = []
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