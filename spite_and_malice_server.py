import socket
import threading
import re
import random
import tomllib
import sys
import platform
from player import Player
from card import Card, CardPosition, send_cards, deal, create_deck
from socket_utils import receive_message, send_message
from path_utils import get_path
from pathlib import Path

VERSION = "1.1.0"
HOST = "0.0.0.0"


class ServerError(Exception):
    pass

class ClientHandler:
    players: list[Player] = []
    connection_count = 0
    current_turn = 0
    current_turn_lock = threading.Lock()
    connection_count_lock = threading.Lock()
    card_lock = threading.Lock()
    deck: list[Card] = []
    draw_pile: list[Card] = []
    build_piles: list[list[Card]] = [[], [], [], []]
    rematch_setup_complete = False
    rematch_setup_lock = threading.Lock()

    def __init__(self):
        self.player_number = 0

    def handle_client(self, client_socket: socket.socket, client_address: tuple[str, int], num_decks: int, payoff_pile_size: int) -> None:

        print(f"[+] Accepted connection from {client_address[0]}:{client_address[1]}", flush=True)

        try:
            while True:
                request = receive_message(client_socket)
                if not request:
                    print("[*] Client disconnected!", flush=True)
                    break

                elif "Player ready!" in request:
                    ClientHandler.connection_count_lock.acquire()
                    if ClientHandler.connection_count == 2:
                        send_message(client_socket, "Game lobby is full")
                        ClientHandler.connection_count_lock.release()
                    else:
                        ClientHandler.connection_count += 1
                        self.player_number = ClientHandler.connection_count
                        ClientHandler.connection_count_lock.release()

                        player_name_match = re.search(r"Name: (.*)", request)
                        if player_name_match:
                            player_name = player_name_match.group(1)
                            new_player = Player(self.player_number, player_name)
                            ClientHandler.players.append(new_player)
                            print(f"[*] Player {new_player.number} ({new_player.name}) has joined the game", flush=True)
                            send_message(client_socket,f"You are player {new_player.number}")
                        else:
                            raise ServerError("Received an invalid player name")

                # Note: This request should only be sent by the player 1 client
                elif request == "Has player 2 joined?":
                    ClientHandler.connection_count_lock.acquire()
                    if ClientHandler.connection_count == 2:
                        ClientHandler.connection_count_lock.release()
                        send_message(client_socket, "Player 2 has joined")
                    elif ClientHandler.connection_count == 1:
                        ClientHandler.connection_count_lock.release()
                        send_message(client_socket, "Waiting for player 2")
                    else:
                        ClientHandler.connection_count_lock.release()
                        raise ServerError("Has player 2 joined request - Invalid connection count")


                elif "What is player" in request and "name" in request:
                    pattern = r"player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError("Could not parse target player ID from client data")

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if p.number == target_player), None)
                        if not player:
                            raise ServerError(
                                f"Player name request - Object for player {target_player} does not exist")
                        send_message(client_socket, player.name)
                    else:
                        raise ServerError(f"Invalid player ID ({target_player}) specified in client data")


                elif "Player" in request and "did not want a re-match" in request:
                    pattern = r"Player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError(
                            "Could not parse target player ID from client data")

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if p.number == target_player), None)
                        if not player:
                            raise ServerError(
                                f"Player did not want re-match request - Object for player {target_player} does not exist")
                        player.rematch = False
                    else:
                        raise ServerError(f"Invalid player ID ({target_player}) specified in client data")


                elif "Player" in request and "wants a re-match" in request:
                    pattern = r"Player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError(
                            "Could not parse target player ID from client data")

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if p.number == target_player), None)
                        if not player:
                            raise ServerError(
                                f"Player wants re-match request - Object for player {target_player} does not exist")
                        player.rematch = True
                    else:
                        raise ServerError(f"Invalid player ID ({target_player}) specified in client data")


                elif "Does player" in request and "also want a re-match?" in request:
                    pattern = r"player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError(
                            "Could not parse target player ID from client data")

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if p.number == target_player), None)
                        if not player:
                            raise ServerError(
                                f"Does opponent also want a rematch request - Object for player {target_player} does not exist")

                        if player.rematch is True:
                            send_message(client_socket, "Yes")
                        elif player.rematch is False:
                            send_message(client_socket, "No")
                        else:
                            send_message(client_socket, "Undecided")

                    else:
                        raise ServerError(f"Invalid player ID ({target_player}) specified in client data")


                elif request == "Set up a new game":
                    ClientHandler.rematch_setup_lock.acquire()

                    if ClientHandler.rematch_setup_complete:
                        ClientHandler.rematch_setup_complete = False
                    else:
                        print("[*] New game requested, resetting game parameters...", flush=True)
                        ClientHandler.card_lock.acquire()
                        ClientHandler.deck = []
                        ClientHandler.build_piles = [[], [], [], []]
                        ClientHandler.draw_pile = []
                        ClientHandler.card_lock.release()

                        for player in ClientHandler.players:
                            player.reset()

                        ClientHandler.current_turn_lock.acquire()
                        ClientHandler.current_turn = 0
                        ClientHandler.current_turn_lock.release()
                        ClientHandler.rematch_setup_complete = True

                    ClientHandler.rematch_setup_lock.release()

                elif request == "Draw pile needs to be reshuffled":

                    ClientHandler.card_lock.acquire()

                    draw_pile_needs_to_be_reshuffled = False
                    cards_to_shuffle = []
                    if len(ClientHandler.build_piles[0]) == 12:
                        cards_to_shuffle += ClientHandler.build_piles[0]
                        ClientHandler.build_piles[0] = []
                        draw_pile_needs_to_be_reshuffled = True
                    if len(ClientHandler.build_piles[1]) == 12:
                        cards_to_shuffle += ClientHandler.build_piles[1]
                        ClientHandler.build_piles[1] = []
                        draw_pile_needs_to_be_reshuffled = True
                    if len(ClientHandler.build_piles[2]) == 12:
                        cards_to_shuffle += ClientHandler.build_piles[2]
                        ClientHandler.build_piles[2] = []
                        draw_pile_needs_to_be_reshuffled = True
                    if len(ClientHandler.build_piles[3]) == 12:
                        cards_to_shuffle += ClientHandler.build_piles[3]
                        ClientHandler.build_piles[3] = []
                        draw_pile_needs_to_be_reshuffled = True

                    if draw_pile_needs_to_be_reshuffled:
                        ClientHandler.draw_pile += cards_to_shuffle
                        random.shuffle(ClientHandler.draw_pile)

                    ClientHandler.card_lock.release()

                elif request == "Create new deck and payoff piles":
                    ClientHandler.card_lock.acquire()

                    if len(ClientHandler.players) != 2:
                        ClientHandler.card_lock.release()
                        raise ServerError("Request to create new deck and payoff piles without two players")

                    if not ClientHandler.deck and not ClientHandler.players[0].payoff_pile and not ClientHandler.players[1].payoff_pile and not ClientHandler.draw_pile:
                        # Create the deck, payoff piles and draw pile
                        print(f"[*] Creating the deck (player {self.player_number} thread)...", flush=True)
                        full_deck = create_deck(get_path(Path("assets") / "card_faces"), num_decks)
                        print(f"[*] Creating the payoff piles and draw pile (player {self.player_number} thread)...", flush=True)
                        ClientHandler.players[0].payoff_pile, ClientHandler.players[1].payoff_pile, ClientHandler.draw_pile = deal(full_deck, payoff_pile_size)
                    else:
                        print(f"[*] Status update from player {self.player_number} thread: other thread already created decks and piles", flush=True)

                    ClientHandler.card_lock.release()

                elif request == "Is the other player still connected?":
                    ClientHandler.connection_count_lock.acquire()
                    if ClientHandler.connection_count == 1:
                        send_message(client_socket, "No")
                    elif ClientHandler.connection_count == 2:
                        send_message(client_socket, "Yes")
                    else:
                        ClientHandler.connection_count_lock.release()
                        raise ServerError("Other player still connected request - Invalid connection count")
                    ClientHandler.connection_count_lock.release()

                elif "How many cards are in player" in request and "hand" in request:
                    pattern = r"player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError(
                            "Could not parse target player ID from client data")

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if target_player == p.number), None)
                        if not player:
                            raise ServerError(
                                f"Player hand card count request - Object for player {target_player} does not exist")
                        ClientHandler.card_lock.acquire()
                        send_message(client_socket, str(len(player.hand)))
                        ClientHandler.card_lock.release()
                    else:
                        raise ServerError(f"Invalid player ID ({target_player}) specified in client data")

                elif "How many cards are left in player" in request and "payoff pile?" in request:
                    pattern = r"player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError(
                            "Could not parse target player ID from client data")

                    ClientHandler.card_lock.acquire()

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if target_player == p.number), None)
                        if not player:
                            ClientHandler.card_lock.release()
                            raise ServerError(f"Payoff pile count request - Object for target player {target_player} does not exist")
                        send_message(client_socket, str(len(player.payoff_pile)))
                    else:
                        ClientHandler.card_lock.release()
                        raise ServerError(f"Attempt to check payoff pile of unrecognized target player {target_player}")

                    ClientHandler.card_lock.release()

                elif "Send the top card of player" in request and "payoff pile" in request:
                    pattern = r"player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError(
                            "Could not parse target player ID from client data")

                    ClientHandler.card_lock.acquire()

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if p.number == target_player), None)
                        if not player:
                            ClientHandler.card_lock.release()
                            raise ServerError(
                                f"Payoff pile top card request - Object for player {target_player} does not exist")
                        send_cards(client_socket, [player.payoff_pile[-1]])
                    else:
                        ClientHandler.card_lock.release()
                        raise ServerError(f"Request to send top card of payoff pile of unrecognized target player {target_player}")

                    ClientHandler.card_lock.release()

                elif request == "Is the game over?":

                    if len(ClientHandler.players) != 2:
                        raise ServerError("Attempt to check game over without two players in game")

                    ClientHandler.card_lock.acquire()
                    if not ClientHandler.players[0].payoff_pile or not ClientHandler.players[1].payoff_pile or not ClientHandler.draw_pile:
                        send_message(client_socket, "Yes")
                    else:
                        send_message(client_socket, "No")
                    ClientHandler.card_lock.release()

                elif request == "Who won the game?":

                    if len(ClientHandler.players) != 2:
                        raise ServerError("Attempt to retrieve final game result without two players in game")

                    ClientHandler.card_lock.acquire()

                    if not ClientHandler.players[0].payoff_pile:
                        send_message(client_socket, f"Player {ClientHandler.players[0].number}")
                    elif not ClientHandler.players[1].payoff_pile:
                        send_message(client_socket,f"Player {ClientHandler.players[1].number}")
                    elif not ClientHandler.draw_pile:
                        if len(ClientHandler.players[0].payoff_pile) < len(ClientHandler.players[1].payoff_pile):
                            send_message(client_socket, f"Player {ClientHandler.players[0].number}")
                        elif len(ClientHandler.players[0].payoff_pile) > len(ClientHandler.players[1].payoff_pile):
                            send_message(client_socket,f"Player {ClientHandler.players[1].number}")
                        elif len(ClientHandler.players[0].payoff_pile) == len(ClientHandler.players[1].payoff_pile):
                            send_message(client_socket, "Stalemate")

                    ClientHandler.card_lock.release()

                elif request == "How many cards are left in the draw pile?":

                    ClientHandler.card_lock.acquire()
                    send_message(client_socket, str(len(ClientHandler.draw_pile)))
                    ClientHandler.card_lock.release()

                elif "What was" in request and "last move" in request:
                    pattern = r"player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).isdigit():
                        target_player = int(first_match.group(1))
                    else:
                        raise ServerError("Invalid player ID specified in request")

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if p.number == target_player), None)
                        if not player:
                            raise ServerError(
                                f"Players last move request - Object for player {target_player} does not exist")

                        if player.moves_queue:
                            last_move = player.moves_queue.popleft()
                            send_message(client_socket, last_move[0])
                            if last_move[1] is not None:
                                send_cards(client_socket, [last_move[1]])
                        else:
                            send_message(client_socket, "Nothing")

                    else:
                        raise ServerError(f"Request to send last move of unrecognized player {target_player}")



                elif request == "Whose turn is it?":

                    if len(ClientHandler.players) != 2:
                        raise ServerError("Attempt to determine current turn without two players in game")

                    ClientHandler.current_turn_lock.acquire()
                    if ClientHandler.current_turn == 0:
                        if ClientHandler.players[0].payoff_pile[-1].rank > ClientHandler.players[1].payoff_pile[-1].rank:
                            ClientHandler.current_turn = ClientHandler.players[0].number
                        elif ClientHandler.players[0].payoff_pile[-1].rank < ClientHandler.players[1].payoff_pile[-1].rank:
                            ClientHandler.current_turn = ClientHandler.players[1].number
                        else:
                            # Determine the first turn of the game randomly if ranks are equal
                            ClientHandler.current_turn = random.randint(1, 2)
                    send_message(client_socket, f"Player {ClientHandler.current_turn}")
                    ClientHandler.current_turn_lock.release()

                elif "ended their turn" in request:

                    player1 = next((p for p in ClientHandler.players if p.number == 1), None)
                    player2 = next((p for p in ClientHandler.players if p.number == 2), None)
                    if not player1:
                        raise ServerError(
                            "Players last move request - Object for player 1 does not exist")
                    if not player2:
                        raise ServerError(
                            "Players last move request - Object for player 2 does not exist")

                    ClientHandler.current_turn_lock.acquire()

                    current_turn_player = next((p for p in ClientHandler.players if p.number == ClientHandler.current_turn), None)
                    current_turn_player.draw_count = 0

                    # Switch turns
                    if ClientHandler.current_turn == 1:
                        ClientHandler.current_turn = 2
                    elif ClientHandler.current_turn == 2:
                        ClientHandler.current_turn = 1

                    ClientHandler.current_turn_lock.release()

                elif "Player" in request and "draws 5 cards" in request:
                    pattern = r"Player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError("Invalid player ID specified in draw request")

                    if target_player == 1 or target_player == 2:
                        player = next((p for p in ClientHandler.players if p.number == target_player), None)
                        if not player:
                            raise ServerError(
                                f"Player draws 5 cards request - Object for player {target_player} does not exist")

                        ClientHandler.card_lock.acquire()

                        for _ in range(5):
                            player.hand.append(ClientHandler.draw_pile.pop())
                        send_cards(client_socket, player.hand)

                        ClientHandler.card_lock.release()

                        player.draw_count += 5

                    else:
                        raise ServerError(
                            f"Player draws 5 cards request - unrecognized player {target_player}")


                elif "moved" in request and "from their" in request:
                    last_card_moved_from_hand = None
                    pattern = r"Player (\d)"
                    first_match = re.search(pattern, request)
                    if first_match and first_match.group(1).strip().isdigit():
                        target_player = int(first_match.group(1).strip())
                    else:
                        raise ServerError("Invalid player ID specified in move request")
                    pattern = r"moved\b(.*)\bfrom"
                    first_match = re.search(pattern, request)
                    if first_match:
                        card_name = first_match.group(1).strip()
                    else:
                        raise ServerError("Invalid card name specified in move request")
                    pattern = r"their\b(.*)\bto"
                    first_match = re.search(pattern, request)
                    if first_match:
                        moving_from = first_match.group(1).strip()
                    else:
                        raise ServerError("Invalid 'moving from' location specified in move request")
                    pattern = r"to\b(.*)$"
                    first_match = re.search(pattern, request)
                    if first_match:
                        moving_to = first_match.group(1).strip()
                    else:
                        raise ServerError("Invalid 'moving to' location specified in move request")

                    if target_player != 1 and target_player != 2:
                        raise ServerError(f"Invalid target player {target_player} specified in move request")

                    player = next((p for p in ClientHandler.players if target_player == p.number), None)
                    if not player:
                        raise ServerError(f"Move request - Object for player {target_player} does not exist")

                    if moving_from == "hand":

                        if moving_to.startswith("discard pile") or moving_to.startswith("build pile"):

                            if not moving_to[-1].isdigit():
                                if moving_to.startswith("discard pile"):
                                    raise ServerError(f"Move request - Invalid discard pile number to move to ({moving_to[-1]})")
                                else:
                                    raise ServerError(f"Move request - Invalid build pile number to move to ({moving_to[-1]})")

                            to_pile_num = int(moving_to[-1])

                            if to_pile_num < 0 or to_pile_num > 3:
                                if moving_to.startswith("discard pile"):
                                    raise ServerError(f"Move request - Invalid discard pile number to move to ({to_pile_num}")
                                else:
                                    raise ServerError(f"Move request - Invalid build pile number to move to ({to_pile_num})")

                            ClientHandler.card_lock.acquire()

                            card_to_move = next((card for card in player.hand if card.name == card_name), None)
                            if not card_to_move:
                                ClientHandler.card_lock.release()
                                if moving_to.startswith("discard pile"):
                                    raise ServerError(f"Move request - Card to move from hand into discard pile {to_pile_num} does not exist")
                                else:
                                    raise ServerError(f"Move request - Card to move from hand into build pile {to_pile_num} does not exist")

                            player.hand.remove(card_to_move)
                            card_to_move.position = CardPosition.FACE_UP

                            if moving_to.startswith("discard pile"):
                                player.discard_piles[to_pile_num].append(card_to_move)
                            else:
                                ClientHandler.build_piles[to_pile_num].append(card_to_move)

                            last_card_moved_from_hand = card_to_move
                            ClientHandler.card_lock.release()

                        else:
                            raise ServerError("Invalid 'moving to' location specified in move request")

                    elif moving_from.startswith("discard pile"):

                        if not moving_from[-1].isdigit():
                            raise ServerError(f"Move request - Invalid discard pile number to move from ({moving_from[-1]})")

                        from_pile_num = int(moving_from[-1])

                        if from_pile_num < 0 or from_pile_num > 3:
                            raise ServerError(f"Move request - Invalid discard pile number to move from ({from_pile_num})")

                        ClientHandler.card_lock.acquire()

                        card_to_move = player.discard_piles[from_pile_num].pop()

                        # Top card should have the same name as the card in the move request
                        if card_to_move.name != card_name:
                            ClientHandler.card_lock.release()
                            raise ServerError(f"Name of top card on discard pile {from_pile_num} did not match card name in move request")

                        if moving_to.startswith("build pile"):
                            if not moving_to[-1].isdigit():
                                ClientHandler.card_lock.release()
                                raise ServerError(f"Move request - Invalid build pile number to move to ({moving_to[-1]})")

                            to_pile_num = int(moving_to[-1])

                            if to_pile_num < 0 or to_pile_num > 3:
                                ClientHandler.card_lock.release()
                                raise ServerError(f"Move request - Invalid build pile number to move to ({to_pile_num})")

                            ClientHandler.build_piles[to_pile_num].append(card_to_move)
                            ClientHandler.card_lock.release()
                        else:
                            ClientHandler.card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")


                    elif moving_from == "payoff pile":
                        ClientHandler.card_lock.acquire()
                        card_to_move = player.payoff_pile.pop()

                        if card_to_move.name != card_name:
                            ClientHandler.card_lock.release()
                            raise ServerError("Name of top card on payoff pile did not match card name in move request")

                        # Flip over top card if payoff pile still has cards
                        if player.payoff_pile:
                            player.payoff_pile[-1].position = CardPosition.FACE_UP

                        if moving_to.startswith("build pile"):

                            if not moving_to[-1].isdigit():
                                raise ServerError(f"Move request - Invalid build pile number to move to ({moving_to[-1]})")

                            to_pile_num = int(moving_to[-1])

                            if to_pile_num < 0 or to_pile_num > 3:
                                raise ServerError(f"Move request - Invalid build pile number to move to ({to_pile_num})")

                            ClientHandler.build_piles[to_pile_num].append(card_to_move)
                            ClientHandler.card_lock.release()

                        else:
                            ClientHandler.card_lock.release()
                            raise ServerError("Invalid 'moving to' location specified in move request")
                    else:
                        raise ServerError("Invalid 'moving from' location specified in move request")

                    if moving_from == "hand":
                        player.moves_queue.append((f"Player {target_player} moved {card_name} from {moving_from} to {moving_to}", last_card_moved_from_hand))
                    else:
                        player.moves_queue.append((f"Player {target_player} moved {card_name} from {moving_from} to {moving_to}", None))

                else:
                    print(f"[*] Client {client_address[0]}:{client_address[1]} sent incorrect data", flush=True)
                    raise ServerError("Incorrect data received from client")

        except ServerError as se:
            print(f"[*] Error handling client {client_address[0]}:{client_address[1]}: {se}", flush=True)
        except ConnectionResetError:
            print("[*] Connection reset by client (client disconnected)", flush=True)
        except BrokenPipeError:
            print("[*] Client disconnected in the middle of an operation", flush=True)
        finally:
            client_socket.close()
            ClientHandler.connection_count_lock.acquire()
            ClientHandler.connection_count -= 1

            ClientHandler.card_lock.acquire()
            ClientHandler.deck = []
            ClientHandler.draw_pile = []
            ClientHandler.build_piles = [[], [], [], []]
            ClientHandler.card_lock.release()

            match ClientHandler.connection_count:
                case 0:
                    ClientHandler.players.clear()
                case 1:
                    this_player = next((p for p in ClientHandler.players if p.number == self.player_number), None)
                    if this_player:
                        ClientHandler.players.remove(this_player)
                    else:
                        ClientHandler.connection_count_lock.release()
                        raise ServerError("Could not find and remove current player object")

                    if len(ClientHandler.players) == 1:
                        ClientHandler.players[0].reset()
                    else:
                        ClientHandler.connection_count_lock.release()
                        raise ServerError("Current number of remaining players does not match connection count")
                case _:
                    ClientHandler.connection_count_lock.release()
                    raise ServerError("Connection count after player disconnect is not 0 or 1")

            ClientHandler.connection_count_lock.release()
            ClientHandler.current_turn_lock.acquire()
            ClientHandler.current_turn = 0
            ClientHandler.current_turn_lock.release()
            print(f"[-] Connection with {client_address[0]}:{client_address[1]} closed.", flush=True)

