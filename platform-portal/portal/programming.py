from flask import Blueprint

from .programming_routes import register_routes

programming_bp = Blueprint("programming", __name__)
register_routes(programming_bp)

__all__ = ["programming_bp"]
