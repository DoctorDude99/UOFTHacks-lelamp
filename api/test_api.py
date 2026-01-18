#!/usr/bin/env python3
"""
Test script for the new modular API structure.

Run with: uv run python api/test_api.py
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all imports work correctly."""
    print("Testing imports...")

    try:
        from api import create_api
        print("  ✓ api.create_api")
    except ImportError as e:
        print(f"  ✗ api.create_api: {e}")
        return False

    try:
        from api.deps import load_config, save_config, get_config_path
        print("  ✓ api.deps")
    except ImportError as e:
        print(f"  ✗ api.deps: {e}")
        return False

    try:
        from api.v1 import router
        print("  ✓ api.v1.router")
    except ImportError as e:
        print(f"  ✗ api.v1.router: {e}")
        return False

    try:
        from api.v1.setup import router as setup_router
        print("  ✓ api.v1.setup")
    except ImportError as e:
        print(f"  ✗ api.v1.setup: {e}")
        return False

    try:
        from api.v1.dashboard import router as dashboard_router
        print("  ✓ api.v1.dashboard")
    except ImportError as e:
        print(f"  ✗ api.v1.dashboard: {e}")
        return False

    try:
        from api.v1.agent import router as agent_router
        print("  ✓ api.v1.agent")
    except ImportError as e:
        print(f"  ✗ api.v1.agent: {e}")
        return False

    return True


def test_app_creation():
    """Test that the FastAPI app can be created."""
    print("\nTesting app creation...")

    try:
        from api import create_api
        app = create_api()
        print(f"  ✓ App created: {app.title}")

        # List all routes
        routes = [route.path for route in app.routes if hasattr(route, 'path')]
        print(f"  ✓ Routes registered: {len(routes)}")

        # Show API routes
        api_routes = [r for r in routes if r.startswith('/api')]
        print(f"\n  API endpoints ({len(api_routes)}):")
        for route in sorted(api_routes):
            print(f"    - {route}")

        return True
    except Exception as e:
        print(f"  ✗ App creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_access():
    """Test config loading/saving."""
    print("\nTesting config access...")

    try:
        from api.deps import load_config, get_config_path

        config_path = get_config_path()
        print(f"  ✓ Config path: {config_path}")

        config = load_config()
        print(f"  ✓ Config loaded: {len(config)} top-level keys")
        print(f"    Keys: {list(config.keys())}")

        return True
    except Exception as e:
        print(f"  ✗ Config access failed: {e}")
        return False


def main():
    print("=" * 50)
    print("LeLamp API Module Test")
    print("=" * 50)

    results = []
    results.append(("Imports", test_imports()))
    results.append(("App Creation", test_app_creation()))
    results.append(("Config Access", test_config_access()))

    print("\n" + "=" * 50)
    print("Results:")
    print("=" * 50)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed! The new API structure is ready.")
    else:
        print("Some tests failed. Please fix issues before integrating.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
