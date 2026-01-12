<img width="927" height="982" alt="image" src="https://github.com/user-attachments/assets/f4f628b0-0909-4468-bfd0-711a5c9628ca" />

</br>The game of Spite and Malice, written in Python utilizing the Pygame engine!

# Rules

Spite and Malice, also known as Skip-Bo, is a two-player card game usually played with two decks of standard playing cards where the object of the game is to get rid of all the cards in your payoff pile 
before the other player. To do this, players use four shared build piles to count from 1-12 (1-10, Jack, Queen), using cards from their hand, personal discard piles and payoff pile. The top card of the payoff pile will determine who goes first (highest rank). At the beginning of their turn, 
if they have no cards, a player draws 5 cards from the draw pile to their hand and proceeds to stack cards in the build piles starting with aces and working their way up to queens. When a queen is placed on the 
build pile, that pile is reshuffled back into the draw pile. A player ends their turn by placing a card from their hand onto one of their four personal discard piles. Kings are wild cards and can substitute for 
any other ranked card. Suits do not matter in this game. Jokers are also not used. The first player to have no cards left in their payoff pile wins. If the number of draw pile cards run out before both payoff piles have
been emptied, the winner is determined by who has the lowest amount of cards left on their payoff pile. If both payoff piles have the same number of cards left, the game is a stalemate.

# Features

- Play with two players over the internet or on your local network
- Server port, number of playing card decks and number of payoff pile cards configurable on the server
- Auto-reshuffling when a queen is placed on a build pile
- Automatic drawing of 5 cards when it's the players turn and they have no cards in their hand
- Stack value displayed below build piles during gameplay in case a king is on the top of the pile
- Multiple card back colors configurable on the client
- Custom player names configurable on the client
- Shuffling and drawing sounds in-game (You can also turn these off in the client)
- Ability to challenge your opponent to a re-match after the conclusion of a game (both players must select yes to proceed)

# Getting Started (Setup and Configuration)

This repository contains two main scripts, the server script (spite_and_malice_server.py) and the client script (spite_and_malice_client.py). The server script is a command line application while the client script
contains the main game GUI that each player will require to play the game. 

The server script requires the following files/directories and modules to run:
- pygame-ce (```pip install pygame-ce```)
- card.py
- socket_utils.py
- path_utils.py
- assets/card_faces directory

The client script requires the following files/directories and modules to run:
- pygame-ce (```pip install pygame-ce```)
- pygame-gui (```pip install pygame-gui```)
- card.py
- socket_utils.py
- path_utils.py
- assets/card_backs directory
- assets/dealing_cards.wav
- assets/shuffle_cards.wav
- theme.json

If you would prefer to run single executables of the client and server with all dependencies included, check out the releases page!

Both players will require a mouse to move cards on the client while playing the game.

The server component will require either a local host or dedicated server with a firewall configured to allow inbound IPv4 traffic on an ephemeral port between 32768 
and 65535. This port will then be passed to the server script/executable on first run and stored in a config file. If running on a cloud host, a visible IPv4 address for the server will be required to play across 
the internet.

After setting up a python virtual environment and installing pygame-ce (or simply running the single server executable from the releases page) and running the server script/executable, you will be presented with 
the following prompt:

<img width="995" height="21" alt="image" src="https://github.com/user-attachments/assets/0a324a69-b67d-4236-908c-dc529e1bb2c2" />

This is the ephermeral port number mentioned earlier that should be opened for inbound IPv4 traffic on your server. Enter your chosen ephermeral port number and press Enter.

You will then see the following:

<img width="638" height="24" alt="image" src="https://github.com/user-attachments/assets/e3db83c9-70a1-4ed4-be9a-982c158d6b63" />

This is the number of standard playing card decks the game will use for each game. Standard games of Spite and Malice use 2 decks, but I prefer using 4. Enter a number between 2-6 and press Enter again.

You will then see yet another user prompt:

<img width="620" height="18" alt="image" src="https://github.com/user-attachments/assets/ee74a8c6-ad6e-4ad7-bb2e-a8f2a37462ba" />

This is the number of cards to use for each payoff pile. Standard games of Spite and Malice use either 20 or 30, but you can enter any value between and including 20 and 30. Press Enter once again to complete
the initial configuration.

You should then see a notification that a configuration file was written to a local directory path and that the server has begun listening for traffic. Configuration files are written by the server to the
following locations depending on the platform of the host:

**Windows**: ```C:/ProgramData/jscdev909/spite_and_malice_server```
</br>**MacOS/Linux**: ```$HOME/.config/spite_and_malice_server```

These files are fully editable but if any wrong information is read from them while restarting the server you will receive the setup prompts again to re-write the file with valid information.

Initial server configuration is now complete. The entered information will be remembered for all subsequent runs of the server. To get the initial user setup prompts again, simply delete the config file.

On the client side, after setting up a python virtual environment and installing pygame-ce and pygame-gui (or simply starting the single client executable from the releases page), you will be presented
with the following empty configuration screen:

<img width="927" height="982" alt="image" src="https://github.com/user-attachments/assets/254cd349-97b9-4030-a3c7-7f96817e4869" />

Player name can be any name up to 8 characters in length. The server IP is the visible IPv4 address of the server (or 127.0.0.1 if hosting locally) and the port is the ephemeral port configured on the server 
earlier. The game options control the color of the card backs seen in the GUI and if any shuffling or dealing card sounds should be played during the game. These can be adjusted as necessary. After pressing
OK all of these settings will be stored in a config.toml file at the following path depending on the host platform:

**Windows**: ```C:/ProgramData/jscdev909/spite_and_malice_client```
</br>**MacOS/Linux**: ```$HOME/.config/spite_and_malice_client```

The configuration file is automatically re-written each time you press OK in the client. To get a blank client setup screen again, simply delete the configuration file.

Press OK to connect to another client to play the game. You should see connection status notifications on the client and the server should start outputting status messages for the players as well. 
At this point both running clients should be able to connect to each other and play the game. 

Enjoy!

If you have any questions or concerns with the game functionality, don't be afraid to open an issue and let me know!

# Asset Credits

- Playing cards (by Byron Knoll, open source/public domain license): https://opengameart.org/content/playing-cards-vector-png
- Colored card backs (by jeffshee, [Creative Commons 3.0 license](https://creativecommons.org/licenses/by/3.0/)): https://opengameart.org/content/colorful-poker-card-back
- Icon used for MacOS/Windows executables (by Everaldo, [LGPL Open Source license](https://www.gnu.org/licenses/lgpl-3.0.html)): https://www.iconarchive.com/show/crystal-clear-icons-by-everaldo/App-Card-game-icon.html

# Special Thanks
- [Stack Overflow](stackoverflow.com), for tons of answers of relevant Python questions and for providing the source code for the get_path and recv_all helper functions in path_utils.py and socket_utils.py, respectively
- My mother, for playing Skip-Bo with me which inspired this whole project









