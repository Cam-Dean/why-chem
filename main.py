"""
Platform game showcasing chemistry careers.

Tiled available from: https://www.mapeditor.org/

If Python and Arcade are installed, this can be run from the command line with:
python main.py

Future possibilities:
- moving platforms
- enemies (moving?)
- untouchable objects (ex: lava)
- different scientist character for each level?

"""
import os

import arcade
import pyglet
import time
import sys
import PIL.Image
from pathlib import Path
from pytiled_parser.parsers.json.tiled_map import parse

# Constants
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 650
SCREEN_TITLE = "WhyChem"

# Constants used to scale our sprites from their original size
# TEST
TILE_SCALING = 4 #4/0.5
CHARACTER_SCALING = TILE_SCALING * 0.2 #0.2/2
COIN_SCALING = TILE_SCALING
SPRITE_PIXEL_SIZE = 128
GRID_PIXEL_SIZE = SPRITE_PIXEL_SIZE * TILE_SCALING

# Movement speed of player, in pixels per frame
PLAYER_MOVEMENT_SPEED = 7
GRAVITY = 1.4 #1.3/1.5
PLAYER_JUMP_SPEED = 30

PLAYER_START_X = SCREEN_WIDTH / 4
PLAYER_START_Y = SCREEN_HEIGHT / 4

# Constants used to track if the player is facing left or right
RIGHT_FACING = 0
LEFT_FACING = 1

LAYER_NAME_PLATFORMS = "Platforms"
LAYER_NAME_PLATFORMS_1 = "Platforms_1"
LAYER_NAME_PLATFORMS_2 = "Platforms_2"
LAYER_NAME_COINS = "Coins"
#LAYER_NAME_LADDERS = "Ladders"
LAYER_NAME_PLAYER = "Player"
LAYER_NAME_DECORATIONS = "Decorations"
#LAYER_NAME_GROUND = "Ground"
#LAYER_NAME_TEXT = "Text"
NON_BACKGROUND_LAYERS = [LAYER_NAME_PLATFORMS, LAYER_NAME_PLATFORMS_1, LAYER_NAME_PLATFORMS_2, LAYER_NAME_PLAYER, LAYER_NAME_COINS, LAYER_NAME_DECORATIONS]


# Define the ends of each map
END_OF_MAP = [7.25,12.26,12.26,12.26]

# Start/end screen fade
FADE_RATE = 5


def load_texture_pair(filename):
    """
    Load a texture pair, with the second being a mirror image.
    """
    return [
        arcade.load_texture(filename),
        arcade.load_texture(filename, flipped_horizontally=True),
    ]


