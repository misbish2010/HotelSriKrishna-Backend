from flask import Blueprint, request, jsonify
from model import model_routes
import phonenumbers
from flask import request, jsonify
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, and_, or_, cast, Date
from sqlalchemy.orm import joinedload

IST = timezone(timedelta(hours=5, minutes=30))

# Defining a blueprint
guest_bp = Blueprint(
    'guest_bp', __name__,
    template_folder='templates',
    static_folder='static'
)

# ─────────────────────────────────────────────
# DEBUG HELPER  (set DEBUG_DAILY_CHART = False to silence all logs)
# ─────────────────────────────────────────────
DEBUG_DAILY_CHART = True

def _log(section: str, msg: str, data=None):
    if not DEBUG_DAILY_CHART:
        return
    separator = "─" * 60
    if data is not None:
        print(f"\n[DAILY-CHART | {section}] {msg}")
        print(f"  └─ {data}")
    else:
        print(f"\n[DAILY-CHART | {section}] {msg}")


def _log_room_header(room_number):
    if not DEBUG_DAILY_CHART:
        return
    print(f"\n{'═'*60}")
    print(f"  ROOM {room_number}")
    print(f"{'═'*60}")


def _log_booking_classify(room_number, b, label: str):
    """Log which bucket a booking was placed into."""
    if not DEBUG_DAILY_CHART:
        return
    checkin  = b.check_in_date.date() if b.check_in_date else "None"
    checkout = b.expected_check_out_date.date() if b.expected_check_out_date else "None"
    guest    = b.customer.name if b.customer else "Unknown"
    print(f"  [CLASSIFY] Room {room_number} | Booking #{b.id} | Guest: {guest} | "
          f"CheckIn: {checkin} → CheckOut: {checkout} | Status: {b.status}  →  [{label}]")


def _log_decision(room_number, status, extra: dict = None):
    if not DEBUG_DAILY_CHART:
        return
    print(f"\n  [DECISION] Room {room_number}  →  STATUS = '{status}'")
    if extra:
        for k, v in extra.items():
            print(f"    {k}: {v}")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def get_payment_summary_for_booking(db, booking_id):
    Payment = model_routes.Payment
    Booking = model_routes.Booking

    total_paid = (
        db.session.query(
            func.coalesce(func.sum(Payment.payment_amount), 0)
        )
        .filter(
            Payment.booking_id == booking_id,
            func.lower(Payment.payment_status) == "paid"
        )
        .scalar()
    )

    booking = Booking.query.get(booking_id)
    total_payable = float(booking.total_price or 0)
    pending = max(total_payable - float(total_paid or 0), 0)

    summary = {
        "total_payable": total_payable,
        "advance_paid": float(total_paid or 0),
        "pending_amount": pending,
    }
    _log("PAYMENT", f"Summary for booking #{booking_id}", summary)
    return summary


def format_name(name: str) -> str:
    if not name:
        return name
    return " ".join(word.capitalize() for word in name.strip().split())


def format_name_upper(name: str) -> str:
    if not name:
        return name
    return " ".join(word.upper() for word in name.strip().split())


def booking_active_on_date(b, target_date):
    b_checkin  = b.check_in_date.date() if b.check_in_date else None
    b_checkout = b.expected_check_out_date.date() if b.expected_check_out_date else None

    if b_checkout is None and getattr(b, "duration_of_stay", None):
        b_checkout = (b.check_in_date + timedelta(days=b.duration_of_stay)).date()

    if not b_checkin:
        return False
    if b_checkout:
        return b_checkin <= target_date < b_checkout
    return b_checkin <= target_date


def _date_only(dt):
    if dt is None:
        return None
    return dt.date() if isinstance(dt, datetime) else dt


def guest_info_from_booking(b):
    if not b or not getattr(b, "customer", None):
        return None, None
    return (
        format_name_upper(getattr(b.customer, "name", None)),
        format_name_upper(getattr(b.customer, "phone", None)),
    )


# ─────────────────────────────────────────────
# DAILY CHART ENDPOINT
# ─────────────────────────────────────────────

