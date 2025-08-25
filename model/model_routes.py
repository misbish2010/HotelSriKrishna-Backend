from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from datetime import datetime

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<User(username='{self.username}', is_admin={self.is_admin})>"


# ---- Customer Table ----
class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    identity = db.Column(db.String(15), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    # Relationship to Booking
    bookings = db.relationship('Booking', back_populates='customer', cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Customer(name='{self.name}')>"


class BookingRoom(db.Model):
    __tablename__ = 'booking_rooms'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    extra_persons = db.Column(db.Integer, default=0)
    final_price_per_night = db.Column(db.Float, nullable=True)
    # Relationships
    room = db.relationship('Room', back_populates='booking_associations')
    booking = db.relationship('Booking', back_populates='room_associations')

    def __repr__(self):
        return f"<BookingRoom(booking_id={self.booking_id}, room_id={self.room_id})>"


class Room(db.Model):
    __tablename__ = 'rooms'
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), nullable=False)
    room_type = db.Column(db.String(50), nullable=False)
    occupancy = db.Column(db.String(50), nullable=False)
    is_ac = db.Column(db.Boolean, default=True)
    price_per_night = db.Column(db.Float, nullable=False)
    extra_bed_price = db.Column(db.Float, nullable=False)
    # Relationships
    booking_associations = db.relationship('BookingRoom', back_populates='room')

    def __repr__(self):
        return f"<Room(room_number='{self.room_number}')>"


# ---- Booking Table ----
class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    check_in_date = db.Column(db.DateTime, nullable=False)
    check_out_date = db.Column(db.DateTime, nullable=True)
    expected_check_out_date = db.Column(db.DateTime, nullable=True)
    duration_of_stay = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20))  # E.g., "confirmed", "canceled"
    mode = db.Column(db.String(20))  # E.g., "online", "walk-in"
    total_price = db.Column(db.Float, nullable=False)
    final_price_per_night = db.Column(db.Float, nullable=False)
    # Relationships
    customer = db.relationship('Customer', back_populates='bookings')
    payments = db.relationship('Payment', back_populates='booking', cascade="all, delete-orphan")
    room_associations = db.relationship('BookingRoom', back_populates='booking', cascade="all, delete-orphan")
    gst_bill_mapping = db.relationship('GSTBillMapping', back_populates='booking', uselist=False, cascade="all, delete-orphan")

def __repr__(self):
        return f"<Booking(id={self.id}, customer_id={self.customer_id})>"


# ---- Payment Table ----
class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    payment_amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    payment_mode = db.Column(db.String(50), nullable=False)  # e.g., "credit card", "cash", "online"
    payment_status = db.Column(db.String(50), nullable=False)  # e.g., "completed", "pending", "failed"
    notes = db.Column(db.Text, nullable=True)  # Additional information about the payment

    # Relationships
    booking = db.relationship('Booking', back_populates='payments')

    def __repr__(self):
        return f"<Payment(id={self.id}, booking_id={self.booking_id}, amount={self.payment_amount}, status={self.payment_status})>"

# ---- Expense Table ----

class GSTBillMapping(db.Model):
    __tablename__ = 'gst_bill_mapping'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), unique=True, nullable=False)
    gst_bill_no = db.Column(db.String(50), unique=True, nullable=False)
    guest_gst_no = db.Column(db.String(50))
    gst_bill_date = db.Column(db.Date, default=datetime.utcnow, nullable=False)
    guest_company_name = db.Column(db.String(100))  # ✅ New field
    # Relationship
    booking = db.relationship('Booking', back_populates='gst_bill_mapping')

    def __repr__(self):
        return f"<GSTBillMapping(booking_id={self.booking_id}, gst_bill_no={self.gst_bill_no})>"


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.utcnow, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    mode = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"<Expense(date={self.date}, amount={self.amount})>"


# ---- Staff Table ----
class Staff(db.Model):
    __tablename__ = 'staff'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # e.g., "Receptionist", "Manager"
    phone = db.Column(db.String(15), nullable=False)
    salary = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f"<Staff(name='{self.name}', role='{self.role}')>"
