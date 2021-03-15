from dataclasses import dataclass
from enum import Enum
from random import random, choice
import pickle
from json import dumps
from typing import Optional, Any, Callable

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


class NoSuchRoomException(Exception):
    """
    Thrown in case there is no such room yet.
    """
    pass


class Singleton(type):
    """
    A metaclass that turns classes deriving from it into
    Singleton classes, only one class can derive from this
    variation for the sake of simplicity.

    Modified version of: https://stackoverflow.com/a/6798042/6663851
    """
    instance: "Singleton" = None

    def __call__(cls, *args, **kwargs) -> "Singleton":
        if cls.instance is None: # If it hasn't been created yet.
            cls.instance = super(Singleton, cls).__call__() # Create it.
        return cls.instance


class ConnectionManager(metaclass=Singleton):
    """
    Connection manager for Redis instance, a singleton.
    """
    def __init__(self):
        self.connection = Redis(host="localhost", port=6379, db=0)

    def create_obj(self, obj_type: str, obj_id: str, mapping: dict[str, str]) -> None:
        """
        Create an object of given type.

        :param obj_type: Type of the object.
        :param obj_id: ID of the object.
        :param mapping: KV pairs for the object.
        :return:
        """
        self.connection.hmset(f"{obj_type}:{obj_id}", mapping)

    def modify(self, obj_type: str, id_: str, attribute: str, new_value: Any) -> None:
        """
        Modify an object in the Redis KV store, objects are
            hashes. Users and static string values of Rooms
            are objects.

        :param obj_type: Type of the object to modify.
        :param id_: Id of the Object to modify.
        :param attribute: Attribute to be modified.
        :param new_value: New value of the attribute.
        """
        self.connection.hset(f"{obj_type}:{id_}", attribute, new_value)

    def get_from(self, obj_type: str, id_: str, attribute: str) -> str:
        """
        Get an attribute of an object given its type and id.

        :param obj_type: Type of the object, User or Room.
        :param id_: ID of the object.
        :param attribute: Attribute to access.
        :return: The attribute of the object.
        """
        return self.connection.hget(f"{obj_type}:{id_}", attribute)

    def get(self, obj_type: str, id_: str, attribute: str) -> Any:
        """
        Get the value from REDIS.

        :param obj_type: Type of the object.
        :param id_: ID of the object.
        :param attribute: Attribute to be get.
        :return: the Attribute.
        """
        return self.connection.get(f"{obj_type}:{id_}:{attribute}")

    def push_list(self, owner: "ConnectionObject", list_name: str, obj: str, transform: Callable = None):
        """
        Push the object into the list, if transform is provided,
            transform the object with this method first.

        :param owner: List owner object.
        :param list_name: List that will hold the object.
        :param obj: Object to be pushed.
        :param transform: If provided object will be transformed first.
        """
        if transform:
            obj = transform(obj)
        self.connection.rpush(f"{owner.type_}:{owner.id_}:{list_name}", obj)

    def get_list(self, owner: "ConnectionObject", list_name: str, transform: Callable = None) -> list[Any]:
        """
        Get a list from the Redis KV store, if tranform is provided,
            transform the contents accordingly.

        :param owner: Owner of the list.
        :param list_name: Name of the list.
        :param transform: Transformation function to be applied,
            by default, None.
        :return: A list of object mapped to the transformation function,
            if it exists.
        """
        list_ = self.connection.lrange(f"{owner.type_}:{owner.id_}:{list_name}", 0, -1) # Get all elements.
        if transform:
            list_ = [transform(element) for element in list_]
        return list_

    def exists(self, key) -> bool:
        return self.connection.exists(key)

    def __contains__(self, item) -> bool:
        """
        Check if the given object exists in the KV store.

        :param item: Item to check for.
        :return: True if it is in Redis, False otherwise.
        """
        if not isinstance(item, ConnectionObject):
            return False
        return self.connection.exists(f"{item.type_}:{item.id_}")


