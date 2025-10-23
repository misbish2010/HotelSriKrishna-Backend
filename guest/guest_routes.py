from flask import Blueprint
from datetime import datetime, timedelta
from model import model_routes
import phonenumbers
from sqlalchemy.sql import func
from flask import request, jsonify
from datetime import datetime


# Defining a blueprint
guest_bp = Blueprint(
    'guest_bp', __name__,
    template_folder='templates',
    static_folder='static'
)


def format_phone_number(phone_number, default_country="IN"):
    try:
        # Parse and format the phone number
        parsed_number = phonenumbers.parse(phone_number, default_country)
        return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        raise ValueError("Invalid phone number!")


@guest_bp.route('/api/existing_customers', methods=['GET'])
def retrieve_customer():
    phone = request.args.get('phoneNumber')
    identity = request.args.get('identity')
    existing_customer = None
    if phone:
        existing_customer = model_routes.Customer.query.filter_by(phone=phone).first()
    elif identity:
        existing_customer = model_routes.Customer.query.filter_by(identity=identity).first()

    if existing_customer:
        return jsonify({"name": existing_customer.name,
                        "address": existing_customer.address,
                        "email": existing_customer.email,
                        "phone": existing_customer.phone,
                        "identity": existing_customer.identity}), 201

    return jsonify({"error": "No Customer Details Found"}), 201


import traceback

