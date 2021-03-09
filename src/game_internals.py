from dataclasses import dataclass
from enum import Enum
from random import random, choice
import pickle
from json import dumps
from typing import Optional

from redis import Redis


class GameState(Enum):
    """
    An enum class that represents the room state
        independent of other players.
    """
    LOBBY = 0
    NORMAL = 1
    CAMPFIRE_OUT = 2  # Skip here is for easier syncing.
    BURN_CAMPER = 4  # Since turn states have an extra.
    CAMPER_VICTORY = 5
    CHANGELING_VICTORY = 6


class PlayerState(Enum):
    """
    An enum class that represents valid states
        player's characters may exist.
    """
    UNASSIGNED = "unassigned"
    CHANGELING = "changeling"
    CAMPER = "camper"
    DEAD = "dead"


@dataclass
class User:
    user_id: str
    username: str
    portrait_name: str
    player_role: PlayerState = PlayerState.UNASSIGNED

    def __eq__(self, other) -> bool:
        if type(self) != type(other):
            return False
        return self.user_id == other.user_id

    def get_player_data(self, admin: bool = False, show_changeling: bool = False):
        """
        Get JSON serialisable player data.

        :param admin: true if the user is admin.
        :param show_changeling: If false, changelings are shown as
            campers.
        :return: JSON serialisable player data as dict.
        """
        player_role = self.player_role
        if player_role == PlayerState.CHANGELING and not show_changeling:
            player_role = PlayerState.CAMPER # Campers can't see changelings
            # Are changelings.
        return {
            "user_id": self.user_id,
            "name": self.username,
            "portraitName": self.portrait_name,
            "playerRole": player_role.value,
            "admin": admin,
        }


@dataclass
class GameRoom:
    room_id: str  # Unique id of the room.
    admin: User  # Session ID of the admin.
    users: list[User]  # Ordered users.
    changelings: list[User]  # Ordered changelings.
    turn: int  # Turn the game is in.
    turn_state: GameState
    turn_owner_index: int = 0  # Index of the turn owner.
    real_turn: int = 0

    @property
    def turn_owner(self) -> User:
        return self.users[self.turn_owner_index]

    @turn_owner.setter
    def set_turn_owner(self, owner: User) -> None:
        self.turn_owner_index = self.users.index(owner)

    def assign_roles(self) -> User:
        """
        Assign player roles to players, one changeling,
            all others campers, initially.

        :return: the User that became the changeling.
        """
        for user in self.users: # Initially make them all campers.
            user.player_role = PlayerState.CAMPER
        random_camper = choice(self.users)
        random_camper.player_role = PlayerState.CHANGELING  # Set random user to changeling.
        self.changelings.append(random_camper)
        return random_camper  # Return that user.

    def get_user_states(self, show_changelings: bool) -> str:
        """
        Get the user states in JSON format

        :return: the user states in a string that is JSON parsable.
        """
        # Get the user states
        user_states = [user.get_player_data(admin=(user == self.admin), show_changeling=show_changelings) for user in self.users]
        user_states = "{ \"players\": [" + ','.join(map(dumps, user_states)) + "]}"  # Convert it to json.
        return user_states

    @property
    def game_state(self):
        """
        The state of the room, ie: the dictionary
            for the JSON callback to the resp_sync_gamestate

        :return: The state of the game room, minus the users.
        """
        return {
            "game_state": self.turn_state.value,
            "turn_count": self.turn,
            "ownership": self.turn_owner.user_id
        }

    def next_turn(self) -> None:
        """
        Proceed to the next turn decide if it should be a special turn.

        :return: None
        """
        self.real_turn += 1  # This is updated no matter what.
        if self.turn != 0 and self.turn % 5: # If turn is divisible by five
            # In special turn we either burn a camper or create a changeling.
            self.turn_state = choice([GameState.BURN_CAMPER, GameState.BURN_CAMPER, GameState.CHANGELING_VICTORY])
        else:
            self.turn += 1
            self.turn_owner_index += 1


class NoSuchRoomException(Exception):
    """
    Thrown in case there is no such room yet.
    """
    pass


class RoomConnectionManager:
    """
    Manages requests to get and modify Room objects
    between different threads using a Redis database
    residing in memory.
    """

    def __init__(self, **kwargs) -> None:
        self.connection = Redis(**kwargs)  # Establish communication.

    def __setitem__(self, room_id: str, room_obj: GameRoom) -> None:
        """
        Add the room to the Redis database for syncing up
            between different players.

        :param room_id: ID of the room.
        :param room_obj: Room object.
        """
        room_picked = pickle.dumps(room_obj)
        self.connection.set(room_id, room_picked)

    def __getitem__(self, room_id: str) -> GameRoom:
        """
        Get a room object from Redis.

        :param room_id: ID Of the room object.
        :return: the Room object.
        """
        if room_id not in self:
            raise NoSuchRoomException
        return pickle.loads(self.connection.get(room_id))

    def __delitem__(self, room_id: str) -> None:
        """
        Delete a room from the Redis storage.

        :param room_id: Room to delete.
        """
        self.connection.delete(room_id)

    def __contains__(self, room_id: str) -> bool:
        """
        Check if a room is in the Redis storage.

        :param room_id: ID of the room.
        :return: True if the room is in memory.
        """
        return self.connection.exists(room_id) > 0

    def generate_room_id(self) -> str:
        """
        Generate a unique room ID.

        :return: a new room ID.
        """
        room_id = f"{hash(random()):X}"[0:6]  # Generate a random room ID.
        while room_id in self:  # Continue generating until no match in rooms.
            room_id = f"{hash(random()):X}"[0:6]
        return room_id
