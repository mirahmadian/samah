from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class AdminUser(UserMixin, db.Model):
    __tablename__ = 'admin_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(128))
    role = db.Column(db.String(32), default='operator')  # superadmin, admin, operator, viewer
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Border(db.Model):
    __tablename__ = 'borders'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    name_fa = db.Column(db.String(64), nullable=False)
    border_type = db.Column(db.String(32), default='land')  # land, air, sea
    is_active = db.Column(db.Boolean, default=True)
    is_exit = db.Column(db.Boolean, default=True)
    is_entry = db.Column(db.Boolean, default=True)
    max_daily_capacity = db.Column(db.Integer, default=0)
    display_order = db.Column(db.Integer, default=0)


class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.String(256))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        s = SystemSetting.query.filter_by(key=key).first()
        return s.value if s else default

    @staticmethod
    def set(key, value, description=None):
        s = SystemSetting.query.filter_by(key=key).first()
        if s:
            s.value = value
            s.updated_at = datetime.utcnow()
        else:
            s = SystemSetting(key=key, value=value, description=description)
            db.session.add(s)
        db.session.commit()


class PilgrimGroup(db.Model):
    __tablename__ = 'pilgrim_groups'
    id = db.Column(db.Integer, primary_key=True)
    group_code = db.Column(db.String(20), unique=True, nullable=False)
    head_member_id = db.Column(db.Integer, db.ForeignKey('pilgrims.id'), nullable=True)
    exit_border_id = db.Column(db.Integer, db.ForeignKey('borders.id'))
    entry_border_id = db.Column(db.Integer, db.ForeignKey('borders.id'))
    departure_date = db.Column(db.String(10))  # Shamsi date YYYY/MM/DD
    return_date = db.Column(db.String(10))
    transport_to_border = db.Column(db.String(32))  # personal, bus, minibus, taxi, train
    transport_return = db.Column(db.String(32))
    vehicle_plates = db.Column(db.Text)  # JSON list of plates
    offer_ride = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(32), default='draft')  # draft, pending_payment, paid, cancelled
    province = db.Column(db.String(64))
    city = db.Column(db.String(64))
    address = db.Column(db.Text)
    postal_code = db.Column(db.String(10))
    phone_landline = db.Column(db.String(15))
    total_amount = db.Column(db.Integer, default=0)  # in Rials
    payment_ref = db.Column(db.String(64))
    payment_date = db.Column(db.DateTime)
    receipt_printed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    exit_border = db.relationship('Border', foreign_keys=[exit_border_id])
    entry_border = db.relationship('Border', foreign_keys=[entry_border_id])
    members = db.relationship('Pilgrim', foreign_keys='Pilgrim.group_id', backref='group')
    head = db.relationship('Pilgrim', foreign_keys=[head_member_id])


class Pilgrim(db.Model):
    __tablename__ = 'pilgrims'
    id = db.Column(db.Integer, primary_key=True)
    national_id = db.Column(db.String(10), nullable=False, index=True)
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    father_name = db.Column(db.String(64))
    id_number = db.Column(db.String(20))  # شناسنامه
    birth_date = db.Column(db.String(10))  # Shamsi YYYY/MM/DD
    gender = db.Column(db.String(8))  # male, female
    phone = db.Column(db.String(11))
    emergency_phone = db.Column(db.String(11))
    passport_number = db.Column(db.String(20))
    passport_letter = db.Column(db.String(2))
    passport_expiry = db.Column(db.String(10))  # Miladi YYYY/MM/DD
    has_disease = db.Column(db.Boolean, default=False)
    diseases = db.Column(db.Text)  # JSON list
    insurance_selected = db.Column(db.Boolean, default=True)
    insurance_amount = db.Column(db.Integer, default=0)
    iban = db.Column(db.String(26))  # for refund
    iban_verified = db.Column(db.Boolean, default=False)
    group_id = db.Column(db.Integer, db.ForeignKey('pilgrim_groups.id'))
    is_group_head = db.Column(db.Boolean, default=False)
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, refunded, cancelled
    refund_amount = db.Column(db.Integer, default=0)
    refund_date = db.Column(db.DateTime)
    cancellation_date = db.Column(db.DateTime)
    qr_code_path = db.Column(db.String(256))
    registration_number = db.Column(db.String(20), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class TrafficHistory(db.Model):
    __tablename__ = 'traffic_history'
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    day_number = db.Column(db.Integer, nullable=False)  # day of Arbaeen period
    shamsi_date = db.Column(db.String(10))
    border_id = db.Column(db.Integer, db.ForeignKey('borders.id'), nullable=True)
    count = db.Column(db.Integer, default=0)
    is_current_year = db.Column(db.Boolean, default=False)

    border = db.relationship('Border')


class AnnualRegistration(db.Model):
    """Tracks daily registration counts for the current year chart"""
    __tablename__ = 'annual_registrations'
    id = db.Column(db.Integer, primary_key=True)
    shamsi_date = db.Column(db.String(10), unique=True)
    count = db.Column(db.Integer, default=0)
