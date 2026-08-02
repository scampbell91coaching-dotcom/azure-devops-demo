from flask import Blueprint

from .athletes import register_athlete_routes
from .blocks import register_block_routes
from .prescriptions import register_prescription_routes
from .sessions import register_session_routes
from .weeks import register_week_routes


def register_routes(blueprint: Blueprint) -> None:
    register_athlete_routes(blueprint)
    register_block_routes(blueprint)
    register_week_routes(blueprint)
    register_session_routes(blueprint)
    register_prescription_routes(blueprint)