@guest_bp.route("/api/daily-chart", methods=["GET"])
def daily_chart():
    """
    Query param: date=YYYY-MM-DD  (required)
    Statuses: available | checked_in | new_booking | continue_checked_in |
              continue_confirmed | checkout_to_new_booking | checkout_available |
              checkout_completed_available | checkout_completed_to_new_booking
    """
    try:
        date_str = request.args.get("date")
        if not date_str:
            return jsonify({"error": "missing 'date' param (YYYY-MM-DD)"}), 400

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            return jsonify({"error": "invalid 'date' format; expected YYYY-MM-DD"}), 400

        _log("INIT", f"Daily chart requested for date = {target_date}")

        db         = model_routes.db
        Booking    = model_routes.Booking
        BookingRoom = model_routes.BookingRoom
        Room       = model_routes.Room

        # ── Load & dedupe rooms ──────────────────────────────────────
        all_rooms = Room.query.order_by(Room.room_number.asc()).all()
        unique_rooms_by_number = {}
        for r in all_rooms:
            if r.room_number not in unique_rooms_by_number:
                unique_rooms_by_number[r.room_number] = r
        rooms_list = list(unique_rooms_by_number.values())

        _log("ROOMS", f"Total rooms in DB: {len(all_rooms)} | Unique room numbers: {len(rooms_list)}",
             [r.room_number for r in rooms_list])

        # ── Overlapping bookings query ───────────────────────────────
        overlapping_br_rows = (
            db.session.query(BookingRoom)
            .join(Booking, BookingRoom.booking_id == Booking.id)
            .options(joinedload(BookingRoom.booking).joinedload(Booking.customer))
            .filter(
                Booking.status.in_(["Confirmed", "Checked-In", "Checked-Out"]),
                func.date(Booking.check_in_date) <= target_date,
                or_(
                    Booking.expected_check_out_date == None,
                    func.date(Booking.expected_check_out_date) >= target_date,
                    ),
                )
            .all()
        )

        _log("QUERY", f"Overlapping BookingRoom rows fetched: {len(overlapping_br_rows)}")
        for br in overlapping_br_rows:
            b = br.booking
            guest = b.customer.name if b.customer else "?"
            _log("QUERY",
                 f"  BookingRoom → room_id={br.room_id} | booking #{b.id} | "
                 f"guest={guest} | status={b.status} | "
                 f"checkin={b.check_in_date.date() if b.check_in_date else None} | "
                 f"checkout={b.expected_check_out_date.date() if b.expected_check_out_date else None}")

        # Map room_id → list of bookings
        overlapping_by_room = {}
        for br in overlapping_br_rows:
            overlapping_by_room.setdefault(br.room_id, []).append(br.booking)

        # Starting-today query (belt-and-suspenders for new_booking detection)
        starting_today_br_rows = (
            db.session.query(BookingRoom)
            .join(Booking, BookingRoom.booking_id == Booking.id)
            .options(joinedload(BookingRoom.booking).joinedload(Booking.customer))
            .filter(
                Booking.status.in_(["Confirmed", "Checked-In"]),
                func.date(Booking.check_in_date) == target_date,
                )
            .all()
        )
        _log("QUERY", f"Starting-today BookingRoom rows: {len(starting_today_br_rows)}")

        starting_today_by_room = {}
        for br in starting_today_br_rows:
            starting_today_by_room.setdefault(br.room_id, []).append(br.booking)

        # ── Per-room decision loop ───────────────────────────────────
        rooms_resp = []

        for room in rooms_list:
            _log_room_header(room.room_number)

            variant_ids = [r.id for r in all_rooms if r.room_number == room.room_number]
            _log("VARIANTS", f"Room {room.room_number} → DB variant ids: {variant_ids}")

            overlapping_bookings = []
            for rid in variant_ids:
                overlapping_bookings.extend(overlapping_by_room.get(rid, []))
            overlapping_bookings = list({b.id: b for b in overlapping_bookings}.values())

            _log("BOOKINGS", f"Room {room.room_number} → {len(overlapping_bookings)} overlapping booking(s)")

            # ── Response skeleton ────────────────────────────────────
            resp = {
                "room_number": room.room_number,
                "status": "available",
                "guest_name": None,
                "phone": None,
                "current_guest_name": None,
                "current_guest_phone": None,
                "next_guest_name": None,
                "next_guest_phone": None,
                "next_check_in_time": None,
                "current_check_out_time": None,
                "total_payable": None,
                "advance_paid": None,
                "pending_amount": None,
            }

            # ── Bucket variables ─────────────────────────────────────
            current_booking                = None
            same_day_booking               = None
            same_day_booking_completed     = None
            checked_in_today_booking       = None
            new_booking_today              = None
            checkout_today_booking_completed = None
            checkout_today_booking         = None
            active_bookings                = []

            # ── Classify each booking ────────────────────────────────
            for b in overlapping_bookings:
                status_norm = (b.status or "").strip().lower()
                b_checkin   = _date_only(b.check_in_date)
                b_checkout  = _date_only(b.expected_check_out_date)

                if booking_active_on_date(b, target_date):
                    active_bookings.append(b)

                # SAME-DAY (checkin == checkout == today)
                if b_checkin == target_date == b_checkout:
                    if status_norm == "checked-out":
                        same_day_booking_completed = same_day_booking_completed or b
                        _log_booking_classify(room.room_number, b, "same_day_booking_completed")
                    else:
                        same_day_booking = same_day_booking or b
                        _log_booking_classify(room.room_number, b, "same_day_booking")
                    continue

                # Spanning (strictly between: checkin < today < checkout)
                if b_checkin and b_checkout and b_checkin < target_date < b_checkout:
                    current_booking = b
                    _log_booking_classify(room.room_number, b,
                                          f"current_booking (spanning, status={b.status})")
                    continue

                # Checked-out starting today with future checkout
                if (status_norm == "checked-out" and b_checkin and b_checkout
                        and b_checkin == target_date < b_checkout):
                    checked_in_today_booking = checked_in_today_booking or b
                    _log_booking_classify(room.room_number, b, "checked_in_today_booking (checked-out, starts today)")
                    continue

                # Starts today
                if b_checkin == target_date:
                    if status_norm == "checked-in":
                        checked_in_today_booking = checked_in_today_booking or b
                        _log_booking_classify(room.room_number, b, "checked_in_today_booking (starts today)")
                    elif status_norm == "confirmed":
                        if not new_booking_today or b.check_in_date < new_booking_today.check_in_date:
                            new_booking_today = b
                            _log_booking_classify(room.room_number, b, "new_booking_today (confirmed)")
                    continue

                # Ends today
                if b_checkout == target_date:
                    if status_norm == "checked-out":
                        checkout_today_booking_completed = checkout_today_booking_completed or b
                        _log_booking_classify(room.room_number, b, "checkout_today_booking_completed")
                    if not booking_active_on_date(b, target_date):
                        checkout_today_booking = checkout_today_booking or b
                        _log_booking_classify(room.room_number, b, "checkout_today_booking")
                    continue

            # ── Summary of bucket state before decision ──────────────
            _log("BUCKETS", f"Room {room.room_number} bucket state", {
                "same_day_booking":               f"#{same_day_booking.id}" if same_day_booking else None,
                "same_day_booking_completed":      f"#{same_day_booking_completed.id}" if same_day_booking_completed else None,
                "checked_in_today_booking":        f"#{checked_in_today_booking.id}" if checked_in_today_booking else None,
                "new_booking_today":               f"#{new_booking_today.id}" if new_booking_today else None,
                "current_booking":                 f"#{current_booking.id}" if current_booking else None,
                "checkout_today_booking":          f"#{checkout_today_booking.id}" if checkout_today_booking else None,
                "checkout_today_booking_completed": f"#{checkout_today_booking_completed.id}" if checkout_today_booking_completed else None,
                "active_bookings":                 [f"#{b.id}" for b in active_bookings],
            })

            # ── Decision tree ────────────────────────────────────────

            def attach_payment(checkout_b):
                """Attach payment summary to primary room only."""
                booking_rooms = sorted(
                    checkout_b.room_associations,
                    key=lambda br: str(br.room.room_number)
                )
                primary_room_number = booking_rooms[0].room.room_number if booking_rooms else None
                _log("PAYMENT", f"Room {room.room_number} | primary room for payment = {primary_room_number}")
                if room.room_number == primary_room_number:
                    summary = get_payment_summary_for_booking(db, checkout_b.id)
                    resp.update(summary)
                else:
                    resp["total_payable"]  = None
                    resp["advance_paid"]   = None
                    resp["pending_amount"] = None

            # ─────────────────────────────────────────────────────────
            # PAYMENT RULE (applied uniformly):
            #   ✅ attach_payment → checkout expected today, NOT yet done (not Checked-Out)
            #   ❌ skip           → status == Checked-Out (_completed branches)
            # ─────────────────────────────────────────────────────────

            # 0) HIGHEST PRIORITY: someone already checked in today
            #    A live guest in the room always wins over any completed checkout record
            # 0) HIGHEST PRIORITY: someone checked in today
            if checked_in_today_booking:
                resp["status"] = "checked_in"
                cur_name, cur_phone = guest_info_from_booking(checked_in_today_booking)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone)
                _log_decision(room.room_number, resp["status"], {"current": cur_name})

            # 1) SECOND PRIORITY: continuing stay (checked in before today, still here)
            #    Must be above all _completed branches — live guest always wins
            elif current_booking and (current_booking.status or "").lower() == "checked-in":
                resp["status"] = "continue_checked_in"
                cur_name, cur_phone = guest_info_from_booking(current_booking)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone)
                _log_decision(room.room_number, resp["status"], {"current": cur_name})

            # 2) Same-day + new booking arriving (checkout still pending)
            elif same_day_booking and new_booking_today and same_day_booking.id != new_booking_today.id:
                resp["status"] = "checkout_to_new_booking"
                cur_name, cur_phone = guest_info_from_booking(same_day_booking)
                nxt_name, nxt_phone = guest_info_from_booking(new_booking_today)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone,
                            next_guest_name=nxt_name, next_guest_phone=nxt_phone,
                            current_check_out_time=same_day_booking.expected_check_out_date,
                            next_check_in_time=new_booking_today.check_in_date)
                attach_payment(same_day_booking)
                _log_decision(room.room_number, resp["status"],
                              {"current": cur_name, "next": nxt_name})

            # 3) Same-day only (checkout still pending)
            elif same_day_booking:
                resp["status"] = "checkout_available"
                cur_name, cur_phone = guest_info_from_booking(same_day_booking)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone,
                            current_check_out_time=same_day_booking.expected_check_out_date)
                attach_payment(same_day_booking)
                _log_decision(room.room_number, resp["status"], {"current": cur_name})

            # 4) Same-day already Checked-Out + new booking
            elif same_day_booking_completed and new_booking_today and same_day_booking_completed.id != new_booking_today.id:
                resp["status"] = "checkout_completed_to_new_booking"
                cur_name, cur_phone = guest_info_from_booking(same_day_booking_completed)
                nxt_name, nxt_phone = guest_info_from_booking(new_booking_today)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone,
                            next_guest_name=nxt_name, next_guest_phone=nxt_phone,
                            current_check_out_time=same_day_booking_completed.expected_check_out_date,
                            next_check_in_time=new_booking_today.check_in_date)
                _log_decision(room.room_number, resp["status"],
                              {"current": cur_name, "next": nxt_name})

            # 5) Same-day already Checked-Out, room free
            elif same_day_booking_completed:
                resp["status"] = "checkout_completed_available"
                cur_name, cur_phone = guest_info_from_booking(same_day_booking_completed)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone,
                            current_check_out_time=same_day_booking_completed.expected_check_out_date)
                _log_decision(room.room_number, resp["status"], {"current": cur_name})

            # 6) Checkout already done (Checked-Out) + new booking arriving
            elif checkout_today_booking_completed and new_booking_today and checkout_today_booking_completed.id != new_booking_today.id:
                resp["status"] = "checkout_completed_to_new_booking"
                cur_name, cur_phone = guest_info_from_booking(checkout_today_booking_completed)
                nxt_name, nxt_phone = guest_info_from_booking(new_booking_today)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone,
                            next_guest_name=nxt_name, next_guest_phone=nxt_phone,
                            current_check_out_time=checkout_today_booking_completed.expected_check_out_date,
                            next_check_in_time=new_booking_today.check_in_date)
                _log_decision(room.room_number, resp["status"],
                              {"current": cur_name, "next": nxt_name})

            # 7) Checkout already done (Checked-Out), room free
            elif checkout_today_booking_completed:
                resp["status"] = "checkout_completed_available"
                cur_name, cur_phone = guest_info_from_booking(checkout_today_booking_completed)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone,
                            current_check_out_time=checkout_today_booking_completed.expected_check_out_date)
                _log_decision(room.room_number, resp["status"], {"current": cur_name})

            # 8) Checkout pending today + new booking arriving
            elif checkout_today_booking and new_booking_today and checkout_today_booking.id != new_booking_today.id:
                resp["status"] = "checkout_to_new_booking"
                cur_name, cur_phone = guest_info_from_booking(checkout_today_booking)
                nxt_name, nxt_phone = guest_info_from_booking(new_booking_today)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone,
                            next_guest_name=nxt_name, next_guest_phone=nxt_phone,
                            current_check_out_time=checkout_today_booking.expected_check_out_date,
                            next_check_in_time=new_booking_today.check_in_date)
                attach_payment(checkout_today_booking)
                _log_decision(room.room_number, resp["status"],
                              {"current": cur_name, "next": nxt_name})

            # 9) Continuing stay — confirmed but not checked in yet
            elif current_booking:
                resp["status"] = "continue_confirmed"
                cur_name, cur_phone = guest_info_from_booking(current_booking)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone)
                _log_decision(room.room_number, resp["status"], {"current": cur_name})

            # 10) New booking arriving today (room currently empty)
            elif new_booking_today:
                resp["status"] = "new_booking"
                nxt_name, nxt_phone = guest_info_from_booking(new_booking_today)
                resp.update(next_guest_name=nxt_name, next_guest_phone=nxt_phone,
                            next_check_in_time=new_booking_today.check_in_date)
                _log_decision(room.room_number, resp["status"], {"next": nxt_name})

            # 11) Checkout pending today, no incoming guest
            elif checkout_today_booking:
                resp["status"] = "checkout_available"
                cur_name, cur_phone = guest_info_from_booking(checkout_today_booking)
                resp.update(current_guest_name=cur_name, current_guest_phone=cur_phone,
                            current_check_out_time=checkout_today_booking.expected_check_out_date)
                attach_payment(checkout_today_booking)
                _log_decision(room.room_number, resp["status"], {"current": cur_name})

            # 12) Truly available
            else:
                resp["status"] = "available"
                _log_decision(room.room_number, "available")

            # ── Conflict detection ───────────────────────────────────
            if len(active_bookings) > 1:
                resp["conflict"] = True
                resp["conflict_bookings"] = [
                    {
                        "booking_id": b.id,
                        "guest_name": format_name_upper(b.customer.name) if b.customer else None,
                        "phone": b.customer.phone if b.customer else None,
                        "status": b.status,
                        "check_in": b.check_in_date,
                        "check_out": b.expected_check_out_date,
                    }
                    for b in active_bookings
                ]
                _log("CONFLICT", f"⚠️  Room {room.room_number} has {len(active_bookings)} active bookings!",
                     [f"#{b.id}" for b in active_bookings])
            else:
                resp["conflict"] = False
                resp["conflict_bookings"] = []

            rooms_resp.append(resp)

        rooms_resp = sorted(rooms_resp, key=lambda x: str(x["room_number"]))
        _log("DONE", f"Returning {len(rooms_resp)} rooms for date {target_date}")
        return jsonify({"date": target_date.strftime("%Y-%m-%d"), "rooms": rooms_resp}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"name": format_name_upper(existing_customer.name),
                        "address": format_name_upper(existing_customer.address),
                        "email": existing_customer.email,
                        "phone": existing_customer.phone,
                        "identity": existing_customer.identity}), 201

    return jsonify({"error": "No Customer Details Found"}), 201


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
            amount = p.get("amount", 0)

            # 🚫 Skip zero-amount entries
            if not amount or float(amount) == 0:
                continue

            payment_date = None
            if p.get("date"):
                try:
                    payment_date = datetime.strptime(p["date"], "%Y-%m-%d")
                except Exception:
                    payment_date = datetime.utcnow()

            payment = model_routes.Payment(
                booking_id=booking.id,
                payment_amount=amount,
                payment_date=payment_date or datetime.utcnow(),
                payment_mode=p.get("mode", ""),
                payment_status=p.get("status", "Paid"),
                notes=p.get("notes", "")
            )
            model_routes.db.session.add(payment)


        model_routes.db.session.commit()
        return jsonify({"success": True, "booking_id": booking.id})

    except Exception as e:
        model_routes.db.session.rollback()
        print("Error during booking creation:", str(e))
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


