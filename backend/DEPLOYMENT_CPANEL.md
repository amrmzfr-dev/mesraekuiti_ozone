# cPanel Deployment Guide

## Files Created for cPanel:
- `.htaccess` - Apache configuration (points to existing ozontelemetry/wsgi.py)
- Updated `requirements.txt` with exact versions
- Updated `settings.py` for production

## Deployment Steps:

### 1. Upload Files
Upload the entire `backend` folder to your cPanel public_html directory.

### 2. Install Requirements
In cPanel Python App:
- Go to Python App
- Select your app
- Go to "Requirements" tab
- Install from `requirements.txt`

### 3. Configure Environment Variables
Set these in cPanel Python App settings:
- `DEBUG=False`
- `SECRET_KEY=your-secret-key-here` (generate a new one)
- `ALLOWED_HOSTS=yourdomain.com,yourcpaneldomain.com`

### 4. Database Setup
- Create a PostgreSQL database in cPanel
- Update DATABASES setting in settings.py:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'your_db_name',
        'USER': 'your_db_user',
        'PASSWORD': 'your_db_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### 5. Run Migrations
In cPanel terminal or SSH:
```bash
cd backend
python manage.py migrate
python manage.py collectstatic
python manage.py seed_default_admin
```

### 6. Update ALLOWED_HOSTS
Replace `.yourdomain.com` in settings.py with your actual domain.

## Common Issues:

### Content Type Error
- Make sure `.htaccess` points to `ozontelemetry/wsgi.py`
- Check that your existing WSGI file is properly configured
- Verify Python version compatibility

### Static Files Not Loading
- Run `python manage.py collectstatic`
- Check STATIC_ROOT and STATIC_URL settings
- Verify file permissions

### Database Connection
- Ensure PostgreSQL is enabled in cPanel
- Check database credentials
- Verify database exists

## Testing:
1. Visit your domain
2. Should redirect to login page
3. Login with admin/admin
4. Check that real-time updates work
