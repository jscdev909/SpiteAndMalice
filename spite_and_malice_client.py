import re
import socket
import threading
import tomllib
import os
import sys
import pygame
import pygame_gui

from card import CardPosition, receive_cards
from socket_utils import send_message, receive_message
from path_utils import get_path
from enum import Enum
from pathlib import Path


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
    CARD_DATA_RECEIVE_ERROR = 3,
    OTHER_PLAYER_DISCONNECTED = 4

class RematchStatus(Enum):
    UNSET = 0,
    IN_PROGRESS = 1,
    RECEIVING_CARD_DATA = 2,
    COMPLETE = 3,
    ERROR = 4

class RematchErrorStatus(Enum):
    UNSET = 0,
    ERROR_RECEIVING_CARD_DATA = 1


class ClientError(Exception):
    pass

VERSION = "dev.1.7.26"

DARK_GREEN = (0, 100, 0)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)

WINDOW_WIDTH = 925
WINDOW_HEIGHT = 950

FPS = 60

host = ""
port = 0

player_number = 0
player_name = ""
opponent_player = 0
opponent_player_name = ""
payoff_pile1_top_card = None
payoff_pile2_top_card = None
current_hand = []

sound_option = "On"
card_back_color_option = "Red"

initial_setup_status = SetupStatus.UNSET
initial_setup_error_status = SetupErrorStatus.UNSET

rematch_setup_status = RematchStatus.UNSET
rematch_setup_error_status = RematchErrorStatus.UNSET