class PlayerCharacter(arcade.Sprite):
    """Player Sprite"""

    def __init__(self):

        # Set up parent class
        super().__init__()

        # Default to face-right
        self.character_face_direction = RIGHT_FACING

        # Used for flipping between image sequences
        self.cur_texture = 0
        self.scale = CHARACTER_SCALING

        # Track our state
        self.jumping = False
        self.climbing = False
        self.is_on_ladder = False

        # --- Load Textures ---

        # Images from Kenney.nl's Asset Pack 3
        main_path = "resources/images/female_person_scientist/femalePerson"

        # Load textures for idle standing
        self.idle_texture_pair = load_texture_pair(f"{main_path}_idle.png")
        self.jump_texture_pair = load_texture_pair(f"{main_path}_jump.png")
        self.fall_texture_pair = load_texture_pair(f"{main_path}_fall.png")

        # Load textures for walking
        self.walk_textures = []
        for i in range(8):
            texture = load_texture_pair(f"{main_path}_walk{i}.png")
            self.walk_textures.append(texture)

        # Load textures for climbing
        self.climbing_textures = []
        texture = arcade.load_texture(f"{main_path}_climb0.png")
        self.climbing_textures.append(texture)
        texture = arcade.load_texture(f"{main_path}_climb1.png")
        self.climbing_textures.append(texture)

        # Set the initial texture
        self.texture = self.idle_texture_pair[0]

        # Hit box will be set based on the first image used. If you want to specify
        # a different hit box, you can do it like the code below.
        # set_hit_box = [[-22, -64], [22, -64], [22, 28], [-22, 28]]
        self.hit_box = self.texture.hit_box_points

    def update_animation(self, delta_time: float = 1 / 60):

        # Figure out if we need to flip face left or right
        if self.change_x < 0 and self.character_face_direction == RIGHT_FACING:
            self.character_face_direction = LEFT_FACING
        elif self.change_x > 0 and self.character_face_direction == LEFT_FACING:
            self.character_face_direction = RIGHT_FACING

        # Climbing animation
        if self.is_on_ladder:
            self.climbing = True
        if not self.is_on_ladder and self.climbing:
            self.climbing = False
        if self.climbing and abs(self.change_y) > 1:
            self.cur_texture += 1
            if self.cur_texture > 7:
                self.cur_texture = 0
        if self.climbing:
            self.texture = self.climbing_textures[self.cur_texture // 4]
            return

        # Jumping animation
        if self.change_y > 0 and not self.is_on_ladder:
            self.texture = self.jump_texture_pair[self.character_face_direction]
            return
        elif self.change_y < 0 and not self.is_on_ladder:
            self.texture = self.fall_texture_pair[self.character_face_direction]
            return

        # Idle animation
        if self.change_x == 0:
            self.texture = self.idle_texture_pair[self.character_face_direction]
            return

        # Walking animation
        self.cur_texture += 1
        if self.cur_texture > 7:
            self.cur_texture = 0
        self.texture = self.walk_textures[self.cur_texture][
            self.character_face_direction
        ]


class GameView(arcade.View):
    """
    Main application class.
    """

    def __init__(self):
        """
        Initializer for the game
        """

        # Call the parent class and set up the window
        #super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        super().__init__()

        # Set the path to start with this program
        file_path = os.path.dirname(os.path.abspath(__file__))
        os.chdir(file_path)

        # Track the current state of what key is pressed
        self.left_pressed = False
        self.right_pressed = False
        self.up_pressed = False
        self.down_pressed = False
        self.jump_needs_reset = False

        # Our TileMap Object
        self.tile_map = None

        # Our Scene Object
        self.scene = None

        # Separate variable that holds the player sprite
        self.player_sprite = None

        # Our 'physics' engine
        self.physics_engine = None

        # A Camera that can be used for scrolling the screen
        self.camera = None

        # A Camera that can be used to draw GUI elements
        self.gui_camera = None

        self.end_of_map = 0

        # Keep track of the score
        self.score = 0

        # Load sounds
        self.collect_coin_sound = arcade.load_sound("resources/sounds/coin1.wav")
        self.jump_sound = arcade.load_sound("resources/sounds/jump1.wav")
        self.victory_sound = arcade.load_sound("resources/sounds/JKL83NH-video-game-win.mp3")
        self.theme_music = arcade.load_sound("resources/sounds/Stardew Valley OST - Spring (Wild Horseradish Jam).mp3")

        # Level
        self.level = 1
        self.max_level = 4
        self.level_over = False
        self.next_level = False

        # Parallax
        self.camera_x_prev = PLAYER_START_X

    def setup(self):
        """Set up the game here. Call this function to restart the game."""

        # Set up the Cameras
        self.camera = arcade.Camera(self.window.width, self.window.height)
        self.gui_camera = arcade.Camera(self.window.width, self.window.height)

        # Load in TileMap
        self.load_level(self.level)

        # Keep track of the score
        self.score = 0

        self.play_sound = arcade.play_sound(self.theme_music, looping=True)

    def load_level(self, level):
        # Layer Specific Options for the Tilemap
        if self.level > 1: #and self.level < 4:
            layer_options = {
                LAYER_NAME_PLATFORMS: {
                    "use_spatial_hash": True,
                },
                LAYER_NAME_PLATFORMS_1: {
                    "use_spatial_hash": True,
                },
                LAYER_NAME_PLATFORMS_2: {
                    "use_spatial_hash": True,
                },
                # LAYER_NAME_DECORATIONS: {
                #     "use_spatial_hash": True
                # },
                #LAYER_NAME_MOVING_PLATFORMS: {
                #    "use_spatial_hash": False,
                #},
                #LAYER_NAME_LADDERS: {
                #    "use_spatial_hash": True,
                #},
                LAYER_NAME_COINS: {
                "use_spatial_hash": True,
                },
            }
        else:
            layer_options = {
                LAYER_NAME_PLATFORMS: {
                    "use_spatial_hash": True,
                },
                LAYER_NAME_COINS: {
                "use_spatial_hash": True,
                },
            }

        # Read in the tiled map
        self.tile_map = arcade.load_tilemap(
            f"resources/maps/level_{level}.json", TILE_SCALING, layer_options,
            # TEST
            #":resources:tiled_maps/map_with_ladders.json", TILE_SCALING, layer_options,
        )

        # Initiate New Scene with our TileMap, this will automatically add all layers
        # from the map as SpriteLists in the scene in the proper order.
        self.scene = arcade.Scene.from_tilemap(self.tile_map)

        # print(self.tile_map.object_lists.keys())
        # print(self.scene["Text"])

        # Set up the player, specifically placing it at these coordinates.
        self.player_sprite = PlayerCharacter()
        self.player_sprite.center_x = PLAYER_START_X
        self.player_sprite.center_y = PLAYER_START_Y
        self.scene.add_sprite(LAYER_NAME_PLAYER, self.player_sprite)

        # --- Walls ---

        # Calculate the right edge of the my_map in pixels
        self.end_of_map = END_OF_MAP[level-1] * GRID_PIXEL_SIZE
        # self.end_of_map = self.tile_map.width * GRID_PIXEL_SIZE

        if level > 1:
            self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS].extend(self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS+"_1"])
            self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS].extend(self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS+"_2"])
        # elif level == 3:
        #     self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS].extend(self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS+"_1"])
            # self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS].extend(self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS+"_2"])
            # self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS].extend(self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS+"_3"])
        # elif level == 4:
            # self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS].extend(self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS+"_1"])

        self.physics_engine = arcade.PhysicsEnginePlatformer(
            self.player_sprite,
            self.tile_map.sprite_lists[LAYER_NAME_PLATFORMS],
            gravity_constant=GRAVITY,
            # walls=self.scene[LAYER_NAME_PLATFORMS],
        )

        # --- Other stuff
        # Set the background color
        if self.tile_map.background_color:
            arcade.set_background_color(self.tile_map.background_color)

        # Set the view port boundaries
        # These numbers set where we have 'scrolled' to.
        # self.view_left = 0
        # self.view_bottom = 0

        self.background_layer_names = sorted( [ name for name in self.scene.name_mapping.keys() if name not in NON_BACKGROUND_LAYERS] )

        self.camera_x_prev = PLAYER_START_X

    def on_draw(self):
        """Render the screen."""

        # Determine font color
        if self.level == 1:
            font_color = arcade.color.BLACK
        else:
            font_color = arcade.color.WHITE

        # Clear the screen to the background color
        self.clear()

        # Activate the game camera
        self.camera.use()

        # Draw our Scene
        self.scene.draw()

        # Manually draw text
        y_scale = [0.62, 1, 1, 1.3]
        pytiled_map = parse(Path(f"resources/maps/level_{self.level}.json"))
        for layer in pytiled_map.layers:
            if layer.name == "Text":
                tiled_objects = layer.tiled_objects
                for t_obj in tiled_objects:
                    if t_obj.font_family == "Chalkduster":
                        font = "Chalkduster"
                    else:
                        font = "American Typewriter"
                    arcade.draw_text(
                        t_obj.text,
                        t_obj.coordinates[0]/32 * GRID_PIXEL_SIZE/TILE_SCALING,
                        t_obj.coordinates[1]/32 * GRID_PIXEL_SIZE/TILE_SCALING*y_scale[self.level-1],
                        t_obj.color,
                        t_obj.font_size*3,
                        t_obj.size.width*4,
                        t_obj.horizontal_align,
                        font,
                        # anchor_x=t_obj.horizontal_align,
                        # anchor_y=t_obj.vertical_align,
                        multiline=t_obj.wrap,
                    )

        # Redraw player in front
        self.scene.draw(["Player"])

        # Activate the GUI camera before drawing GUI elements
        self.gui_camera.use()

        # Draw our score on the screen, scrolling it with the viewport
        score_text = f"Score: {self.score}"
        arcade.draw_text(
            score_text,
            10,
            10,
            font_color,
            18,
            font_name="American Typewriter",
        )

        if self.level_over:
            if self.level == 4:
                arcade.draw_text(
                    f"Well done! Your score was: {self.score}",
                    SCREEN_WIDTH / 2,
                    3 * SCREEN_HEIGHT / 4,
                    font_color,
                    30,
                    font_name="American Typewriter",
                    anchor_x="center",
                )
            arcade.draw_text(
                    "Press <space> to continue",
                    SCREEN_WIDTH / 2,
                    SCREEN_HEIGHT / 2,
                    font_color,
                    30,
                    font_name="American Typewriter",
                    anchor_x="center",
                )

    def process_keychange(self):
        """
        Called when we change a key up/down or we move on/off a ladder.
        """
        # Process up/down
        if not self.level_over:
            if self.up_pressed and not self.down_pressed:
                if self.physics_engine.is_on_ladder():
                    self.player_sprite.change_y = PLAYER_MOVEMENT_SPEED
                elif (
                    self.physics_engine.can_jump(y_distance=10)
                    and not self.jump_needs_reset
                ):
                    self.player_sprite.change_y = PLAYER_JUMP_SPEED
                    self.jump_needs_reset = True
                    arcade.play_sound(self.jump_sound)
            elif self.down_pressed and not self.up_pressed:
                if self.physics_engine.is_on_ladder():
                    self.player_sprite.change_y = -PLAYER_MOVEMENT_SPEED

            # Process up/down when on a ladder and no movement
            if self.physics_engine.is_on_ladder():
                if not self.up_pressed and not self.down_pressed:
                    self.player_sprite.change_y = 0
                elif self.up_pressed and self.down_pressed:
                    self.player_sprite.change_y = 0

            # Process left/right
            if self.right_pressed and not self.left_pressed:
                self.player_sprite.change_x = PLAYER_MOVEMENT_SPEED
            elif self.left_pressed and not self.right_pressed:
                self.player_sprite.change_x = -PLAYER_MOVEMENT_SPEED
            else:
                self.player_sprite.change_x = 0

    def on_key_press(self, key, modifiers):
        """Called whenever a key is pressed."""

        if key == arcade.key.UP or key == arcade.key.W:
            self.up_pressed = True
        elif key == arcade.key.DOWN or key == arcade.key.S:
            self.down_pressed = True
        elif key == arcade.key.LEFT or key == arcade.key.A:
            self.left_pressed = True
        elif key == arcade.key.RIGHT or key == arcade.key.D:
            self.right_pressed = True
        elif key == arcade.key.SPACE and self.level_over:
            self.next_level = True

        self.process_keychange()

    def on_key_release(self, key, modifiers):
        """Called when the user releases a key."""

        if key == arcade.key.UP or key == arcade.key.W:
            self.up_pressed = False
            self.jump_needs_reset = False
        elif key == arcade.key.DOWN or key == arcade.key.S:
            self.down_pressed = False
        elif key == arcade.key.LEFT or key == arcade.key.A:
            self.left_pressed = False
        elif key == arcade.key.RIGHT or key == arcade.key.D:
            self.right_pressed = False

        self.process_keychange()

    def center_camera_to_player(self):
        screen_center_x = self.player_sprite.center_x - (self.camera.viewport_width / 2)
        screen_center_y = self.player_sprite.center_y - (
            self.camera.viewport_height / 2
        )
        if screen_center_x < 0:
            screen_center_x = 0
        if screen_center_y < 0:
            screen_center_y = 0
        player_centered = screen_center_x, screen_center_y

        self.camera.move_to(player_centered, 0.2)


    def on_update(self, delta_time):
        """Movement and game logic"""

        # Update level
        if self.player_sprite.right >= self.end_of_map:
            if self.level == 4 and not self.level_over:
                arcade.play_sound(self.victory_sound)
                time.sleep(2)
            if self.level < self.max_level:
                self.level_over = True
                if self.next_level:
                    self.level_over = False
                    self.next_level = False
                    self.level += 1
                    self.load_level(self.level)
                    self.player_sprite.center_x = SCREEN_WIDTH
                    self.player_sprite.center_y = SCREEN_HEIGHT / 2
                    self.player_sprite.change_x = 0
                    self.player_sprite.change_y = 0
            else:
                arcade.stop_sound(self.play_sound)
                self.level_over = True
                if self.next_level:
                    end_view = EndView()
                    self.window.show_view(end_view)

        else:
            # Move the player with the physics engine
            self.physics_engine.update()

            # Update animations
            if self.physics_engine.can_jump():
                self.player_sprite.can_jump = False
            else:
                self.player_sprite.can_jump = True

            if self.physics_engine.is_on_ladder() and not self.physics_engine.can_jump():
                self.player_sprite.is_on_ladder = True
                self.process_keychange()
            else:
                self.player_sprite.is_on_ladder = False
                self.process_keychange()

            # Parallax background
            self.camera_x = self.camera.position[0]
            if self.level > 1:
                for count, sprite_name in enumerate(self.background_layer_names):
                    if self.level == 4 and count == 3:
                        pass
                    else:
                        for sprite in self.scene.name_mapping[sprite_name]:
                            sprite.left += (self.camera_x - self.camera_x_prev) / ((count + 4) * 0.25)

            self.camera_x_prev = self.camera_x
                    
                    # layer = count // 2      0, 0, 1, 1
                    # frame = count % 2       0, 1, 0, 1
                    # offset = camera_x / (2 ** (layer + 1))   c/2, c/2, c/4, c/4    
                    # jump = (camera_x - offset) // sprite.width    c/2, c/2, 3c/4, 3c/4
                    # final_offset = offset + (jump + frame) * sprite.width 
                    # sprite.left = final_offset

            # Update Animations
            if self.level == 1:
                self.scene.update_animation(
                #    delta_time, [LAYER_NAME_COINS, LAYER_NAME_BACKGROUND, LAYER_NAME_PLAYER]
                    delta_time, [LAYER_NAME_COINS, LAYER_NAME_PLAYER, LAYER_NAME_DECORATIONS],
                )
            else:
                layer_names = NON_BACKGROUND_LAYERS + self.background_layer_names
                self.scene.update_animation(
                #    delta_time, [LAYER_NAME_COINS, LAYER_NAME_BACKGROUND, LAYER_NAME_PLAYER]
                    delta_time, layer_names,
                )

            # Update walls, used with moving platforms
            #self.scene.update([LAYER_NAME_MOVING_PLATFORMS])

            # See if we hit any coins
            coin_hit_list = arcade.check_for_collision_with_list(
               self.player_sprite, self.scene[LAYER_NAME_COINS]
            )

            # Loop through each coin we hit (if any) and remove it
            for coin in coin_hit_list:

            #     Figure out how many points this coin is worth
                # if "Points" not in coin.properties:
                #     print("Warning, collected a coin without a Points property.")
                # else:
                    # points = int(coin.properties["Points"])
                self.score += 10

            #     Remove the coin
                coin.remove_from_sprite_lists()
                arcade.play_sound(self.collect_coin_sound)

            # Position the camera
            self.center_camera_to_player()

