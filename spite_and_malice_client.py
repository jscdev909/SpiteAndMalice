import re
import socket
import pygame
from card import CardPosition, receive_cards, send_cards
from socket_utils import send_message, receive_message

DARK_GREEN = (0, 100, 0)
WHITE = (255, 255, 255)
WINDOW_WIDTH = 925
WINDOW_HEIGHT = 950

FPS = 60

HOST = "127.0.0.1"
PORT = 65432

class ClientError(Exception):
    pass

def main():

    pygame.init()

    display_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Spite and Malice")

    discard_piles1 = [[], [], [], []]
    discard_piles1_rects = [None, None, None, None]

    discard_piles2 = [[], [], [], []]
    discard_piles2_rects = [None, None, None, None]

    build_piles = [[], [], [], []]
    build_piles_rects = [None, None, None, None]

    card_back = pygame.image.load("assets/card_back_red.png").convert_alpha()
    card_back = pygame.transform.scale(card_back, (100, 150))
    card_back_rect = card_back.get_rect()

    currently_dragging_card = False
    card_being_dragged = None

    game_result_determined = False

    original_dragging_x = 0
    original_dragging_y = 0

    font = pygame.font.SysFont("Arial", 30)
    game_result_font = pygame.font.SysFont("Arial", 60)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:

            # Connection screen
            display_surface.fill(DARK_GREEN)

            connection_text = font.render("Connecting to server, please wait...", True, WHITE, DARK_GREEN)
            connection_text_rect = connection_text.get_rect()
            connection_text_rect.centerx = WINDOW_WIDTH//2
            connection_text_rect.centery = WINDOW_HEIGHT//2
            display_surface.blit(connection_text, connection_text_rect)
            pygame.display.update()

            server_socket.settimeout(30)
            server_socket.connect((HOST, PORT))

            # Receive player number
            send_message(server_socket, "Player ready!")
            print("Sent player ready message to server") # DEBUG
            data = receive_message(server_socket)
            print(data)

            player_number = 0
            if "You are player" in data and data[-1].isdigit():
                player_number = int(data[-1])
                print(f"Player number: {player_number}")
            elif "Game lobby is full":
                raise ClientError("Game lobby is already full!")

            opponent_player = 0
            if player_number == 1:
                opponent_player = 2
            elif player_number == 2:
                opponent_player = 1

            if player_number == 1:

                # Receive other player status message
                send_message(server_socket, "Has player 2 joined?")
                data = receive_message(server_socket)

                if data == "Waiting for player 2":
                    # Wait for player 2
                    player1_text = font.render("You are player 1. Waiting for player 2...", True, WHITE, DARK_GREEN)
                    player1_text_rect = player1_text.get_rect()
                    player1_text_rect.centerx = WINDOW_WIDTH // 2
                    player1_text_rect.centery = WINDOW_HEIGHT // 2
                    while True:
                        display_surface.fill(DARK_GREEN)
                        display_surface.blit(player1_text, player1_text_rect)
                        pygame.display.update()
                        send_message(server_socket, "Has player 2 joined?")
                        data = receive_message(server_socket)
                        if data == "Player 2 has joined":
                            break
                        else:
                            pygame.time.wait(2000)

            elif player_number == 2:
                player1_text = font.render(f"You are player 2. Player 1 has already joined", True, WHITE, DARK_GREEN)
                player1_text_rect = player1_text.get_rect()
                player1_text_rect.centerx = WINDOW_WIDTH // 2
                player1_text_rect.centery = WINDOW_HEIGHT // 2
                display_surface.fill(DARK_GREEN)
                display_surface.blit(player1_text, player1_text_rect)
                pygame.display.update()
                pygame.time.wait(2000)

            send_message(server_socket, "Awaiting card data")
            print("Sent awaiting card data message to server") # DEBUG

            payoff_pile1 = []
            payoff_pile2 = []
            draw_pile = []

            receiving_cards_text = font.render("Receiving card data from server...", True, WHITE, DARK_GREEN)
            receiving_cards_rect = receiving_cards_text.get_rect()
            receiving_cards_rect.centerx = WINDOW_WIDTH // 2
            receiving_cards_rect.centery = WINDOW_HEIGHT // 2
            display_surface.fill(DARK_GREEN)
            display_surface.blit(receiving_cards_text, receiving_cards_rect)
            pygame.display.update()

            # Receive payoff pile 1
            print("Receiving payoff pile 1")
            data = receive_message(server_socket)

            if data == "Sending payoff pile 1":
                payoff_pile1 = receive_cards(server_socket, 20)
                if not payoff_pile1:
                    raise ClientError("Error receiving payoff pile 1 from server")
                print("Payoff pile 1 received on client:")
                for payoff_pile_card in payoff_pile1:
                    print(f"{payoff_pile_card.name}:{payoff_pile_card.order}")

            # Receive payoff pile 2
            print("Receiving payoff pile 2")
            data = receive_message(server_socket)

            if data == "Sending payoff pile 2":
                payoff_pile2 = receive_cards(server_socket, 20)
                if not payoff_pile2:
                    raise ClientError("Error receiving payoff pile 2 from server")
                print("Payoff pile 2 received on client:")
                for payoff_pile_card in payoff_pile2:
                    print(f"{payoff_pile_card.name}:{payoff_pile_card.order}")

            # Receive draw pile
            print("Receiving draw pile")
            data = receive_message(server_socket)

            if data == "Sending draw pile":
                draw_pile = receive_cards(server_socket, 168)
                if not draw_pile:
                    raise ClientError("Error receiving draw pile from server")
                print("Draw pile received on client:")
                for draw_pile_card in draw_pile:
                    print(f"{draw_pile_card.name}:{draw_pile_card.order}")

            print("in here 60 - client")
            send_message(server_socket, "Is the other player still connected?")
            data = receive_message(server_socket)

            if data == "No":
                raise ClientError("Other player disconnected!")

            while True:
                send_message(server_socket, "Have both players received the decks and piles?")
                data = receive_message(server_socket)
                if data == "Yes":
                    break
                elif data == "No":
                    pygame.time.wait(2000)

            current_turn = 0

            running = True

            current_hand = []
            draggable_cards = []
            draggable_cards_set = False
            networking_delay_timer = 10
            opponents_hand_size = 0
            draw_pile_needs_to_be_reshuffled = False

            opponent_draw_count = 0

            clock = pygame.time.Clock()

            first_turn = True

            while running:

                clock.tick(FPS)

                send_message(server_socket, "Is the other player still connected?")
                data = receive_message(server_socket)
                if data == "No":
                    raise ClientError("Other player disconnected!")

                if current_turn == player_number:
                    opponent_draw_count = 0
                    if not draggable_cards_set:
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
                else:

                    if not draggable_cards_set:
                        draggable_cards = []
                        draggable_cards_set = True

                    if networking_delay_timer == 0:
                        if current_turn != player_number:
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
                            elif moved_to == "discard pile 1":
                                if opponent_player == 1:
                                    discard_piles1[1].append(received_card)
                                elif opponent_player == 2:
                                    discard_piles2[1].append(received_card)
                            elif moved_to == "discard pile 2":
                                if opponent_player == 1:
                                    discard_piles1[2].append(received_card)
                                elif opponent_player == 2:
                                    discard_piles2[2].append(received_card)
                            elif moved_to == "discard pile 3":
                                if opponent_player == 1:
                                    discard_piles1[3].append(received_card)
                                elif opponent_player == 2:
                                    discard_piles2[3].append(received_card)
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
                    # Send request to server first
                    send_message(server_socket, "Draw pile needs to be reshuffled")

                    # Then send new draw pile length
                    send_message(server_socket, str(len(draw_pile) + len(cards_to_shuffle)))

                    # DEBUG
                    print(f"New draw pile length sent to server from client {player_number}: {str(len(draw_pile) + len(cards_to_shuffle))}")

                    response = receive_message(server_socket)
                    if response == "Ready to receive new draw pile cards":

                        print(f"Sending new draw pile cards - player {player_number}") # DEBUG
                        send_message(server_socket, str(len(cards_to_shuffle)))
                        send_cards(server_socket, cards_to_shuffle)

                    print(f"Requesting the new draw pile - player {player_number}") # DEBUG
                    send_message(server_socket, "Please send the draw pile")
                    draw_pile_length = receive_message(server_socket)
                    print(f"Draw pile length from server: {draw_pile_length}") # DEBUG

                    if draw_pile_length and draw_pile_length.strip().isdigit():
                        draw_pile_length = int(draw_pile_length.strip())
                    else:
                        raise ClientError("Issue syncing draw pile with server")

                    draw_pile = receive_cards(server_socket, draw_pile_length)

                    if not draw_pile:
                        raise ClientError("Server returned an empty draw pile")

                    print(f"Listing new draw pile cards received for client {player_number}")

                    # DEBUG
                    for draw_pile_card in draw_pile:
                        print(f"{draw_pile_card.name}: {draw_pile_card.order}")

                    draw_pile_needs_to_be_reshuffled = False

                    shuffle_sound_effect = pygame.mixer.Sound("assets/shuffle_cards.wav")
                    shuffle_sound_effect.play()

                send_message(server_socket, "Whose turn is it?")
                data = receive_message(server_socket)

                if int(data[-1]) != current_turn:
                    draggable_cards_set = False

                if data == "Player 1":
                    current_turn = 1
                elif data == "Player 2":
                    current_turn = 2

                if not current_hand and current_turn == player_number:
                    send_message(server_socket, f"Player {player_number} draws 5 cards")
                    for _ in range(0, 5, 1):
                        current_hand.append(draw_pile.pop())
                    draw_cards_sound_effect = pygame.mixer.Sound("assets/dealing_cards.wav")
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

                if first_turn or networking_delay_timer == 0:
                    send_message(server_socket, f"How many cards are in player {opponent_player}'s hand?")
                    num_cards = receive_message(server_socket)
                    if num_cards.isdigit():
                        opponents_hand_size = int(num_cards)
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

                current_turn_text = font.render(f"Current turn:\n   Player {current_turn}", True, WHITE, DARK_GREEN)
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
                    shuffle_sound_effect = pygame.mixer.Sound("assets/shuffle_cards.wav")
                    shuffle_sound_effect.play()
                    pygame.time.wait(1000)
                    first_turn = False

                if networking_delay_timer == 0:
                    networking_delay_timer = 10
                else:
                    networking_delay_timer -= 1

                if game_result_determined:
                    paused = True
                    while paused:
                        for event in pygame.event.get():
                            if event.type == pygame.QUIT:
                                paused = False
                    break

    except ConnectionRefusedError as cre:
        display_surface.fill(DARK_GREEN)
        error_message = "Server actively refused the client connection.\n       Please check the server and restart."
        error_text = font.render(error_message, True, WHITE, DARK_GREEN)
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
    except ClientError as ce:
        display_surface.fill(DARK_GREEN)
        error_message = ""
        if "]" in str(ce):
            error_message = "There was an issue communicating with the server.\nPlease restart the program and try again."
        elif str(ce) == "timed out":
            error_message = "Connection to the server timed out (30 seconds)"
        else:
            error_message = str(ce)
        error_text = font.render(error_message, True, WHITE, DARK_GREEN)
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
    main()