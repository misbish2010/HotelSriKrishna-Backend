from model import model_routes


def get_booking_details_by_booking_id(booking_id):
    return model_routes.Booking.query.filter_by(id=booking_id).filter(
        model_routes.Booking.status.in_(['Checked-In', 'Checked-Out', 'Confirmed', 'Cancelled'])
    ).first()


def get_active_booking_details_by_booking_id(booking_id):
    return model_routes.Booking.query.filter_by(id=booking_id).filter(
        model_routes.Booking.status.in_(['Checked-In'])
    ).first()