class FadingView(arcade.View):
    def __init__(self):
        super().__init__()
        self.fade_out = None
        self.fade_in = 255

    def update_fade(self, next_view=None, setup=True):
        if self.fade_out is not None:
            self.fade_out += FADE_RATE
            if self.fade_out is not None and self.fade_out > 255 and next_view is not None:
                game_view = next_view()
                game_view.setup()
                self.window.show_view(game_view)

        if self.fade_in is not None:
            self.fade_in -= FADE_RATE
            if self.fade_in <= 0:
                self.fade_in = None

    def draw_fading(self):
        if self.fade_out is not None:
            arcade.draw_rectangle_filled(self.window.width / 2, self.window.height / 2,
                                         self.window.width, self.window.height,
                                         (0, 0, 0, self.fade_out))

        if self.fade_in is not None:
            arcade.draw_rectangle_filled(self.window.width / 2, self.window.height / 2,
                                         self.window.width, self.window.height,
                                         (0, 0, 0, self.fade_in))

class StartView(FadingView):
    """ Class that manages the 'menu' view. """

    def on_update(self, dt):
        self.update_fade(next_view=GameView)

    def on_show_view(self):
        """ Called when switching to this view"""
        arcade.set_background_color(arcade.color.WHITE)

    def on_draw(self):
        """ Draw the menu """
        self.clear()
        image = PIL.Image.open("resources/images/Bottle Background.png")
        texture = arcade.Texture("bckgd", image)
        arcade.draw_texture_rectangle(SCREEN_WIDTH / 2, 10 * SCREEN_HEIGHT / 18, 1000, 650, texture)
        arcade.load_font("resources/fonts/Chalkduster.ttf")
        arcade.load_font("resources/fonts/AmericanTypewriterRegular.ttf")
        text = arcade.Text("Welcome to WhyChem, a world where you can explore chemistry!", SCREEN_WIDTH // 2, 39*SCREEN_HEIGHT // 72,
                         arcade.color.BLACK, font_size=30, anchor_x="center", align="center", multiline=True, width = SCREEN_WIDTH * 13/16, font_name="American Typewriter")
        text.draw()
        text = arcade.Text("Collect", SCREEN_WIDTH * 5 / 16, SCREEN_HEIGHT * 25 / 64,
                         arcade.color.BLACK, font_size=20, anchor_x="center", align="right", multiline=True, width = SCREEN_WIDTH * 6/16, font_name="American Typewriter")
        text.draw()
        text = arcade.Text("Advance Using", SCREEN_WIDTH * 5 / 16, SCREEN_HEIGHT * 39 / 128,
                         arcade.color.BLACK, font_size=20, anchor_x="center", align="right", multiline=True, width = SCREEN_WIDTH * 6/16, font_name="American Typewriter")
        text.draw()
        text = arcade.Text("Press <space>\nto continue", SCREEN_WIDTH // 2, SCREEN_HEIGHT * 1 / 8,
                         arcade.color.BLACK, font_size=30, anchor_x="center", align="center", multiline=True, width = SCREEN_WIDTH * 13/16, font_name="American Typewriter")
        text.draw()
        image = PIL.Image.open("resources/images/Sprites + Stone Objects/Sprites/11-Door/Idle.png")
        texture = arcade.Texture("door", image)
        arcade.draw_texture_rectangle(550, 210, 50, 50, texture)
        image = PIL.Image.open("resources/images/MegaPixelArt32x32pxIcons_SpriteSheet/erlenmeyer_flask.png")
        texture = arcade.Texture("erlenmeyer", image)
        arcade.draw_texture_rectangle(550, 270, 50, 50, texture)
        self.draw_fading()

    def on_key_press(self, key, _modifiers):
        """ If user hits space, go to the start of the game """
        if self.fade_out is None and key == arcade.key.SPACE:
            self.fade_out = 0

    def setup(self):
        """ This should set up your game and get it ready to play """
        pass
        

