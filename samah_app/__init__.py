from flask import Blueprint

samah_bp = Blueprint('samah', __name__, url_prefix='/samah',
                     template_folder='../templates/samah',
                     static_folder='../static')

from . import routes  # noqa
