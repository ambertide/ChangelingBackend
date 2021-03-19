# Websockets server for the Changeling.
from flask import Flask, session, request, g
from json import dumps, loads
from flask_socketio import SocketIO, join_room, rooms
from game_internals import User, GameState, PlayerState, Room


app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!' # This will obviously change on production.
socketio = SocketIO(app, cors_allowed_origins="*")
app.config['MAX_USERS_PER_ROOM'] = 5


def sync_room_state(room_id: str) -> None:
    """
    Sync the room state across the players in the room.

    :param room_id: ID of the room to sync.
    :return:
    """
    room = Room(room_id)  # Get the room.
    payload = dumps(room.get_game_state())
    socketio.emit("resp_sync_gamestate", payload,
                  room=room_id)  # Emit the new game state to all members of the room.
    sync_user_states(room_id)


def sync_user_states(room_id: str) -> None:
    """
    Sync the state of the users within a given room.
        changelings must be handled seperately as they
        can see each other while normal users cannot
        see their status.

    :param room_id: ID of the room to sync.
    :return: None
    """
    room = Room(room_id)
    normal_users = [user for user in room.users if user not in room.changelings]
    camper_view = room.get_user_states(False)  # View the campers see.
    changeling_view = room.get_user_states(True)  # View the changelings see.
    for user in normal_users:
        socketio.emit('resp_sync_players', camper_view, room=user.user_id)
    for user in room.changelings:
        socketio.emit('resp_sync_players', changeling_view, room=user.user_id)


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
    new_user = User(user_id, payload["name"], payload["portrait"], player_role=PlayerState.UNASSIGNED)
    room_id = Room.generate_room_id()  # Generate new room id.
    new_room = Room(room_id, new_user)
    new_room.turn_owner = new_user  # Set the admin as the current turn owner.
    join_room(room_id)  # Actually join the room.
    session["user_room"] = room_id
    session["user_obj"] = new_user  # Set the user object.
    socketio.emit("resp_ack_host", dumps({"room_id": room_id, **new_user.get_player_data(admin=True)}))


@socketio.on("req_join_game")
def join_game(data) -> None:
    """
    When a player requests to join the game check if it is eligible
        and add the player to the necessary room.

    :param data: Payload of the request.
    :return: None.
    """
    payload: dict[str, str] = loads(data)
    if len(rooms()) > 2:
        emit_error("err_already_joined")
        return
    user_id = request.sid
    new_user = User(user_id, payload["name"], payload["portrait"])
    room_id = payload["roomID"]
    if not Room.room_exists(room_id):
        emit_error("err_room_not_found")
        return
    room = Room(room_id) # Get the room object.
    if len(room.users) >= app.config["MAX_USERS_PER_ROOM"]:
        emit_error("err_user_limit")
        return
    room.add_player(new_user)
    socketio.emit("resp_ack_join", dumps({"roomID": room_id, "player": new_user.get_player_data()}), room=user_id)  # Acknowledge game join
    session["user_obj"] = new_user
    session["user_room"] = room_id
    join_room(room_id)
    sync_user_states(room_id)


@socketio.on("req_start_game")
def start_game() -> None:
    """
    Answer to the request of starting the game.
    """
    user, room_id = session['user_obj'], session['user_room']  # Get the current user and room id.
    room = Room(room_id)  # Get the room object from the room manager.
    room.turn_state = GameState.NORMAL  # Start the game.
    room.turn = 40
    room.turn_owner = room.users[0]
    selected_user = room.assign_roles()
    if selected_user == session['user_obj']:  # If our player turned.
        session['user_obj'] = selected_user  # Update its state.
    socketio.emit("resp_ack_start", room=room_id)  # Send start signal.
    sync_room_state(room_id)  # Synchronise the room state.


@socketio.on("req_next_turn")
def next_turn() -> None:
    """
    Answer to the request to progress to
        the next turn.
    """
    user, room = session['user_obj'], Room(session['user_room'])
    if user != room.turn_owner:
        emit_error("err_user_not_owner")  # User does not have the permission for this!
    else:
        room.next_turn()
        sync_room_state(session['user_room'])  # Sync the room state.


if __name__ == '__main__':
    socketio.run(app,  debug=True)