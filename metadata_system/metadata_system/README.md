# Metadata Management System

A simple base project for cataloguing assets (datasets, tables, files, reports, APIs)
and managing their metadata. Built with Flask + SQLite.

## Features
- Create, view, edit, delete assets
- Core metadata: name, description, type, owner, source, tags, timestamps
- Custom key-value fields per asset
- Search (name, owner, tags, custom fields) and filter by type / tag
- JSON REST API

## Run
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000

## API
    GET    /api/assets
    GET    /api/assets/<id>
    POST   /api/assets      {"name": "...", "asset_type": "Dataset", "tags": ["a","b"], "custom_fields": {"k": "v"}}
    DELETE /api/assets/<id>

## Structure
    app.py            routes, DB logic, API
    templates/        Jinja2 pages (base, index, detail, form)
    static/style.css  styling
    metadata.db       SQLite file (auto-created)
