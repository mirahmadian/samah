from flask import Blueprint

admin_bp = Blueprint('samahadmin', __name__, url_prefix='/samahadmin',
                     template_folder='../templates/samahadmin',
                     static_folder='../static')

from . import routes  # noqa
