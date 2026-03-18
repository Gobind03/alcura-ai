# Alcura

Custom Frappe Application built on Frappe Framework v15.

## Installation

### Prerequisites

- Python 3.10+
- Node.js 18+
- A working [Frappe Bench](https://frappeframework.com/docs/v15/user/en/installation) setup

### Install on Bench

```bash
# From your frappe-bench directory
bench get-app https://github.com/alcura/alcura.git
bench --site your-site.localhost install-app alcura
```

### Development Setup

```bash
# Install the app in development mode
bench get-app /path/to/alcura
bench --site your-site.localhost install-app alcura

# Build frontend assets
bench build --app alcura

# Watch for changes during development
bench watch --apps alcura
```

## Project Structure

```
alcura/
├── alcura/
│   ├── api/           # Whitelisted REST API endpoints
│   ├── config/        # Desk and documentation config
│   ├── alcura/        # Default module (DocTypes live here)
│   ├── overrides/     # DocType override classes
│   ├── services/      # Business logic layer
│   ├── utils/         # Shared utility functions
│   ├── public/        # Static assets (JS/CSS bundles)
│   ├── templates/     # Jinja templates
│   ├── www/           # Portal pages
│   ├── tests/         # Test suite
│   ├── patches/       # Data migration patches
│   ├── hooks.py       # Frappe hook registrations
│   ├── modules.txt    # Module definitions
│   └── patches.txt    # Patch execution order
├── frontend/          # Optional SPA frontend
├── pyproject.toml     # Build config, deps, linting
└── package.json       # Node dependencies
```

## Backend Development

### Adding a New Module

1. Create a directory under `alcura/` for the module
2. Add the module name to `alcura/modules.txt`
3. Create DocTypes inside the module directory using `bench new-doctype`

### Adding API Endpoints

Place whitelisted methods under `alcura/api/`:

```python
import frappe

@frappe.whitelist()
def my_endpoint():
    return {"status": "ok"}
```

Callable at: `/api/method/alcura.api.v1.my_endpoint`

### Database Patches

Add migration functions to `alcura/patches/` and register them in `alcura/patches.txt`:

```
alcura.patches.my_patch
```

## Frontend Development

### Desk Bundles

Edit `alcura/public/js/alcura.bundle.js` and `alcura/public/css/alcura.bundle.css` to customize the Desk UI. These are automatically picked up by `bench build`.

### Optional SPA Frontend

To scaffold a standalone Vue 3 + Frappe UI frontend:

```bash
cd alcura
npx degit frappe/frappe-ui-starter frontend
cd frontend
yarn install
yarn dev
```

For a React-based frontend:

```bash
cd alcura
npx degit rtCamp/frappe-ui-react-starter frontend
cd frontend
npm install
npm run dev
```

## Testing

```bash
# Run all tests for this app
bench run-tests --app alcura

# Run a specific test module
bench run-tests --app alcura --module alcura.tests.test_sample_api

# Run tests for a specific DocType
bench run-tests --app alcura --doctype "Your DocType"
```

## Code Quality

### Linting

```bash
# Python (ruff)
ruff check alcura/
ruff format --check alcura/

# JavaScript (eslint)
yarn lint
```

### Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

## License

MIT
