from flask import Blueprint
from flask import request, jsonify
from datetime import datetime, timedelta
from guest.utility import *
from model import model_routes
#import pywhatkit as kit
import phonenumbers
from sqlalchemy import and_, or_
from datetime import datetime, timezone
from sqlalchemy.sql import func


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


@guest_bp.route('/api/create-booking', methods=['POST'])
def create_booking():
    try:
        data = request.json
        # Personal Info
        name = data['personal_info']['name']
        address = data['personal_info']['address']
        email = data['personal_info']['email']
        phone = data['personal_info']['phoneNumber']
        identity = data['personal_info']['identity']

        if not all([name, address, phone, identity]):
            return jsonify({"error": "All fields are required (name, address, identity, phone)"}), 400

        if phone:
            existing_customer = model_routes.Customer.query.filter_by(phone=phone).first()
        elif identity:
            existing_customer = model_routes.Customer.query.filter_by(identity=identity).first()
        customer_id = None
        if existing_customer:
            customer_id = existing_customer.id
        else:
            # Create a new Customer record
            new_customer = model_routes.Customer(name=name, address=address, email=email, phone=phone, identity=identity)
            model_routes.db.session.add(new_customer)
            model_routes.db.session.flush()
            customer_id = new_customer.id
        # Stay Info
        check_in_date = datetime.strptime(data['stay_info']['checkInDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
        expected_check_out_date = datetime.strptime(data['stay_info']['probableCheckOutDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')

        # Log the parsed dates for debugging
        print(f"Parsed Check-In Date: {check_in_date}")
        print(f"Parsed Check-Out Date: {expected_check_out_date}")

        duration_of_stay = int(data['stay_info']['durationOfStay'])
        mode = data['stay_info']['bookingMode']

        status = data['bookingStatus']
        check_in_date = datetime.strptime(data['stay_info']['checkInDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
        payment_mode = data['payment_info']['paymentMode']
        payment_date = datetime.strptime(data['payment_info']['paymentDate'], '%Y-%m-%dT%H:%M:%S.%fZ')
        payment_amount = float(data['payment_info']['paymentAmount'])
        final_price_per_night = float(data['payment_info']['finalPricePerNight'])
        total_price = final_price_per_night * duration_of_stay
        # Create a new booking
        new_booking = model_routes.Booking(
            customer_id=customer_id,
            check_in_date=check_in_date,
            expected_check_out_date=expected_check_out_date,
            duration_of_stay=duration_of_stay,
            status=status,
            mode=mode,
            total_price=total_price,
            final_price_per_night=final_price_per_night
        )

        model_routes.db.session.add(new_booking)
        model_routes.db.session.flush()  # Flush to get the booking ID
        if payment_amount != 0.0:
            payment = model_routes.Payment(
                booking_id=new_booking.id,
                payment_amount=payment_amount,
                payment_mode=payment_mode,
                payment_status="",
                payment_date=payment_date,
                notes=None
            )

            model_routes.db.session.add(payment)
        # Add rooms to the booking
        for room_data in data['rooms']:
            room_id = room_data['roomId']
            extra_persons = room_data['extraPersons']

            booking_room = model_routes.BookingRoom(
                booking_id=new_booking.id,
                room_id=room_id,
                extra_persons=extra_persons,
            )
            model_routes.db.session.add(booking_room)
        model_routes.db.session.commit()

        return jsonify({
            'success': True,
            'booking_id': new_booking.id
        }), 201

    except Exception as e:
        model_routes.db.session.rollback()
        print("Error:", e)
        return jsonify({'success': False, 'error': 'Failed to create booking'}), 500


@guest_bp.route('/api/search_booking', methods=['GET'])
def search_booking():
    booking_status = request.args.get('bookingStatus')
    booking_id = request.args.get('bookingId')
    phone_number = request.args.get('phoneNumber')
    room_number = request.args.get('roomNumber')
    check_in_date = request.args.get('checkInDate')

    query = model_routes.Booking.query

    # Apply filters based on query parameters
    if booking_id:
        query = query.filter(model_routes.Booking.id == booking_id)
    if phone_number:
        query = query.filter(model_routes.Booking.customer.has(phone=phone_number))
    if room_number and check_in_date:
        query = query.filter(
            model_routes.Booking.room_associations.any(
                model_routes.BookingRoom.room.has(room_number=room_number)
            ),
            model_routes.Booking.check_in_date == check_in_date
        )
    booking = None
    if booking_status == "ACTIVE":
        booking = query.filter(model_routes.Booking.status == "Checked-In").first()
    elif booking_status == "PAST":
        booking = (
            query.filter(model_routes.Booking.status.in_(["Checked-Out", "Cancelled"]))
            .order_by(model_routes.Booking.check_in_date.desc())
            .first()
        )
    elif booking_status == "FUTURE":
        booking = query.filter(model_routes.Booking.status == "Confirmed").first()

    if not booking:
        return jsonify({'error': 'No bookings found'}), 404

    result = []
    # Fetch GST Bill Mapping
    gst_mapping = model_routes.GSTBillMapping.query.filter_by(booking_id=booking.id).first()
    gst_bill_no = gst_mapping.gst_bill_no if gst_mapping else None
    guest_gst_no = gst_mapping.guest_gst_no if gst_mapping else None

    result.append({
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
                {'amount': payment.payment_amount, 'date': payment.payment_date, 'mode': payment.payment_mode,
                 'notes': payment.notes, 'status': payment.payment_status}
                for payment in booking.payments
            ],
            'room_details': [
                {
                    'room_number': association.room.room_number,
                    'room_type': association.room.room_type,
                    'is_ac': association.room.is_ac,
                    'extra_persons': association.extra_persons,
                    'occupancy': association.room.occupancy
                }
                for association in booking.room_associations
            ],
            'gst_info': {
                'gst_bill_no': gst_bill_no,
                'guest_gst_no': guest_gst_no,
            }
        })

    return jsonify({'bookingDetails': result}), 200


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


@guest_bp.route('/api/available-rooms', methods=['GET'])
def check_available_rooms():
    try:
        # Parse input parameters
        duration_of_stay = int(request.args.get('durationOfStay'))
        target_check_in_date = datetime.strptime(request.args.get('checkInDateTime'), '%Y-%m-%dT%H:%M:%S.%fZ')
        target_expected_check_out_date = datetime.strptime(request.args.get('probableCheckOutDateTime'), '%Y-%m-%dT%H:%M:%S.%fZ')
        target_check_out_date = target_check_in_date + timedelta(days=duration_of_stay)
        # Step 1: Get all active bookings with associated rooms
        active_bookings = model_routes.Booking.query.filter(
            model_routes.Booking.status.in_(["Confirmed", "Checked-In"])
        ).all()
        # Step 2: Collect all booked room IDs and their associated room numbers for overlapping bookings
        booked_rooms = set()  # A set of tuples (room_id, room_number)

        for booking in active_bookings:
            # Calculate the actual check-out date (expected or actual)
            calculated_check_out_date = (
                booking.check_in_date + timedelta(days=booking.duration_of_stay)
                if booking.duration_of_stay else None
            )
            # Check if the booking overlaps with the target date range
            if (
                    booking.check_in_date < target_expected_check_out_date and
                    booking.expected_check_out_date > target_check_in_date
            ):
            # if (
            #         booking.check_in_date < target_check_out_date and
            #         calculated_check_out_date > target_check_in_date
            # ):
                # Add associated room IDs and room numbers to the booked list
                for room_association in booking.room_associations:
                    # Fetch room details (assuming room_association.room provides access to room object)
                    room = room_association.room  # Replace with the correct property or query if needed
                    booked_rooms.add((room.id, room.room_number))  # Collect both ID and number
                    # Example: booked_rooms = {(1, '001'), (2, '102'), ...}

        # Step 4: Fetch all rooms with matching room numbers
        # Extract room numbers from the booked_rooms set
        booked_room_numbers = [room_number for _, room_number in booked_rooms]
        # Query to fetch rooms based on the room numbers
        all_related_rooms = model_routes.Room.query.filter(
            model_routes.Room.room_number.in_(booked_room_numbers)
        ).all()

        # Step 4: Combine all booked room IDs, including related rooms
        all_booked_room_ids = {room.id for room in all_related_rooms}

        # Step 5: Fetch all room details and distinguish booked vs available
        all_rooms = model_routes.Room.query.all()

        booked_rooms_list = [room for room in all_rooms if room.id in all_booked_room_ids]
        available_rooms_list = [room for room in all_rooms if room.id not in all_booked_room_ids]
        # Step 6: Prepare response with available room details
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
    start_date = datetime.strptime(request.args.get('startDate'), '%Y-%m-%dT%H:%M:%S.%fZ')
    end_date = datetime.strptime(request.args.get('endDate'), '%Y-%m-%dT%H:%M:%S.%fZ')

    # Adjust the date range to include the full day
    start_of_day = datetime.combine(start_date, datetime.min.time())
    end_of_day = datetime.combine(end_date, datetime.max.time())

    expenses = model_routes.Expense.query.filter(
        model_routes.Expense.date >= start_date,
        model_routes.Expense.date <= end_date
    ).all()
    # Query to fetch unique payment details (grouped by booking_id)
    results = (
        model_routes.db.session.query(
            model_routes.Booking.id.label('booking_id'),
            model_routes.Customer.name.label('customer_name'),
            model_routes.Customer.phone.label('contact_number'),
            model_routes.Payment.payment_mode.label('payment_mode'),
            model_routes.Payment.payment_amount.label('amount'),
            model_routes.Payment.payment_date.label('payment_date'),
            func.group_concat(model_routes.Room.room_number).label('room_numbers'),  # Group room numbers
        )
        .join(model_routes.Customer, model_routes.Booking.customer_id == model_routes.Customer.id)  # Booking -> Customer
        .join(model_routes.Payment, model_routes.Booking.id == model_routes.Payment.booking_id)  # Booking -> Payment
        .join(model_routes.BookingRoom, model_routes.Booking.id == model_routes.BookingRoom.booking_id)  # Booking -> BookingRoom
        .join(model_routes.Room, model_routes.BookingRoom.room_id == model_routes.Room.id)  # BookingRoom -> Room
        .filter(
            and_(
                model_routes.Payment.payment_date.between(start_of_day, end_of_day),
                model_routes.Payment.notes.is_(None)
            )
        )
        .group_by(
            model_routes.Booking.id,
            model_routes.Customer.name,
            model_routes.Customer.phone,
            model_routes.Payment.payment_mode,
            model_routes.Payment.payment_amount,
            model_routes.Payment.payment_date
        )
        .all()
    )

    results_due_payments = (
        model_routes.db.session.query(
            model_routes.Booking.id.label('booking_id'),
            model_routes.Customer.name.label('customer_name'),
            model_routes.Customer.phone.label('contact_number'),
            model_routes.Payment.payment_mode.label('payment_mode'),
            model_routes.Payment.payment_amount.label('amount'),
            model_routes.Payment.payment_date.label('payment_date'),
            func.group_concat(model_routes.Room.room_number).label('room_numbers'),  # Group room numbers
        )
        .join(model_routes.Customer, model_routes.Booking.customer_id == model_routes.Customer.id)  # Booking -> Customer
        .join(model_routes.Payment, model_routes.Booking.id == model_routes.Payment.booking_id)  # Booking -> Payment
        .join(model_routes.BookingRoom, model_routes.Booking.id == model_routes.BookingRoom.booking_id)  # Booking -> BookingRoom
        .join(model_routes.Room, model_routes.BookingRoom.room_id == model_routes.Room.id)  # BookingRoom -> Room
        .filter(
            and_(
                model_routes.Payment.payment_date <= end_of_day,  # Payments till the end of today
                model_routes.Payment.payment_status == "DUE"      # Filter for payment status "DUE"
            )
        )
        .group_by(
            model_routes.Booking.id,
            model_routes.Customer.name,
            model_routes.Customer.phone,
            model_routes.Payment.payment_mode,
            model_routes.Payment.payment_amount,
            model_routes.Payment.payment_date
        )
        .all()
    )

    # Format the results into a list of dictionaries
    payment_details = [
        {
            "booking_id": row.booking_id,
            "customer_name": row.customer_name,
            "contact_number": row.contact_number,
            "payment_mode": row.payment_mode.upper(),
            "amount": row.amount,
            "payment_date": row.payment_date,
            "room_numbers": row.room_numbers.split(',') if row.room_numbers else [],  # Split room numbers into a list
        }
        for row in results
    ]

    pending_payment_details = [
        {
            "booking_id": row.booking_id,
            "customer_name": row.customer_name,
            "contact_number": row.contact_number,
            "payment_mode": row.payment_mode.upper(),
            "amount": row.amount,
            "payment_date": row.payment_date,
            "room_numbers": row.room_numbers.split(',') if row.room_numbers else [],  # Split room numbers into a list
        }
        for row in results_due_payments
    ]
    expense_details = [
        {
            "description": row.description,
            "amount": row.amount,
            "mode": row.mode
        }
        for row in expenses
    ]

    # Debug log (remove or modify for production use)
    print(payment_details)

    # Return the payment details as JSON
    return jsonify({"payment_details": payment_details, "pending_payment_details": pending_payment_details, "expense_details": expense_details}), 200


@guest_bp.route('/api/update_payment', methods=['POST'])
def add_or_remove_payment():
    data = request.json
    print(data)
    payment_mode = data['paymentMode']
    booking_id = data['bookingId']
    payment_amount = data['paymentAmount']
    transaction_type = data['transactionType']
    payment_note = data['paymentNote']
    print("####")
    print(data['paymentDate'])
    payment_date = datetime.strptime(data['paymentDate'], '%Y-%m-%dT%H:%M:%S.%fZ')
    if payment_note == "":
        payment_note = None
    booking = get_booking_details_by_booking_id(booking_id)
    if not booking or booking.status not in ("Checked-In", "Confirmed", "Checked-Out"):
        return jsonify({"error": "No booking found for this room"}), 404
    payment_message = None

    if transaction_type == "DEBIT":
        payment_message = "Refund Successful"
        payment_amount = -float(payment_amount)
    elif transaction_type == "CREDIT":
        payment_message = "Payment Successful"
        payment_amount = float(payment_amount)

    if payment_note == "PAY LATER":
        payment_status = "DUE"
    elif payment_note == "SETTLEMENT":
        payment = model_routes.Payment.query.filter_by(booking_id=booking_id, payment_status="DUE").first()
        if not payment:
            model_routes.db.session.delete(payment)
    else:
        payment_status = ""

    payment = model_routes.Payment(
        booking_id=booking.id,
        payment_amount=payment_amount,
        payment_mode=payment_mode,
        payment_status=payment_status,  # Set conditionally
        payment_date=payment_date,
        notes=payment_note
    )
    model_routes.db.session.add(payment)
    model_routes.db.session.commit()

    return jsonify({'message': payment_message, 'booking_id': booking.id}), 200


# @guest_bp.route('/api/message', methods=['POST'])
# def send_whatsapp_message():
#     data = request.get_json()
#     phone_number = data['phoneNumber']
#     # phone_number = '+91' + phone_number
#     phone_number = format_phone_number(phone_number)
#     message = data['message']
#     try:
#         # Use pywhatkit to send a message instantly
#         kit.sendwhatmsg_instantly(phone_number, message, wait_time=15)
#         return jsonify({'message': 'Message Sent successfully'}), 201
#     except Exception as e:
#         return jsonify({'error': 'Message Sending Failed ..'}), 201
#

@guest_bp.route('/api/update_booking', methods=['POST'])
def cancel_or_checkout_booking():
    # Extract booking ID from request
    data = request.get_json()
    booking_id = data.get("bookingId")
    booking_status = data.get("bookingStatus")
    stay_duration = data.get("stayDuration")
    check_out_date = datetime.strptime(data.get('checkOutDateTime'), '%Y-%m-%dT%H:%M:%S.%fZ')
    if not booking_id:
        return jsonify({"error": "Booking ID is required"}), 400
    # Fetch the booking from the database
    booking = get_booking_details_by_booking_id(booking_id)

    if not booking:
        return jsonify({"error": "Booking not found"}), 404
    # Ensure the booking is currently checked-in
    if booking.status not in ("Checked-In", "Confirmed"):
        return jsonify({"error": f" Current Booking status: {booking.status}"}), 400
    message = None
    if booking_status == "Checked-In":
        booking.duration_of_stay = stay_duration
        booking.check_out_date = check_out_date
        booking.status = "Checked-Out"
        message = "CheckOut Successful"
    elif booking_status == "Confirmed":
        booking.duration_of_stay = 0
        booking.check_out_date = check_out_date
        booking.status = "Cancelled"
        message = "Cancellation Successful"

    model_routes.db.session.commit()
    return jsonify({"message": message, "bookingId": booking_id}), 200


@guest_bp.route('/api/add_expense', methods=['POST'])
def add_expense():
    data = request.get_json()
    date = datetime.strptime(data['date'], '%Y-%m-%d')
    description = data['description']
    amount = data['amount']
    mode = data['mode']

    existing_expense = model_routes.Expense.query.filter_by(date=date, description=description).first()
    print(existing_expense)
    if existing_expense:
        print("Expense already exists for this date and description.")
        return jsonify({'message': 'Expense Record already Inserted'}), 201
    expense = model_routes.Expense(
        date=date,
        description=description,
        amount=amount,
        mode=mode
    )

    model_routes.db.session.add(expense)
    model_routes.db.session.commit()

    return jsonify({'message': 'New Expense Record created successfully'}), 201


# TODO
@guest_bp.route('/api/booking/extend', methods=['POST'])
def extend_active_booking():
    data = request.get_json()
    booking_id = data['bookingId']
    duration_stay = int(data['stayDuration'])
    booking = None
    if booking_id:
        booking = get_active_booking_details_by_booking_id(booking_id)

    if booking is None:
        return jsonify({"error": "No Active Booking found "}), 404

    booking.duration_of_stay = booking.duration_of_stay + duration_stay
    model_routes.db.session.commit()

    return jsonify({'message': 'Booking extended successfully'}), 200


@guest_bp.route('/api/room/dashboard', methods=['GET'])
def check_rooms_dashboard():

    start_date = datetime.strptime(request.args.get('startDate'), '%Y-%m-%dT%H:%M:%S.%fZ')
    end_date = datetime.strptime(request.args.get('endDate'), '%Y-%m-%dT%H:%M:%S.%fZ')

    # Adjust the date range to include the full day
    start_of_day = datetime.combine(start_date, datetime.min.time())
    end_of_day = datetime.combine(end_date, datetime.max.time())

    checked_out_bookings = model_routes.Booking.query.filter(

        model_routes.Booking.check_out_date >= start_of_day,
        model_routes.Booking.check_out_date <= end_of_day
    ).all()
    print(checked_out_bookings)
    checked_out_rooms = set()  # A set of tuples (room, room_number)
    for booking in checked_out_bookings:
        for room_association in booking.room_associations:
            room = room_association.room  # Replace with the correct property or query if needed
            checked_out_rooms.add((room.id, room.room_number))  # Collect both ID and number
    print(checked_out_rooms)



    # Step 1: Get all active bookings
    active_bookings = model_routes.Booking.query.filter(
        model_routes.Booking.status.in_(["Confirmed", "Checked-In"])
    ).all()
    booked_rooms = set()  # A set of tuples (room, room_number)
    for booking in active_bookings:
        # Calculate the actual check-out date (expected or actual)
        calculated_check_out_date = (
            booking.check_in_date + timedelta(days=booking.duration_of_stay)
            if booking.duration_of_stay else None
        )
        # Check if the booking overlaps with the target date range
        if (
                booking.check_in_date < end_of_day and
                calculated_check_out_date > start_of_day
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
    checked_out_room_ids = [room_id for room_id, _ in checked_out_rooms]
    all_rooms = model_routes.Room.query.all()
    booked_rooms_list = [room for room in all_rooms if room.id in booked_room_ids]
    checked_out_rooms_list = [room for room in all_rooms if room.id in checked_out_room_ids]
    print("!!!!!!")
    print(checked_out_rooms_list)
    available_rooms_list = [room for room in all_rooms if room.room_number not in booked_room_numbers]

    unique_available_rooms = {}
    for room in available_rooms_list:
        if room.room_number not in booked_room_numbers:
            unique_available_rooms[room.room_number] = room

    # Get the unique available rooms
    unique_available_rooms_list = list(unique_available_rooms.values())
    print("~~~~~~~~~~~")
    print(booked_rooms_list)
    print(checked_out_rooms_list)
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
                        association.booking.check_in_date < end_of_day and
                        (
                                association.booking.expected_check_out_date is None or
                                association.booking.expected_check_out_date > start_of_day
                        )
                )
            ]
        }
        for room in booked_rooms_list
    ]


    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print(booked_rooms_details)
    checked_out_rooms_details = [
        {
            'room_number': room.room_number,
            'bookings': [
                {
                    'booking_id': association.booking.id,
                    'customer_name': association.booking.customer.name,
                    'customer_contact': association.booking.customer.phone,
                    'check_in_date': association.booking.check_in_date,  # Include check-in date
                    'probable_check_out_date': association.booking.expected_check_out_date,  # Include check-out date
                    'duration_of_stay': association.booking.duration_of_stay,  # Include duration
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
                if association.booking.status in ["Checked-Out"]
            ]
        }
        for room in checked_out_rooms_list
    ]

    print(checked_out_rooms_details)

    available_rooms_details = [{'room_number': room.room_number,
                                'room_type': room.room_type}
                               for room in unique_available_rooms_list]

    return jsonify({'booked_rooms': booked_rooms_details, 'checked_out_rooms': checked_out_rooms_details, 'available_rooms': available_rooms_details}), 200


@guest_bp.route('/api/update-booking', methods=['POST'])
def update_booking():
    try:
        data = request.json
        print(data)
        # Get Booking ID
        booking_id = data['stay_info']['bookingId']
        print(booking_id)
        if not booking_id:
            return {"error": "Booking ID is required."}, 400

        # Fetch the existing booking
        existing_booking = model_routes.Booking.query.filter_by(id=booking_id).first()
        if not existing_booking:
            return {"error": "Booking not found."}, 404

        # Get the associated customer
        customer_id = existing_booking.customer_id
        print(customer_id)
        customer = model_routes.Customer.query.filter_by(id=customer_id).first()
        if not customer:
            return {"error": "Associated customer not found."}, 404

        # Update Personal Info
        customer.name = data['personal_info']['name']
        customer.address = data['personal_info']['address']
        customer.email = data['personal_info']['email']
        customer.phone = data['personal_info']['phoneNumber']
        customer.identity = data['personal_info']['identity']

        # Update Booking Info
        check_in_date = datetime.strptime(data['stay_info']['checkInDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
        expected_check_out_date = datetime.strptime(data['stay_info']['probableCheckOutDateTime'], '%Y-%m-%dT%H:%M:%S.%fZ')

        duration_of_stay = int(data['stay_info']['durationOfStay'])
        mode = data['stay_info']['bookingMode']
        status = data['stay_info']['bookingStatus']
        print(status)
        is_update_room_required = data['isUpdateRoomRequired']
        existing_booking.check_in_date = check_in_date
        existing_booking.expected_check_out_date = expected_check_out_date
        existing_booking.duration_of_stay = duration_of_stay
        existing_booking.mode = mode
        existing_booking.status = status
        print(is_update_room_required)
        if is_update_room_required: # if room data is changed
            # Update associated rooms
            print("----------")
            model_routes.BookingRoom.query.filter_by(booking_id=booking_id).delete()  # Clear existing room associations
            final_price_per_night = float(data['payment_info']['pricePerNight'])
            existing_booking.final_price_per_night=final_price_per_night
            for room_data in data['rooms']:
                room_id = room_data['roomId']
                extra_persons = room_data['extraPersons']

                booking_room = model_routes.BookingRoom(
                    booking_id=booking_id,
                    room_id=room_id,
                    extra_persons=extra_persons,
                )
                model_routes.db.session.add(booking_room)

        # Commit all changes
        model_routes.db.session.commit()
        return jsonify({
            'success': True,
            'booking_id': booking_id
        }), 201

    except Exception as e:
        model_routes.db.session.rollback()
        print(f"Error updating booking: {e}")
        return {"error": "An error occurred while updating the booking."}, 500


@guest_bp.route('/api/retrieve-gst-bill-number', methods=['GET'])
def get_gst_bill_number():
    booking_id = request.args.get('bookingId')
    guest_gst_no = request.args.get('guestGSTNumber')

    print(booking_id)
    # Get the current date and fiscal year
    current_date = datetime.now()
    fiscal_year_start = current_date.year if current_date.month >= 4 else current_date.year - 1
    fiscal_year_end = fiscal_year_start + 1
    fiscal_year = f"FY{fiscal_year_start}-{fiscal_year_end}"

    # Get the current month in two-digit format
    current_month = f"{current_date.month:02d}"

    # Check if GST bill number already exists for this booking ID
    mapping = model_routes.GSTBillMapping.query.filter_by(booking_id=booking_id).first()
    print("~~~~~")
    print(mapping)

    result = []

    if mapping:
        result.append({
            'gst_bill_no': mapping.gst_bill_no,
            'guest_gst_no': mapping.guest_gst_no,
            'gst_bill_date': mapping.gst_bill_date
        })

        return jsonify({'gstDetails': result}), 200

    # Get the latest GST bill number for the current fiscal year and month
    latest_mapping = (
        model_routes.GSTBillMapping.query
        .filter(
            model_routes.GSTBillMapping.gst_bill_no.like(f"HSK/{fiscal_year}/{current_month}/%")
        )
        .order_by(model_routes.GSTBillMapping.gst_bill_no.desc())
        .first()
    )

    # Determine the next sequential number
    if latest_mapping:
        latest_number = int(latest_mapping.gst_bill_no.split('/')[-1])
        next_number = latest_number + 1
    else:
        next_number = 1  # Start from 001 if no bills exist for the current fiscal year and month

    # Format the new GST bill number
    new_gst_bill_no = f"HSK/{fiscal_year}/{current_month}/{next_number:03d}"  # Example: HSK/FY2024-25/04/001

    # Save to database
    new_mapping = model_routes.GSTBillMapping(booking_id=booking_id, gst_bill_no=new_gst_bill_no, guest_gst_no=guest_gst_no)
    model_routes.db.session.add(new_mapping)
    model_routes.db.session.commit()
    result.append({
        'gst_bill_no': new_gst_bill_no,
        'guest_gst_no': guest_gst_no,
        'gst_bill_date': datetime.utcnow()
    })

    return jsonify({'gstDetails': result}), 200



@guest_bp.route('/api/bookings-by-date-range', methods=['POST'])
def bookings_by_date_range():
    try:
        data = request.json
        start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
        end_date = datetime.strptime(data['endDate'], '%Y-%m-%d')
        print(data)
        # Fetch booking id from bill table in the date range
        # then fetch the details from booking table for those booking id
        # Fetch booking IDs from GSTBillMapping within the date range
        gst_records = model_routes.GSTBillMapping.query.filter(
            model_routes.GSTBillMapping.gst_bill_date.between(start_date, end_date)
        ).all()
        print(gst_records)
        # Extract booking IDs
        booking_ids = [record.booking_id for record in gst_records]
        print(booking_ids)
        # Fetch bookings for the extracted booking IDs
        bookings = model_routes.Booking.query.filter(model_routes.Booking.id.in_(booking_ids)).all()
        print(bookings)
        if not bookings:
            return jsonify({"message": "No bookings found in the given date range"}), 404

        booking_list = [
            {
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
                    {'amount': payment.payment_amount, 'date': payment.payment_date, 'mode': payment.payment_mode,
                     'notes': payment.notes, 'status': payment.payment_status}
                    for payment in booking.payments
                ],
                'room_details': [
                    {
                        'room_number': association.room.room_number,
                        'room_type': association.room.room_type,
                        'is_ac': association.room.is_ac,
                        'extra_persons': association.extra_persons,
                        'occupancy': association.room.occupancy
                    }
                    for association in booking.room_associations
                ],
                'gst_info': {
                    'gst_bill_no': booking.gst_bill_mapping.gst_bill_no if booking.gst_bill_mapping else None,
                    'guest_gst_no': booking.gst_bill_mapping.guest_gst_no if booking.gst_bill_mapping else None,
                    'gst_bill_date': booking.gst_bill_mapping.gst_bill_date.strftime('%Y-%m-%d') if booking.gst_bill_mapping else None,
                },
            }
            for booking in bookings
        ]
        return jsonify({"bookings": booking_list}), 200
    except Exception as e:
        print(e)
        return jsonify({"message": "Error occurred", "error": str(e)}), 500
