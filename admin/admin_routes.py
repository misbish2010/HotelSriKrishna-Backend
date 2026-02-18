from flask import Blueprint, request, abort, jsonify
from flask_login import current_user
from functools import wraps
from flask_bcrypt import generate_password_hash
from model import model_routes


# Defining a blueprint
admin_bp = Blueprint(
    'admin_bp', __name__,
    template_folder='templates',
    static_folder='static'
)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)  # Forbidden access
        return f(*args, **kwargs)

    return decorated_function


@admin_bp.route('/api/add_user', methods=['POST'])
def signup_user():
    data = request.get_json()
    username = data['username']
    password = data['password']
    is_admin = data['isAdmin']
    hashed_password = generate_password_hash(password).decode('utf-8')
    user = model_routes.User.query.filter_by(username=username).first()
    if user:
        return jsonify({'error': 'User already exists'}), 400

    new_user = model_routes.User(username=username, password=hashed_password, is_admin=is_admin)
    model_routes.db.session.add(new_user)
    model_routes.db.session.commit()

    return jsonify({'message': 'User created successfully'}), 201


@admin_bp.route('/api/update_user_password', methods=['POST'])
def update_user_password():
    data = request.get_json()

    username = data.get('username')
    new_password = data.get('newPassword')

    if not username or not new_password:
        return jsonify({'error': 'Username and new password are required'}), 400

    user = model_routes.User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    hashed_password = generate_password_hash(new_password).decode('utf-8')
    user.password = hashed_password

    model_routes.db.session.commit()

    return jsonify({'message': 'Password updated successfully'}), 200


@admin_bp.route('/api/register_staff', methods=['POST'])
@admin_required
def register_staff():
    data = request.get_json()
    name = data['name']
    phone = data['phone']
    role = data['role']
    salary = data['salary']

    staff = model_routes.Staff.query.filter_by(name=name, phone=phone).first()

    if staff:
        return jsonify({'error': 'Staff already exists'}), 400

    new_staff = model_routes.Staff(name=name, phone=phone, role=role, salary=salary)
    model_routes.db.session.add(new_staff)
    model_routes.db.session.commit()
    return jsonify({'message': 'Staff Registered successfully'}), 201


@admin_bp.route('/api/room_add', methods=['POST'])
@admin_required
def register_room():
    data = request.get_json()
    room_number = data['roomNumber']
    room_type = data['roomType']
    occupancy = data['occupancy']
    is_ac = data['isAcRoom']
    price_per_night = data['pricePerNight']
    extra_bed_price = data['extraBedPrice']
    room = model_routes.Room.query.filter_by(room_number=room_number, room_type=room_type, is_ac=is_ac,
                                             occupancy=occupancy).first()
    if room:
        return jsonify({'error': 'Room is already registered'}), 400

    room = model_routes.Room(
        room_number=room_number,
        room_type=room_type,
        occupancy=occupancy,
        is_ac=is_ac,
        price_per_night=price_per_night,
        extra_bed_price=extra_bed_price
    )

    model_routes.db.session.add(room)
    model_routes.db.session.commit()

    return jsonify({'message': 'Room created successfully'}), 201


