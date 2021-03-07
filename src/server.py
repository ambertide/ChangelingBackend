# Websockets server for the Changeling.
from flask import Flask, session, request, g
from json import dumps, loads
from flask_socketio import SocketIO, join_room, rooms
from dataclasses import dataclass
from enum import Enum
from game_internals import GameRoom, User, GameState, PlayerState, RoomConnectionManager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!' # This will obviously change on production.
socketio = SocketIO(app, cors_allowed_origins="*")
room_manager = RoomConnectionManager(host="localhost", port=6379, db=0)
app.config['MAX_USERS_PER_ROOM'] = 5

def emit_error(err_type: str) -> None:
    """
    Send an error message to the client.

    :param err_type: Error type.
    """
    socketio.emit("error_occured", dumps({
        "err_type": err_type
    }))


@socketio.on("req_host_game")
def host_game(data: str) -> None:
    """
    Listens for requests to host a game.

    :param data:
    :return:
    """
    payload: dict[str, str] = loads(data)
    if len(rooms()) > 2:  # User can at most be in one room at any given time.
        emit_error("err_already_joined")
        return
    user_id = request.sid
    new_user = User(user_id, payload["name"], payload["portrait"])
    room_id = room_manager.generate_room_id()  # Generate new room id.
    new_room = GameRoom(room_id, new_user, [new_user, ], [],
                        {new_user.user_id: PlayerState.UNASSIGNED}, 0,
                        GameState.LOBBY)
    room_manager[room_id] = new_room  # Add room to the room "list".
    join_room(room_id)  # Actually join the room.
    session["user_obj"] = new_user # Set the user object.
    socketio.emit("resp_ack_host", dumps({"room_id": room_id, **new_user.get_player_data(is_you=True, admin=True)}))


def sync_user_info_first_join(room_id: str) -> None:
    """
    Sync up the user info after user first joins the game,
        send already existing data to this user and get data
        of other users for this user.

    :param room_id: ID number of the room.
    """
    room = room_manager[room_id]
    this_user: User = session["user_obj"]  # Get the user object for this user.
    users = room.users  # Get all users in our room.
    other_users = [user for user in users if user != this_user]
    socketio.emit("resp_player_join", dumps(this_user.get_player_data(is_you=True)), room=this_user.user_id) # Announce the player to themselves.
    for user in other_users:
        # Announce the new user to other players
        socketio.emit("resp_player_join", dumps(this_user.get_player_data()), room=user.user_id)
        # Announce other players to the new player
        socketio.emit("resp_player_join", dumps(user.get_player_data()), room=this_user.user_id)


@socketio.on("req_join_game")
def join_game(data):
    payload: dict[str, str] = loads(data)
    if len(rooms()) > 2:
        emit_error("err_already_joined")
        return
    user_id = request.sid
    new_user = User(user_id, payload["name"], payload["portrait"])
    room_id = payload["roomID"]
    if room_id not in room_manager:
        emit_error("err_room_not_found")
        return
    room = room_manager[room_id] # Get the room object.
    if len(room.users) >= app.config["MAX_USERS_PER_ROOM"]:
        emit_error("err_user_limit")
        return
    room.users.append(new_user)
    socketio.emit("resp_ack_join", dumps({"roomID": room_id}))  # Acknowledge game join
    session["user_obj"] = new_user
    room_manager[room_id] = room
    join_room(room_id)
    sync_user_info_first_join(room_id)
    return ""

@socketio.on("message")
def general_msg(data):
    print("Message")
    return ""

if __name__ == '__main__':
    socketio.run(app,  debug=True)