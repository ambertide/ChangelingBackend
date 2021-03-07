from dataclasses import dataclass
from enum import Enum
from random import random
import pickle
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
class GameRoom:
    room_id: str # Unique id of the room.
    admin: "User"  # Session ID of the admin.
    users: list["User"]  # Ordered users.
    changelings: list["User"]  # Ordered changelings.
    user_states: dict[str, PlayerState]  # Dictionary with user and user states.
    turn: int  # Turn the game is in.
    game_state: GameState


@dataclass
class User:
    user_id: str
    username: str
    portrait_name: str

    def __eq__(self, other) -> bool:
        if type(self) != type(other):
            return False
        return self.user_id == other.user_id

    def get_player_data(self, admin: bool = False, is_you: bool = False):
        """
        Get JSON serialisable player data.

        :param admin: true if the user is admin.
        :param is_you: True if the user is the client.
        :return: JSON serialisable player data as dict.
        """
        return {
            "user_id": self.user_id,
            "name": self.username,
            "portraitName": self.portrait_name,
            "playerRole": "unassigned",
            "admin": admin,
            "is_you": is_you
        }


class RoomConnectionManager:
    def __init__(self, **kwargs) -> None:
        self.connection = Redis(**kwargs) # Establish communication.

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
        return self.connection.exists(room_id)

    def generate_room_id(self) -> str:
        """
        Generate a unique room ID.

        :return: a new room ID.
        """
        room_id = f"{hash(random()):X}"[0:6]  # Generate a random room ID.
        while room_id in self:  # Continue generating until no match in rooms.
            room_id = f"{hash(random()):X}"[0:6]
        return room_id