@admin_bp.route('/api/room_add_first_time', methods=['POST'])
@admin_required
def register_room_():
    rooms = [
        {"room_number": "000", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 00.0,
         "extra_bed_price": 300.0},
        {"room_number": "000", "occupancy": "Double", "room_type": "Studio", "is_ac": False, "price_per_night": 00.0,
         "extra_bed_price": 300.0},
        {"room_number": "000", "occupancy": "Single", "room_type": "Triple", "is_ac": False, "price_per_night": 00.0,
         "extra_bed_price": 300.0},
        {"room_number": "000", "occupancy": "Single", "room_type": "Luxury", "is_ac": True, "price_per_night": 00.0,
         "extra_bed_price": 300.0},
        {"room_number": "000", "occupancy": "Double", "room_type": "Studio", "is_ac": True, "price_per_night": 00.0,
         "extra_bed_price": 300.0},
        {"room_number": "000", "occupancy": "Single", "room_type": "Triple", "is_ac": True, "price_per_night": 00.0,
         "extra_bed_price": 300.0},

        {"room_number": "001", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "001", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "002", "occupancy": "Single", "room_type": "Studio", "is_ac": False, "price_per_night": 1200.0,
         "extra_bed_price": 300.0},
        {"room_number": "002", "occupancy": "Double", "room_type": "Studio", "is_ac": False, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "003", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "003", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "101", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "101", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "102", "occupancy": "Single", "room_type": "Studio", "is_ac": False, "price_per_night": 1200.0,
         "extra_bed_price": 300.0},
        {"room_number": "102", "occupancy": "Double", "room_type": "Studio", "is_ac": False, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "103", "occupancy": "Triple", "room_type": "Triple", "is_ac": False, "price_per_night": 1900.0,
         "extra_bed_price": 300.0},
        {"room_number": "104", "occupancy": "Single", "room_type": "Studio", "is_ac": False, "price_per_night": 1200.0,
         "extra_bed_price": 300.0},
        {"room_number": "104", "occupancy": "Double", "room_type": "Studio", "is_ac": False, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "105", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "105", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "201", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "201", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "202", "occupancy": "Single", "room_type": "Studio", "is_ac": False, "price_per_night": 1200.0,
         "extra_bed_price": 300.0},
        {"room_number": "202", "occupancy": "Double", "room_type": "Studio", "is_ac": False, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "203", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "203", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "204", "occupancy": "Single", "room_type": "Studio", "is_ac": False, "price_per_night": 1200.0,
         "extra_bed_price": 300.0},
        {"room_number": "204", "occupancy": "Double", "room_type": "Studio", "is_ac": False, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "205", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "205", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "301", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "301", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "302", "occupancy": "Single", "room_type": "Studio", "is_ac": False, "price_per_night": 1200.0,
         "extra_bed_price": 300.0},
        {"room_number": "302", "occupancy": "Double", "room_type": "Studio", "is_ac": False, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "303", "occupancy": "Triple", "room_type": "Triple", "is_ac": False, "price_per_night": 1900.0,
         "extra_bed_price": 300.0},
        {"room_number": "304", "occupancy": "Single", "room_type": "Studio", "is_ac": False, "price_per_night": 1200.0,
         "extra_bed_price": 300.0},
        {"room_number": "304", "occupancy": "Double", "room_type": "Studio", "is_ac": False, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "305", "occupancy": "Single", "room_type": "Luxury", "is_ac": False, "price_per_night": 1400.0,
         "extra_bed_price": 300.0},
        {"room_number": "305", "occupancy": "Double", "room_type": "Luxury", "is_ac": False, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        # AC ROOMS
        {"room_number": "001", "occupancy": "Single", "room_type": "Luxury", "is_ac": True, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "001", "occupancy": "Double", "room_type": "Luxury", "is_ac": True, "price_per_night": 2000.0,
         "extra_bed_price": 300.0},
        {"room_number": "101", "occupancy": "Single", "room_type": "Luxury", "is_ac": True, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "101", "occupancy": "Double", "room_type": "Luxury", "is_ac": True, "price_per_night": 2000.0,
         "extra_bed_price": 300.0},
        {"room_number": "201", "occupancy": "Single", "room_type": "Luxury", "is_ac": True, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "201", "occupancy": "Double", "room_type": "Luxury", "is_ac": True, "price_per_night": 2000.0,
         "extra_bed_price": 300.0},
        {"room_number": "203", "occupancy": "Single", "room_type": "Luxury", "is_ac": True, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "203", "occupancy": "Double", "room_type": "Luxury", "is_ac": True, "price_per_night": 2000.0,
         "extra_bed_price": 300.0},
        {"room_number": "205", "occupancy": "Single", "room_type": "Luxury", "is_ac": True, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "205", "occupancy": "Double", "room_type": "Luxury", "is_ac": True, "price_per_night": 2000.0,
         "extra_bed_price": 300.0},
        {"room_number": "301", "occupancy": "Single", "room_type": "Luxury", "is_ac": True, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "301", "occupancy": "Double", "room_type": "Luxury", "is_ac": True, "price_per_night": 2000.0,
         "extra_bed_price": 300.0},
        {"room_number": "303", "occupancy": "Triple", "room_type": "Triple", "is_ac": True, "price_per_night": 2200.0,
         "extra_bed_price": 300.0},
        {"room_number": "305", "occupancy": "Single", "room_type": "Luxury", "is_ac": True, "price_per_night": 1700.0,
         "extra_bed_price": 300.0},
        {"room_number": "305", "occupancy": "Double", "room_type": "Luxury", "is_ac": True, "price_per_night": 2000.0,
         "extra_bed_price": 300.0},
        {"room_number": "304", "occupancy": "Single", "room_type": "Studio", "is_ac": True, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "304", "occupancy": "Double", "room_type": "Studio", "is_ac": True, "price_per_night": 1800.0,
         "extra_bed_price": 300.0},
        {"room_number": "302", "occupancy": "Single", "room_type": "Studio", "is_ac": True, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "302", "occupancy": "Double", "room_type": "Studio", "is_ac": True, "price_per_night": 1800.0,
         "extra_bed_price": 300.0},
        {"room_number": "204", "occupancy": "Single", "room_type": "Studio", "is_ac": True, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "204", "occupancy": "Double", "room_type": "Studio", "is_ac": True, "price_per_night": 1800.0,
         "extra_bed_price": 300.0},
        {"room_number": "202", "occupancy": "Single", "room_type": "Studio", "is_ac": True, "price_per_night": 1500.0,
         "extra_bed_price": 300.0},
        {"room_number": "202", "occupancy": "Double", "room_type": "Studio", "is_ac": True, "price_per_night": 1800.0,
         "extra_bed_price": 300.0},
    ]

    # Insert each room into the database
    for room_data in rooms:
        room = model_routes.Room(
            room_number=room_data["room_number"],
            room_type=room_data["room_type"],
            occupancy=room_data["occupancy"],
            is_ac=room_data["is_ac"],
            price_per_night=room_data["price_per_night"],
            extra_bed_price=room_data["extra_bed_price"]
        )
        room_object = model_routes.Room.query.filter_by(room_number=room.room_number, room_type=room.room_type,
                                                        is_ac=room.is_ac, occupancy=room.occupancy).first()
        if room_object:
            continue
        model_routes.db.session.add(room)
    model_routes.db.session.commit()

    return jsonify({'message': 'Room created successfully'}), 201


# Modify Room Price: PUT /api/update_room
@admin_bp.route('/api/update_room/', methods=['PUT'])
@admin_required
def update_price():
    data = request.get_json()
    room_type = data['roomType']
    occupancy = data['occupancy']
    is_ac = data['isAcRoom']
    price_per_night = data['price_per_night']
    extra_bed_price = data["extra_bed_price"]
    rooms = model_routes.Room.query.filter_by(room_type=room_type, is_ac=is_ac,
                                              occupancy=occupancy).all()

    if not rooms:
        return jsonify({'error': 'Room not found'}), 404

    for room in rooms:
        room.price_per_night = price_per_night
        room.extra_bed_price = extra_bed_price
        model_routes.db.session.add(room)
    model_routes.db.session.commit()
    return jsonify({'message': 'Price Updated successful'}), 200


# Modify Room Price: PUT /api/convert_to_ac_room
@admin_bp.route('/api/convert_to_ac_room/', methods=['PUT'])
@admin_required
def convert_to_ac_room():
    data = request.get_json()
    room_number = data['roomNumber']
    rooms = model_routes.Room.query.filter_by(room_number=room_number).all()

    if not rooms:
        return jsonify({'error': 'Room not found'}), 404

    for room in rooms:
        if room.is_ac:
            return jsonify({'error': 'Already a AC Room'}), 404
        room.is_ac = True
        room.price_per_night = room.price_per_night + 300.00
        model_routes.db.session.add(room)
    model_routes.db.session.commit()
    return jsonify({'message': 'Converted to AC Room'}), 200