class ConnectionObject:
    """
    Any object that is saved inside Redis KV.
    """
    connection_manager: ConnectionManager = ConnectionManager() # The global connection manager.

    def __init__(self, type_: str, id_: str, mapping: dict[str, str]):
        self.type_ = type_
        self.id_ = id_
        if self not in self.connection_manager: # If the item does not exist in the Redis
            self.connection_manager.create_obj(self.type_, self.id_, mapping) # Create it.

    def __getattr__(self, item):
        """
        Return an attribute of the User.
        :param item: Attribute to return.
        :return: The attribute
        """
        return self.connection_manager.get_from(self.type_, self.user_id, item)

    def __setattr__(self, key, value) -> None:
        """
        Set an attribute of the user.
        :param key: Name of the attribute.
        :param value: New value for the attribute.
        """
        self.connection_manager.modify(self.type_, self.id_, key, value)


class User(ConnectionObject):
    """
    A User class that is used to construct a user.
    """
    def __init__(self, user_id: str, username: str = "", portrait_name: str = "", player_role=PlayerState.UNASSIGNED):
        self.__dict__["user_id"] = user_id
        values = {"user_id": user_id,
                  "username": username,
                  "portrait_name": portrait_name,
                  "player_role": player_role}
        super().__init__('user', user_id, values)

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
            player_role = PlayerState.CAMPER  # Campers can't see changelings
            # Are changelings.
        return {
            "user_id": self.user_id,
            "name": self.username,
            "portraitName": self.portrait_name,
            "playerRole": player_role.value,
            "admin": admin,
        }


class Room(ConnectionObject):
    """
    Manages requests to get and modify Room objects
    between different threads using a Redis database
    residing in memory.
    """
    def __init__(self, room_id: str, admin: User = None) -> None:
        self.__dict__["room_id"] = room_id
        values = {
            "room_id": room_id,
            "admin": admin.user_id,
            "turn_state": GameState.LOBBY, # Initial condition.
            "turn": 0,
            "real_turn": 0,
            "turn_owner_index": 0
        }
        super().__init__('room', room_id, values)
        self.connection_manager.push_list(self, 'users', admin.user_id)

    def __getattr__(self, item) -> Any:
        # Get Attribute must be overriden
        # To deal with lists.
        if item in ['users', 'changelings']:
            return self.connection_manager.get_list(self, item, lambda e: User(e))
        return super().__getattr__(item)  # Otherwise call connection object's variation.

    @classmethod
    def generate_room_id(cls) -> str:
        """
        Generate a unique room ID.

        :return: a new room ID.
        """
        room_id = f"{hash(random()):X}"[0:6]  # Generate a random room ID.
        while cls.connection_manager.connection.exists(f"room:{room_id}"):  # Continue generating until no match in rooms.
            room_id = f"{hash(random()):X}"[0:6]
        return room_id

    @property
    def turn_owner(self) -> User:
        return self.users[self.turn_owner_index % 5]

    @turn_owner.setter
    def turn_owner(self, owner: User) -> None:
        self.turn_owner_index = self.users.index(owner)

    def assign_roles(self) -> User:
        """
        Assign player roles to players, one changeling,
            all others campers, initially.

        :return: the User that became the changeling.
        """
        for user in self.users:  # Initially make them all campers.
            user.player_role = PlayerState.CAMPER
        random_camper = choice(self.users)
        random_camper.player_role = PlayerState.CHANGELING  # Set random user to changeling.
        self.connection_manager.push_list(self, "changelings", random_camper.user_id)
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

    @classmethod
    def room_exists(cls, room_id: str) -> bool:
        """
        Check if a room exists in the REDIS.

        :param cls: Class itself.
        :param room_id: ID of the Room.
        :return: If the room exists.
        """
        return cls.connection_manager.exists(f"room:{room_id}")

    def add_player(self, user: User) -> None:
        """
        Add a player to the room.

        :param user: User to add.
        """
        self.connection_manager.push_list(self, 'users', user.id_)

    def add_changeling(self, user: User) -> None:
        """
        Add a changeling to the room.

        :param user: User to add.
        """
        self.connection_manager.push_list(self, 'changelings', user.id_)


