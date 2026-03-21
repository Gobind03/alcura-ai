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
bench --site your-site.localhost install-app alcura_ai
```

The app’s Python package is `alcura_ai` (`app_name` in `hooks.py`). The directory under `apps/` may still be named `alcura` from the clone URL; use `install-app alcura_ai` regardless.

### Development Setup

```bash
# Install the app in development mode
bench get-app /path/to/alcura
bench --site your-site.localhost install-app alcura_ai

# Build frontend assets
bench build --app alcura_ai

# Watch for changes during development
bench watch --apps alcura_ai
```

## Project Structure

```
alcura/                    # repository root (name from git clone)
├── alcura_ai/             # Frappe app package (matches app_name)
│   ├── api/               # Whitelisted REST API endpoints
│   ├── config/            # Desk and documentation config
│   ├── alcura/            # Default module (DocTypes live here)
│   ├── overrides/         # DocType override classes
│   ├── services/          # Business logic layer
│   ├── utils/             # Shared utility functions
│   ├── public/            # Static assets (JS/CSS bundles)
│   ├── templates/         # Jinja templates
│   ├── www/               # Portal pages
│   ├── tests/             # Test suite
│   ├── patches/           # Data migration patches
│   ├── hooks.py           # Frappe hook registrations
│   ├── modules.txt        # Module definitions
│   └── patches.txt        # Patch execution order
├── frontend/              # Optional SPA frontend
├── pyproject.toml         # Build config, deps, linting
└── package.json           # Node dependencies
```

## Backend Development

### Adding a New Module

1. Create a directory under `alcura_ai/` for the module
2. Add the module name to `alcura_ai/modules.txt`
3. Create DocTypes inside the module directory using `bench new-doctype`

### Adding API Endpoints

Place whitelisted methods under `alcura_ai/api/`:

```python
import frappe

@frappe.whitelist()
def my_endpoint():
    return {"status": "ok"}
```

Callable at: `/api/method/alcura_ai.api.v1.my_endpoint`

### Database Patches

Add migration functions to `alcura_ai/patches/` and register them in `alcura_ai/patches.txt`:

```
alcura_ai.patches.my_patch
```

## Frontend Development

### Desk Bundles

Edit `alcura_ai/public/js/alcura_ai.bundle.js` and `alcura_ai/public/css/alcura_ai.bundle.css` to customize the Desk UI. These are automatically picked up by `bench build`.

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
bench run-tests --app alcura_ai

# Run a specific test module
bench run-tests --app alcura_ai --module alcura_ai.tests.test_sample_api

# Run tests for a specific DocType
bench run-tests --app alcura_ai --doctype "Your DocType"
```

## Code Quality

### Linting

```bash
# Python (ruff)
ruff check alcura_ai/
ruff format --check alcura_ai/

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
