from flask import Blueprint, jsonify, request, session
from flask_login import LoginManager, login_user, logout_user, login_required
from flask_bcrypt import check_password_hash
from model import model_routes

# Defining a blueprint
auth_bp = Blueprint(
    'auth_bp', __name__,
    template_folder='templates',
    static_folder='static'
)

login_manager = LoginManager()
login_manager.login_view = 'auth_bp.login'


@login_manager.user_loader
def load_user(user_id):
    return model_routes.User.query.get(int(user_id))


@auth_bp.route('/api/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        # Logic to handle the GET request (e.g., rendering a login page)
        return jsonify({"message": "Login page"})
    elif request.method == 'POST':
        data = request.json
        user = model_routes.User.query.filter_by(username=data['username']).first()
        if user and check_password_hash(user.password, data['password']):
            login_user(user)
            return jsonify({'message': 'Login successful', 'is_admin': user.is_admin})
        return jsonify({'error': 'Invalid credentials'}), 401


@auth_bp.route('/api/logout', methods=['POST'])
@login_required
def logout():
    # logout_user()
    session.clear()
    return jsonify({"message": "Signed out successfully"}), 200