class EndView(FadingView):
    """ Class that manages the 'menu' view. """

    def on_update(self, dt):
        self.update_fade(next_view=EndView2)

    def on_show_view(self):
        """ Called when switching to this view"""
        arcade.set_background_color(arcade.color.WHITE)

    def on_draw(self):
        """ Draw the menu """
        self.clear()
        image = PIL.Image.open("resources/images/EndScreen.png")
        texture = arcade.Texture("endscrn", image)
        arcade.draw_texture_rectangle(SCREEN_WIDTH / 2, 11 * SCREEN_HEIGHT / 18, 1000, 650, texture)
        text = arcade.Text("With chemistry\nyou can...", SCREEN_WIDTH * 49/64,  SCREEN_HEIGHT * 12 / 16,
                         arcade.color.BLACK, font_size=30, anchor_x="center", align="left", multiline=True, width = SCREEN_WIDTH * 18/64, font_name="American Typewriter")
        text.draw()
        text = arcade.Text("travel to new places", SCREEN_WIDTH * 11/16,  SCREEN_HEIGHT * 8 / 16,
                         arcade.color.BLACK, font_size=24, anchor_x="center", align="center", multiline=True, width = SCREEN_WIDTH * 1/4, font_name="American Typewriter", rotation=4)
        text.draw()
        text = arcade.Text("learn new things", SCREEN_WIDTH * 20/32,  SCREEN_HEIGHT * 7 / 32,
                         arcade.color.BLACK, font_size=24, anchor_x="center", align="center", multiline=True, width = SCREEN_WIDTH * 1/4, font_name="American Typewriter", rotation=-20)
        text.draw()
        text = arcade.Text("create a better world around you", SCREEN_WIDTH * 47/64,  SCREEN_HEIGHT * 6 / 16,
                         arcade.color.BLACK, font_size=24, anchor_x="center", align="center", multiline=True, width = SCREEN_WIDTH * 3/8, font_name="American Typewriter", rotation=20)
        text.draw()
        text = arcade.Text("Press <space> to continue", SCREEN_WIDTH // 2, SCREEN_HEIGHT // 18,
                         arcade.color.BLACK, font_size=24, anchor_x="center", align="center", multiline=True, width = SCREEN_WIDTH * 3/4, font_name="American Typewriter")
        text.draw()
        self.draw_fading()

    def on_key_press(self, key, _modifiers):
        """ If user hits space, go back to the start view """
        if self.fade_out is None and key == arcade.key.SPACE:
            self.fade_out = 0

    def setup(self):
        """ This should set up your game and get it ready to play """
        pass

