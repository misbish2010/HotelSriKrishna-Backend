from flask import Blueprint, request, abort, jsonify
from flask_login import current_user
from functools import wraps
from flask_bcrypt import generate_password_hash
from model import model_routes

admin_bp = Blueprint(
    'admin_bp', __name__,
    template_folder='templates',
    static_folder='static'
)


# ─── Auth guard ───────────────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# ─── User Management ──────────────────────────────────────────────────────────

@admin_bp.route('/api/add_user', methods=['POST'])
@admin_required  # FIX: was missing — anyone could create users before
def signup_user():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    is_admin = data.get('isAdmin', False)

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    if model_routes.User.query.filter_by(username=username).first():
        return jsonify({'error': 'User already exists'}), 400

    hashed_password = generate_password_hash(password).decode('utf-8')
    model_routes.db.session.add(
        model_routes.User(username=username, password=hashed_password, is_admin=is_admin)
    )
    model_routes.db.session.commit()
    return jsonify({'message': 'User created successfully'}), 201


@admin_bp.route('/api/update_user_password', methods=['POST'])
@admin_required  # FIX: was missing — anyone could reset any password before
def update_user_password():
    data = request.get_json()
    username    = data.get('username', '').strip()
    new_password = data.get('newPassword', '')

    if not username or not new_password:
        return jsonify({'error': 'Username and new password are required'}), 400

    user = model_routes.User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    user.password = generate_password_hash(new_password).decode('utf-8')
    model_routes.db.session.commit()
    return jsonify({'message': 'Password updated successfully'}), 200


@admin_bp.route('/api/get_users', methods=['GET'])
@admin_required
def get_users():
    users = model_routes.User.query.all()
    return jsonify([
        {'id': u.id, 'username': u.username, 'is_admin': u.is_admin}
        for u in users
    ]), 200


