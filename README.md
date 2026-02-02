# QR Equipment Management System

A Django-based web application for managing equipment maintenance and inspections using QR codes. Designed for companies with multiple technicians, it streamlines equipment tracking, service record keeping, and team collaboration.

![Django](https://img.shields.io/badge/Django-4.2.24-092E20?logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)

## ✨ Features

- **QR Code Generation & Scanning** – Each equipment item gets a unique QR code that technicians can scan to view details and log service records.
- **Multi‑Company & Multi‑User** – Companies can invite team members with role‑based permissions (Admin, Technician).
- **Subscription‑Based Access** – Integrated payment processing via YooKassa for monthly/annual plans.
- **Equipment Templates** – Define reusable checklists and fields for different equipment types.
- **Service History** – Full audit trail of all maintenance activities with photos and notes.
- **Dashboard & Analytics** – Separate dashboards for admins and technicians with activity overviews.
- **Security** – Two‑factor authentication (2FA), login rate limiting, and CSRF protection.
- **Responsive UI** – Clean, mobile‑friendly interface built with Bootstrap.

## 🏗️ Technology Stack

| Layer           | Technology                                                                 |
|-----------------|----------------------------------------------------------------------------|
| **Backend**     | Django 4.2, Django REST Framework (optional API)                           |
| **Database**    | PostgreSQL (production), SQLite (development)                              |
| **Payment**     | YooKassa API                                                               |
| **QR Codes**    | `qrcode` library                                                           |
| **Authentication** | Django‑OTP, django‑axes                                                |
| **Frontend**    | HTML5, CSS3, Bootstrap 5, JavaScript (vanilla)                             |
| **Deployment**  | Gunicorn, Whitenoise, dotenv, dj‑database‑url                              |

## 📦 Installation

### Prerequisites
- Python 3.9 or higher
- PostgreSQL (optional for development)
- Git

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/project_qr.git
cd project_qr
```

### 2. Create a virtual environment
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r reqs.txt
```

### 4. Configure environment variables
Create a `.env` file in the project root (copy from `.env.example` if available):
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgres://user:pass@localhost:5432/db_name  # or sqlite:///db.sqlite3
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
```

### 5. Set up the database
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Collect static files (optional for development)
```bash
python manage.py collectstatic
```

### 7. Run the development server
```bash
python manage.py runserver
```
Visit **http://127.0.0.1:8000** in your browser.

## 🚀 Usage

1. **Register a company** – The first user becomes an admin and creates a company.
2. **Invite team members** – Send email invitations to technicians.
3. **Add equipment** – Create equipment items, each gets a printable QR code.
4. **Define templates** – Create reusable checklists for equipment types.
5. **Scan & service** – Technicians scan QR codes, fill out checklists, attach photos.
6. **Manage subscriptions** – Admins can upgrade/downgrade plans via YooKassa.

### User Roles
- **Admin** – Full access: manage company, equipment, templates, team, billing.
- **Technician** – Can view assigned equipment, scan QR codes, create service records.

## 📁 Project Structure

```
project_qr/
├── manage.py
├── reqs.txt
├── project_qr/          # Main Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── ...
├── qr_app/              # Core application
│   ├── models.py        # Equipment, Company, User, Subscription, etc.
│   ├── views.py         # All business logic
│   ├── forms.py         # Django forms
│   ├── services.py      # Payment, QR generation, email
│   ├── management/commands/
│   └── templates/       # App‑specific templates
├── static/              CSS, images, icons
├── templates/           Base templates, landing page, dashboards
└── tests/               Unit tests
```

## 🔧 Configuration & Customization

### Payment Integration
The system uses YooKassa (Russian payment service). To enable:
1. Register at [YooKassa](https://yookassa.ru).
2. Obtain `YOOKASSA_SHOP_ID` and `YOOKASSA_SECRET_KEY`.
3. Add them to `.env`.
4. Configure webhook endpoint (if needed).

### Email Notifications
Currently uses Django’s console email backend. To switch to SMTP, update `settings.py`:
```python
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-password'
```

### Deployment
For production, ensure:
- `DEBUG = False`
- Secure `SECRET_KEY`
- Proper `ALLOWED_HOSTS`
- PostgreSQL database
- Static files served via Whitenoise/CDN
- Gunicorn as WSGI server

Example Gunicorn command:
```bash
gunicorn --workers 3 --bind 0.0.0.0:8000 project_qr.wsgi:application
```

## 🧪 Running Tests
```bash
python manage.py test tests/
```

## 🤝 Contributing
Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'Add amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
5. Open a Pull Request.

## 📬 Contact
For questions or support, please open an issue on GitHub or contact the maintainers.

---

*Developed by R057*