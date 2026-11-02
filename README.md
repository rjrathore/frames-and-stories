# Frames & Stories

A Flask + MySQL photography storytelling website. Only the admin can upload photographs. Visitors can register with email/password, verify their email, like photographs and publish comments.

## Features

- Dark cinematic responsive design
- Public home page and category-filtered gallery
- Photo detail pages with long-form stories
- Admin-only photograph upload, edit and delete
- Cloudinary image storage
- Visitor registration and email verification
- Login/logout with Flask-Login
- Likes with one-like-per-user-per-photo database constraint
- Comments appear immediately after submission
- Users can delete their own comments; admin can moderate any comment
- CSRF protection on forms

## Requirements

- Python 3.10+
- MySQL 8+
- Cloudinary account
- SMTP email account (Gmail App Password is one option)

## 1. Create the MySQL database

Open MySQL Workbench or MySQL command line and run:

```sql
CREATE DATABASE frames_stories
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

## 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Or use Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

## 3. Install packages

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure environment variables

Copy `.env.example` to `.env`, then fill in:

- `SECRET_KEY`: a long random secret
- `DATABASE_URL`: your MySQL username and password
- `MAIL_USERNAME` and `MAIL_PASSWORD`: SMTP account and app password
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- `SITE_URL`: local address for development; use your HTTPS production domain after deployment

For Gmail, use a Google App Password (not your normal Gmail password). Your Google account generally needs 2-Step Verification enabled to create an App Password.

Example database URL:

```text
mysql+pymysql://root:MyPassword@localhost:3306/frames_stories?charset=utf8mb4
```

If your MySQL password contains URL-special characters such as `@`, `#`, `/` or `:`, URL-encode them in the connection string.

## 5. Create database tables

```powershell
flask --app app init-db
```

## 6. Create your admin account

```powershell
flask --app app create-admin
```

Enter your admin display name, email and a strong password (at least 12 characters). This command creates an already-verified admin account. Do not register your admin account through the public registration page.

## 7. Run the website

```powershell
flask --app app run --debug
```

Open:

- Public website: http://127.0.0.1:5000
- Admin login: http://127.0.0.1:5000/login
- Admin dashboard: http://127.0.0.1:5000/admin

Sign in with the admin account and upload your first photograph.

## 8. Email verification

A newly registered visitor receives a verification link by email. The link expires after one hour. They must verify before signing in and using likes/comments.

For Gmail SMTP, create an App Password from your Google Account security settings. Never put your normal Gmail password in the project.

## 9. Cloudinary

Create a Cloudinary account and copy the cloud name, API key and API secret from the dashboard into `.env`. Uploaded photos are placed in the `frames-and-stories` folder in Cloudinary.

## Important security and production notes

This is a development starter, not yet a hardened production deployment.

Before publishing:
- Set a strong, unique `SECRET_KEY`.
- Set `DEBUG=False` and use HTTPS.
- Set `SITE_URL` to your real HTTPS domain.
- Use a managed MySQL database and keep backups.
- Keep `.env` out of GitHub; never commit API keys or passwords.
- Add rate limiting to registration, login, email resend, comments and likes.
- Consider CAPTCHA and email-provider delivery limits.
- Configure secure session cookies and trusted proxy settings for your hosting platform.
- Add image content validation (not only filename/MIME checks), moderation/reporting and spam protection.
- For larger galleries, add pagination and database-level count queries.
- Use migrations (Flask-Migrate/Alembic) before changing database models in production.

## Current project limitation

The initial version uses a single-file Flask application to make the first build easier to understand. Once it runs successfully, it can be refactored into Flask blueprints (`auth`, `photos`, `admin`) and separate model/form modules.