def run_server(valid_port: int, num_decks: int, payoff_pile_size: int) -> None:

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:

        server.bind((HOST, valid_port))
        server.listen(2)
        server.settimeout(1)
        print(f"[*] Listening on {HOST}:{valid_port}", flush=True)

        while True:
            try:
                client_socket, addr = server.accept()
                client_handler = ClientHandler()
                handler_thread = threading.Thread(target=client_handler.handle_client, args=(client_socket, addr, num_decks, payoff_pile_size,))
                handler_thread.start()
            except socket.timeout:
                print("Socket timed out! Consider increasing timeout value", flush=True)

    except KeyboardInterrupt:
        print("\n[*] KeyboardInterrupt received. Server shutting down...", flush=True)
    except OSError as err:
        if "Address already in use" in str(err):
            print(f"[*] Error binding to address {HOST}:{valid_port}: Address already in use", flush=True)
        elif "Permission denied" in str(err):
            # Should never reach here due to prior error checking
            print(f"[*] Error binding to port {valid_port}: Did you specify a privileged port?", flush=True)
        elif "Invalid argument" in str(err):
            # Should never reach here due to prior error checking
            print(f"[*] Error binding to port {valid_port}: Invalid port number specified", flush=True)
    finally:
        server.close()

def main():

    unknown_os = False
    if platform.system() == "Windows":
        config_file_path = Path("C:/ProgramData") / "jscdev909" / "spite_and_malice_server" / "config.toml"
    elif platform.system() == "Darwin" or platform.system() == "Linux":
        config_file_path = Path.home() / ".config" / "spite_and_malice_server" / "config.toml"
    else:
        unknown_os = True
        config_file_path = Path()

    port = 0
    decks = 0
    payoff_pile_size = 0

    try:
        if config_file_path.exists():
            print(f"Using config file found at {config_file_path}", flush=True)
            with open(config_file_path, "rb") as config_file:
                data = tomllib.load(config_file)
            if ("port" in data and 32768 <= data["port"] <= 65535 and "decks" in data and 2 <= data["decks"] <= 6
                    and "payoff_pile_size" in data and 20 <= data["payoff_pile_size"] <= 30):
                port = data["port"]
                decks = data["decks"]
                payoff_pile_size = data["payoff_pile_size"]
            else:
                print("Config file contains incorrect data, rewriting config file with new input")
                receiving_port_input = True
                while receiving_port_input:
                    user_input = input("Please enter a port number (32768-65535) for the server to listen to: ")
                    if user_input.isdigit() and 32768 <= int(user_input) <= 65535:
                        port = int(user_input)
                        receiving_port_input = False

                receiving_decks_input = True
                while receiving_decks_input:
                    user_input = input("How many playing card decks should the game use? (2-6): ")
                    if user_input.isdigit() and 2 <= int(user_input) <= 6:
                        decks = int(user_input)
                        receiving_decks_input = False

                receiving_payoff_pile_size_input = True
                while receiving_payoff_pile_size_input:
                    user_input = input("How many cards should be in each payoff pile? (20-30): ")
                    if user_input.isdigit() and 20 <= int(user_input) <= 30:
                        payoff_pile_size = int(user_input)
                        receiving_payoff_pile_size_input = False

                with open(config_file_path, "w") as config_file:
                    config_file.write(f"port = {port}\n")
                    config_file.write(f"decks = {decks}\n")
                    config_file.write(f"payoff_pile_size = {payoff_pile_size}\n")

                print(f"Re-wrote config file to {str(config_file_path)}",
                      flush=True)
        else:
            receiving_port_input = True
            while receiving_port_input:
                user_input = input("Please enter a port number (32768-65535) for the server to listen to: ")
                if user_input.isdigit() and 32768 <= int(user_input) <= 65535:
                    port = int(user_input)
                    receiving_port_input = False

            receiving_decks_input = True
            while receiving_decks_input:
                user_input = input("How many playing card decks should the game use? (2-6): ")
                if user_input.isdigit() and 2 <= int(user_input) <= 6:
                    decks = int(user_input)
                    receiving_decks_input = False

            receiving_payoff_pile_size_input = True
            while receiving_payoff_pile_size_input:
                user_input = input(
                    "How many cards should be in each payoff pile? (20-30): ")
                if user_input.isdigit() and 20 <= int(user_input) <= 30:
                    payoff_pile_size = int(user_input)
                    receiving_payoff_pile_size_input = False

            if not unknown_os:
                config_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_file_path, "w") as config_file:
                    config_file.write(f"port = {port}\n")
                    config_file.write(f"decks = {decks}\n")
                    config_file.write(f"payoff_pile_size = {payoff_pile_size}\n")

                print(f"Wrote new config file to {str(config_file_path)}", flush=True)

        run_server(port, decks, payoff_pile_size)

    except KeyboardInterrupt:
        print("\nExiting...", flush=True)


if __name__ == "__main__":
    if sys.version_info >= (3, 11):
        print(f"Spite and Malice Server - Version {VERSION}", flush=True)
        main()
    else:
        print("This script requires at least Python 3.11", flush=True)