@guest_bp.route('/api/available-rooms-modify', methods=['GET'])
def check_available_rooms_for_modify():
    try:
        duration_of_stay = int(request.args.get('durationOfStay'))
        target_check_in_date = datetime.strptime(
            request.args.get('checkInDateTime'), '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        target_expected_check_out_date = datetime.strptime(
            request.args.get('probableCheckOutDateTime'), '%Y-%m-%dT%H:%M:%S.%fZ'
        )
        exclude_booking_id = request.args.get('excludeBookingId', type=int)

        # Only Checked-In bookings should block rooms
        active_bookings = model_routes.Booking.query.filter(
            model_routes.Booking.status.in_(["Confirmed", "Checked-In"])
        )

        if exclude_booking_id:
            active_bookings = active_bookings.filter(model_routes.Booking.id != exclude_booking_id)

        active_bookings = active_bookings.all()

        checkedin_rooms = set()  # Fully blocked rooms
        reserved_rooms_status = {}  # For confirmed rooms marking

        for booking in active_bookings:
            if (
                    booking.check_in_date < target_expected_check_out_date and
                    booking.expected_check_out_date > target_check_in_date
            ):
                for room_association in booking.room_associations:
                    room = room_association.room

                    if booking.status == "Checked-In":
                        checkedin_rooms.add(room.id)
                    elif booking.status == "Confirmed":
                        reserved_rooms_status[room.id] = True

        all_rooms = model_routes.Room.query.all()

        rooms = []
        for room in all_rooms:
            # Skip only Checked-In rooms
            if room.id in checkedin_rooms:
                continue

            rooms.append({
                'room_id': room.id,
                'room_number': room.room_number,
                'room_type': room.room_type,
                'occupancy': room.occupancy,
                'is_ac': room.is_ac,
                'room_price': room.price_per_night,
                'extra_bed_price': room.extra_bed_price,
                'is_reserved': reserved_rooms_status.get(room.id, False)  # Mark reserved
            })

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
            'name': format_name_upper(booking.customer.name),
            'phone': booking.customer.phone,
            'identity': booking.customer.identity,
            'address': format_name_upper(booking.customer.address),
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
            if p.payment_amount and p.payment_amount != 0
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
            'guest_company_name': format_name_upper(guest_company_name)
        }
    }]
    return jsonify({'bookingDetails': result}), 200


