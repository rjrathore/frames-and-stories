import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse, urljoin

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, redirect, render_template, request,
    url_for, current_app
)
from flask_login import (
    LoginManager, UserMixin, current_user, login_required,
    login_user, logout_user
)
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, TextAreaField, SelectField, FileField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional
from wtforms import ValidationError

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-this")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/frames_stories?charset=utf8mb4"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Enable SSL for cloud MySQL when a CA certificate is provided
ca_cert = os.getenv("DB_CA_CERT")

if ca_cert:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {
            "ssl": {
                "ca": ca_cert
            }
        }
    }

app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit

app.config.update(
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
    MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "true").lower() == "true",
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER") or os.getenv("MAIL_USERNAME"),
)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."
mail = Mail(app)
csrf = CSRFProtect(app)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

CATEGORIES = [
    ("Street", "Street"), ("Nature", "Nature"),
    ("Portrait", "Portrait"), ("Architecture", "Architecture"),
    ("Travel", "Travel"), ("Everyday Moments", "Everyday Moments"),
    ("Other", "Other")
]


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Photograph(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    story = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(1000), nullable=False)
    cloudinary_public_id = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(60), nullable=False, default="Other")
    location = db.Column(db.String(160))
    photo_date = db.Column(db.Date)
    is_published = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    likes = db.relationship("Like", backref="photograph", cascade="all, delete-orphan")
    comments = db.relationship(
        "Comment", backref="photograph", cascade="all, delete-orphan",
        order_by="Comment.created_at.desc()"
    )

    @property
    def like_count(self):
        return len(self.likes)

    @property
    def comment_count(self):
        return len(self.comments)