class EndView2(FadingView):
    """ Class that manages the 'menu' view. """

    def on_update(self, dt):
        self.update_fade(next_view=StartView)

    def on_show_view(self):
        """ Called when switching to this view"""
        arcade.set_background_color(arcade.color.WHITE)

    def on_draw(self):
        """ Draw the menu """
        self.clear()
        image = PIL.Image.open("resources/images/arcade-logo.png")
        texture = arcade.Texture("arcade", image)
        arcade.draw_texture_rectangle(SCREEN_WIDTH * 13 / 16, SCREEN_HEIGHT * 8 / 10, 200, 200, texture)
        image = PIL.Image.open("resources/images/python-logo.png")
        texture = arcade.Texture("python", image)
        arcade.draw_texture_rectangle(SCREEN_WIDTH * 5 / 16, SCREEN_HEIGHT * 8 / 10, 600, 200, texture)
        text = arcade.Text("Thanks for playing!\n\nThis game was written in the Python programming language, and created using the Arcade library.\n\nPress <space> to restart game", SCREEN_WIDTH // 2, SCREEN_HEIGHT * 5 / 8,
                         arcade.color.BLACK, font_size=30, anchor_x="center", align="center", multiline=True, width = SCREEN_WIDTH * 3/4, font_name="American Typewriter")
        text.draw()
        self.draw_fading()

    def on_key_press(self, key, _modifiers):
        """ If user hits space, go back to the start view """
        if self.fade_out is None and key == arcade.key.SPACE:
            self.fade_out = 0

    def setup(self):
        """ This should set up your game and get it ready to play """
        pass

def main():
    """Main function"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        os.chdir(sys._MEIPASS)
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
    start_view = StartView()
    window.show_view(start_view)
    # end_view = EndView()
    # window.show_view(end_view)
    arcade.run()


if __name__ == "__main__":
    main()