@guest_bp.route('/api/update-booking', methods=['POST'])
def update_booking():
    try:
        data = request.get_json()

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
                amount = p.get('amount', 0)

                # ❌ Skip zero-amount payments
                if not amount or float(amount) == 0:
                    continue
                payment_date = p.get('date')
                if isinstance(payment_date, str):
                    try:
                        payment_date = datetime.strptime(payment_date, "%Y-%m-%d")
                    except ValueError:
                        payment_date = datetime.utcnow()

                status = (p.get('status') or '').strip() or 'Paid'
                payment = model_routes.Payment(
                    booking_id=booking.id,
                    payment_amount=abs(amount),
                    payment_date=payment_date or datetime.utcnow(),
                    payment_mode=p.get('mode'),
                    notes=p.get('notes', ''),
                    payment_status=status
                )
                model_routes.db.session.add(payment)

        model_routes.db.session.commit()
        return jsonify({"success": True, "message": "Booking updated successfully"})


    except Exception as e:
        model_routes.db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@guest_bp.route("/api/bookings/<int:booking_id>/gst-invoice", methods=["GET"])
def get_or_create_invoice(booking_id):

    # 1️⃣ Check existing invoice
    invoice = model_routes.GSTBillMapping.query.filter_by(booking_id=booking_id).first()
    if invoice:
        return jsonify({
            "gst_bill_no": invoice.gst_bill_no,
            "gst_bill_date": invoice.gst_bill_date.strftime("%Y-%m-%d")
        }), 200

    # 2️⃣ Fetch booking
    booking = model_routes.Booking.query.get_or_404(booking_id)

    if not booking.expected_check_out_date:
        return jsonify({"message": "Checkout date not available"}), 400

    invoice_date = booking.expected_check_out_date.date()  # 🔑 KEY CHANGE

    # 3️⃣ Financial year calculation
    fy_start = invoice_date.year if invoice_date.month >= 4 else invoice_date.year - 1
    fy_end = fy_start + 1
    fiscal_year = f"{str(fy_start)[-2:]}-{str(fy_end)[-2:]}" #25-26

    month = f"{invoice_date.month:02d}"

    # 4️⃣ Get last invoice of same FY + month
    last_invoice = (
        model_routes.GSTBillMapping.query
        .filter(model_routes.GSTBillMapping.gst_bill_no.like(f"HSK/{fiscal_year}/{month}/%"))
        .order_by(model_routes.GSTBillMapping.gst_bill_no.desc())
        .first()
    )

    if last_invoice:
        last_number = int(last_invoice.gst_bill_no.split("/")[-1])
        next_number = last_number + 1
    else:
        next_number = 1

    # 5️⃣ Generate GST bill number
    gst_bill_no = f"HSK/{fiscal_year}/{month}/{next_number:03d}"

    # 6️⃣ Save mapping
    new_mapping = model_routes.GSTBillMapping(
        booking_id=booking_id,
        gst_bill_no=gst_bill_no,
        gst_bill_date=invoice_date  # 🔑 checkout date
    )

    model_routes.db.session.add(new_mapping)
    model_routes.db.session.commit()

    return jsonify({
        "gst_bill_no": gst_bill_no,
        "gst_bill_date": invoice_date.strftime("%Y-%m-%d")
    }), 200


