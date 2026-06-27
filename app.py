import os
from flask import Flask, redirect, url_for
from config import Config
from models import db, AdminUser, Border, SystemSetting


def create_app():
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    app.config.from_object(Config)

    os.makedirs(app.config.get('UPLOAD_FOLDER', 'static/uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.root_path, 'static', 'qrcodes'), exist_ok=True)

    db.init_app(app)

    import json as _json
    @app.template_filter('from_json')
    def from_json_filter(s):
        try:
            return _json.loads(s) if s else []
        except Exception:
            return []

    from samah_app import samah_bp
    from samahadmin_app import admin_bp
    app.register_blueprint(samah_bp)
    app.register_blueprint(admin_bp)

    @app.route('/')
    def root():
        return redirect('/samah/')

    with app.app_context():
        db.create_all()
        _seed_defaults()

    return app


def _seed_defaults():
    """Seed initial data if DB is empty"""
    # Admin user
    if not AdminUser.query.first():
        admin = AdminUser(
            username='admin',
            email='admin@samah.haj.ir',
            full_name='مدیر سیستم',
            role='superadmin',
            is_active=True,
        )
        admin.set_password('Admin@1234')
        db.session.add(admin)

    # Borders
    if not Border.query.first():
        borders_data = [
            ('mehran', 'مهران', 'land', True, True, 1),
            ('shalanche', 'شلمچه', 'land', True, True, 2),
            ('chazabeh', 'چذابه', 'land', True, True, 3),
            ('khosravi', 'خسروی', 'land', True, True, 4),
            ('bashmaq', 'باشماق', 'land', True, True, 5),
            ('tamarchin', 'تمرچین', 'land', True, True, 6),
            ('havai', 'هوایی', 'air', True, True, 7),
            ('daryai', 'دریایی', 'sea', True, True, 8),
        ]
        for name, name_fa, btype, is_exit, is_entry, order in borders_data:
            b = Border(name=name, name_fa=name_fa, border_type=btype,
                       is_active=True, is_exit=is_exit, is_entry=is_entry,
                       display_order=order)
            db.session.add(b)

    # Default settings
    defaults = {
        'max_group_size': ('10', 'حداکثر تعداد اعضای گروه'),
        'insurance_amount': ('500000', 'مبلغ بیمه به ریال'),
        'max_stay_days': ('10', 'حداکثر روزهای اقامت در عراق'),
        'departure_start': ('1403/06/01', 'شروع بازه خروج'),
        'departure_end': ('1403/07/15', 'پایان بازه خروج'),
        'arbaeen_date': ('1403/07/01', 'تاریخ اربعین'),
        'registration_open': ('true', 'وضعیت باز بودن ثبت نام'),
        'site_message': ('', 'پیام سراسری سایت'),
    }
    for key, (val, desc) in defaults.items():
        if not SystemSetting.query.filter_by(key=key).first():
            db.session.add(SystemSetting(key=key, value=val, description=desc))

    db.session.commit()


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
