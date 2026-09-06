from flask import Blueprint

from .athletes import register_athlete_routes
from .blocks import register_block_routes
from .prescriptions import register_prescription_routes
from .lift_slots import register_lift_slot_routes
from .sessions import register_session_routes
from .warmups import register_warmup_routes
from .weeks import register_week_routes
from .bulk import register_bulk_routes


def register_routes(blueprint: Blueprint) -> None:
    register_athlete_routes(blueprint)
    register_block_routes(blueprint)
    register_week_routes(blueprint)
    register_session_routes(blueprint)
    register_prescription_routes(blueprint)
    register_lift_slot_routes(blueprint)
    register_warmup_routes(blueprint)
    register_bulk_routes(blueprint)