@guest_bp.route("/api/bookings/<int:booking_id>/gst-invoice", methods=["DELETE"])
def delete_gst_invoice(booking_id):
    invoice = model_routes.GSTBillMapping.query.filter_by(booking_id=booking_id).first()

    if not invoice:
        return jsonify({"message": "No GST invoice found for this booking"}), 404

    model_routes.db.session.delete(invoice)
    model_routes.db.session.commit()

    return jsonify({"message": "GST invoice deleted successfully"}), 200


# ✅ Room Dashboard API with Full Booking Details
@guest_bp.route('/api/room/dashboard', methods=['GET'])
def check_rooms_dashboard():
    try:
        # 1️⃣ Parse UTC from UI
        start_dt_utc = datetime.strptime(
            request.args.get('startDate'),
            '%Y-%m-%dT%H:%M:%S.%fZ'
        ).replace(tzinfo=timezone.utc)

        end_dt_utc = datetime.strptime(
            request.args.get('endDate'),
            '%Y-%m-%dT%H:%M:%S.%fZ'
        ).replace(tzinfo=timezone.utc)

        # 2️⃣ Convert to IST
        start_dt_ist = start_dt_utc.astimezone(IST)
        end_dt_ist = end_dt_utc.astimezone(IST)

        # 3️⃣ Extract DATE boundaries (IST)
        start_date = start_dt_ist.date()
        end_date = end_dt_ist.date()

        # 4️⃣ NIGHT-OVERLAP RANGE (critical logic)
        range_start = datetime.combine(start_date, datetime.min.time())
        range_end = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

        # 5️⃣ Overlap condition (hotel-correct)
        bookings = model_routes.Booking.query.filter(
            model_routes.Booking.check_in_date < range_end,
            model_routes.Booking.expected_check_out_date > range_start
        ).order_by(
            model_routes.Booking.expected_check_out_date.asc()
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
                    'name': format_name_upper(booking.customer.name),
                    'phone': booking.customer.phone,
                    'identity': booking.customer.identity,
                    'address': format_name_upper(booking.customer.address),
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
                    if p.payment_status != "Discount"
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
                    'guest_company_name': format_name_upper(guest_company_name)
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
    try:
        # -------------------------------
        # 1️⃣ Parse request (UTC → IST)
        # -------------------------------
        checkin_utc = datetime.strptime(
            request.args.get('checkInDateTime'),
            '%Y-%m-%dT%H:%M:%S.%fZ'
        ).replace(tzinfo=timezone.utc)

        booking_window_hours = int(request.args.get('booking_window'))

        requested_start = checkin_utc.astimezone(IST).replace(tzinfo=None)
        requested_end = requested_start + timedelta(hours=booking_window_hours)

        # -------------------------------
        # 2️⃣ Fetch ACTIVE bookings only
        # -------------------------------
        active_bookings = model_routes.Booking.query.filter(
            model_routes.Booking.status.in_(["Confirmed", "Checked-In"])
        ).all()

        blocked_room_numbers = set()
        booked_rooms_details = {}

        # -------------------------------
        # 3️⃣ Overlap detection (CORE)
        # -------------------------------
        for booking in active_bookings:
            booking_start = booking.check_in_date
            booking_end = booking.expected_check_out_date or booking.check_out_date

            if not booking_start or not booking_end:
                continue

            # 🔑 OVERLAP RULE
            if booking_start < requested_end and booking_end > requested_start:
                for assoc in booking.room_associations:
                    room = assoc.room
                    blocked_room_numbers.add(room.room_number)

                    if room.room_number not in booked_rooms_details:
                        booked_rooms_details[room.room_number] = {
                            'room_number': room.room_number,
                            'room_type': room.room_type,
                            'is_ac': room.is_ac,
                            'occupancy': room.occupancy,
                            'bookings': []
                        }

                    booked_rooms_details[room.room_number]['bookings'].append({
                        'booking_id': booking.id,
                        'customer_name': format_name_upper(booking.customer.name),
                        'customer_contact': booking.customer.phone,
                        'check_in_date': booking_start,
                        'expected_check_out_date': booking_end,
                        'booking_status': booking.status,
                        'final_price_per_night': booking.final_price_per_night
                    })

        # -------------------------------
        # 4️⃣ Available rooms
        # -------------------------------
        all_rooms = model_routes.Room.query.all()

        available_rooms = [
            {
                'room_number': room.room_number,
                'room_type': room.room_type,
                'is_ac': room.is_ac,
                'occupancy': room.occupancy
            }
            for room in all_rooms
            if room.room_number not in blocked_room_numbers
        ]

        return jsonify({
            'requested_window': {
                'from': requested_start,
                'to': requested_end
            },
            'booked_rooms': list(booked_rooms_details.values()),
            'available_rooms': available_rooms
        }), 200

    except Exception as e:
        print("❌ Room status error:", e)
        return jsonify({'error': str(e)}), 500


@guest_bp.route('/api/get_payment', methods=['GET'])
def get_payments_by_date():
    # Parse dates from request
    # Parse incoming UTC datetimes
    start_dt_utc = datetime.strptime(
        request.args.get('startDate'),
        '%Y-%m-%dT%H:%M:%S.%fZ'
    ).replace(tzinfo=timezone.utc)

    end_dt_utc = datetime.strptime(
        request.args.get('endDate'),
        '%Y-%m-%dT%H:%M:%S.%fZ'
    ).replace(tzinfo=timezone.utc)

    # Convert to IST
    start_dt_ist = start_dt_utc.astimezone(IST)
    end_dt_ist = end_dt_utc.astimezone(IST)

    # Extract dates (IST-correct)
    start_date = start_dt_ist.date()
    end_date = end_dt_ist.date()

    # Full-day boundaries (IST, stored as naive)
    start_of_day = datetime.combine(start_date, datetime.min.time())
    end_of_day = datetime.combine(end_date, datetime.max.time())

    # Expenses
    # --------------------
    expenses = (
        model_routes.Expense.query
        .filter(model_routes.Expense.date.between(start_date, end_date))
        .all()
    )

    # --------------------
    # Paid Payments (aggregated by booking + mode)
    # --------------------
    payment_subq = (
        model_routes.db.session.query(
            model_routes.Payment.booking_id.label('booking_id'),
            model_routes.Payment.payment_mode.label('payment_mode'),
            model_routes.Payment.payment_status.label('payment_status'),
            func.sum(model_routes.Payment.payment_amount).label('amount'),
            func.max(model_routes.Payment.payment_date).label('payment_date')
        )
        .filter(
            model_routes.Payment.payment_date.between(start_of_day, end_of_day),
            ~func.lower(model_routes.Payment.payment_status).in_(["discount", "pending"]),
            ~func.lower(model_routes.Payment.notes).in_(["Pending"])
        )
        .group_by(
            model_routes.Payment.booking_id,
            model_routes.Payment.payment_mode,
            model_routes.Payment.payment_status
        )
        .subquery()
    )

    paid_results = (
        model_routes.db.session.query(
            model_routes.Booking.id.label('booking_id'),
            model_routes.Booking.status.label('booking_status'),
            model_routes.Booking.check_in_date.label('booking_date'),
            model_routes.Customer.name.label('customer_name'),
            model_routes.Customer.phone.label('contact_number'),
            payment_subq.c.payment_mode,
            payment_subq.c.payment_status,
            payment_subq.c.amount,
            payment_subq.c.payment_date,
            func.group_concat(model_routes.Room.room_number).label('room_numbers')
        )
        .join(model_routes.Customer, model_routes.Booking.customer_id == model_routes.Customer.id)
        .join(payment_subq, model_routes.Booking.id == payment_subq.c.booking_id)
        .join(model_routes.BookingRoom, model_routes.Booking.id == model_routes.BookingRoom.booking_id)
        .join(model_routes.Room, model_routes.BookingRoom.room_id == model_routes.Room.id)
        .group_by(
            model_routes.Booking.id,
            model_routes.Booking.status,
            model_routes.Customer.name,
            model_routes.Customer.phone,
            payment_subq.c.payment_mode,
            payment_subq.c.payment_status
        )
        .order_by(func.min(model_routes.Room.room_number))
        .all()
    )

    # --------------------
    # Pending Payments
    # --------------------
    checked_in_bookings = (
        model_routes.db.session.query(
            model_routes.Booking,
            model_routes.Customer.name.label("customer_name"),
            model_routes.Customer.phone.label("contact_number"),
            func.group_concat(model_routes.Room.room_number).label("room_numbers")
        )
        .join(model_routes.Customer, model_routes.Booking.customer_id == model_routes.Customer.id)
        .join(model_routes.BookingRoom, model_routes.Booking.id == model_routes.BookingRoom.booking_id)
        .join(model_routes.Room, model_routes.BookingRoom.room_id == model_routes.Room.id)
        .filter(model_routes.Booking.status.in_(["Checked-In"]))
        .group_by(model_routes.Booking.id)
        .order_by(func.min(model_routes.Room.room_number))
        .all()
    )

    checked_out_pending = (
        model_routes.db.session.query(
            model_routes.Booking.id.label("booking_id"),
            model_routes.Booking.status.label("booking_status"),
            model_routes.Booking.check_in_date,
            model_routes.Booking.expected_check_out_date.label("checkout_date"),
            model_routes.Customer.name.label("customer_name"),
            model_routes.Customer.phone.label("contact_number"),
            func.group_concat(model_routes.Room.room_number).label("room_numbers"),
            func.sum(model_routes.Payment.payment_amount).label("pending_amount")
        )
        .join(model_routes.Payment, model_routes.Booking.id == model_routes.Payment.booking_id)
        .join(model_routes.Customer, model_routes.Booking.customer_id == model_routes.Customer.id)
        .join(model_routes.BookingRoom, model_routes.Booking.id == model_routes.BookingRoom.booking_id)
        .join(model_routes.Room, model_routes.BookingRoom.room_id == model_routes.Room.id)
        .filter(
            model_routes.Booking.status == "Checked-Out",
            func.lower(func.coalesce(model_routes.Payment.notes, "")) == "pending"
        )
        .group_by(model_routes.Booking.id)
        .order_by(func.min(model_routes.Room.room_number))
        .all()
    )
    today = datetime.utcnow().date()
    #today = end_of_day.date()   # IMPORTANT → use TO_DATE
    pending_payment_details = []

    for row in checked_in_bookings:
        booking = row.Booking
        check_in_date = booking.check_in_date.date()

        effective_end_date = min(
            today,
            booking.expected_check_out_date.date()
            if booking.expected_check_out_date else today
        )

        total_paid = (
            model_routes.db.session.query(
                func.coalesce(func.sum(model_routes.Payment.payment_amount), 0)
            )
            .filter(
                model_routes.Payment.booking_id == booking.id,
                #model_routes.Payment.payment_status != "Discount",
                func.lower(model_routes.Payment.payment_status) != "discount",
                model_routes.Payment.payment_date <= end_of_day
            )
            .scalar()
        )
        checkin_start = datetime.combine(
            booking.check_in_date,
            datetime.min.time()
        )

        advance_paid = (
            model_routes.db.session.query(
                func.coalesce(func.sum(model_routes.Payment.payment_amount), 0)
            )
            .filter(
                model_routes.Payment.booking_id == booking.id,
                func.lower(model_routes.Payment.payment_status) == "paid",
                model_routes.Payment.payment_date < checkin_start
            )
            .scalar()
        )
        agreed_price_per_night = (
            model_routes.db.session.query(
                func.coalesce(func.sum(model_routes.BookingRoom.final_price_per_night), 0)
            )
            .filter(
                model_routes.BookingRoom.booking_id == booking.id
            )
            .scalar()
        )
        nights = max((effective_end_date - check_in_date).days + 1, 1)
        calculated_charge = agreed_price_per_night * nights
        pending_amount = calculated_charge - total_paid

        if pending_amount > 0:
            pending_payment_details.append({
                "booking_id": booking.id,
                "booking_status": booking.status,
                "check_in_date": booking.check_in_date,
                "customer_name": format_name_upper(row.customer_name),
                "contact_number": row.contact_number,
                "net_pending_amount": round(pending_amount,2),
                "advance_paid": round(advance_paid, 2),
                "agreed_price_per_night": round(agreed_price_per_night, 2),
                "room_numbers": row.room_numbers.split(",")
            })
    for row in checked_out_pending:
        booking = model_routes.Booking.query.get(row.booking_id)

        if not booking or not booking.expected_check_out_date:
            continue

        # -----------------------------
        # Advance paid (before check-in)
        # -----------------------------
        checkin_start = datetime.combine(
            booking.check_in_date,
            datetime.min.time()
        )

        advance_paid = (
            model_routes.db.session.query(
                func.coalesce(func.sum(model_routes.Payment.payment_amount), 0)
            )
            .filter(
                model_routes.Payment.booking_id == booking.id,
                func.lower(model_routes.Payment.payment_status) == "paid",
                model_routes.Payment.payment_date < checkin_start
            )
            .scalar()
        )

        # -----------------------------
        # FINAL payable (booking-level)
        # -----------------------------
        total_payable = booking.total_price or 0

        # -----------------------------
        # Paid till CHECKOUT DATE ONLY
        # -----------------------------
        total_paid_till_checkout = (
            model_routes.db.session.query(
                func.coalesce(func.sum(model_routes.Payment.payment_amount), 0)
            )
            .filter(
                model_routes.Payment.booking_id == booking.id,
                func.lower(model_routes.Payment.payment_status).in_(["paid", "discount"]),
                model_routes.Payment.payment_date <= booking.expected_check_out_date
            )
            .scalar()
        )

        net_pending_amount = round(
            total_payable - total_paid_till_checkout,
            2
        )

        if net_pending_amount > 0:
            pending_payment_details.append({
                "booking_id": booking.id,
                "booking_status": booking.status,
                "check_in_date": booking.check_in_date,
                "customer_name": format_name_upper(row.customer_name),
                "contact_number": row.contact_number,
                "net_pending_amount": net_pending_amount,
                "advance_paid": round(advance_paid, 2),
                "total_payable": round(total_payable, 2),
                "note": "Pending",
                "room_numbers": row.room_numbers.split(",")
            })


    # --------------------
    # Format for JSON
    # --------------------
    payment_details = [
        {
            "booking_id": row.booking_id,
            "booking_status": row.booking_status,  # Added
            "check_in_date": row.booking_date,
            "customer_name": format_name_upper(row.customer_name),
            "contact_number": row.contact_number,
            "payment_mode": row.payment_mode.upper(),
            "payment_status": row.payment_status,
            "amount": row.amount,
            "payment_date": row.payment_date,
            "room_numbers": row.room_numbers.split(',') if row.room_numbers else []
        }
        for row in paid_results
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
    # --------------------
    # Advance Adjusted Today
    # --------------------
    adjusted_payment_details = []

    adjusted_payment_details = []

    all_bookings_with_payments = (
        model_routes.db.session.query(model_routes.Booking)
        .join(model_routes.Payment)
        .filter(
            func.lower(model_routes.Payment.payment_status) == "paid",
            model_routes.Booking.check_in_date >= start_of_day,
            model_routes.Booking.check_in_date <= end_of_day
        )
        .distinct()
        .all()
    )

    for booking in all_bookings_with_payments:

        # Detect CHECK-IN TODAY
        if not (start_of_day <= booking.check_in_date <= end_of_day):
            continue

        checkin_start = datetime.combine(
            booking.check_in_date.date(),
            datetime.min.time()
        )

        advance_payments = (
            model_routes.db.session.query(model_routes.Payment)
            .filter(
                model_routes.Payment.booking_id == booking.id,
                func.lower(model_routes.Payment.payment_status) == "paid",
                model_routes.Payment.payment_date < checkin_start
            )
            .order_by(model_routes.Payment.payment_date.asc())
            .all()
        )

        total_advance_before_checkin = sum(
            p.payment_amount for p in advance_payments if p.payment_amount > 0
        )

        if total_advance_before_checkin <= 0:
            continue

        adjusted_payment_details.append({
            "booking_id": booking.id,
            "customer_name": format_name_upper(booking.customer.name),
            "contact_number": booking.customer.phone,
            "total_advance": round(total_advance_before_checkin, 2),
            "advance_payments": [
                {
                    "mode": p.payment_mode,
                    "amount": p.payment_amount,
                    "date": p.payment_date.strftime("%Y-%m-%d")
                }
                for p in advance_payments
            ],
            "adjusted_on": booking.check_in_date,
            "check_in_date": booking.check_in_date,
            "room_numbers": [
                br.room.room_number for br in booking.room_associations
            ]
        })
    return jsonify({
        "payment_details": payment_details,
        "pending_payment_details": pending_payment_details,
        "expense_details": expense_details,
        "adjusted_payment_details": adjusted_payment_details
    }), 200


@guest_bp.route('/api/bookings-by-date-range', methods=['POST'])
def bookings_by_date_range():
    try:
        data = request.json
        start_date = datetime.strptime(data['startDate'], '%Y-%m-%d')
        end_date = datetime.strptime(data['endDate'], '%Y-%m-%d')

        range_type = data.get('rangeType', 'custom')  # monthly / quarterly / custom

        # --- Handle Monthly / Quarterly ---
        if range_type == 'monthly':
            # Align start to 1st of month, end to last day of month
            start_date = start_date.replace(day=1)
            from calendar import monthrange
            last_day = monthrange(start_date.year, start_date.month)[1]
            end_date = end_date.replace(day=last_day)

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
            .filter(
                model_routes.GSTBillMapping.gst_bill_date >= start_date.date(),
                model_routes.GSTBillMapping.gst_bill_date <= end_date.date()
            )
            .order_by(model_routes.GSTBillMapping.gst_bill_no.asc())
            .all()
        )

        if not gst_records:
            return jsonify({"bookings": []}), 200

        booking_ids = [record.booking_id for record in gst_records]

        # --- Fetch bookings that match those IDs ---
        # Create a map: booking_id -> gst_record
        gst_map = {record.booking_id: record for record in gst_records}

        bookings = (
            model_routes.Booking.query
            .filter(model_routes.Booking.id.in_(booking_ids))
            .all()
        )

        # 🔑 Sort bookings by GST bill number
        bookings.sort(
            key=lambda b: gst_map[b.id].gst_bill_no
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
                    'name': format_name_upper(booking.customer.name) if booking.customer else None,
                    'phone': booking.customer.phone if booking.customer else None,
                    'identity': booking.customer.identity if booking.customer else None,
                    'address': format_name_upper(booking.customer.address) if booking.customer else None,
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
                    'guest_company_name': format_name_upper(booking.gst_bill_mapping.guest_company_name) if booking.gst_bill_mapping else None,
                },
            })

        return jsonify({"bookings": booking_list}), 200

    except Exception as e:
        print("Error in bookings_by_date_range:", e)
        return jsonify({"message": "Error occurred", "error": str(e)}), 500


@guest_bp.route('/api/add_expense', methods=['POST'])
def add_expense():
    data = request.get_json()
    date = datetime.strptime(data['date'], '%Y-%m-%d')
    description = data['description']
    amount = data['amount']
    mode = data['mode']

    existing_expense = model_routes.Expense.query.filter_by(date=date, description=description).first()
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
