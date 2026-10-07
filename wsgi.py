"""
WSGI entry point.

PythonAnywhere (and any other WSGI host) imports the Flask application from
here as ``application``. Gunicorn can also use it:

    gunicorn wsgi:application

On Render the shorter ``gunicorn app:app`` is used, which imports the ``app``
object straight from app.py. Both work.
"""

from app import app as application

# Some tools look for ``app`` as well.
app = application

if __name__ == "__main__":
    # Only for a quick local check: python wsgi.py
    application.run(debug=True, host="0.0.0.0", port=5000)
