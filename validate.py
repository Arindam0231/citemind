import dash
from app import app

try:
    # Test if dash app layout compiles and validates
    app._validate_layout()
    print("Layout validates successfully.")
except Exception as e:
    print(f"Layout validation error: {e}")

try:
    app._validate_callbacks()
    print("Callbacks validate successfully.")
except Exception as e:
    print(f"Callback validation error: {e}")
