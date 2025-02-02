"""Initialize Flask app."""
from flask import Flask
from flask_migrate import Migrate
from flask_cors import CORS

migrate = Migrate()


def create_app():
    """Create Flask application."""
    app = Flask(__name__, instance_relative_config=False)
    #app.config['SERVER_NAME'] = 'hotelsrikrishna:8000'
    CORS(app)
    app.config.from_object('config.Config')
    app._static_folder = 'admin/static'

    with app.app_context():
        from model import model_routes
        from auth import auth_routes
        model_routes.db.init_app(app)
        migrate.init_app(app, model_routes.db)
        auth_routes.login_manager.init_app(app)

    # Import parts of our application
        model_routes.db.create_all()

        from admin import admin_routes
        from auth import auth_routes
        from guest import guest_routes
        # Register Blueprints
        app.register_blueprint(admin_routes.admin_bp)
        app.register_blueprint(auth_routes.auth_bp)
        app.register_blueprint(guest_routes.guest_bp)
        return app


application = create_app()

if __name__ == "__main__":
    application.run(debug=True)