@guest_bp.route("/api/create-booking", methods=["POST"])
def create_booking():
    try:
        data = request.get_json()
        print("Incoming booking payload:", data)

        personal_info = data.get("personal_info", {})
        stay_info = data.get("stay_info", {})
        rooms_data = data.get("rooms", [])
        pricing_info = data.get("pricing_info", {})  # contract/price details
        payments = data.get("payment_info", [])      # list of transactions

        # ---- 1. Create or fetch customer ----
        customer = model_routes.Customer.query.filter_by(phone=personal_info.get("phone")).first()
        if not customer:
            customer = model_routes.Customer(
                name=personal_info.get("name"),
                address=personal_info.get("address", ""),
                email=personal_info.get("email", ""),
                identity=personal_info.get("identity", ""),
                phone=personal_info.get("phone")
            )
            model_routes.db.session.add(customer)
            model_routes.db.session.flush()

        # ---- 2. Create booking ----
        check_in = datetime.strptime(stay_info['checkInDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
        check_out = datetime.strptime(stay_info['probableCheckOutDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')

        booking = model_routes.Booking(
            customer_id=customer.id,
            check_in_date=check_in,
            expected_check_out_date=check_out,
            duration_of_stay=stay_info.get("durationOfStay", 0),
            status=data.get("bookingStatus", "Confirmed"),
            mode=stay_info.get("bookingMode", "WALKIN"),
            total_price=pricing_info.get("totalPrice", 0),
            final_price_per_night=pricing_info.get("finalPricePerNight", 0)
        )
        model_routes.db.session.add(booking)
        model_routes.db.session.flush()

        # ---- 3. Add rooms ----
        for idx, room in enumerate(rooms_data):
            agreed_price = (
                pricing_info.get("roomAgreedPrices", [{}])[idx].get("agreedPrice")
                if pricing_info.get("roomAgreedPrices") else None
            )
            booking_room = model_routes.BookingRoom(
                booking_id=booking.id,
                room_id=room.get("roomId"),
                extra_persons=room.get("extraPersons", 0),
                final_price_per_night=agreed_price
            )
            model_routes.db.session.add(booking_room)

        # ---- 4. Add payment(s) ----
        for p in payments:
            payment_date = None
            if p.get("date"):
                try:
                    payment_date = datetime.strptime(p["date"], "%Y-%m-%d")
                except Exception:
                    payment_date = datetime.utcnow()

            payment = model_routes.Payment(
                booking_id=booking.id,
                payment_amount=p.get("amount", 0),
                payment_date=payment_date or datetime.utcnow(),
                payment_mode=p.get("mode", ""),
                payment_status=p.get("status", "paid"),
                notes=p.get("notes", "")
            )
            model_routes.db.session.add(payment)

        model_routes.db.session.commit()
        return jsonify({"success": True, "booking_id": booking.id})

    except Exception as e:
        model_routes.db.session.rollback()
        print("Error during booking creation:", str(e))
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@guest_bp.route('/api/available-rooms', methods=['GET'])
def check_available_rooms():
    try:
        duration_of_stay = int(request.args.get('durationOfStay'))
        target_check_in_date = datetime.strptime(
            request.args.get('checkInDateTime'), '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        target_expected_check_out_date = datetime.strptime(
            request.args.get('probableCheckOutDateTime'), '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        exclude_booking_id = request.args.get('excludeBookingId', type=int)

        active_bookings = model_routes.Booking.query.filter(
            model_routes.Booking.status.in_(["Confirmed", "Checked-In"])
        )

        # Exclude the current booking (if editing)
        if exclude_booking_id:
            active_bookings = active_bookings.filter(model_routes.Booking.id != exclude_booking_id)

        active_bookings = active_bookings.all()

        booked_rooms = set()

        for booking in active_bookings:
            if (
                    booking.check_in_date < target_expected_check_out_date and
                    booking.expected_check_out_date > target_check_in_date
            ):
                for room_association in booking.room_associations:
                    room = room_association.room
                    booked_rooms.add((room.id, room.room_number))

        booked_room_numbers = [room_number for _, room_number in booked_rooms]
        all_related_rooms = model_routes.Room.query.filter(
            model_routes.Room.room_number.in_(booked_room_numbers)
        ).all()

        all_booked_room_ids = {room.id for room in all_related_rooms}
        all_rooms = model_routes.Room.query.all()

        available_rooms_list = [
            room for room in all_rooms if room.id not in all_booked_room_ids
        ]

        rooms = [{
            'room_id': room.id,
            'room_number': room.room_number,
            'room_type': room.room_type,
            'occupancy': room.occupancy,
            'is_ac': room.is_ac,
            'room_price': room.price_per_night,
            'extra_bed_price': room.extra_bed_price
        } for room in available_rooms_list]

        return jsonify({'available_rooms': rooms}), 200

    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500



@guest_bp.route('/api/all-rooms', methods=['GET'])
def fetch_all_rooms():
    try:
        all_rooms = model_routes.Room.query.all()

        rooms = [{
            'room_id': room.id,
            'room_number': room.room_number,
            'room_type': room.room_type,
            'occupancy': room.occupancy,
            'is_ac': room.is_ac,
            'room_price': room.price_per_night,
            'extra_bed_price': room.extra_bed_price
        } for room in all_rooms]

        return jsonify({'all_rooms': rooms}), 200

    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500
        
        
@guest_bp.route('/api/search_booking', methods=['GET'])
def search_booking():
    booking_id = request.args.get('bookingId')
    phone_number = request.args.get('phoneNumber')
    room_number = request.args.get('roomNumber')
    check_in_date = request.args.get('checkInDate')

    if not any([booking_id, phone_number, (room_number and check_in_date)]):
        return jsonify({'error': 'Please provide Booking ID, Phone Number, or Room & Date'}), 400

    query = model_routes.Booking.query

    # 1. Booking ID
    if booking_id:
        booking = query.filter(model_routes.Booking.id == booking_id).first()
    # 2. Phone number
    elif phone_number:
        booking = (
            query.filter(model_routes.Booking.customer.has(phone=phone_number))
            .order_by(model_routes.Booking.check_in_date.desc())
            .first()
        )
    # 3. Room number + date
    elif room_number and check_in_date:
        booking = query.filter(
            model_routes.Booking.room_associations.any(
                model_routes.BookingRoom.room.has(room_number=room_number)
            ),
            model_routes.Booking.check_in_date == check_in_date
        ).first()
    else:
        booking = None

    if not booking:
        return jsonify({'error': 'No booking found'}), 404

    # GST Mapping
    gst_mapping = model_routes.GSTBillMapping.query.filter_by(booking_id=booking.id).first()
    gst_bill_no = gst_mapping.gst_bill_no if gst_mapping else None
    guest_gst_no = gst_mapping.guest_gst_no if gst_mapping else None
    guest_company_name = gst_mapping.guest_company_name if gst_mapping else None

    result = [{
        'booking_id': booking.id,
        'booking_mode': booking.mode,
        'booking_status': booking.status,
        'price_per_night': booking.final_price_per_night,
        'total_price': booking.total_price,
        'customer_info': {
            'name': booking.customer.name,
            'phone': booking.customer.phone,
            'identity': booking.customer.identity,
            'address': booking.customer.address,
            'email': booking.customer.email,
        },
        'stay_info': {
            'check_in_date': booking.check_in_date,
            'check_out_date': booking.check_out_date,
            'probable_check_out_date': booking.expected_check_out_date,
            'duration': booking.duration_of_stay,
            'mode': booking.mode
        },
        'payment_info': [
            {
                'amount': p.payment_amount,
                'date': p.payment_date,
                'mode': p.payment_mode,
                'notes': p.notes,
                'status': p.payment_status
            }
            for p in booking.payments
        ],
        'room_details': [
            {
                'room_id': assoc.room.id,
                'room_number': assoc.room.room_number,
                'room_type': assoc.room.room_type,
                'is_ac': assoc.room.is_ac,
                'extra_persons': assoc.extra_persons,
                'occupancy': assoc.room.occupancy,
                'room_price': getattr(assoc, 'final_price_per_night', None) or getattr(assoc.room, 'price_per_night', 0),
                'extra_bed_price': getattr(assoc.room, 'extra_bed_price', 0)
            }
            for assoc in booking.room_associations
        ],
        'gst_info': {
            'gst_bill_no': gst_bill_no,
            'guest_gst_no': guest_gst_no,
            'guest_company_name': guest_company_name
        }
    }]
    print("---------------------")
    print(result)
    return jsonify({'bookingDetails': result}), 200


@guest_bp.route('/api/update-booking', methods=['POST'])
def update_booking():
    try:
        data = request.get_json()
        print(data)

        booking_id = data.get('bookingId')
        booking_status = data.get('bookingStatus')
        booking = model_routes.Booking.query.get(booking_id)
        if not booking:
            return jsonify({"error": "Booking not found"}), 404

        # 1️⃣ Status
        if booking_status:
            booking.status = booking_status

        # 2️⃣ Guest Info
        guest_info = data.get('personal_info')
        if guest_info:
            customer = booking.customer
            customer.name = guest_info.get('name', customer.name)
            customer.address = guest_info.get('address', customer.address)
            customer.email = guest_info.get('email', customer.email)
            customer.identity = guest_info.get('identity') or guest_info.get('idNumber', customer.identity)
            customer.phone = guest_info.get('phone', customer.phone)

        # 3️⃣ Stay Info
        stay_info = data.get('stay_info')
        if stay_info:
            if stay_info.get('checkInDateTime'):
                booking.check_in_date = datetime.strptime(stay_info['checkInDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
            if stay_info.get('probableCheckOutDateTime'):
                booking.expected_check_out_date = datetime.strptime(stay_info['probableCheckOutDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
            if stay_info.get('durationOfStay'):
                booking.duration_of_stay = stay_info['durationOfStay']
            if stay_info.get('bookingMode'):
                booking.mode = stay_info['bookingMode']

        # 4️⃣ Room Info
        rooms_data = data.get('rooms')
        if rooms_data is not None:
            booking.room_associations.clear()
            for room in rooms_data:
                room_obj = model_routes.Room.query.get(room['room_id'])
                if room_obj:
                    assoc = model_routes.BookingRoom(
                        room=room_obj,
                        extra_persons=room.get('extra_persons', 0),
                        final_price_per_night=room.get('final_price_per_night')  # use provided
                    )
                    booking.room_associations.append(assoc)

        # 5️⃣ Pricing Info
        pricing_info = data.get('pricing_info')
        if pricing_info:
            booking.total_price = pricing_info.get("totalPrice", booking.total_price)
            booking.final_price_per_night = pricing_info.get("finalPricePerNight", booking.final_price_per_night)
            # You could also persist gstRate here if your model has a field for it

        # 5️⃣ GST Info (optional)
        gst_info = data.get('gstInfo')
        if gst_info:
            gst_mapping = model_routes.GSTBillMapping.query.filter_by(booking_id=booking.id).first()
            if not gst_mapping:
                gst_mapping = model_routes.GSTBillMapping(booking_id=booking.id)
                model_routes.db.session.add(gst_mapping)
            gst_mapping.gst_bill_no = gst_info.get('gst_bill_no', gst_mapping.gst_bill_no)
            gst_mapping.guest_gst_no = gst_info.get('guest_gst_no', gst_mapping.guest_gst_no)
            gst_mapping.guest_company_name = gst_info.get('guest_company_name', gst_mapping.guest_company_name)

        # 6️⃣ Payment Info (list)
        payments = data.get('payment_info')
        if payments is not None and isinstance(payments, list):
            # Clear existing
            model_routes.Payment.query.filter_by(booking_id=booking.id).delete()
            for p in payments:
                payment_date = p.get('date')
                if isinstance(payment_date, str):
                    try:
                        payment_date = datetime.strptime(payment_date, "%Y-%m-%d")
                    except ValueError:
                        payment_date = datetime.utcnow()
                payment = model_routes.Payment(
                    booking_id=booking.id,
                    payment_amount=p.get('amount', 0),
                    payment_date=payment_date or datetime.utcnow(),
                    payment_mode=p.get('mode'),
                    notes=p.get('notes', ''),
                    payment_status=p.get('status', 'paid')
                )
                model_routes.db.session.add(payment)

        model_routes.db.session.commit()
        return jsonify({"success": True, "message": "Booking updated successfully"})

    except Exception as e:
        model_routes.db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@guest_bp.route("/api/bookings/<int:booking_id>/gst-invoice", methods=["GET"])
def get_or_create_invoice(booking_id):
    # 1. Check if invoice already exists for this booking
    invoice = model_routes.GSTBillMapping.query.filter_by(booking_id=booking_id).first()
    if invoice:
        return jsonify({
            'gst_bill_no': invoice.gst_bill_no,
            'gst_bill_date': invoice.gst_bill_date
        }), 200

    # 2. Generate fiscal year and month info
    current_date = datetime.now()
    fiscal_year_start = current_date.year if current_date.month >= 4 else current_date.year - 1
    fiscal_year_end = fiscal_year_start + 1
    fiscal_year = f"FY{fiscal_year_start}-{fiscal_year_end}"
    current_month = f"{current_date.month:02d}"

    # 3. Get the latest GST bill number for this fiscal year/month
    latest_mapping = (
        model_routes.GSTBillMapping.query
        .filter(model_routes.GSTBillMapping.gst_bill_no.like(f"HSK/{fiscal_year}/{current_month}/%"))
        .order_by(model_routes.GSTBillMapping.gst_bill_no.desc())
        .first()
    )

    if latest_mapping:
        latest_number = int(latest_mapping.gst_bill_no.split('/')[-1])
        next_number = latest_number + 1
    else:
        next_number = 1  # Start fresh for this month/year

    # 4. Generate new GST bill number
    new_gst_bill_no = f"HSK/{fiscal_year}/{current_month}/{next_number:03d}"

    # 5. Save mapping to DB
    new_mapping = model_routes.GSTBillMapping(
        booking_id=booking_id,
        gst_bill_no=new_gst_bill_no,
        gst_bill_date=datetime.utcnow()
    )
    model_routes.db.session.add(new_mapping)
    model_routes.db.session.commit()

    return jsonify({
        'gst_bill_no': new_mapping.gst_bill_no,
        'gst_bill_date': new_mapping.gst_bill_date
    }), 200


# ✅ Room Dashboard API with Full Booking Details
@guest_bp.route('/api/room/dashboard', methods=['GET'])
def check_rooms_dashboard():
    try:
        start_date = datetime.strptime(request.args.get('startDate'), '%Y-%m-%dT%H:%M:%S.%fZ')
        end_date = datetime.strptime(request.args.get('endDate'), '%Y-%m-%dT%H:%M:%S.%fZ')

        # Adjust to cover full days
        start_of_day = datetime.combine(start_date, datetime.min.time())
        end_of_day = datetime.combine(end_date, datetime.max.time())

        # 🔹 Fetch all bookings in the date range
        bookings = model_routes.Booking.query.filter(
            model_routes.Booking.check_in_date < end_of_day,
            (model_routes.Booking.expected_check_out_date == None) | (model_routes.Booking.expected_check_out_date > start_of_day)
        ).all()

        booking_details = []
        booked_room_numbers = set()

        for booking in bookings:
            # Track rooms as booked
            for assoc in booking.room_associations:
                booked_room_numbers.add(assoc.room.room_number)

            # GST Mapping
            gst_mapping = model_routes.GSTBillMapping.query.filter_by(booking_id=booking.id).first()
            gst_bill_no = gst_mapping.gst_bill_no if gst_mapping else None
            guest_gst_no = gst_mapping.guest_gst_no if gst_mapping else None
            guest_company_name = gst_mapping.guest_company_name if gst_mapping else None

            # Serialize booking (same as /api/search_booking)
            booking_details.append({
                'booking_id': booking.id,
                'booking_mode': booking.mode,
                'booking_status': booking.status,
                'price_per_night': booking.final_price_per_night,
                'total_price': booking.total_price,
                'customer_info': {
                    'name': booking.customer.name,
                    'phone': booking.customer.phone,
                    'identity': booking.customer.identity,
                    'address': booking.customer.address,
                    'email': booking.customer.email,
                },
                'stay_info': {
                    'check_in_date': booking.check_in_date,
                    'check_out_date': booking.check_out_date,
                    'probable_check_out_date': booking.expected_check_out_date,
                    'duration': booking.duration_of_stay,
                    'mode': booking.mode
                },
                'payment_info': [
                    {
                        'amount': p.payment_amount,
                        'date': p.payment_date,
                        'mode': p.payment_mode,
                        'notes': p.notes,
                        'status': p.payment_status
                    }
                    for p in booking.payments
                    if p.payment_status != "applied" or p.payment_status != "Discount"
                ],
                'room_details': [
                    {
                        'room_id': assoc.room.id,
                        'room_number': assoc.room.room_number,
                        'room_type': assoc.room.room_type,
                        'is_ac': assoc.room.is_ac,
                        'extra_persons': assoc.extra_persons,
                        'occupancy': assoc.room.occupancy,
                        'room_price': getattr(assoc, 'final_price_per_night', None) or getattr(assoc.room, 'price_per_night', 0),
                        'extra_bed_price': getattr(assoc.room, 'extra_bed_price', 0)
                    }
                    for assoc in booking.room_associations
                ],
                'gst_info': {
                    'gst_bill_no': gst_bill_no,
                    'guest_gst_no': guest_gst_no,
                    'guest_company_name': guest_company_name
                }
            })
        # 🔹 Available rooms (rooms not in booked_room_numbers)
        all_rooms = model_routes.Room.query.all()
        seen = set()
        available_rooms = []
        for room in all_rooms:
            if room.room_number not in booked_room_numbers and room.room_number not in seen:
                available_rooms.append({
                    'room_number': room.room_number,
                    'room_type': room.room_type
                })
                seen.add(room.room_number)

        return jsonify({'bookings': booking_details, 'available_rooms': available_rooms}), 200

    except Exception as e:
        print("❌ Error in room dashboard:", e)
        return jsonify({'error': str(e)}), 500


@guest_bp.route('/api/room/status', methods=['GET'])
def check_rooms_status():
    duration_window = int(request.args.get('booking_window'))
    target_check_in_date = datetime.strptime(request.args.get('checkInDateTime'), '%Y-%m-%dT%H:%M:%S.%fZ')
    target_check_out_date = target_check_in_date + timedelta(hours=duration_window)

    # Step 1: Get all active bookings
    active_bookings = model_routes.Booking.query.filter(
        model_routes.Booking.status.in_(["Confirmed", "Checked-In"])
    ).all()

    print(active_bookings)

    booked_rooms = set()  # A set of tuples (room, room_number)
    for booking in active_bookings:
        # Calculate the actual check-out date (expected or actual)
        print(booking)
        calculated_check_out_date = (
            booking.check_in_date + timedelta(days=booking.duration_of_stay)
            if booking.duration_of_stay else None
        )
        # Check if the booking overlaps with the target date range
        if (
                booking.check_in_date < target_check_out_date and
                calculated_check_out_date > target_check_in_date
        ):
            # Add associated room IDs and room numbers to the booked list
            for room_association in booking.room_associations:
                # Fetch room details (assuming room_association.room provides access to room object)
                room = room_association.room  # Replace with the correct property or query if needed
                booked_rooms.add((room.id, room.room_number))  # Collect both ID and number
    # Step 4: Fetch all rooms with matching room numbers
    # Extract room numbers from the booked_rooms set
    booked_room_numbers = [room_number for _, room_number in booked_rooms]
    print(booked_room_numbers)
    booked_room_ids = [room_id for room_id, _ in booked_rooms]
    all_rooms = model_routes.Room.query.all()
    booked_rooms_list = [room for room in all_rooms if room.id in booked_room_ids]
    available_rooms_list = [room for room in all_rooms if room.room_number not in booked_room_numbers]

    unique_available_rooms = {}
    for room in available_rooms_list:
        if room.room_number not in booked_room_numbers:
            unique_available_rooms[room.room_number] = room

    # Get the unique available rooms
    unique_available_rooms_list = list(unique_available_rooms.values())
    print("~~~~~~~~~~~")
    print(booked_rooms_list)
    booked_rooms_details = [
        {
            'room_number': room.room_number,
            'bookings': [
                {
                    'booking_id': association.booking.id,
                    'customer_name': association.booking.customer.name,
                    'customer_contact': association.booking.customer.phone,
                    'check_in_date': association.booking.check_in_date,  # Include check-in date
                    'probable_check_out_date': association.booking.expected_check_out_date,  # Include check-out date
                    'duration_of_stay': association.booking.duration_of_stay,  # Include duration of stay
                    'room_type': room.room_type,  # Include room type
                    'is_ac': room.is_ac,  # Include AC status
                    'occupancy': room.occupancy,  # Include occupancy
                    'payment_details': [
                        {
                            'payment_id': payment.id,
                            'payment_amount': payment.payment_amount,
                            'payment_date': payment.payment_date
                        }
                        for payment in association.booking.payments
                    ],
                    'booking_status': association.booking.status,
                    'final_price_per_night': association.booking.final_price_per_night
                }
                for association in room.booking_associations
                if (
                        association.booking.status in ["Checked-In", "Confirmed"] and
                        association.booking.check_in_date < target_check_out_date and
                        (
                                association.booking.expected_check_out_date is None or
                                association.booking.expected_check_out_date > target_check_in_date
                        )
                )
            ]
        }
        for room in booked_rooms_list
    ]

    print(booked_rooms_details)

    available_rooms_details = [{'room_number': room.room_number,
                                'room_type': room.room_type}
                               for room in unique_available_rooms_list]

    return jsonify({'booked_rooms': booked_rooms_details, 'available_rooms': available_rooms_details}), 200


@guest_bp.route('/api/get_payment', methods=['GET'])
def get_payments_by_date():
    # Parse dates from request
    start_date = datetime.strptime(request.args.get('startDate'), '%Y-%m-%dT%H:%M:%S.%fZ')
    end_date = datetime.strptime(request.args.get('endDate'), '%Y-%m-%dT%H:%M:%S.%fZ')

    # Adjust to full day boundaries
    start_of_day = datetime.combine(start_date, datetime.min.time())
    end_of_day = datetime.combine(end_date, datetime.max.time())

    # --------------------
    # Expenses
    # --------------------
    expenses = (
        model_routes.Expense.query
        .filter(model_routes.Expense.date >= start_of_day,
                model_routes.Expense.date <= end_of_day)
        .all()
    )

    # --------------------
    # Paid Payments (aggregated by booking + mode)
    # --------------------
    paid_results = (
        model_routes.db.session.query(
            model_routes.Booking.id.label('booking_id'),
            model_routes.Customer.name.label('customer_name'),
            model_routes.Customer.phone.label('contact_number'),
            model_routes.Payment.payment_mode.label('payment_mode'),
            func.sum(model_routes.Payment.payment_amount).label('amount'),
            func.max(model_routes.Payment.payment_date).label('payment_date'),
            func.group_concat(model_routes.Room.room_number).label('room_numbers')
        )
        .join(model_routes.Customer, model_routes.Booking.customer_id == model_routes.Customer.id)
        .join(model_routes.Payment, model_routes.Booking.id == model_routes.Payment.booking_id)
        .join(model_routes.BookingRoom, model_routes.Booking.id == model_routes.BookingRoom.booking_id)
        .join(model_routes.Room, model_routes.BookingRoom.room_id == model_routes.Room.id)
        .filter(
            model_routes.Payment.payment_date.between(start_of_day, end_of_day),
            model_routes.Payment.payment_status != "Discount"   # <-- added
            #model_routes.Payment.notes.is_(None)
        )
        .group_by(
            model_routes.Booking.id,
            model_routes.Customer.name,
            model_routes.Customer.phone,
            model_routes.Payment.payment_mode
        )
        .all()
    )

    # --------------------
    # Pending Payments
    # --------------------
    pending_results = (
        model_routes.db.session.query(
            model_routes.Booking.id.label('booking_id'),
            model_routes.Customer.name.label('customer_name'),
            model_routes.Customer.phone.label('contact_number'),
            model_routes.Payment.payment_mode.label('payment_mode'),
            func.sum(model_routes.Payment.payment_amount).label('amount'),
            func.max(model_routes.Payment.payment_date).label('payment_date'),
            func.group_concat(model_routes.Room.room_number).label('room_numbers')
        )
        .join(model_routes.Customer, model_routes.Booking.customer_id == model_routes.Customer.id)
        .join(model_routes.Payment, model_routes.Booking.id == model_routes.Payment.booking_id)
        .join(model_routes.BookingRoom, model_routes.Booking.id == model_routes.BookingRoom.booking_id)
        .join(model_routes.Room, model_routes.BookingRoom.room_id == model_routes.Room.id)
        .filter(
            model_routes.Payment.payment_status == "DUE",
            model_routes.Payment.payment_date <= end_of_day
            # Optional: restrict to past/current bookings only
            # model_routes.Booking.check_in_date <= datetime.today()
        )
        .group_by(
            model_routes.Booking.id,
            model_routes.Customer.name,
            model_routes.Customer.phone,
            model_routes.Payment.payment_mode
        )
        .all()
    )

    # --------------------
    # Format for JSON
    # --------------------
    payment_details = [
        {
            "booking_id": row.booking_id,
            "customer_name": row.customer_name,
            "contact_number": row.contact_number,
            "payment_mode": row.payment_mode.upper(),
            "amount": row.amount,
            "payment_date": row.payment_date,
            "room_numbers": row.room_numbers.split(',') if row.room_numbers else []
        }
        for row in paid_results
    ]

    pending_payment_details = [
        {
            "booking_id": row.booking_id,
            "customer_name": row.customer_name,
            "contact_number": row.contact_number,
            "payment_mode": row.payment_mode.upper(),
            "amount": row.amount,
            "payment_date": row.payment_date,
            "room_numbers": row.room_numbers.split(',') if row.room_numbers else []
        }
        for row in pending_results
    ]

    expense_details = [
        {
            "description": row.description,
            "amount": row.amount,
            "mode": row.mode,
            "date": row.date
        }
        for row in expenses
    ]
    print(payment_details)
    return jsonify({
        "payment_details": payment_details,
        "pending_payment_details": pending_payment_details,
        "expense_details": expense_details
    }), 200


@guest_bp.route('/api/bookings-by-date-range', methods=['POST'])
def bookings_by_date_range():
    try:
        data = request.json
        start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
        end_date = datetime.strptime(data['endDate'], '%Y-%m-%d')

        range_type = data.get('rangeType', 'custom')  # monthly / quarterly / custom
        print(start_date)
        print(end_date)

        # --- Handle Monthly / Quarterly ---
        if range_type == 'monthly':
            # Align start to 1st of month, end to last day of month
            start_date = start_date.replace(day=1)
            from calendar import monthrange
            last_day = monthrange(start_date.year, start_date.month)[1]
            end_date = end_date.replace(day=last_day)
            print(start_date)
            print(end_date)

        elif range_type == 'quarterly':
            # Align start to first month of quarter
            quarter = (start_date.month - 1) // 3 + 1
            start_month = 3 * (quarter - 1) + 1
            start_date = datetime(start_date.year, start_month, 1)
            from calendar import monthrange
            end_month = start_month + 2
            last_day = monthrange(start_date.year, end_month)[1]
            end_date = datetime(start_date.year, end_month, last_day)

        # --- Query GST mapping in date range ---
        gst_records = (
            model_routes.GSTBillMapping.query
            .filter(model_routes.GSTBillMapping.gst_bill_date.between(start_date, end_date))
            .all()
        )
        if not gst_records:
            return jsonify({"bookings": []}), 200

        booking_ids = [record.booking_id for record in gst_records]

        # --- Fetch bookings that match those IDs ---
        bookings = (
            model_routes.Booking.query
            .filter(model_routes.Booking.id.in_(booking_ids))
            .all()
        )

        booking_list = []
        for booking in bookings:
            booking_list.append({
                'booking_id': booking.id,
                'booking_mode': booking.mode,
                'booking_status': booking.status,
                'price_per_night': booking.final_price_per_night,
                'total_price': booking.total_price,
                'customer_info': {
                    'name': booking.customer.name if booking.customer else None,
                    'phone': booking.customer.phone if booking.customer else None,
                    'identity': booking.customer.identity if booking.customer else None,
                    'address': booking.customer.address if booking.customer else None,
                    'email': booking.customer.email if booking.customer else None,
                },
                'stay_info': {
                    'check_in_date': booking.check_in_date,
                    'check_out_date': booking.check_out_date,
                    'probable_check_out_date': booking.expected_check_out_date,
                    'duration': booking.duration_of_stay,
                    'mode': booking.mode,
                },
                'payment_info': [
                    {
                        'amount': p.payment_amount,
                        'date': p.payment_date,
                        'mode': p.payment_mode,
                        'notes': p.notes,
                        'status': (p.payment_status or "").lower()  # normalize to lowercase
                    }
                    for p in booking.payments
                ],
                'room_details': [
                    {
                        'room_number': assoc.room.room_number,
                        'room_type': assoc.room.room_type,
                        'is_ac': assoc.room.is_ac,
                        'extra_persons': assoc.extra_persons,
                        'occupancy': assoc.room.occupancy,
                        # include nightly rate (fallback to booking.final_price_per_night if None)
                        'room_price': assoc.final_price_per_night or booking.final_price_per_night or 0
                    }
                    for assoc in booking.room_associations
                ],
                'gst_info': {
                    'gst_bill_no': booking.gst_bill_mapping.gst_bill_no if booking.gst_bill_mapping else None,
                    'guest_gst_no': booking.gst_bill_mapping.guest_gst_no if booking.gst_bill_mapping else None,
                    'gst_bill_date': booking.gst_bill_mapping.gst_bill_date.strftime('%Y-%m-%d') if booking.gst_bill_mapping else None,
                    'guest_company_name': booking.gst_bill_mapping.guest_company_name if booking.gst_bill_mapping else None,
                },
            })

        return jsonify({"bookings": booking_list}), 200

    except Exception as e:
        print("Error in bookings_by_date_range:", e)
        return jsonify({"message": "Error occurred", "error": str(e)}), 500


