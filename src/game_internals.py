from enum import Enum
from random import random, choice
from json import dumps
from typing import Any, Callable, Optional
from redis import Redis
from .configs import REDIS_CONFIG


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


def get_game_state_from_player(player_type: PlayerState) -> GameState:
    """
    Given the player type that won, return the
        GameState that will be set.

    :param player: Player type that won.
    :return: Game state to set.
    """
    return {PlayerState.CHANGELING: GameState.CHANGELING_VICTORY,
            PlayerState.CAMPER: GameState.CAMPER_VICTORY}[player_type]


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
        self.connection = Redis(host=REDIS_CONFIG.hostname, port=REDIS_CONFIG.port,
                                username=REDIS_CONFIG.username, password=REDIS_CONFIG.password,
                                db=0, decode_responses=True)

    def create_obj(self, object_: "ConnectionObject", mapping: dict[str, str], suffix: str = "") -> None:
        """
        Create an object of given type.

        :param object_: Owner of the mapping.
        :param mapping: KV pairs for the object.
        :param suffix: Object suffix to follow after id.
        :return:
        """
        key = f"{object_.type_}:{object_.id_}"
        if suffix:
            key += f":{suffix}"
        self.connection.hmset(key, mapping)

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
        val = self.connection.hget(f"{obj_type}:{id_}", attribute)
        if isinstance(val, bytes):
            val = val.decode(encoding='utf-8') # Convert to string.
        return val

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
        """
        Check if a certain key exists in Redis KV store.
        :param key: Key to check for.
        :return: True if the key exists.
        """
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

    def increment(self, object_: "ConnectionObject", attribute: str, suffix: str = "") -> None:
        """
        Increment an attribute of an object in the
            KV store.

        :param object_: Object that owns the attribute.
        :param attribute: Attribute to increment.
        :param suffix: Suffix of the object to be added after type, if exists.
        """
        key = f"{object_.type_}:{object_.id_}"
        if suffix:
            key += f":{suffix}"  # Add suffix if exists.
        self.connection.hincrby(key, attribute, 1)

    def get_dict(self, object_: "ConnectionObject", suffix: str) -> dict[str, Any]:
        """
        Get a hash object as a dictionary.

        :param object_: Object that owns the hash.
        :param suffix: Suffix of the hash.
        :return: The hash object as a dictionary.
        """
        dict_ = self.connection.hgetall(f"{object_.type_}:{object_.id_}:{suffix}")
        return dict_

    def remove_element_from_list(self, object_: "ConnectionObject", suffix: str, element: str) -> None:
        """
        Remove a string from a list.

        :param object_: Object that owns the list.
        :param suffix: Name of the list.
        :param element: Element to remove
        :return: None.
        """
        self.connection.lrem(f"{object_.type_}:{object_.id_}:{suffix}", 0, element)  # Remove the element from the list.


class ConnectionObject:
    """
    Any object that is saved inside Redis KV.
    """
    connection_manager: ConnectionManager = ConnectionManager() # The global connection manager.

    def __init__(self, type_: str, id_: str, mapping: dict[str, str]):
        self.__dict__["type_"] = type_
        self.__dict__["id_"] = id_
        self.__dict__["cache"] = {}  # Create a cache.
        if self not in self.connection_manager:  # If the item does not exist in the Redis
            self.connection_manager.create_obj(self, mapping)  # Create it.

    def __getattr__(self, item):
        """
        Return an attribute of the User.
        :param item: Attribute to return.
        :return: The attribute
        """
#        if item in (cache := self.__dict__["cache"]) and (val := cache[item]) is not None:  # Check if it is in cache.
#            return val
        value = self.connection_manager.get_from(self.type_, self.id_, item)
        self.__dict__['cache'][item] = value  # Cache it if it is not.
        return value

    def __setattr__(self, key, value) -> None:
        """
        Set an attribute of the user.
        :param key: Name of the attribute.
        :param value: New value for the attribute.
        """
        store_value = value # Value to be stored.
        if isinstance(value, Enum): # If value is enum
            store_value = value.value # String version of the enum.
        elif isinstance(value, User):
            store_value = value.user_id
        self.connection_manager.modify(self.type_, self.id_, key, store_value)
        self.__dict__["cache"][key] = value  # Cache the change, the enum version if it is enum..