@admin_bp.route('/api/delete_user/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    user = model_routes.User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    # Prevent deleting yourself
    if user.id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    model_routes.db.session.delete(user)
    model_routes.db.session.commit()
    return jsonify({'message': f'User {user.username} deleted'}), 200


# ─── Staff Management ─────────────────────────────────────────────────────────

@admin_bp.route('/api/register_staff', methods=['POST'])
@admin_required
def register_staff():
    data = request.get_json()
    name   = data.get('name', '').strip()
    phone  = data.get('phone', '').strip()
    role   = data.get('role', '').strip()
    salary = data.get('salary')

    if not all([name, phone, role, salary]):
        return jsonify({'error': 'All fields are required'}), 400

    if model_routes.Staff.query.filter_by(name=name, phone=phone).first():
        return jsonify({'error': 'Staff already exists'}), 400

    model_routes.db.session.add(
        model_routes.Staff(name=name, phone=phone, role=role, salary=salary)
    )
    model_routes.db.session.commit()
    return jsonify({'message': 'Staff registered successfully'}), 201


@admin_bp.route('/api/get_staff', methods=['GET'])
@admin_required
def get_staff():
    staff = model_routes.Staff.query.order_by(model_routes.Staff.name).all()
    return jsonify([
        {'id': s.id, 'name': s.name, 'role': s.role, 'phone': s.phone, 'salary': s.salary}
        for s in staff
    ]), 200


@admin_bp.route('/api/update_staff/<int:staff_id>', methods=['PUT'])
@admin_required
def update_staff(staff_id):
    staff = model_routes.Staff.query.get(staff_id)
    if not staff:
        return jsonify({'error': 'Staff not found'}), 404

    data = request.get_json()
    staff.name   = data.get('name',   staff.name)
    staff.phone  = data.get('phone',  staff.phone)
    staff.role   = data.get('role',   staff.role)
    staff.salary = data.get('salary', staff.salary)

    model_routes.db.session.commit()
    return jsonify({'message': 'Staff updated successfully'}), 200


@admin_bp.route('/api/delete_staff/<int:staff_id>', methods=['DELETE'])
@admin_required
def delete_staff(staff_id):
    staff = model_routes.Staff.query.get(staff_id)
    if not staff:
        return jsonify({'error': 'Staff not found'}), 404
    model_routes.db.session.delete(staff)
    model_routes.db.session.commit()
    return jsonify({'message': f'{staff.name} removed'}), 200


# ─── Room Management ──────────────────────────────────────────────────────────

@admin_bp.route('/api/get_rooms', methods=['GET'])
@admin_required
def get_rooms():
    """Get all room configs, grouped by room_number for easy display."""
    rooms = model_routes.Room.query.order_by(
        model_routes.Room.room_number, model_routes.Room.is_ac, model_routes.Room.occupancy
    ).all()
    return jsonify([
        {
            'id':               r.id,
            'room_number':      r.room_number,
            'room_type':        r.room_type,
            'occupancy':        r.occupancy,
            'is_ac':            r.is_ac,
            'price_per_night':  r.price_per_night,
            'extra_bed_price':  r.extra_bed_price,
        }
        for r in rooms
    ]), 200


@admin_bp.route('/api/room_add', methods=['POST'])
@admin_required
def register_room():
    data = request.get_json()
    room_number     = data.get('roomNumber')
    room_type       = data.get('roomType')
    occupancy       = data.get('occupancy')
    is_ac           = data.get('isAcRoom')
    price_per_night = data.get('pricePerNight')
    extra_bed_price = data.get('extraBedPrice')

    if model_routes.Room.query.filter_by(
        room_number=room_number, room_type=room_type,
        is_ac=is_ac, occupancy=occupancy
    ).first():
        return jsonify({'error': 'Room already registered'}), 400

    model_routes.db.session.add(model_routes.Room(
        room_number=room_number, room_type=room_type,
        occupancy=occupancy, is_ac=is_ac,
        price_per_night=price_per_night, extra_bed_price=extra_bed_price
    ))
    model_routes.db.session.commit()
    return jsonify({'message': 'Room created successfully'}), 201


@admin_bp.route('/api/update_room_price', methods=['PUT'])
@admin_required
def update_room_price():
    """
    Update price for all rooms of a given category.
    { roomType: "Studio", occupancy: "Double", isAcRoom: true,
      pricePerNight: 1600, extraBedPrice: 300 }
    """
    data            = request.get_json()
    room_type       = data.get('roomType')
    occupancy       = data.get('occupancy')
    is_ac           = data.get('isAcRoom')
    price_per_night = data.get('pricePerNight')
    extra_bed_price = data.get('extraBedPrice')

    if not all([room_type, occupancy, is_ac is not None, price_per_night is not None]):
        return jsonify({'error': 'roomType, occupancy, isAcRoom and pricePerNight are required'}), 400

    rooms = model_routes.Room.query.filter_by(
        room_type=room_type, occupancy=occupancy, is_ac=is_ac
    ).all()
    if not rooms:
        return jsonify({'error': 'No rooms found for that category'}), 404

    for room in rooms:
        room.price_per_night = price_per_night
        if extra_bed_price is not None:
            room.extra_bed_price = extra_bed_price
    model_routes.db.session.commit()
    return jsonify({
        'message': f'Price updated for {len(rooms)} room(s) '
                   f'({room_type}, {occupancy}, {"AC" if is_ac else "Non-AC"})'
    }), 200


@admin_bp.route('/api/delete_room/<int:room_id>', methods=['DELETE'])
@admin_required
def delete_room(room_id):
    """Delete a single room config row by its DB id."""
    room = model_routes.Room.query.get(room_id)
    if not room:
        return jsonify({'error': 'Room not found'}), 404

    # Safety: block delete if active bookings exist for this room
    active = model_routes.BookingRoom.query.filter_by(room_id=room_id).first()
    if active:
        return jsonify({
            'error': 'Cannot delete room — it has booking history. '
                     'Deactivate it instead or remove bookings first.'
        }), 400

    model_routes.db.session.delete(room)
    model_routes.db.session.commit()
    return jsonify({'message': f'Room {room.room_number} config deleted'}), 200


@admin_bp.route('/api/delete_room_by_number/<room_number>', methods=['DELETE'])
@admin_required
def delete_room_by_number(room_number):
    """Delete all config rows for a room number e.g. DELETE /api/delete_room_by_number/000"""
    rooms = model_routes.Room.query.filter_by(room_number=room_number).all()
    if not rooms:
        return jsonify({'error': f'Room {room_number} not found'}), 404

    deleted = 0
    skipped = 0
    for room in rooms:
        has_bookings = model_routes.BookingRoom.query.filter_by(room_id=room.id).first()
        if has_bookings:
            skipped += 1
            continue
        model_routes.db.session.delete(room)
        deleted += 1

    model_routes.db.session.commit()

    if skipped:
        return jsonify({
            'message': f'Deleted {deleted} config(s) for room {room_number}. '
                       f'Skipped {skipped} — they have booking history.'
        }), 200

    return jsonify({'message': f'All {deleted} config(s) for room {room_number} deleted'}), 200


@admin_bp.route('/api/convert_to_ac_room', methods=['PUT'])
@admin_required
def convert_to_ac_room():
    data        = request.get_json()
    room_number = data.get('roomNumber')
    rooms       = model_routes.Room.query.filter_by(room_number=room_number).all()

    if not rooms:
        return jsonify({'error': 'Room not found'}), 404

    already_ac = [r for r in rooms if r.is_ac]
    if len(already_ac) == len(rooms):
        return jsonify({'error': 'Room is already fully AC'}), 400

    for room in rooms:
        if not room.is_ac:
            room.is_ac           = True
            room.price_per_night = round(room.price_per_night + 300.0, 2)
    model_routes.db.session.commit()
    return jsonify({'message': f'Room {room_number} converted to AC'}), 200


# ─── Bulk room setup (first-time only) ───────────────────────────────────────

@admin_bp.route('/api/room_add_first_time', methods=['POST'])
@admin_required
def register_room_bulk():
    rooms = [
        {"room_number": "001", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "001", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        {"room_number": "002", "occupancy": "Single",  "room_type": "Studio", "is_ac": False, "price_per_night": 1100.0, "extra_bed_price": 300.0},
        {"room_number": "002", "occupancy": "Double",  "room_type": "Studio", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "003", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "003", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        {"room_number": "101", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "101", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        {"room_number": "102", "occupancy": "Single",  "room_type": "Studio", "is_ac": False, "price_per_night": 1100.0, "extra_bed_price": 300.0},
        {"room_number": "102", "occupancy": "Double",  "room_type": "Studio", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "103", "occupancy": "Triple",  "room_type": "Triple", "is_ac": False, "price_per_night": 1700.0, "extra_bed_price": 300.0},
        {"room_number": "104", "occupancy": "Single",  "room_type": "Studio", "is_ac": False, "price_per_night": 1100.0, "extra_bed_price": 300.0},
        {"room_number": "104", "occupancy": "Double",  "room_type": "Studio", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "105", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "105", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        {"room_number": "201", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "201", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        {"room_number": "202", "occupancy": "Single",  "room_type": "Studio", "is_ac": False, "price_per_night": 1100.0, "extra_bed_price": 300.0},
        {"room_number": "202", "occupancy": "Double",  "room_type": "Studio", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "203", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "203", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        {"room_number": "204", "occupancy": "Single",  "room_type": "Studio", "is_ac": False, "price_per_night": 1100.0, "extra_bed_price": 300.0},
        {"room_number": "204", "occupancy": "Double",  "room_type": "Studio", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "205", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "205", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        {"room_number": "301", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "301", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        {"room_number": "302", "occupancy": "Single",  "room_type": "Studio", "is_ac": False, "price_per_night": 1100.0, "extra_bed_price": 300.0},
        {"room_number": "302", "occupancy": "Double",  "room_type": "Studio", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "303", "occupancy": "Triple",  "room_type": "Triple", "is_ac": False, "price_per_night": 1700.0, "extra_bed_price": 300.0},
        {"room_number": "304", "occupancy": "Single",  "room_type": "Studio", "is_ac": False, "price_per_night": 1100.0, "extra_bed_price": 300.0},
        {"room_number": "304", "occupancy": "Double",  "room_type": "Studio", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "305", "occupancy": "Single",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1300.0, "extra_bed_price": 300.0},
        {"room_number": "305", "occupancy": "Double",  "room_type": "Luxury", "is_ac": False, "price_per_night": 1500.0, "extra_bed_price": 300.0},
        # AC rooms
        {"room_number": "001", "occupancy": "Single",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "001", "occupancy": "Double",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1800.0, "extra_bed_price": 300.0},
        {"room_number": "101", "occupancy": "Single",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "101", "occupancy": "Double",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1800.0, "extra_bed_price": 300.0},
        {"room_number": "201", "occupancy": "Single",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "201", "occupancy": "Double",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1800.0, "extra_bed_price": 300.0},
        {"room_number": "203", "occupancy": "Single",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "203", "occupancy": "Double",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1800.0, "extra_bed_price": 300.0},
        {"room_number": "205", "occupancy": "Single",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "205", "occupancy": "Double",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1800.0, "extra_bed_price": 300.0},
        {"room_number": "301", "occupancy": "Single",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "301", "occupancy": "Double",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1800.0, "extra_bed_price": 300.0},
        {"room_number": "303", "occupancy": "Triple",  "room_type": "Triple", "is_ac": True,  "price_per_night": 2000.0, "extra_bed_price": 300.0},
        {"room_number": "305", "occupancy": "Single",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "305", "occupancy": "Double",  "room_type": "Luxury", "is_ac": True,  "price_per_night": 1800.0, "extra_bed_price": 300.0},
        {"room_number": "304", "occupancy": "Single",  "room_type": "Studio", "is_ac": True,  "price_per_night": 1400.0, "extra_bed_price": 300.0},
        {"room_number": "304", "occupancy": "Double",  "room_type": "Studio", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "302", "occupancy": "Single",  "room_type": "Studio", "is_ac": True,  "price_per_night": 1400.0, "extra_bed_price": 300.0},
        {"room_number": "302", "occupancy": "Double",  "room_type": "Studio", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "204", "occupancy": "Single",  "room_type": "Studio", "is_ac": True,  "price_per_night": 1400.0, "extra_bed_price": 300.0},
        {"room_number": "204", "occupancy": "Double",  "room_type": "Studio", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
        {"room_number": "202", "occupancy": "Single",  "room_type": "Studio", "is_ac": True,  "price_per_night": 1400.0, "extra_bed_price": 300.0},
        {"room_number": "202", "occupancy": "Double",  "room_type": "Studio", "is_ac": True,  "price_per_night": 1600.0, "extra_bed_price": 300.0},
    ]

    added = 0
    for room_data in rooms:
        exists = model_routes.Room.query.filter_by(
            room_number=room_data["room_number"],
            room_type=room_data["room_type"],
            is_ac=room_data["is_ac"],
            occupancy=room_data["occupancy"]
        ).first()
        if exists:
            continue
        model_routes.db.session.add(model_routes.Room(**room_data))
        added += 1

    model_routes.db.session.commit()
    return jsonify({'message': f'{added} rooms added successfully'}), 201