class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    photograph_id = db.Column(db.Integer, db.ForeignKey("photograph.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "photograph_id", name="unique_user_photo_like"),)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    photograph_id = db.Column(db.Integer, db.ForeignKey("photograph.id"), nullable=False)
    body = db.Column(db.String(1200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    author = db.relationship("User", backref="comments")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class RegisterForm(FlaskForm):
    name = StringField("Your name", validators=[DataRequired(), Length(min=2, max=80)])
    email = StringField("Email address", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm password", validators=[DataRequired(), EqualTo("password")]
    )


class LoginForm(FlaskForm):
    email = StringField("Email address", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])


class PhotoForm(FlaskForm):
    title = StringField("Photograph title", validators=[DataRequired(), Length(max=160)])
    story = TextAreaField("The story behind this photograph", validators=[DataRequired(), Length(max=10000)])
    category = SelectField("Category", choices=CATEGORIES, validators=[DataRequired()])
    location = StringField("Location (optional)", validators=[Optional(), Length(max=160)])
    photo_date = StringField("Date captured (optional)", validators=[Optional()])
    image = FileField("Photograph", validators=[DataRequired()])


class EditPhotoForm(FlaskForm):
    title = StringField("Photograph title", validators=[DataRequired(), Length(max=160)])
    story = TextAreaField("The story behind this photograph", validators=[DataRequired(), Length(max=10000)])
    category = SelectField("Category", choices=CATEGORIES, validators=[DataRequired()])
    location = StringField("Location (optional)", validators=[Optional(), Length(max=160)])
    photo_date = StringField("Date captured (optional)", validators=[Optional()])


def serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def make_token(email, purpose):
    return serializer().dumps({"email": email, "purpose": purpose})


def read_token(token, purpose, max_age=3600):
    try:
        data = serializer().loads(token, max_age=max_age)
        if data.get("purpose") != purpose:
            return None
        return data.get("email")
    except (BadSignature, SignatureExpired):
        return None


def send_email(to, subject, html):
    if not app.config.get("MAIL_USERNAME") or not app.config.get("MAIL_PASSWORD"):
        raise RuntimeError("Email is not configured. Set MAIL_USERNAME and MAIL_PASSWORD in .env.")
    msg = Message(subject=subject, recipients=[to], html=html)
    mail.send(msg)


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def safe_next_url(target):
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


@app.context_processor
def inject_globals():
    return {"current_year": datetime.now().year}


@app.route("/")
def index():
    photos = Photograph.query.filter_by(is_published=True).order_by(Photograph.created_at.desc()).limit(9).all()
    return render_template("index.html", photos=photos)


@app.route("/gallery")
def gallery():
    category = request.args.get("category", "").strip()
    query = Photograph.query.filter_by(is_published=True)
    if category in dict(CATEGORIES):
        query = query.filter_by(category=category)
    photos = query.order_by(Photograph.created_at.desc()).all()
    return render_template("gallery.html", photos=photos, categories=CATEGORIES, selected_category=category)


@app.route("/photo/<int:photo_id>")
def photo_detail(photo_id):
    photo = Photograph.query.filter_by(id=photo_id, is_published=True).first_or_404()
    liked = False
    if current_user.is_authenticated:
        liked = Like.query.filter_by(user_id=current_user.id, photograph_id=photo.id).first() is not None
    return render_template("photo_detail.html", photo=photo, liked=liked)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists. Please sign in.", "warning")
            return redirect(url_for("login"))
        user = User(name=form.name.data.strip(), email=email, is_verified=False)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        token = make_token(user.email, "verify")
        verify_url = url_for("verify_email", token=token, _external=True)
        try:
            send_email(
                user.email, "Verify your Frames & Stories account",
                f'<p>Hello {user.name},</p><p>Please verify your email to activate your account.</p>'
                f'<p><a href="{verify_url}">Verify my email</a></p><p>This link expires in 1 hour.</p>'
            )
        except Exception:
            app.logger.exception("Verification email could not be sent")
            flash("Your account was created, but the verification email could not be sent. Check the email settings and try resend verification.", "danger")
            return redirect(url_for("resend_verification"))
        flash("Account created! Check your inbox for the verification link.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form=form)


@app.route("/verify/<token>")
def verify_email(token):
    email = read_token(token, "verify")
    if not email:
        flash("That verification link is invalid or expired. Request a new one.", "warning")
        return redirect(url_for("resend_verification"))
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Account not found.", "danger")
        return redirect(url_for("register"))
    user.is_verified = True
    db.session.commit()
    flash("Email verified! You can now sign in.", "success")
    return redirect(url_for("login"))


@app.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    form = LoginForm()
    if request.method == "POST" and form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        # Generic response avoids revealing whether an email has an account.
        if user and not user.is_verified:
            token = make_token(user.email, "verify")
            verify_url = url_for("verify_email", token=token, _external=True)
            try:
                send_email(user.email, "Verify your Frames & Stories account",
                           f'<p><a href="{verify_url}">Verify my email</a></p><p>This link expires in 1 hour.</p>')
            except Exception:
                app.logger.exception("Could not resend verification email")
        flash("If an unverified account exists for that email, a new link has been sent.", "info")
        return redirect(url_for("login"))
    return render_template("resend_verification.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard" if current_user.is_admin else "index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.check_password(form.password.data):
            if not user.is_verified and not user.is_admin:
                flash("Please verify your email before signing in.", "warning")
                return redirect(url_for("resend_verification"))
            login_user(user)
            flash("Welcome back!", "success")
            target = request.args.get("next")
            if safe_next_url(target):
                return redirect(target)
            return redirect(url_for("admin_dashboard" if user.is_admin else "index"))
        flash("Email or password is incorrect.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have signed out.", "info")
    return redirect(url_for("index"))


@app.route("/photo/<int:photo_id>/like", methods=["POST"])
@login_required
def toggle_like(photo_id):
    if not current_user.is_verified and not current_user.is_admin:
        abort(403)
    photo = Photograph.query.filter_by(id=photo_id, is_published=True).first_or_404()
    existing = Like.query.filter_by(user_id=current_user.id, photograph_id=photo.id).first()
    if existing:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(Like(user_id=current_user.id, photograph_id=photo.id))
        liked = True
    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return {"liked": liked, "count": photo.like_count}
    return redirect(url_for("photo_detail", photo_id=photo.id))


@app.route("/photo/<int:photo_id>/comment", methods=["POST"])
@login_required
def add_comment(photo_id):
    photo = Photograph.query.filter_by(id=photo_id, is_published=True).first_or_404()
    body = request.form.get("body", "").strip()
    if not body or len(body) > 1200:
        flash("Please write a comment between 1 and 1200 characters.", "warning")
    else:
        db.session.add(Comment(user_id=current_user.id, photograph_id=photo.id, body=body))
        db.session.commit()
        flash("Your comment has been published.", "success")
    return redirect(url_for("photo_detail", photo_id=photo.id) + "#comments")


@app.route("/admin")
@admin_required
def admin_dashboard():
    photos = Photograph.query.order_by(Photograph.created_at.desc()).all()
    comments = Comment.query.order_by(Comment.created_at.desc()).limit(10).all()
    return render_template("admin/dashboard.html", photos=photos, comments=comments)


@app.route("/admin/photo/new", methods=["GET", "POST"])
@admin_required
def new_photo():
    form = PhotoForm()
    if form.validate_on_submit():
        image = form.image.data
        if not image or not image.filename:
            flash("Choose an image to upload.", "warning")
            return render_template("admin/photo_form.html", form=form, heading="Add a photograph")
        if not os.getenv("CLOUDINARY_CLOUD_NAME") or not os.getenv("CLOUDINARY_API_KEY") or not os.getenv("CLOUDINARY_API_SECRET"):
            flash("Cloudinary is not configured. Add its credentials to your .env file.", "danger")
            return render_template("admin/photo_form.html", form=form, heading="Add a photograph")
        try:
            result = cloudinary.uploader.upload(
                image, folder="frames-and-stories",
                resource_type="image",
                transformation=[{"quality": "auto", "fetch_format": "auto"}]
            )
            date_value = datetime.strptime(form.photo_date.data, "%Y-%m-%d").date() if form.photo_date.data else None
            photo = Photograph(
                title=form.title.data.strip(), story=form.story.data.strip(),
                image_url=result["secure_url"], cloudinary_public_id=result["public_id"],
                category=form.category.data, location=(form.location.data or "").strip(),
                photo_date=date_value
            )
            db.session.add(photo)
            db.session.commit()
            flash("Photograph published successfully!", "success")
            return redirect(url_for("admin_dashboard"))
        except Exception:
            db.session.rollback()
            app.logger.exception("Photo upload failed")
            flash("Upload failed. Check Cloudinary settings and the image file.", "danger")
    return render_template("admin/photo_form.html", form=form, heading="Add a photograph")


@app.route("/admin/photo/<int:photo_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_photo(photo_id):
    photo = db.session.get(Photograph, photo_id) or abort(404)
    form = EditPhotoForm(obj=photo)
    if request.method == "GET":
        form.photo_date.data = photo.photo_date.isoformat() if photo.photo_date else ""
    if form.validate_on_submit():
        photo.title = form.title.data.strip()
        photo.story = form.story.data.strip()
        photo.category = form.category.data
        photo.location = (form.location.data or "").strip()
        photo.photo_date = datetime.strptime(form.photo_date.data, "%Y-%m-%d").date() if form.photo_date.data else None
        db.session.commit()
        flash("Photograph updated.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin/photo_form.html", form=form, heading="Edit photograph", photo=photo)


@app.route("/admin/photo/<int:photo_id>/delete", methods=["POST"])
@admin_required
def delete_photo(photo_id):
    photo = db.session.get(Photograph, photo_id) or abort(404)
    try:
        if photo.cloudinary_public_id:
            cloudinary.uploader.destroy(photo.cloudinary_public_id, resource_type="image")
    except Exception:
        app.logger.exception("Cloudinary delete failed; deleting database record anyway")
    db.session.delete(photo)
    db.session.commit()
    flash("Photograph deleted.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/comment/<int:comment_id>/delete", methods=["POST"])
@admin_required
def admin_delete_comment(comment_id):
    comment = db.session.get(Comment, comment_id) or abort(404)
    photo_id = comment.photograph_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comment removed.", "info")
    return redirect(url_for("photo_detail", photo_id=photo_id))


@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_own_comment(comment_id):
    comment = db.session.get(Comment, comment_id) or abort(404)
    if comment.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    photo_id = comment.photograph_id
    db.session.delete(comment)
    db.session.commit()
    flash("Comment deleted.", "info")
    return redirect(url_for("photo_detail", photo_id=photo_id) + "#comments")


@app.cli.command("init-db")
def init_db():
    """Create database tables."""
    with app.app_context():
        db.create_all()
    print("Database tables created.")


@app.cli.command("create-admin")
def create_admin():
    """Create the one admin account interactively."""
    import getpass
    with app.app_context():
        name = input("Admin display name: ").strip()
        email = input("Admin email: ").strip().lower()
        password = getpass.getpass("Admin password (minimum 12 characters): ")
        if len(password) < 12:
            print("Password must be at least 12 characters.")
            return
        if User.query.filter_by(email=email).first():
            print("An account with that email already exists.")
            return
        user = User(name=name, email=email, is_verified=True, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print("Admin account created. Sign in at /login.")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You don't have permission to access this page."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="That page could not be found."), 404


@app.errorhandler(413)
def too_large(_error):
    return render_template("error.html", code=413, message="The uploaded file is too large. Maximum size is 8 MB."), 413


if __name__ == "__main__":
    app.run(debug=True)