class User(ConnectionObject):
    """
    A User class that is used to construct a user.
    """
    def __init__(self, user_id: str, username: str = "", portrait_name: str = "", player_role=PlayerState.UNASSIGNED):
        self.__dict__["user_id"] = user_id
        values = {
            "user_id": user_id,
            "username": username,
            "portrait_name": portrait_name,
            "player_role": player_role.value
                  }
        super().__init__('user', user_id, values)

    def __eq__(self, other) -> bool:
        if type(self) != type(other):
            return False
        return self.user_id == other.user_id

    def __getattr__(self, item) -> Any:
        # Get Attribute must be overriden
        # To deal with enums.
        if item == 'player_role':
            return PlayerState(super().__getattr__('player_role'))
        return super().__getattr__(item)  # Otherwise call connection object's variation.

    def get_player_data(self, admin: bool = False, show_changeling: bool = False):
        """
        Get JSON serializable player data.

        :param admin: true if the user is admin.
        :param show_changeling: If false, changelings are shown as
            campers.
        :return: JSON serializable player data as dict.
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
            "admin": admin.user_id if admin else '',
            "turn_state": GameState.LOBBY.value,  # Initial condition.
            "turn": 0,
            "real_turn": 0,
            "turn_owner_index": 0
        }
        self.__dict__['special_attributes'] = {  # Dictionary that holds attributes that must be converted.
            'admin': User,
            'turn_state': lambda s: GameState(int(s)),
            'turn': int,
            'users_voted': int
        }
        super().__init__('room', room_id, values)
        if admin:  # If just initialised.
            self.connection_manager.push_list(self, 'users', admin.user_id)

    def __getattr__(self, item) -> Any:
        # Get Attribute must be overriden
        # To deal with lists and enums.
        if item in ['users', 'changelings']:
            return self.connection_manager.get_list(self, item, lambda e: User(e))
        elif item in self.__dict__['special_attributes']:
            return self.__dict__['special_attributes'][item](super().__getattr__(item))  # Convert it into the right type.
        return super().__getattr__(item)  # Otherwise call connection object's variation.

    def __setattr__(self, key, value) -> None:
        # Setattr is overridden to set
        # the turn_owner since properties are
        # overriden by the parent setattr.
        if key == 'turn_owner':
            users = self.users
            self.turn_owner_index = self.users.index(value)
        else:
            super().__setattr__(key, value)

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
        users_list = self.connection_manager.get_list(self, 'users', lambda e: User(e))
        return users_list[int(self.turn_owner_index) % len(users_list)]

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

    def get_game_state(self):
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

    def set_up_voting(self) -> None:
        """
        Set up the voting objects.
        """
        users: list[User] = self.users
        mapping = {user.user_id: 0 for user in users}  # Create the voting map
        self.connection_manager.create_obj(self, mapping, "user_votes")  # Generate the voting object.

    def cast_vote(self, user_id) -> None:
        """
        Cast a vote to burn a particular user.

        :param user_id: ID of the user voted to be burned
        """
        self.connection_manager.increment(self, user_id, 'user_votes')  # Increment vote count for a user.
        self.connection_manager.increment(self, 'users_voted')  # Increment the number of users who have voted.

    def has_all_voted(self) -> bool:
        """
        Return true if all the users have voted.

        :return: true if all users voted, false otherwise.
        """
        users = self.users
        number_of_living = sum(user.player_role != PlayerState.DEAD for user in users)
        return self.users_voted == self.number_of_living

    def tally_votes(self) -> User:
        """
        Tally the votes and return the user that
            has the maximum amount of votes.

        :return: The user with the maximum amount of
            votes.
        """
        votes = self.connection_manager.get_dict(self, 'user_votes')
        tuples: list[tuple[str, Any]] = [*votes.items()]  # Convert it into a list of KV pair tuples for sorting.
        tuples.sort(key=lambda kv_pair: kv_pair[1], reverse=True)
        return User(tuples[0][0])

    def burn_player(self, player: User) -> None:
        """
        Burn a player character by converting their role
            to dead.

        :param player:
        :return:
        """
        player.player_role = PlayerState.DEAD  # Set player to dead.
        # There is a chance that the player is also changeling,
        # Therefore we need to remove it if it is.
        changelings = self.changelings
        if player in changelings:
            self.connection_manager.remove_element_from_list(self, 'changelings', player.id_)

    def get_winner(self) -> Optional[PlayerState]:
        """
        Return the winner of the game, if there is any.

        :return: Either camper or changeling, or None if there is no victory.
        """
        changeling_count = len(self.changelings)  # Get the count of changelings.
        if changeling_count > self.number_of_living:  # If the changelings are in a majority.
            return PlayerState.CHANGELING  # Then the changelings won.
        elif self.turn > 40 or not changeling_count:  # If the daylight came or all changelings died.
            return PlayerState.CAMPER  # Then the campers won.
        else:  # Otherwise
            return None  # Then no one won.

    def next_turn(self, progress: bool = False) -> GameState:
        """
        Proceed to the next turn decide if it should be a special turn.

        :param progress: When set to true, do not roll dice for special
            turns.
        :return: The state the turn is in after progressing.
        """
        self.connection_manager.increment(self, 'real_turn')  # This is updated no matter what.
        if winner := self.get_winner():
            self.turn_state = winner
        elif not progress and self.turn != 0 and self.turn % 5 == 0:  # If turn is divisible by five
            # In special turn we either burn a camper or create a changeling.
            self.turn_state = choice([GameState.BURN_CAMPER, GameState.BURN_CAMPER, GameState.BURN_CAMPER])
            if self.turn_state == GameState.BURN_CAMPER:
                self.set_up_voting()
        else:  # Also triggers when progress.
            self.connection_manager.increment(self, 'turn')
            self.connection_manager.increment(self, 'turn_owner_index')
            self.turn_state = GameState.NORMAL
        return self.turn_state

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