def get_user_configuration(display_surface: pygame.Surface) -> bool:
    global player_number, player_name, host, port, sound_option, card_back_color_option, VERSION

    getting_user_input = True
    check_user_input = False

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

    manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT),
                                   theme_path=get_path("theme.json"))

    name_entry_line = pygame_gui.elements.UITextEntryLine(
        relative_rect=pygame.Rect(450, 250, 225, 50), manager=manager)
    name_entry_line.set_text_length_limit(8)
    server_ip_entry_line = pygame_gui.elements.UITextEntryLine(
        relative_rect=pygame.Rect(425, 400, 300, 50), manager=manager)
    server_ip_entry_line.set_text_length_limit(15)
    server_port_entry_line = pygame_gui.elements.UITextEntryLine(
        relative_rect=pygame.Rect(425, 475, 125, 50), manager=manager)
    server_port_entry_line.set_text_length_limit(5)
    ok_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect(WINDOW_WIDTH // 2 - 50, 850, 100, 50), text="OK", manager=manager)
    sound_option_choices = ["On", "Off"]
    sound_starting_option = ""
    card_back_color_option_choices = ["Red", "Black", "Blue", "Green",
                                      "Orange", "Purple"]
    card_back_color_starting_option = ""

    if config_file_path.exists():
        with open(config_file_path, "rb") as config_file:
            data = tomllib.load(config_file)
        if ("name" in data and data["name"] and "server_ip" in data and
                re.search(server_ip_pattern, data["server_ip"]) is not None and
                "server_port" in data and 32768 < data[
                    "server_port"] < 65535 and
                "sound" in data and "card_back_color" in data):
            name_entry_line.set_text(data["name"])
            server_ip_entry_line.set_text(data["server_ip"])
            server_port_entry_line.set_text(str(data["server_port"]))
            sound_starting_option = data["sound"]
            card_back_color_starting_option = data["card_back_color"]

    if sound_starting_option:
        sound_option_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=sound_option_choices,
            starting_option=sound_starting_option,
            relative_rect=pygame.Rect(465, 665, 100, 50), manager=manager)
    else:
        sound_option_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=sound_option_choices,
            starting_option=sound_option_choices[0],
            relative_rect=pygame.Rect(465, 665, 100, 50), manager=manager)

    if card_back_color_starting_option:
        card_back_color_option_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=card_back_color_option_choices,
            starting_option=card_back_color_starting_option,
            relative_rect=pygame.Rect(540, 740, 100, 50), manager=manager)
    else:
        card_back_color_option_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=card_back_color_option_choices,
            starting_option=card_back_color_option_choices[0],
            relative_rect=pygame.Rect(540, 740, 100, 50), manager=manager)

    name_input_error = False
    server_ip_input_error = False
    server_port_input_error = False
    user_quit_game = False

    clock = pygame.time.Clock()

    while getting_user_input:
        time_delta = clock.tick(FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                user_quit_game = True
                getting_user_input = False

            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == ok_button:
                    check_user_input = True

            manager.process_events(event)

        manager.update(time_delta)

        # Check user input
        if check_user_input:

            if name_entry_line.get_text():
                verified_name = True
                name_input_error = False
            else:
                verified_name = False
                name_input_error = True

            if server_ip_entry_line.get_text():

                ip_match = re.search(server_ip_pattern, server_ip_entry_line.get_text())

                if ip_match:
                    verified_server_ip = True
                    server_ip_input_error = False
                else:
                    verified_server_ip = False
                    server_ip_input_error = True
            else:
                verified_server_ip = False
                server_ip_input_error = True

            if server_port_entry_line.get_text():
                if server_port_entry_line.get_text().isdigit():
                    if 32768 <= int(server_port_entry_line.get_text()) <= 65535:
                        verified_server_port = True
                        server_port_input_error = False
                    else:
                        verified_server_port = False
                        server_port_input_error = True
                else:
                    verified_server_port = False
                    server_port_input_error = True
            else:
                verified_server_port = False
                server_port_input_error = True

            if verified_name and verified_server_ip and verified_server_port:
                if not unknown_os:
                    config_file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(config_file_path, "w") as config_file:
                        config_file.write(f"name = \"{name_entry_line.get_text()}\"\n")
                        config_file.write(f"server_ip = \"{server_ip_entry_line.get_text()}\"\n")
                        config_file.write(f"server_port = {server_port_entry_line.get_text()}\n")
                        config_file.write(f"sound = \"{sound_option_dropdown.selected_option[0]}\"\n")
                        config_file.write(f"card_back_color = \"{card_back_color_option_dropdown.selected_option[0]}\"\n")
                player_name = name_entry_line.get_text()
                host = server_ip_entry_line.get_text()
                port = int(server_port_entry_line.get_text())
                sound_option = sound_option_dropdown.selected_option[0]
                card_back_color_option = card_back_color_option_dropdown.selected_option[0]
                getting_user_input = False

            check_user_input = False

        display_surface.fill(DARK_GREEN)

        game_title_surface = pygame.font.SysFont("Arial", 60).render(
            "Spite and Malice", True, WHITE)
        game_title_rect = game_title_surface.get_rect()
        game_title_rect.centerx = WINDOW_WIDTH // 2
        game_title_rect.centery = 100
        display_surface.blit(game_title_surface, game_title_rect)

        game_version_surface = pygame.font.SysFont("Arial", 32).render(
            f"Client - Version {VERSION}", True, WHITE)
        game_version_rect = game_version_surface.get_rect()
        game_version_rect.centerx = WINDOW_WIDTH // 2
        game_version_rect.centery = 175
        display_surface.blit(game_version_surface, game_version_rect)

        if name_input_error:
            name_label_surface = (pygame.font.SysFont("Arial", 32,italic=True)
                                  .render("Player Name:", True, RED))
        else:
            name_label_surface = (pygame.font.SysFont("Arial", 32)
                                  .render("Player Name:", True, WHITE))

        name_label_rect = name_label_surface.get_rect()
        name_label_rect.x = 250
        name_label_rect.y = 255
        display_surface.blit(name_label_surface, name_label_rect)

        pygame.draw.rect(display_surface, BLACK, (175, 325, 585, 235), 4)

        connection_label_surface = (pygame.font.SysFont("Arial", 32, bold=True)
                                    .render("Connection Info", True, WHITE))
        connection_label_rect = connection_label_surface.get_rect()
        connection_label_rect.x = WINDOW_WIDTH // 2 - 125
        connection_label_rect.y = 350
        display_surface.blit(connection_label_surface, connection_label_rect)

        if server_ip_input_error:
            host_label_surface = (pygame.font.SysFont("Arial", 32, italic=True)
                                  .render("Server IP:", True, RED))
        else:
            host_label_surface = (pygame.font.SysFont("Arial", 32)
                                  .render("Server IP:", True, WHITE))

        host_label_rect = name_label_surface.get_rect()
        host_label_rect.x = 275
        host_label_rect.y = 405
        display_surface.blit(host_label_surface, host_label_rect)

        if server_port_input_error:
            port_label_surface = (pygame.font.SysFont("Arial", 32, italic=True)
                                  .render("Server Port:", True, RED))
        else:
            port_label_surface = (pygame.font.SysFont("Arial", 32)
                                  .render("Server Port:", True, WHITE))

        port_label_rect = name_label_surface.get_rect()
        port_label_rect.x = 245
        port_label_rect.y = 480
        display_surface.blit(port_label_surface, port_label_rect)

        pygame.draw.rect(display_surface, BLACK, (225, 585, 485, 230), 4)

        options_label_surface = (pygame.font.SysFont("Arial", 32, bold=True)
                                 .render("Game Options", True, WHITE))

        options_label_rect = options_label_surface.get_rect()
        options_label_rect.centerx = WINDOW_WIDTH // 2
        options_label_rect.centery = 625
        display_surface.blit(options_label_surface, options_label_rect)

        sound_label_text = (pygame.font.SysFont("Arial", 32)
                            .render("Sound:",True, WHITE))
        sound_label_rect = sound_label_text.get_rect()
        sound_label_rect.x = 355
        sound_label_rect.y = 670
        display_surface.blit(sound_label_text, sound_label_rect)

        card_back_color_text = (pygame.font.SysFont("Arial", 32)
                                .render("Card Back Color:", True, WHITE))
        card_back_color_rect = card_back_color_text.get_rect()
        card_back_color_rect.x = 290
        card_back_color_rect.y = 745
        display_surface.blit(card_back_color_text, card_back_color_rect)

        manager.draw_ui(display_surface)

        pygame.display.update()

    return user_quit_game


def perform_initial_setup(server_socket: socket.socket):

    global player_number, player_name, opponent_player, initial_setup_status, initial_setup_error_status
    global host, port, opponent_player_name, payoff_pile1_top_card, payoff_pile2_top_card

    # Connect to the server
    initial_setup_status = SetupStatus.CONNECTING_TO_SERVER
    server_socket.settimeout(30)

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

    send_message(server_socket, f"What is player {opponent_player}'s name?")
    opponent_player_name = receive_message(server_socket)

    if not opponent_player_name:
        raise ClientError("Received empty opponent player name from server")

    initial_setup_status = SetupStatus.RECEIVING_CARD_DATA

    send_message(server_socket, "Create new deck and payoff piles")

    send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")

    data = receive_cards(server_socket, 1)

    if not data:
        initial_setup_status = SetupStatus.ERROR
        initial_setup_error_status = SetupErrorStatus.CARD_DATA_RECEIVE_ERROR
        return

    if player_number == 1:
        payoff_pile1_top_card = data[0]
    elif player_number == 2:
        payoff_pile2_top_card = data[0]

    send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")

    data = receive_cards(server_socket, 1)

    if not data:
        initial_setup_status = SetupStatus.ERROR
        initial_setup_error_status = SetupErrorStatus.CARD_DATA_RECEIVE_ERROR
        return

    if opponent_player == 1:
        payoff_pile1_top_card = data[0]
    elif opponent_player == 2:
        payoff_pile2_top_card = data[0]

    # send_message(server_socket, "Awaiting card data")
    # print("Sent awaiting card data message to server")  # DEBUG
    #
    # # Receive payoff pile 1
    # print("Receiving payoff pile 1")
    # data = receive_message(server_socket)
    #
    # if data == "Sending payoff pile 1":
    #     payoff_pile1 = receive_cards(server_socket, 20)
    #     if not payoff_pile1:
    #         initial_setup_status = SetupStatus.ERROR
    #         initial_setup_error_status = SetupErrorStatus.PAYOFF_PILE1_RECEIVE_ERROR
    #         return
    #     # DEBUG
    #     print("Payoff pile 1 received on client:")
    #     for payoff_pile_card in payoff_pile1:
    #         print(f"{payoff_pile_card.name}:{payoff_pile_card.order}")
    # else:
    #     initial_setup_status = SetupStatus.ERROR
    #     initial_setup_error_status = SetupErrorStatus.PAYOFF_PILE1_RECEIVE_ERROR
    #     return
    #
    # # Receive payoff pile 2
    # print("Receiving payoff pile 2")
    # data = receive_message(server_socket)
    #
    # if data == "Sending payoff pile 2":
    #     payoff_pile2 = receive_cards(server_socket, 20)
    #     if not payoff_pile2:
    #         initial_setup_status = SetupStatus.ERROR
    #         initial_setup_error_status = SetupErrorStatus.PAYOFF_PILE2_RECEIVE_ERROR
    #         return
    #     # DEBUG
    #     print("Payoff pile 2 received on client:")
    #     for payoff_pile_card in payoff_pile2:
    #         print(f"{payoff_pile_card.name}:{payoff_pile_card.order}")
    # else:
    #     initial_setup_status = SetupStatus.ERROR
    #     initial_setup_error_status = SetupErrorStatus.PAYOFF_PILE2_RECEIVE_ERROR
    #     return
    #
    # # Receive draw pile
    # print("Receiving draw pile")
    # data = receive_message(server_socket)
    #
    # if data == "Sending draw pile":
    #     draw_pile = receive_cards(server_socket, 168)
    #     if not draw_pile:
    #         initial_setup_status = SetupStatus.ERROR
    #         initial_setup_error_status = SetupErrorStatus.DRAW_PILE_RECEIVE_ERROR
    #         return
    #     # DEBUG
    #     print("Draw pile received on client:")
    #     for draw_pile_card in draw_pile:
    #         print(f"{draw_pile_card.name}:{draw_pile_card.order}")
    # else:
    #     initial_setup_status = SetupStatus.ERROR
    #     initial_setup_error_status = SetupErrorStatus.DRAW_PILE_RECEIVE_ERROR
    #     return

    initial_setup_status = SetupStatus.OTHER_PLAYER_STATUS_CHECK
    send_message(server_socket, "Is the other player still connected?")
    data = receive_message(server_socket)

    if data == "No":
        initial_setup_status = SetupStatus.ERROR
        initial_setup_error_status = SetupErrorStatus.OTHER_PLAYER_DISCONNECTED
        return

    # while True:
    #     send_message(server_socket,"Have both players received the decks and piles?")
    #     data = receive_message(server_socket)
    #     if data == "Yes":
    #         break
    #     elif data == "No":
    #         pygame.time.wait(2000)

    initial_setup_status = SetupStatus.COMPLETE
    return


def perform_rematch_setup(server_socket: socket.socket):

    global payoff_pile1_top_card, payoff_pile2_top_card, rematch_setup_status, rematch_setup_error_status
    global player_number, opponent_player

    rematch_setup_status = RematchStatus.IN_PROGRESS

    send_message(server_socket, "Set up a new game")
    send_message(server_socket, "Create new deck and payoff piles")

    rematch_setup_status = RematchStatus.RECEIVING_CARD_DATA

    send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")

    data = receive_cards(server_socket, 1)

    if not data:
        rematch_setup_status = SetupStatus.ERROR
        rematch_setup_error_status = RematchErrorStatus.ERROR_RECEIVING_CARD_DATA
        return

    if player_number == 1:
        payoff_pile1_top_card = data[0]
    elif player_number == 2:
        payoff_pile2_top_card = data[0]

    send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")

    data = receive_cards(server_socket, 1)

    if not data:
        rematch_setup_status = SetupStatus.ERROR
        rematch_setup_error_status = RematchErrorStatus.ERROR_RECEIVING_CARD_DATA
        return

    if opponent_player == 1:
        payoff_pile1_top_card = data[0]
    elif opponent_player == 2:
        payoff_pile2_top_card = data[0]

    rematch_setup_status = RematchStatus.COMPLETE

    return


def run_game(server_socket: socket.socket, display_surface: pygame.Surface):

    global player_number, opponent_player, sound_option, current_hand
    global payoff_pile1_top_card, payoff_pile2_top_card, rematch_setup_status, rematch_setup_error_status

    socket_closed = False

    current_turn = 0

    draggable_cards = []
    draggable_cards_set = False
    draw_pile_needs_to_be_reshuffled = False

    payoff_pile1_remaining_cards = 0
    payoff_pile2_remaining_cards = 0

    opponents_hand_size = 0

    clock = pygame.time.Clock()

    first_turn = True

    discard_piles1 = [[], [], [], []]
    discard_piles1_rects = [None, None, None, None]

    discard_piles2 = [[], [], [], []]
    discard_piles2_rects = [None, None, None, None]

    build_piles = [[], [], [], []]
    build_piles_rects = [None, None, None, None]

    # Make sure card_back has a default value
    card_back = pygame.image.load(get_path("assets/card_backs/card_back_red.png")).convert_alpha()

    if card_back_color_option == "Black":
        card_back = pygame.image.load(get_path("assets/card_backs/card_back_black.png")).convert_alpha()
    elif card_back_color_option == "Blue":
        card_back = pygame.image.load(get_path("assets/card_backs/card_back_blue.png")).convert_alpha()
    elif card_back_color_option == "Green":
        card_back = pygame.image.load(get_path("assets/card_backs/card_back_green.png")).convert_alpha()
    elif card_back_color_option == "Orange":
        card_back = pygame.image.load(get_path("assets/card_backs/card_back_orange.png")).convert_alpha()
    elif card_back_color_option == "Purple":
        card_back = pygame.image.load(get_path("assets/card_backs/card_back_purple.png")).convert_alpha()
    elif card_back_color_option == "Red":
        card_back = pygame.image.load(get_path("assets/card_backs/card_back_red.png")).convert_alpha()

    card_back = pygame.transform.scale(card_back, (100, 150))
    card_back_rect = card_back.get_rect()

    font = pygame.font.SysFont("Arial", 30)
    game_result_font = pygame.font.SysFont("Arial", 60)

    currently_dragging_card = False
    card_being_dragged = None

    original_dragging_x = 0
    original_dragging_y = 0

    network_timer = 10

    running = True

    turn_switch = False

    while running:

        if network_timer == 0 or first_turn:
            send_message(server_socket, "Is the other player still connected?")
            data = receive_message(server_socket)
            if data == "No":
                raise ClientError("Other player disconnected!")

        if turn_switch or first_turn:
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

            turn_switch = False

        if not current_hand and current_turn == player_number:
            send_message(server_socket,f"Player {player_number} draws 5 cards")

            current_hand = receive_cards(server_socket, 5)

            # if len(draw_pile) >= 5:
            #     for _ in range(0, 5, 1):
            #         current_hand.append(draw_pile.pop())
            # else:
            #     for _ in range(0, len(draw_pile), 1):
            #         current_hand.append(draw_pile.pop())

            if sound_option == "On":
                draw_cards_sound_effect = pygame.mixer.Sound(get_path("assets/dealing_cards.wav"))
                draw_cards_sound_effect.play()

            draggable_cards_set = False

        # if reshuffle_draw_pile_status == ShuffleStatus.COMPLETE and reshuffle_draw_pile_error_status == ShuffleErrorStatus.UNSET:
        #     reshuffle_draw_pile_status = ShuffleStatus.UNSET
        #     draggable_cards_set = False
        # elif reshuffle_draw_pile_status == ShuffleStatus.ERROR:
        #     if reshuffle_draw_pile_error_status == ShuffleErrorStatus.INCORRECT_DRAW_PILE_LENGTH:
        #         raise ClientError("Incorrect draw pile length received from server")
        #     elif reshuffle_draw_pile_error_status == ShuffleErrorStatus.EMPTY_DRAW_PILE:
        #         raise ClientError("Empty draw pile received from server")

        if current_turn == player_number:
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
                    draggable_cards.append(payoff_pile1_top_card)
                elif player_number == 2:
                    if discard_piles2[0] and discard_piles2[0][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles2[0][-1])
                    if discard_piles2[1] and discard_piles2[1][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles2[1][-1])
                    if discard_piles2[2] and discard_piles2[2][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles2[2][-1])
                    if discard_piles2[3] and discard_piles2[3][-1] not in draggable_cards:
                        draggable_cards.append(discard_piles2[3][-1])
                    draggable_cards.append(payoff_pile2_top_card)
                draggable_cards_set = True

                print("DEBUG------------------")
                print(f"Player {player_number}'s draggable cards this turn:")
                print([dbg_card.name for dbg_card in draggable_cards])

            # elif reshuffle_draw_pile_status == ShuffleStatus.IN_PROGRESS:
            #     draggable_cards = []

        else:

            if not draggable_cards_set:
                draggable_cards = []
                draggable_cards_set = True


            if network_timer == 0:

            #     send_message(server_socket, f"How many cards has player {opponent_player} drawn this turn?")
            #     data = receive_message(server_socket)
            #
            #     if data.isdigit():
            #
            #         #print(f"DEBUG: Opponent has drawn {int(data)} cards this turn")
            #         if int(data) != opponent_draw_count:
            #             for _ in range(opponent_draw_count, int(data), 1):
            #                 # Cards disappear into the void (intentional)
            #                 draw_pile.pop()
            #             opponent_draw_count = int(data)
            #     else:
            #         raise ClientError("Received invalid number of opponent draws from server")

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
                            turn_switch = True
                        elif moved_to == "discard pile 1":
                            if opponent_player == 1:
                                discard_piles1[1].append(received_card)
                            elif opponent_player == 2:
                                discard_piles2[1].append(received_card)
                            turn_switch = True
                        elif moved_to == "discard pile 2":
                            if opponent_player == 1:
                                discard_piles1[2].append(received_card)
                            elif opponent_player == 2:
                                discard_piles2[2].append(received_card)
                            turn_switch = True
                        elif moved_to == "discard pile 3":
                            if opponent_player == 1:
                                discard_piles1[3].append(received_card)
                            elif opponent_player == 2:
                                discard_piles2[3].append(received_card)
                            turn_switch = True
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
                                build_piles[0].append(payoff_pile1_top_card)
                                send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")
                                payoff_pile1_top_card = receive_cards(server_socket, 1)[0]
                                # if payoff_pile1[-1].name == card_name:
                                #     build_piles[0].append(payoff_pile1.pop())
                                #     # Flip over next card
                                #     if payoff_pile1:
                                #         payoff_pile1[-1].position = CardPosition.FACE_UP
                                # else:
                                #     raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                build_piles[0].append(payoff_pile2_top_card)
                                send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")
                                payoff_pile2_top_card = receive_cards(server_socket, 1)[0]
                                # if payoff_pile2[-1].name == card_name:
                                #     build_piles[0].append(payoff_pile2.pop())
                                #     # Flip over next card
                                #     if payoff_pile2:
                                #         payoff_pile2[-1].position = CardPosition.FACE_UP
                                # else:
                                #     raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 1":
                            if opponent_player == 1:
                                build_piles[1].append(payoff_pile1_top_card)
                                send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")
                                payoff_pile1_top_card = receive_cards(server_socket, 1)[0]
                                # if payoff_pile1[-1].name == card_name:
                                #     build_piles[1].append(payoff_pile1.pop())
                                #     # Flip over next card
                                #     if payoff_pile1:
                                #         payoff_pile1[-1].position = CardPosition.FACE_UP
                                # else:
                                #     raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                build_piles[1].append(payoff_pile2_top_card)
                                send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")
                                payoff_pile2_top_card = receive_cards(server_socket, 1)[0]
                                # if payoff_pile2[-1].name == card_name:
                                #     build_piles[1].append(payoff_pile2.pop())
                                #     # Flip over next card
                                #     if payoff_pile2:
                                #         payoff_pile2[-1].position = CardPosition.FACE_UP
                                # else:
                                #     raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 2":
                            if opponent_player == 1:
                                build_piles[2].append(payoff_pile1_top_card)
                                send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")
                                payoff_pile1_top_card = receive_cards(server_socket, 1)[0]
                                # if payoff_pile1[-1].name == card_name:
                                #     build_piles[2].append(payoff_pile1.pop())
                                #     # Flip over next card
                                #     if payoff_pile1:
                                #         payoff_pile1[-1].position = CardPosition.FACE_UP
                                # else:
                                #     raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                build_piles[2].append(payoff_pile2_top_card)
                                send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")
                                payoff_pile2_top_card = receive_cards(server_socket, 1)[0]
                                # if payoff_pile2[-1].name == card_name:
                                #     build_piles[2].append(payoff_pile2.pop())
                                #     # Flip over next card
                                #     if payoff_pile2:
                                #         payoff_pile2[-1].position = CardPosition.FACE_UP
                                # else:
                                #     raise ClientError("Issue syncing cards with the server")
                        elif moved_to == "build pile 3":
                            if opponent_player == 1:
                                build_piles[3].append(payoff_pile1_top_card)
                                send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")
                                payoff_pile1_top_card = receive_cards(server_socket, 1)[0]
                                # if payoff_pile1[-1].name == card_name:
                                #     build_piles[3].append(payoff_pile1.pop())
                                #     # Flip over next card
                                #     if payoff_pile1:
                                #         payoff_pile1[-1].position = CardPosition.FACE_UP
                                # else:
                                #     raise ClientError("Issue syncing cards with the server")
                            elif opponent_player == 2:
                                build_piles[3].append(payoff_pile2_top_card)
                                send_message(server_socket, f"Send the top card of player {opponent_player}'s payoff pile")
                                payoff_pile2_top_card = receive_cards(server_socket, 1)[0]
                                # if payoff_pile2[-1].name == card_name:
                                #     build_piles[3].append(payoff_pile2.pop())
                                #     # Flip over next card
                                #     if payoff_pile2:
                                #         payoff_pile2[-1].position = CardPosition.FACE_UP
                                # else:
                                #     raise ClientError("Issue syncing cards with the server")

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
                                    elif card_being_dragged == payoff_pile1_top_card:
                                        # payoff_pile1.remove(card_being_dragged)
                                        # # Flip over next card
                                        # if payoff_pile1:
                                        #     payoff_pile1[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 0")
                                        send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")
                                        payoff_pile1_top_card = receive_cards(server_socket, 1)[0]
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
                                    elif card_being_dragged == payoff_pile2_top_card:
                                        # payoff_pile2.remove(card_being_dragged)
                                        # # Flip over next card
                                        # if payoff_pile2:
                                        #     payoff_pile2[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 0")
                                        send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")
                                        payoff_pile2_top_card = receive_cards(server_socket, 1)[0]

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
                                    elif card_being_dragged == payoff_pile1_top_card:
                                        # payoff_pile1.remove(card_being_dragged)
                                        # # Flip over next card
                                        # if payoff_pile1:
                                        #     payoff_pile1[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 1")
                                        send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")
                                        payoff_pile1_top_card = receive_cards(server_socket, 1)[0]
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
                                    elif card_being_dragged == payoff_pile2_top_card:
                                        # payoff_pile2.remove(card_being_dragged)
                                        # # Flip over next card
                                        # if payoff_pile2:
                                        #     payoff_pile2[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 1")
                                        send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")
                                        payoff_pile2_top_card = receive_cards(server_socket, 1)[0]

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
                                    elif card_being_dragged == payoff_pile1_top_card:
                                        # payoff_pile1.remove(card_being_dragged)
                                        # # Flip over next card
                                        # if payoff_pile1:
                                        #     payoff_pile1[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 2")
                                        send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")
                                        payoff_pile1_top_card = receive_cards(server_socket, 1)[0]
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
                                    elif card_being_dragged == payoff_pile2_top_card:
                                        # payoff_pile2.remove(card_being_dragged)
                                        # # Flip over next card
                                        # if payoff_pile2:
                                        #     payoff_pile2[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 2")
                                        send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")
                                        payoff_pile2_top_card = receive_cards(server_socket, 1)[0]

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
                                    elif card_being_dragged == payoff_pile1_top_card:
                                        # payoff_pile1.remove(card_being_dragged)
                                        # # Flip over next card
                                        # if payoff_pile1:
                                        #     payoff_pile1[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 3")
                                        send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")
                                        payoff_pile1_top_card = receive_cards(server_socket, 1)[0]
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
                                    elif card_being_dragged == payoff_pile2_top_card:
                                        # payoff_pile2.remove(card_being_dragged)
                                        # # Flip over next card
                                        # if payoff_pile2:
                                        #     payoff_pile2[-1].position = CardPosition.FACE_UP
                                        send_message(server_socket, f"Player {player_number} moved {card_being_dragged.name} from their payoff pile to build pile 3")
                                        send_message(server_socket, f"Send the top card of player {player_number}'s payoff pile")
                                        payoff_pile2_top_card = receive_cards(server_socket, 1)[0]

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
                                    turn_switch = True

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
                                    turn_switch = True

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
                                    turn_switch = True

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
                                    turn_switch = True

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
                                    turn_switch = True

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
                                    turn_switch = True

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
                                    turn_switch = True

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
                                    turn_switch = True

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
            card_back_rect.left = 25
            card_back_rect.bottom = WINDOW_HEIGHT
            display_surface.blit(card_back, card_back_rect)
            if payoff_pile1_top_card != card_being_dragged:
                payoff_pile1_top_card.rect.left = 25
                payoff_pile1_top_card.rect.bottom = WINDOW_HEIGHT
                display_surface.blit(payoff_pile1_top_card.surface, payoff_pile1_top_card.rect)
        elif player_number == 2:
            card_back_rect.left = 25
            card_back_rect.bottom = WINDOW_HEIGHT
            display_surface.blit(card_back, card_back_rect)
            if payoff_pile2_top_card != card_being_dragged:
                payoff_pile2_top_card.rect.left = 25
                payoff_pile2_top_card.rect.bottom = WINDOW_HEIGHT
                display_surface.blit(payoff_pile2_top_card.surface, payoff_pile2_top_card.rect)

        # if player_number == 1:
        #     for payoff_card in payoff_pile1:
        #         if payoff_card != card_being_dragged:
        #             if payoff_card.position == CardPosition.FACE_UP:
        #                 payoff_card.rect.left = 25
        #                 payoff_card.rect.bottom = WINDOW_HEIGHT
        #                 display_surface.blit(payoff_card.surface, payoff_card.rect)
        #             else:
        #                 card_back_rect.left = 25
        #                 card_back_rect.bottom = WINDOW_HEIGHT
        #                 display_surface.blit(card_back, card_back_rect)
        # elif player_number == 2:
        #     for payoff_card in payoff_pile2:
        #         if payoff_card != card_being_dragged:
        #             if payoff_card.position == CardPosition.FACE_UP:
        #                 payoff_card.rect.left = 25
        #                 payoff_card.rect.bottom = WINDOW_HEIGHT
        #                 display_surface.blit(payoff_card.surface, payoff_card.rect)
        #             else:
        #                 card_back_rect.left = 25
        #                 card_back_rect.bottom = WINDOW_HEIGHT
        #                 display_surface.blit(card_back, card_back_rect)

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
            payoff_pile2_top_card.rect.right = WINDOW_WIDTH - 25
            payoff_pile2_top_card.rect.top = 0
            display_surface.blit(payoff_pile2_top_card.surface, payoff_pile2_top_card.rect)
        elif player_number == 2:
            payoff_pile1_top_card.rect.right = WINDOW_WIDTH - 25
            payoff_pile1_top_card.rect.top = 0
            display_surface.blit(payoff_pile1_top_card.surface, payoff_pile1_top_card.rect)

        # if player_number == 1:
        #     for stock_card in payoff_pile2:
        #         if stock_card.position == CardPosition.FACE_UP:
        #             stock_card.rect.right = WINDOW_WIDTH - 25
        #             stock_card.rect.top = 0
        #             display_surface.blit(stock_card.surface, stock_card.rect)
        #         else:
        #             card_back_rect.right = WINDOW_WIDTH - 25
        #             card_back_rect.top = 0
        #             display_surface.blit(card_back, card_back_rect)
        # if player_number == 2:
        #     for stock_card in payoff_pile1:
        #         if stock_card.position == CardPosition.FACE_UP:
        #             stock_card.rect.right = WINDOW_WIDTH - 25
        #             stock_card.rect.top = 0
        #             display_surface.blit(stock_card.surface, stock_card.rect)
        #         else:
        #             card_back_rect.right = WINDOW_WIDTH - 25
        #             card_back_rect.top = 0
        #             display_surface.blit(card_back, card_back_rect)

        if network_timer == 0:
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

        if player_number == 1:
            player_number1_text = font.render(f"Player 1\n{player_name}", True, WHITE, DARK_GREEN)
            player_number1_rect = player_number1_text.get_rect()
            player_number2_text = font.render(f"Player 2\n{opponent_player_name}", True, WHITE, DARK_GREEN)
            player_number2_rect = player_number2_text.get_rect()
            player_number1_rect.centerx = WINDOW_WIDTH - 100
            player_number1_rect.centery = WINDOW_HEIGHT - 100
            player_number2_rect.centerx = 100
            player_number2_rect.centery = 100
            display_surface.blit(player_number1_text, player_number1_rect)
            display_surface.blit(player_number2_text, player_number2_rect)
        elif player_number == 2:
            player_number1_text = font.render(f"Player 1\n{opponent_player_name}", True, WHITE, DARK_GREEN)
            player_number1_rect = player_number1_text.get_rect()
            player_number2_text = font.render(f"Player 2\n{player_name}", True, WHITE, DARK_GREEN)
            player_number2_rect = player_number2_text.get_rect()
            player_number1_rect.centerx = 100
            player_number1_rect.centery = 100
            player_number2_rect.centerx = WINDOW_WIDTH - 100
            player_number2_rect.centery = WINDOW_HEIGHT - 100
            display_surface.blit(player_number1_text, player_number1_rect)
            display_surface.blit(player_number2_text, player_number2_rect)

        if current_turn == player_number:
            current_turn_text = font.render(f"Current turn:\nPlayer {current_turn}\n{player_name}", True, WHITE, DARK_GREEN)
            current_turn_rect = current_turn_text.get_rect()
            current_turn_rect.right = WINDOW_WIDTH - 25
            current_turn_rect.y = WINDOW_HEIGHT // 2
            display_surface.blit(current_turn_text, current_turn_rect)
        elif current_turn == opponent_player:
            current_turn_text = font.render(f"Current turn:\nPlayer {current_turn}\n{opponent_player_name}", True, WHITE, DARK_GREEN)
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

        if network_timer == 0 or first_turn:
            send_message(server_socket, "How many cards are left in player 1's payoff pile?")
            data = receive_message(server_socket)

            if not data.isdigit():
                raise ClientError("Invalid length of payoff pile received from server")

            payoff_pile1_remaining_cards = data

            send_message(server_socket,"How many cards are left in player 2's payoff pile?")
            data = receive_message(server_socket)

            if not data.isdigit():
                raise ClientError(
                    "Invalid length of payoff pile received from server")

            payoff_pile2_remaining_cards = data

        payoff_pile1_remaining_cards_text = font.render(payoff_pile1_remaining_cards, True, WHITE, DARK_GREEN)
        payoff_pile1_remaining_cards_rect = payoff_pile1_remaining_cards_text.get_rect()
        payoff_pile2_remaining_cards_text = font.render(payoff_pile2_remaining_cards, True, WHITE, DARK_GREEN)
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

        send_message(server_socket, "How many cards are left in the draw pile?")
        remaining_draw_pile_cards = receive_message(server_socket)
        draw_pile_remaining_cards_text = font.render(f"Remaining\ndraw pile\ncards: {remaining_draw_pile_cards}", True, WHITE, DARK_GREEN)
        draw_pile_remaining_cards_rect = draw_pile_remaining_cards_text.get_rect()
        draw_pile_remaining_cards_rect.x = 25
        draw_pile_remaining_cards_rect.y = WINDOW_HEIGHT // 2
        display_surface.blit(draw_pile_remaining_cards_text, draw_pile_remaining_cards_rect)

        if currently_dragging_card:
            display_surface.blit(card_being_dragged.surface, card_being_dragged.rect)

        game_result_text = None

        if network_timer == 0:
            send_message(server_socket, "Has the game result been determined?")
            data = receive_message(server_socket)

            if data == "Yes":

                send_message(server_socket, "Who won the game?")
                data = receive_message(server_socket)

                # Win / lose / stalemate conditions
                if player_number == 1 and data == "Player 1" or player_number == 2 and data == "Player 2":
                    game_result_text = game_result_font.render("YOU WIN!", True, WHITE)
                elif player_number == 2 and data == "Player 1" or player_number == 1 and data == "Player 2":
                    game_result_text = game_result_font.render("Sorry, you lose!", True, WHITE)
                elif data == "Stalemate":
                    game_result_text = game_result_font.render("STALEMATE!", True, WHITE)

        if game_result_text is None:
            if len(build_piles[0]) == 12:
                build_piles[0] = []
                draw_pile_needs_to_be_reshuffled = True
            if len(build_piles[1]) == 12:
                build_piles[1] = []
                draw_pile_needs_to_be_reshuffled = True
            if len(build_piles[2]) == 12:
                build_piles[2] = []
                draw_pile_needs_to_be_reshuffled = True
            if len(build_piles[3]) == 12:
                build_piles[3] = []
                draw_pile_needs_to_be_reshuffled = True
            if draw_pile_needs_to_be_reshuffled:
                send_message(server_socket, "Draw pile needs to be reshuffled")
                if sound_option == "On":
                    shuffle_sound_effect = pygame.mixer.Sound(get_path("assets/shuffle_cards.wav"))
                    shuffle_sound_effect.play()
                draw_pile_needs_to_be_reshuffled = False

        # if reshuffle_draw_pile_status == ShuffleStatus.IN_PROGRESS:
        #     reshuffling_text = font.render("Reshuffling draw pile, please wait...", True, WHITE, DARK_GREEN)
        #     reshuffling_rect = reshuffling_text.get_rect()
        #     reshuffling_rect.centerx = WINDOW_WIDTH // 2
        #     reshuffling_rect.centery = WINDOW_HEIGHT // 2
        #     display_surface.blit(reshuffling_text, reshuffling_rect)

        if first_turn:
            if sound_option == "On":
                shuffle_sound_effect = pygame.mixer.Sound(get_path("assets/shuffle_cards.wav"))
                shuffle_sound_effect.play()
                pygame.time.wait(1000)
            first_turn = False

        user_quit_game = False
        if game_result_text is not None:
            draggable_cards = []
            rematch_manager = pygame_gui.UIManager(
                (WINDOW_WIDTH, WINDOW_HEIGHT), theme_path="theme.json")

            yes_button = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect((335, 550, 100, 50)), text="Yes",
                manager=rematch_manager)
            no_button = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect((485, 550, 100, 50)), text="No (quit)",
                manager=rematch_manager)

            paused = True
            rematch = False

            while paused:
                time_delta = clock.tick(FPS) / 1000.0
                for event in pygame.event.get():

                    if event.type == pygame.QUIT:
                        paused = False

                    if event.type == pygame_gui.UI_BUTTON_PRESSED:
                        if event.ui_element == yes_button:
                            rematch = True
                            paused = False

                        if event.ui_element == no_button:
                            send_message(server_socket, f"Player {player_number} did not want a re-match")
                            paused = False

                    rematch_manager.process_events(event)

                rematch_manager.update(time_delta)

                pygame.draw.rect(display_surface, (0, 150, 0),(WINDOW_WIDTH // 2 - 250, WINDOW_HEIGHT // 2 - 200, 500, 400))
                game_result_rect = game_result_text.get_rect()
                game_result_rect.centerx = WINDOW_WIDTH // 2
                game_result_rect.centery = WINDOW_HEIGHT // 2 - 100
                display_surface.blit(game_result_text, game_result_rect)
                rematch_text = font.render("Request a re-match?", True, WHITE)
                rematch_rect = rematch_text.get_rect()
                rematch_rect.centerx = 460
                rematch_rect.centery = 485
                display_surface.blit(rematch_text, rematch_rect)

                rematch_manager.draw_ui(display_surface)
                pygame.display.update()


            if rematch:
                display_surface.fill(DARK_GREEN)
                status_text = pygame.font.SysFont("Arial", 32).render(
                    "Requesting a re-match...", True, WHITE)
                status_rect = status_text.get_rect()
                status_rect.centerx = WINDOW_WIDTH // 2
                status_rect.centery = WINDOW_HEIGHT // 2
                display_surface.blit(status_text, status_rect)
                pygame.display.update()

                send_message(server_socket,f"Player {player_number} wants a re-match")

                rematch_manager2 = pygame_gui.UIManager(
                    (WINDOW_WIDTH, WINDOW_HEIGHT), theme_path="theme.json")

                ok_quit_button = pygame_gui.elements.UIButton(
                    relative_rect=pygame.Rect((415, 550, 100, 50)),
                    text="OK (Quit)", manager=rematch_manager2)

                while not user_quit_game:

                    time_delta = clock.tick(FPS) / 1000.0
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            user_quit_game = True

                        if event.type == pygame_gui.UI_BUTTON_PRESSED:
                            if event.ui_element == ok_quit_button:
                                user_quit_game = True

                        rematch_manager2.process_events(event)

                    rematch_manager2.update(time_delta)

                    send_message(server_socket,f"Does player {opponent_player} also want a re-match?")
                    data = receive_message(server_socket)

                    if data == "No":
                        display_surface.fill(DARK_GREEN)
                        status_text = pygame.font.SysFont("Arial", 32).render(f"Player {opponent_player} ({opponent_player_name}) did not want a re-match!",True, WHITE)
                        status_rect = status_text.get_rect()
                        status_rect.centerx = WINDOW_WIDTH // 2
                        status_rect.centery = WINDOW_HEIGHT // 2
                        display_surface.blit(status_text, status_rect)
                        rematch_manager2.draw_ui(display_surface)
                        pygame.display.update()
                    elif data == "Yes":
                        display_surface.fill(DARK_GREEN)
                        status_text = font.render(f"Player {opponent_player} ({opponent_player_name}) agreed to a re-match!\n        Setting up a new game...",
                            True, WHITE)
                        status_rect = status_text.get_rect()
                        status_rect.centerx = WINDOW_WIDTH // 2
                        status_rect.centery = WINDOW_HEIGHT // 2
                        display_surface.blit(status_text, status_rect)
                        pygame.display.update()

                        send_message(server_socket, "Set up a new game")

                        discard_piles1 = [[], [], [], []]
                        discard_piles2 = [[], [], [], []]
                        build_piles = [[], [], [], []]
                        draggable_cards_set = False
                        first_turn = True
                        current_hand = []

                        rematch_setup_thread = threading.Thread(target=perform_rematch_setup, args=(server_socket,), daemon=True)
                        rematch_setup_thread.start()

                        setting_up_rematch = True

                        while setting_up_rematch:

                            for event in pygame.event.get():
                                if event.type == pygame.QUIT:
                                    setting_up_rematch = False
                                    user_quit_game = True

                            if rematch_setup_status == RematchStatus.IN_PROGRESS:
                                status_text = font.render(
                                    "Re-match setup in progress, please wait...",
                                    True, WHITE)
                            elif rematch_setup_status == RematchStatus.ERROR:
                                if rematch_setup_error_status == RematchErrorStatus.ERROR_RECEIVING_CARD_DATA:
                                    status_text = font.render(
                                        "      Error receiving card data from server!\nPlease restart the program to enter a new game",
                                        True, WHITE)
                            elif rematch_setup_status == RematchStatus.COMPLETE:
                                status_text = font.render(
                                    "Re-match setup complete! Entering new game...",
                                    True, WHITE)
                                setting_up_rematch = False

                            display_surface.fill(DARK_GREEN)
                            status_rect = status_text.get_rect()
                            status_rect.centerx = WINDOW_WIDTH // 2
                            status_rect.centery = WINDOW_HEIGHT // 2
                            display_surface.blit(status_text, status_rect)

                            pygame.display.update()

                        break

                    elif data == "Undecided":
                        display_surface.fill(DARK_GREEN)
                        status_text = pygame.font.SysFont("Arial", 32).render(
                            f"Waiting for other player's re-match decision...",
                            True, WHITE)
                        status_rect = status_text.get_rect()
                        status_rect.centerx = WINDOW_WIDTH // 2
                        status_rect.centery = WINDOW_HEIGHT // 2
                        display_surface.blit(status_text, status_rect)
                        pygame.display.update()


            else:
                break

        if user_quit_game:
            break

        if network_timer == 0:
            network_timer = 10
        else:
            network_timer -= 1

        pygame.display.update()



    if not socket_closed:
        server_socket.close()


def main():

    global current_hand, initial_setup_status, initial_setup_error_status

    pygame.init()

    display_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Spite and Malice")

    user_quit_game = get_user_configuration(display_surface)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if not user_quit_game:
        try:
            initial_setup_thread = threading.Thread(target=perform_initial_setup, args=(server_socket,), daemon=True)
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
                run_game(server_socket, display_surface)
            else:
                if user_quit_game:
                    server_socket.close()
                else:
                    if initial_setup_error_status == SetupErrorStatus.COULD_NOT_CONNECT_TO_SERVER:
                        raise ClientError(f"Could not connect to server {host}:{port}")
                    elif initial_setup_error_status == SetupErrorStatus.GAME_LOBBY_FULL:
                        raise ClientError("Game lobby full!")
                    elif initial_setup_error_status == SetupErrorStatus.CARD_DATA_RECEIVE_ERROR:
                        raise ClientError("Error receiving card data from server")
                    elif initial_setup_error_status == SetupErrorStatus.OTHER_PLAYER_DISCONNECTED:
                        raise ClientError("Other player disconnected!")

        except TimeoutError:
            server_socket.close()
            display_surface.fill(DARK_GREEN)
            error_message = "An operation with the server timed out\n(other player may have disconnected\nor the server might be down)"
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
            server_socket.close()
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
            server_socket.close()
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
            # crash_log_path = Path("C:/ProgramData") / "jscdev909" / "spite_and_malice_client" / f"crash{player_number}.log"
            #
            # with open(crash_log_path, "w") as crash_log:
            #     crash_log.write("Cards in draw pile:\n")
            #     for card in draw_pile:
            #         crash_log.write(card.name + "\n")
            #     crash_log.write(f"\nCards in current_hand\n")
            #     for card in current_hand:
            #         crash_log.write(card.name + "\n")

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