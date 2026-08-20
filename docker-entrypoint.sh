#!/bin/sh
exec gunicorn --config config/gunicorn.py app.main:app
