from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from portal import create_app
from portal.extensions import db

MIGRATION = (
    Path(__file__).parents[1]
    / "migrations/versions/0027_tenancy_ownership_expand.py"
)


def _app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


def test_0027_has_the_required_parent_and_0030_is_the_only_head():
    config = Config(str(Path(__file__).parents[1] / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["0030_programme_timing_lifecycle"]
    assert scripts.get_revision("0027_tenancy_ownership_expand").down_revision == (
        "0026_programming_exposure_roles"
    )


def test_expansion_source_has_no_data_migration_or_destructive_rename():
    source = MIGRATION.read_text()

    assert "op.execute" not in source
    assert "op.rename" not in source
    assert "alter_column" not in source
    assert "alembic_version" not in source
    assert "coach_athlete_assignments" not in source
    assert 'unique=True' not in source


def test_ownership_and_revocation_fields_are_nullable_in_model_metadata():
    with _app().app_context():
        checks = {
            "athletes": ("organisation_id",),
            "meets": ("organisation_id",),
            "meal_plan_templates": ("organisation_id",),
            "nutrition_import_jobs": ("organisation_id",),
            "support_access_events": ("organisation_id", "target_user_id"),
            "support_delegations": ("organisation_id", "target_user_id"),
            "users": ("session_generation",),
            "organisation_memberships": ("authorization_generation",),
            "support_principals": ("authorization_generation",),
        }
        for table_name, columns in checks.items():
            table = db.metadata.tables[table_name]
            for column_name in columns:
                assert column_name in table.c
                assert table.c[column_name].nullable is True
        assert db.metadata.tables["pdf_meal_plans"].c.organisation_id.nullable is False




def test_assignment_structure_is_deferred():
    assert "coach_athlete_assignments" not in db.metadata.tables
