import os
from flask import Flask
from .db import init_db


def create_app():
    app = Flask(__name__)
    app.config['DB_PATH'] = os.environ.get('DB_PATH', '/data/navigatarr.db')
    app.config['NAVIGATARR_HOST'] = os.environ.get('NAVIGATARR_HOST', 'localhost')

    with app.app_context():
        init_db(app.config['DB_PATH'])

    return app
